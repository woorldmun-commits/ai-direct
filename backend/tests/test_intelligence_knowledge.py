"""Two concrete process/false-inference checks per starting industry; no market averages."""
import pytest

from app.intelligence.knowledge import discover_audiences, industries


@pytest.mark.parametrize('code,stages', [
    ('ecommerce', ['заказ', 'оплата', 'возврат']),
    ('services', ['запись', 'визит', 'оплата']),
    ('real_estate', ['показ', 'бронь', 'сделка']),
    ('automotive', ['обращение', 'заказ-наряд', 'оплата']),
    ('b2b', ['квалификация', 'КП', 'договор', 'оплата']),
])
def test_process_stages_are_distinct_and_sources_reviewed(code, stages):
    profile = next(p for p in industries() if p['code'] == code)
    assert all(stage in profile['purchase_stages'] for stage in stages)
    assert len(set(profile['purchase_stages'])) == len(profile['purchase_stages'])
    assert profile['review_status'] == 'source_reviewed'
    assert profile['version'] and profile['reviewed_at'] and profile['reviewer']
    assert len(profile['sources']) >= 2
    assert all(s['url'].startswith('https://') for s in profile['sources'])


@pytest.mark.parametrize('code,guard', [
    ('ecommerce', 'не доказывает оплату'),
    ('services', 'не основание отключения'),
    ('real_estate', 'не доказывает убыток'),
    ('automotive', 'разную экономику'),
    ('b2b', 'не доказывает убыток'),
])
def test_industry_guard_and_no_automatic_validation(code, guard):
    result = discover_audiences({'revision': 4, 'fields': {'industry_code': code,
                                 'products': ['Услуга'], 'geography': ['Казань'], 'conversion_definition': 'paid_sale'}})
    assert guard in result['limitations'][0]
    assert all(s['status'] == 'hypothesis' and s['profile_revision'] == 4 for s in result['segments'])
    assert all(s['test_plan'] and s['missing_inputs'] and s['success_metric'] == 'paid_sale' for s in result['segments'])
    assert all(s['source_refs'] and s['geography'] == ['Казань'] for s in result['segments'])


def test_unknown_industry_is_explicit_and_never_assigned_a_known_profile():
    source = {'revision': 1, 'fields': {'industry_code': 'unknown', 'products': [],
                                      'geography': [], 'conversion_definition': 'lead'}}
    result = discover_audiences(source)
    assert 'Отрасль не определена' in result['limitations'][0]
    assert result['segments'][0]['status'] == 'hypothesis'
    assert result['segments'][0]['source_refs'] == []
    assert source['fields']['industry_code'] == 'unknown'


@pytest.mark.parametrize('code,stage,need', [('cosmetology', 'визит', 'загрузка'),
                                          ('manufacturing', 'техническое соответствие', 'спецификация')])
def test_specific_processes_do_not_claim_validated_market_knowledge(code, stage, need):
    item = next(item for item in industries() if item['code'] == code)
    assert stage in item['purchase_stages']
    assert need in item['limitations'][0]
    assert item['review_status'] == 'process_hypothesis'
