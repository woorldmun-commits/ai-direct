from datetime import date,datetime,timedelta,timezone
from decimal import Decimal

import pytest

from app.intelligence.contracts import AnalysisContext,SourceReference
from app.intelligence.economics import calculate_metrics,compare_cpa


def setup_case(*,start=date(2026,10,1),source_id='source:1',**changes):
    fields=dict(workspace_id=1,account_ids=(1,),currency='RUB',period_start=start,period_end=start+timedelta(days=7),
                timezone='Europe/Moscow',as_of=datetime(2026,10,20,tzinfo=timezone.utc),attribution_model='last',
                attribution_window='30d',conversion_definition='lead@1',cost_definition='vat_included@1',quality_status='complete')
    fields.update(changes)
    context=AnalysisContext(**fields)
    source=SourceReference(id=source_id,provider='import',source_kind='synthetic',fetched_at=context.as_of,
                           raw_record_refs=(source_id+':row1',),
                           **{key:getattr(context,key) for key in ('workspace_id','account_ids','currency','period_start',
                              'period_end','attribution_model','attribution_window','conversion_definition','cost_definition','quality_status')})
    return context,source


def calculate(values,**changes):
    context,source=setup_case(**changes)
    return calculate_metrics(context,values,(source,))


def values(result):
    return {key:metric.value for key,metric in result.metrics.items()}


def test_section11_fixture_exact_and_every_output_has_evidence():
    result=calculate(dict(cost='12000',impressions=10000,clicks=600,conversions=60,leads=60,
                          sales=12,new_customers=10,net_revenue='60000',attributed_revenue='60000',
                          cogs='30000',other_variable_costs='0'))
    got=values(result)
    expected={'ctr':'6','cpc':'20','cvr':'10','cpl':'200','cpa_sale':'1000','paid_cac':'1200',
              'roas':'5','drr':'20','gross_profit':'30000','gross_margin':'50','contribution_after_ads':'18000'}
    for key,amount in expected.items():
        assert got[key]==Decimal(amount),key
    assert len(result.evidence)==len(result.metrics)
    assert {e.claim_id for e in result.evidence}==set(result.metrics)
    for evidence in result.evidence:
        assert evidence.output==result.metrics[evidence.claim_id]
        assert evidence.source_refs==('source:1',)
        assert evidence.input_ids==('source:1:row1',)
        assert evidence.verifier_result=='not_checked'
    derived=next(e for e in result.evidence if e.claim_id=='cpa_sale')
    assert derived.kind=='derived_fact' and derived.output.status=='actual'
    assert derived.formula=='cost / sales' and derived.metric_refs==('cost','sales')


def test_unknown_variable_costs_are_not_zero_and_negative_profit_is_preserved():
    result=calculate(dict(cost=12000,net_revenue=10000,cogs=30000))
    assert values(result)['gross_profit']==-20000
    assert result.metrics['contribution_after_ads'].value is None
    result=calculate(dict(cost=12000,net_revenue=10000,cogs=30000,other_variable_costs=0))
    assert values(result)['contribution_after_ads']==-32000


def test_missing_and_zero_conversions_preserve_spend_but_cpa_is_undefined():
    absent=calculate(dict(cost=100,clicks=10))
    zero=calculate(dict(cost=100,clicks=10,conversions=0))
    assert absent.metrics['conversions'].value is None and zero.metrics['conversions'].value==0
    assert absent.metrics['cpa'].value is None and zero.metrics['cpa'].value is None
    assert absent.metrics['cpa'].reason_code=='missing_input'
    assert zero.metrics['cpa'].reason_code=='nonpositive_denominator'
    assert absent.metrics['cost'].value==zero.metrics['cost'].value==100


def test_zero_denominators_do_not_make_zero_or_infinity_metrics():
    result=calculate(dict(cost=0,clicks=0,impressions=0,conversions=0,attributed_revenue=0,net_revenue=0,cogs=0))
    for key in ('cpc','ctr','cvr','cpa','roas','drr','gross_margin'):
        assert result.metrics[key].value is None,key
        assert result.metrics[key].reason_code=='nonpositive_denominator',key


def test_no_intermediate_rounding_and_fractional_attribution():
    result=calculate(dict(cost='1',clicks=3,conversions='1.25'))
    assert result.metrics['cpc'].value==Decimal(1)/3
    assert result.metrics['cpa'].value==Decimal('0.8')
    assert result.metrics['conversions'].value==Decimal('1.25')


@pytest.mark.parametrize('patch,reason',[
    ({'workspace_id':2},'workspace'),({'account_ids':(2,)},'accounts'),({'currency':'USD'},'currency'),
    ({'attribution_model':'first'},'attribution_model'),({'attribution_window':'7d'},'attribution_window'),
    ({'conversion_definition':'sale@1'},'conversion_definition'),({'cost_definition':'vat_excluded@1'},'cost_definition'),({'period_start':'2026-10-02'},'source_period'),
])
def test_source_mismatch_is_rejected_before_any_calculation(patch,reason):
    context,source=setup_case()
    with pytest.raises(ValueError,match=reason):
        calculate_metrics(context,{'cost':100},(SourceReference(**(source.model_dump()|patch)),))


@pytest.mark.parametrize('inputs,reason',[
    ({'cost':1.1},'decimal'),({'cost':True},'decimal'),({'cost':'NaN'},'decimal'),
    ({'cost':-1},'negative'),({'sales':'1.25'},'integer_count'),({'invented_metric':3},'unknown_metric'),
])
def test_untrusted_input_numbers_and_keys_are_rejected(inputs,reason):
    context,source=setup_case()
    with pytest.raises(ValueError,match=reason):
        calculate_metrics(context,inputs,(source,))


def test_no_sources_and_duplicate_sources_are_rejected():
    context,source=setup_case()
    with pytest.raises(ValueError,match='source_reference'):
        calculate_metrics(context,{'cost':100},())
    with pytest.raises(ValueError,match='duplicate_source'):
        calculate_metrics(context,{'cost':100},(source,source))
    missing=calculate_metrics(context,{},())
    assert all(m.value is None for m in missing.metrics.values())


def test_d06_exact_cpa_decomposition_and_no_causal_claims():
    before=calculate(dict(cost=10000,clicks=500,conversions=50),source_id='before')
    after=calculate(dict(cost=12000,clicks=400,conversions=20),start=date(2026,10,8),source_id='after')
    assert values(before)['cpc']==20 and values(before)['cvr']==10 and values(before)['cpa']==200
    assert values(after)['cpc']==30 and values(after)['cvr']==5 and values(after)['cpa']==600
    rca=compare_cpa(before,after)
    assert rca.status=='success' and rca.root_cause=='not_established'
    assert values(rca)['cpa_ratio']==3 and values(rca)['cpc_ratio']==Decimal('1.5')
    assert values(rca)['cvr_ratio']==Decimal('0.5')
    assert values(rca)['cpa_ratio']==values(rca)['cpc_ratio']/values(rca)['cvr_ratio']
    assert values(rca)['cpa_change_abs']==400 and values(rca)['cpa_change_pct']==200
    assert 'competition_unverified' in rca.hypotheses and 'landing_page_unverified' in rca.hypotheses
    assert all(e.kind=='derived_fact' and e.metric_refs for e in rca.evidence)


@pytest.mark.parametrize('second,ratio_cpc,ratio_cvr',[
    ({'cost':15000,'clicks':500,'conversions':50},'1.5','1'),
    ({'cost':10000,'clicks':500,'conversions':25},'1','0.5'),
])
def test_cpc_and_cvr_explanations_remain_hypotheses(second,ratio_cpc,ratio_cvr):
    before=calculate(dict(cost=10000,clicks=500,conversions=50),source_id='before')
    after=calculate(second,start=date(2026,10,8),source_id='after')
    rca=compare_cpa(before,after)
    assert values(rca)['cpc_ratio']==Decimal(ratio_cpc) and values(rca)['cvr_ratio']==Decimal(ratio_cvr)
    assert rca.root_cause=='not_established'


@pytest.mark.parametrize('patch,reason',[
    ({'workspace_id':2},'workspace'),({'currency':'USD'},'currency'),({'attribution_model':'first'},'attribution'),
    ({'conversion_definition':'sale@1'},'conversion'),({'attribution_window':'7d'},'attribution_window'),
    ({'cost_definition':'vat_excluded@1'},'cost_definition'),({'account_ids':(2,)},'account'),({'timezone':'UTC'},'timezone'),
])
def test_rca_incompatible_slices_do_not_generate_numbers(patch,reason):
    before=calculate(dict(cost=100,clicks=10,conversions=2),source_id='before')
    after=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,8),source_id='after',**patch)
    rca=compare_cpa(before,after)
    assert rca.status=='incompatible' and not rca.metrics and any(reason in c for c in rca.reason_codes)


def test_quality_or_missing_attribution_does_not_make_actionable_success():
    before=calculate(dict(cost=100,clicks=10,conversions=2),source_id='before')
    for patch in ({'quality_status':'stale'},{'quality_status':'partial'},{'quality_status':'unknown'}):
        after=calculate(dict(cost=120,clicks=10,conversions=2),start=date(2026,10,8),source_id='after',**patch)
        assert compare_cpa(before,after).status=='insufficient'
    one=calculate(dict(cost=100,clicks=10,conversions=2),source_id='before',attribution_window=None)
    two=calculate(dict(cost=120,clicks=10,conversions=2),start=date(2026,10,8),source_id='after',attribution_window=None)
    assert 'attribution_window_missing' in compare_cpa(one,two).reason_codes


def test_zero_baseline_preserves_absolute_change_but_not_relative_change():
    before=calculate(dict(cost=0,clicks=10,conversions=2),source_id='before')
    after=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,8),source_id='after')
    rca=compare_cpa(before,after)
    assert rca.status=='insufficient' and values(rca)['cpa_ratio'] is None
    assert values(rca)['cpa_change_pct'] is None and values(rca)['cpa_change_abs']==50


def test_overlapping_periods_and_reused_source_revision_are_rejected():
    before=calculate(dict(cost=100,clicks=10,conversions=2))
    overlapping=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,7),source_id='after')
    assert compare_cpa(before,overlapping).status=='incompatible'
    reused=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,8))
    assert compare_cpa(before,reused).reason_codes==('source_revision_conflict',)


def test_result_rejects_unresolved_sources_and_tampered_metrics():
    from pydantic import ValidationError
    from app.intelligence.contracts import AnalysisResult
    result=calculate(dict(cost=100,clicks=10,conversions=2))
    data=result.model_dump()
    data['sources']=()
    with pytest.raises(ValidationError,match='unresolved_source'):
        AnalysisResult.model_validate(data)
    result.metrics['cpa']=result.metrics['cpa'].model_copy(update={'value':Decimal('999')})
    after=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,8),source_id='after')
    with pytest.raises(ValidationError,match='metric_evidence_mismatch'):
        compare_cpa(result,after)


def test_partial_source_cannot_be_upgraded_by_complete_context():
    context,source=setup_case()
    source=SourceReference(**(source.model_dump()|{'quality_status':'partial'}))
    result=calculate_metrics(context,dict(cost=100,clicks=10,conversions=2),(source,))
    assert result.context.quality_status=='partial'
    assert all(m.quality_status=='partial' for m in result.metrics.values())
    assert 'data_partial' in result.warnings


def test_cost_definition_is_required_for_comparable_rca():
    before=calculate(dict(cost=100,clicks=10,conversions=2),source_id='before',cost_definition=None)
    after=calculate(dict(cost=100,clicks=10,conversions=2),start=date(2026,10,8),source_id='after',cost_definition=None)
    assert 'cost_definition_missing' in before.warnings
    assert 'cost_definition_missing' in compare_cpa(before,after).reason_codes


@pytest.mark.parametrize('patch', [{'currency':'USD'}, {'account_ids':(2,)},
                                  {'period_end':date(2026,10,7)}, {'cost_definition':'different_tax_basis'}])
def test_result_validation_rechecks_source_context(patch):
    from pydantic import ValidationError
    from app.intelligence.contracts import AnalysisResult
    result=calculate(dict(cost=100,clicks=10,conversions=2))
    data=result.model_dump()
    data['sources'][0].update(patch)
    with pytest.raises(ValidationError,match='incompatible_'):
        AnalysisResult.model_validate(data)
