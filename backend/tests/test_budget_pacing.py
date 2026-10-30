from datetime import date
from decimal import Decimal
import pytest
from app.insights.pacing import calculate


@pytest.mark.parametrize('spent,status,projection,remaining',[
    ('1000','on_track','3000.00','100.00'),
    ('1500','ahead','4500.00','75.00'),
    ('500','behind','1500.00','125.00'),
    ('0','behind','0.00','150.00'),
    ('3500','exceeded','10500.00','0.00'),
])
def test_linear_pacing_uses_covered_days_and_decimal(spent,status,projection,remaining):
    out=calculate(Decimal('3000'),Decimal(spent),date(2026,10,1),date(2026,10,30),date(2026,10,10))
    assert out['status']==status
    assert out['projected_total']==projection and out['remaining_daily']==remaining
    assert out['days_observed']==10 and out['days_total']==30 and out['expected_to_date']=='1000.00'


def test_completed_period_has_no_remaining_daily_division():
    out=calculate(Decimal('3000'),Decimal('3000'),date(2026,10,1),date(2026,10,30),date(2026,10,30))
    assert out['status']=='complete' and out['remaining_daily'] is None


def test_future_observation_is_rejected():
    with pytest.raises(ValueError):
        calculate(Decimal('3000'),Decimal('0'),date(2026,10,1),date(2026,10,30),date(2026,9,30))
