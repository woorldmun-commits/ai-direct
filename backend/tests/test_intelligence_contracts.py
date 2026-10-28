from datetime import date,datetime,timezone
import pytest
from pydantic import ValidationError
from app.contract import Value
from app.intelligence.contracts import AnalysisContext, MetricValue, SourceReference, legacy_to_metric


def context(**changes):
    return AnalysisContext(workspace_id=1,account_ids=(1,),currency='RUB',period_start=date(2026,10,1),
                           period_end=date(2026,10,8),timezone='Europe/Moscow',as_of=datetime(2026,10,9,tzinfo=timezone.utc),
                           attribution_model='last',attribution_window='30d',conversion_definition='lead@1',cost_definition='vat_included@1',
                           quality_status='complete',**changes)


def metric(**changes):
    c=context()
    fields={key:getattr(c,key) for key in ('period_start','period_end','timezone','as_of','completeness','sample_size',
            'attribution_model','attribution_window','conversion_definition','calculation_version','quality_status')}
    return MetricValue(**(fields|dict(metric_id='cost',value='12000',unit='money',currency='RUB',status='actual',
                                     source_refs=('import:1',))|changes))


@pytest.mark.parametrize('bad',[True,False,1.2,'NaN','Infinity','1e2',' 1','1 ',float('nan')])
def test_metric_rejects_lossy_or_non_decimal_input(bad):
    with pytest.raises(ValidationError):
        metric(value=bad)


@pytest.mark.parametrize('patch',[
    {'status':'unavailable'},{'value':None},{'reason_code':'no_data'},{'source_refs':()},
    {'unit':'pct'},{'currency':'rub'},{'completeness':'1.01'},{'completeness':True},
    {'sample_size':True},{'timezone':'Not/AZone'},{'as_of':datetime(2026,10,9)},
    {'period_end':'2026-10-01'},{'period_start':datetime(2026,10,1)},
    {'calculation_version':'latest'},
])
def test_metric_invariants(patch):
    with pytest.raises(ValidationError):
        metric(**patch)


def test_unavailable_and_confirmed_zero_are_distinct():
    absent=metric(value=None,status='unavailable',reason_code='missing_input')
    zero=metric(value='0')
    assert absent.value is None and zero.value==0
    assert absent.status=='unavailable' and zero.status=='actual'


def test_fractional_conversion_is_decimal_and_json_roundtrip_preserves_it():
    from decimal import Decimal
    m=metric(metric_id='conversions',value='1.25',unit='count',currency=None)
    assert m.value==Decimal('1.25')
    assert MetricValue.model_validate_json(m.model_dump_json())==m


def test_context_and_source_validation():
    fields=context().model_dump()
    for patch in ({'account_ids':(2,1)},{'account_ids':(1,1)},{'workspace_id':True},
                  {'period_end':fields['period_start']},{'currency':'rub'}):
        with pytest.raises(ValidationError):
            AnalysisContext(**(fields|patch))
    with pytest.raises(ValidationError):
        SourceReference(id='s',workspace_id=1,provider='import',source_kind='synthetic',
                        fetched_at=datetime(2026,10,9),currency='RUB',period_start='2026-10-01',period_end='2026-10-08')


def test_legacy_adapter_keeps_inclusive_period_and_estimate_without_mutation():
    old=Value(amount='10.125',unit='rub',source='yandex_direct',period_from='2026-10-01',period_to='2026-10-07',
              calculation_type='estimated',data_status='complete',data_sufficiency='sufficient',snapshot_id=4,
              formula='cost / conversions')
    before=old.model_dump_json()
    m=legacy_to_metric(old,metric_id='cpa',context=context(),source_refs=('snapshot:4',))
    assert m.period_end==date(2026,10,8) and m.status=='estimated' and m.value==old.amount
    assert m.completeness is None and old.model_dump_json()==before
    with pytest.raises(ValueError,match='legacy_period'):
        legacy_to_metric(old,metric_id='cpa',context=AnalysisContext(**(context().model_dump()|{'period_end':'2026-10-09'})),source_refs=('s',))
    with pytest.raises(ValueError,match='currency'):
        legacy_to_metric(old,metric_id='cpa',context=AnalysisContext(**(context().model_dump()|{'currency':'USD'})),source_refs=('s',))
