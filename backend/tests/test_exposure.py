"""exposure_total@1 (docs/ECONOMICS.md §3–4): итог без двойного счёта и его инварианты (§3.5) — без БД."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.audit.exposure import VERSION, ExposureFinding, StatUnit, basis_from_meta, basis_meta, exposure_total
from app.contract import Value
from app.rules.domain import FORMULA, SPEND_CAMPAIGN, ExposureBasis

D1 = date(2026, 9, 24)
D7 = D1 + timedelta(6)
AS_OF = D7


def day(n: int) -> date:
    return D1 + timedelta(n - 1)


def lost(amount, *, frm=D1, to=D7, status="complete", snapshot=1, formula="sum(cost) where conversions = 0",
         source="yandex_direct+yandex_metrika") -> Value:
    if amount is None:
        return Value(amount=None, unit="rub", source=source, period_from=frm, period_to=to,
                     calculation_type="unavailable", data_status=status, data_sufficiency="insufficient",
                     snapshot_id=snapshot)
    return Value(amount=Decimal(amount), unit="rub", source=source, period_from=frm, period_to=to,
                 calculation_type="estimated", data_status=status, data_sufficiency="sufficient",
                 snapshot_id=snapshot, rule_version="x@1", formula=formula)


_DEFAULT = object()


def card(issue_type, object_type, object_id, amount, *, account=1, basis=_DEFAULT, **kw) -> ExposureFinding:
    """Основа по умолчанию — как декларируют правила: formula, если задана формула; иначе spend своих единиц."""
    if basis is _DEFAULT:
        if "formula" in kw:
            basis = FORMULA
        elif object_type == "campaign":
            basis = SPEND_CAMPAIGN
        elif object_type == "account":
            basis = None
        else:
            basis = ExposureBasis("spend", object_type, (object_id,))
    return ExposureFinding(account, issue_type, object_type, object_id, lost(amount, **kw), basis)


def placements_card(campaign, amount, ids, **kw) -> ExposureFinding:
    """Как zero_conv_placements@1: вывод уровня кампании, сумма — расход перечисленных площадок за окно."""
    return card("zero_conv_placements", "campaign", campaign, amount, basis=ExposureBasis("spend", "placement", ids),
                **kw)


def unit(campaign, level, object_id, d, cost, *, account=1) -> StatUnit:
    return StatUnit(account, campaign, level, object_id, d, Decimal(cost))


def spend(campaign, per_day: dict[int, str], *, account=1) -> list[StatUnit]:
    return [unit(campaign, "campaign", campaign, day(n), c, account=account) for n, c in per_day.items()]


def amounts(fs) -> list[Decimal]:
    return [f.lost.amount for f in fs if f.lost.amount is not None]


def check_invariants(fs, units):
    out = exposure_total(fs, units, as_of=AS_OF)
    cards = amounts(fs)
    total, overlap = out.total.amount, out.overlap.amount
    assert max(cards) <= total <= sum(cards)
    assert overlap == sum(cards) - total and overlap >= 0
    assert sum(c.amount.amount for c in out.components) == sum(cards)
    return out


# --- Пример ECONOMICS.md §4 ------------------------------------------------------------------------

A, B, C, DD = 101, 102, 103, 104


def economics_example():
    findings = [
        card("zero_conv_campaign", "campaign", A, "21000.00"),
        card("zero_conv_queries", "query", 1, "2000.00"),
        card("zero_conv_queries", "query", 2, "2600.00"),
        card("zero_conv_placements", "placement", 7, "5000.00"),
        card("zero_conv_placements", "placement", 8, "3300.00"),
        card("high_cpa", "campaign", B, "34580.00", formula="(cpa - target_cpa) * conversions"),
        card("zero_conv_queries", "query", 3, "3200.00"),
        card("zero_conv_hours", "hour", 10, "1000.00"),
        card("zero_conv_regions", "region", 213, "1300.00"),
    ]
    units = [
        *spend(A, {n: "3000.00" for n in range(1, 8)}),                        # 21 000 за окно
        unit(A, "query", 1, day(1), "2000.00"), unit(A, "query", 2, day(3), "2600.00"),
        *spend(B, {**{n: "13000.00" for n in range(1, 7)}, 7: "13580.00"}),   # 91 580 = 4 820 × 19
        unit(B, "placement", 7, day(2), "5000.00"), unit(B, "placement", 8, day(5), "3300.00"),
        *spend(C, {4: "10000.00"}), unit(C, "query", 3, day(4), "3200.00"),
        *spend(DD, {1: "5000.00", 2: "5000.00"}),
        unit(DD, "hour", 10, day(1), "700.00"), unit(DD, "hour", 10, day(2), "300.00"),
        unit(DD, "region", 213, day(1), "400.00"), unit(DD, "region", 213, day(2), "900.00"),
    ]
    return findings, units


def test_economics_example_gives_its_numbers():
    findings, units = economics_example()
    out = check_invariants(findings, units)
    assert out.total.amount == Decimal("60380.00")
    assert out.overlap.amount == Decimal("13600.00")
    assert {c.issue_type: c.amount.amount for c in out.components} == {
        "zero_conv_campaign": Decimal("21000.00"), "zero_conv_queries": Decimal("7800.00"),
        "zero_conv_placements": Decimal("8300.00"), "high_cpa": Decimal("34580.00"),
        "zero_conv_hours": Decimal("1000.00"), "zero_conv_regions": Decimal("1300.00")}
    assert sum(c.amount.amount for c in out.components) == Decimal("73980.00")
    assert [c.issue_type for c in out.components][0] == "high_cpa"  # по убыванию суммы
    assert (out.coverage.included, out.coverage.unavailable) == (9, 0)


def test_result_values_are_estimated_with_formula_and_version():
    out = exposure_total(*economics_example(), as_of=AS_OF)
    for v in (out.total, out.overlap, *(c.amount for c in out.components)):
        assert v.calculation_type == "estimated" and v.formula and v.rule_version == VERSION
        assert v.unit == "rub" and v.amount == v.amount.quantize(Decimal("0.01"))
        assert (v.period_from, v.period_to) == (D1, D7)
    assert out.version == VERSION and out.formula == out.total.formula
    assert out.total.source == "yandex_direct+yandex_metrika"


def test_permutation_and_repetition_do_not_change_result():
    findings, units = economics_example()
    first = exposure_total(findings, units, as_of=AS_OF)
    rnd = random.Random(7)
    for _ in range(10):
        fs, us = findings[:], units[:]
        rnd.shuffle(fs), rnd.shuffle(us)
        assert exposure_total(fs, us, as_of=AS_OF) == first


# --- Пустой вход, unavailable, partial -------------------------------------------------------------

def test_empty_input_is_unavailable_not_zero():
    out = exposure_total([], [], as_of=AS_OF)
    for v in (out.total, out.overlap):
        assert v.amount is None and v.calculation_type == "unavailable" and v.data_sufficiency == "insufficient"
        assert (v.period_from, v.period_to) == (AS_OF, AS_OF)
    assert out.components == () and (out.coverage.included, out.coverage.unavailable) == (0, 0)


def test_only_unavailable_cards_are_unavailable_and_counted_in_coverage():
    out = exposure_total([card("high_cpa", "campaign", A, None), card("high_cpa", "campaign", B, None)], [],
                         as_of=AS_OF)
    assert out.total.amount is None and out.total.calculation_type == "unavailable"
    assert (out.coverage.included, out.coverage.unavailable) == (0, 2)


def test_unavailable_card_is_excluded_from_total():
    fs = [card("zero_conv_campaign", "campaign", A, "21000.00"), card("high_cpa", "campaign", B, None)]
    out = check_invariants(fs, spend(A, {n: "3000.00" for n in range(1, 8)}))
    assert out.total.amount == Decimal("21000.00")
    assert [c.issue_type for c in out.components] == ["zero_conv_campaign"]
    assert (out.coverage.included, out.coverage.unavailable) == (1, 1)


def test_partial_data_propagates_to_data_status():
    fs = [card("zero_conv_campaign", "campaign", A, "21000.00"),
          card("high_cpa", "campaign", B, "500.00", status="partial", formula="f")]
    out = exposure_total(fs, [], as_of=AS_OF)
    assert out.total.data_status == "partial" and out.overlap.data_status == "partial"
    by_type = {c.issue_type: c.amount.data_status for c in out.components}
    assert by_type == {"zero_conv_campaign": "complete", "high_cpa": "partial"}
    assert exposure_total(fs[:1], [], as_of=AS_OF).total.data_status == "complete"
    assert exposure_total([card("x", "campaign", A, None, status="partial")], [],
                          as_of=AS_OF).total.data_status == "partial"


def test_non_rub_exposure_is_rejected():
    bad = ExposureFinding(1, "x", "campaign", A, lost("5").model_copy(update={"unit": "count"}))
    with pytest.raises(ValueError):
        exposure_total([bad], [], as_of=AS_OF)


# --- Отдельные правила алгоритма -------------------------------------------------------------------

def test_same_unit_in_two_cards_is_counted_once():
    fs = [card("zero_conv_queries", "query", 1, "500.00"), card("zero_conv_queries_v2", "query", 1, "500.00")]
    out = check_invariants(fs, [unit(A, "query", 1, day(2), "500.00")])
    assert out.total.amount == Decimal("500.00") and out.overlap.amount == Decimal("500.00")


def test_queries_and_placements_add_up():
    fs = [card("zero_conv_queries", "query", 1, "500.00"), card("zero_conv_placements", "placement", 7, "300.00")]
    units = [unit(A, "query", 1, day(2), "500.00"), unit(A, "placement", 7, day(2), "300.00")]
    assert check_invariants(fs, units).total.amount == Decimal("800.00")


def test_campaign_card_covers_only_its_window_days():
    """Кампания без конверсий за дни 5–7; запрос — в дни 2 и 6: день 2 вне окна вывода кампании — добавляется."""
    fs = [card("zero_conv_campaign", "campaign", A, "3000.00", frm=day(5), to=day(7)),
          card("zero_conv_queries", "query", 1, "700.00")]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}),
             unit(A, "query", 1, day(2), "400.00"), unit(A, "query", 1, day(6), "300.00")]
    assert check_invariants(fs, units).total.amount == Decimal("3400.00")


def test_formula_campaign_card_smaller_than_objects_takes_max():
    """Шаг 3: max, а не всегда сумма вывода кампании — итог не меньше самой большой карточки."""
    fs = [card("high_cpa", "campaign", A, "100.00", formula="(cpa - target_cpa) * conversions"),
          card("zero_conv_placements", "placement", 7, "900.00")]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}), unit(A, "placement", 7, day(3), "900.00")]
    assert check_invariants(fs, units).total.amount == Decimal("900.00")


def test_several_campaign_cards_are_max():
    fs = [card("zero_conv_campaign", "campaign", A, "7000.00"),
          card("high_cpa", "campaign", A, "2500.00", formula="f")]
    assert check_invariants(fs, spend(A, {n: "1000.00" for n in range(1, 8)})).total.amount == Decimal("7000.00")


def test_accounts_never_merge():
    """Одна и та же кампания (id) в двух кабинетах — разные единицы."""
    fs = [card("zero_conv_campaign", "campaign", A, "7000.00", account=1),
          card("zero_conv_campaign", "campaign", A, "5000.00", account=2)]
    units = spend(A, {n: "1000.00" for n in range(1, 8)}, account=1)
    assert check_invariants(fs, units).total.amount == Decimal("12000.00")


def test_account_card_against_sum_of_campaigns_is_max():
    fs = [card("zero_conv_account", "account", 1, "9000.00"),
          card("zero_conv_campaign", "campaign", A, "7000.00"), card("zero_conv_campaign", "campaign", B, "4000.00")]
    assert check_invariants(fs, []).total.amount == Decimal("11000.00")
    fs[0] = card("zero_conv_account", "account", 1, "15000.00")
    assert check_invariants(fs, []).total.amount == Decimal("15000.00")


def test_contribution_capped_by_campaign_spend_but_not_below_largest_card():
    fs = [card("zero_conv_queries", "query", 1, "800.00"), card("zero_conv_placements", "placement", 7, "700.00")]
    units = [*spend(A, {2: "1000.00"}), unit(A, "query", 1, day(2), "800.00"),
             unit(A, "placement", 7, day(2), "700.00")]  # несогласованные данные: объекты больше расхода кампании
    assert check_invariants(fs, units).total.amount == Decimal("1000.00")


def test_formula_object_card_is_a_block_of_its_campaign():
    """Сумма объектного вывода не равна расходу его единиц → блок «кампания × окно» со своей суммой."""
    fs = [card("zero_conv_campaign", "campaign", A, "7000.00"),
          card("some_object_rule", "placement", 7, "250.00", formula="(cpa - target) * conv")]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}), unit(A, "placement", 7, day(1), "900.00")]
    assert check_invariants(fs, units).total.amount == Decimal("7000.00")
    # без строк — кампанию не определить: блок добавляется к кабинету целиком
    assert check_invariants(fs, spend(A, {n: "1000.00" for n in range(1, 8)})).total.amount == Decimal("7250.00")


@pytest.mark.parametrize("seed", range(40))
def test_invariants_on_random_cards(seed):
    rnd = random.Random(seed)
    findings, units = [], []
    for account in (1, 2):
        for campaign in range(1, rnd.randint(2, 4)):
            per_day = {n: Decimal(rnd.randint(500, 5000)) for n in range(1, 8)}
            units += spend(campaign, {n: str(c) for n, c in per_day.items()}, account=account)
            budget = dict(per_day)
            for level, ids in (("query", (1, 2)), ("placement", (7,)), ("hour", (10, 11)), ("region", (213,))):
                for oid in ids:
                    cards_days = rnd.sample(range(1, 8), rnd.randint(1, 3))
                    rows = [unit(campaign, level, oid, day(n), str(Decimal(rnd.randint(0, int(budget[n] / 4)))),
                                 account=account) for n in cards_days]
                    units += rows
                    if rnd.random() < 0.6:
                        findings.append(card(f"zc_{level}", level, oid, str(sum(u.cost for u in rows)),
                                             account=account))
            if rnd.random() < 0.5:
                findings.append(card("zero_conv_campaign", "campaign", campaign, str(sum(per_day.values())),
                                     account=account))
            if rnd.random() < 0.5:
                findings.append(card("high_cpa", "campaign", campaign, str(Decimal(rnd.randint(1, 3000))),
                                     account=account, formula="f"))
    if not amounts(findings):
        findings.append(card("high_cpa", "campaign", 1, "10.00", formula="f"))
    out = check_invariants(findings, units)
    shuffled = findings[::-1]
    assert exposure_total(shuffled, units[::-1], as_of=AS_OF) == out


# --- Декларированная основа суммы (ExposureBasis) ---------------------------------------------------

def test_economics_example_with_v1_placements_card():
    """Пример §4 в форме правил v1.0: площадки — один вывод уровня кампании B с перечнем площадок (spend по
    единицам placement), «без конверсий» — spend по кампании, высокий CPA — formula. Итог тот же: 60 380."""
    findings, units = economics_example()
    findings = [f for f in findings if f.issue_type != "zero_conv_placements"] + [
        placements_card(B, "8300.00", (7, 8))]
    out = check_invariants(findings, units)
    assert (out.total.amount, out.overlap.amount) == (Decimal("60380.00"), Decimal("13600.00"))


def test_placements_card_against_zero_conv_campaign_is_max_per_day():
    """Кампания без конверсий за дни 5–7 (блок) и площадки той же кампании в дни 2 и 6: день 6 — внутри блока
    (max), день 2 — вне его окна, добавляется. Не сумма карточек."""
    fs = [card("zero_conv_campaign", "campaign", A, "3000.00", frm=day(5), to=day(7)),
          placements_card(A, "700.00", (7, 8))]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}),
             unit(A, "placement", 7, day(2), "400.00"), unit(A, "placement", 8, day(6), "300.00")]
    assert check_invariants(fs, units).total.amount == Decimal("3400.00")


@pytest.mark.parametrize("high_cpa, total", [("100.00", "900.00"), ("5000.00", "5000.00")])
def test_placements_card_against_high_cpa_formula_block(high_cpa, total):
    """ECONOMICS §3.3 п. 3: в днях окна формульного вывода — max(блок, площадки этих дней)."""
    fs = [card("high_cpa", "campaign", A, high_cpa, formula="(cpa - target_cpa) * conversions"),
          placements_card(A, "900.00", (7,))]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}), unit(A, "placement", 7, day(3), "900.00")]
    assert check_invariants(fs, units).total.amount == Decimal(total)


def test_placements_card_takes_only_its_campaign_rows():
    """Та же площадка (тот же object_id) в другой кампании — не единица этого вывода."""
    fs = [placements_card(A, "900.00", (7,)), placements_card(B, "200.00", (7,))]
    units = [unit(A, "placement", 7, day(3), "900.00"), unit(B, "placement", 7, day(3), "200.00")]
    assert check_invariants(fs, units).total.amount == Decimal("1100.00")


def test_placements_and_queries_of_one_campaign_add_up():
    fs = [placements_card(A, "300.00", (7,)), card("zero_conv_queries", "query", 1, "500.00")]
    units = [unit(A, "placement", 7, day(2), "300.00"), unit(A, "query", 1, day(2), "500.00")]
    assert check_invariants(fs, units).total.amount == Decimal("800.00")


def test_declared_spend_not_matching_rows_falls_back_to_block():
    """Строки расходятся с суммой вывода (неполный снимок) — не раскладывать: блок кампании, итог ≥ карточки."""
    fs = [placements_card(A, "900.00", (7,))]
    units = [*spend(A, {n: "1000.00" for n in range(1, 8)}), unit(A, "placement", 7, day(3), "800.00")]
    assert check_invariants(fs, units).total.amount == Decimal("900.00")
    fs.append(card("zero_conv_campaign", "campaign", A, "7000.00"))
    assert check_invariants(fs, units).total.amount == Decimal("7000.00")


def test_equal_sums_without_declaration_are_not_guessed_as_spend():
    """Эвристики «сумма совпала с расходом — значит, по расходу» нет: старый вывод без декларации — блок, даже если
    сумма до копейки равна расходу единиц. С декларацией те же карточки складываются как запросы + площадки."""
    units = [unit(A, "query", 1, day(2), "500.00"), unit(A, "placement", 7, day(2), "300.00")]
    legacy = [card("zero_conv_queries", "query", 1, "500.00", basis=None),
              card("zero_conv_placements", "placement", 7, "300.00", basis=None)]
    assert check_invariants(legacy, units).total.amount == Decimal("500.00")  # два блока одной кампании — max
    declared = [card("zero_conv_queries", "query", 1, "500.00"), card("zero_conv_placements", "placement", 7, "300.00")]
    assert check_invariants(declared, units).total.amount == Decimal("800.00")


@pytest.mark.parametrize("basis", [SPEND_CAMPAIGN, FORMULA, ExposureBasis("spend", "placement", (7, 2 ** 62))])
def test_basis_round_trips_through_evidence_meta(basis):
    meta = basis_meta(basis)
    assert all(isinstance(v, str) for v in meta.values())
    assert basis_from_meta({"reference_mode": "campaign", **meta}) == basis


@pytest.mark.parametrize("meta", [{}, {"exposure_basis": "guess"}, {"exposure_basis": "spend"},
                                  {"exposure_basis": "spend", "exposure_level": "placement"},
                                  {"exposure_basis": "spend", "exposure_level": "placement",
                                   "exposure_object_ids": "7,x"}])
def test_missing_or_broken_declaration_is_none(meta):
    assert basis_from_meta(meta) is None


@pytest.mark.parametrize("args", [("formula", "campaign"), ("formula", None, (1,)), ("spend",), ("spend", "placement"),
                                  ("spend", "campaign", (1,))])
def test_basis_invariants(args):
    with pytest.raises(ValueError):
        ExposureBasis(*args)
