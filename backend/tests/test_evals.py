"""Golden-прогон правил v1.0 — гейт выпуска (docs/AI_GOVERNANCE.md §4.2). Собирает все evals/cases/**/*.json.
Красный прогон = новая версия правила / политики не включается. Намеренное изменение вывода — правка кейса."""

import copy
import json
from collections import Counter

import pytest

from app.rules import RULES
from evals.golden import CASES_DIR, Case, gate, load_cases

CASES = load_cases()
BY_NAME = {c.name: c for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_golden_case_passes_gate(case):
    assert gate(case) == []


# --- Покрытие набора ------------------------------------------------------------------------------

def test_every_rule_family_has_its_case_directory():
    """Кейсы — по подкаталогу на семейство правила; на семейство ≥ 4 кейсов, из них хотя бы один «чистый»
    и хотя бы один граничный."""
    families = {r.family for r in RULES}
    per_family = Counter(c.name.split("/")[0] for c in CASES)
    for family in families:
        assert per_family[family] >= 4, family
        tags = set().union(*(c.tags for c in CASES if c.name.startswith(family + "/")))
        assert {"clean", "boundary"} <= tags, family


def test_every_rule_version_has_expected_findings():
    """Каждая зарегистрированная версия хотя бы в 4 кейсах — выводом или ожидаемым «недостаточно данных»."""
    mentions = Counter()
    for c in CASES:
        versions = {e["rule_version"] for e in c.data["expected"] + c.data.get("expected_not_enough_data", [])}
        mentions.update(versions)
    for rule in RULES:
        assert mentions[rule.rule_version] >= 4, rule.rule_version
        assert any(e["rule_version"] == rule.rule_version for c in CASES for e in c.data["expected"]), rule.rule_version


def test_required_scenarios_for_v1_rules():
    for family in ("high_cpa", "zero_conv_campaign"):
        tags = set().union(*(c.tags for c in CASES if c.name.startswith(family + "/")))
        assert {"problem", "clean", "boundary", "partial", "autostrategy", "not_enough_data"} <= tags, family


# --- Сам гейт ловит то, что должен ---------------------------------------------------------------

def _mutated(name: str, change) -> Case:
    data = copy.deepcopy(BY_NAME[name].data)
    change(data)
    return Case(name, data)


def _categories(case: Case) -> set[str]:
    return {category for category, _ in gate(case)}


def test_gate_detects_level_raise():
    case = _mutated("high_cpa/target_above_medium_data", lambda d: d["expected"][0].update(action_level="inspect_only"))
    assert {"level_raised", "regression"} <= _categories(case)


def test_gate_detects_changed_exposure_and_action():
    case = _mutated("zero_conv_campaign/target_spend_without_conversions",
                    lambda d: d["expected"][0].update(exposure="41999.99", action={"type": "pause"}))
    assert _categories(case) == {"regression"}
    assert len(gate(case)) == 2


def test_gate_detects_missing_finding():
    """Порог правила вырос бы — ожидаемый вывод пропал бы: регрессия."""
    case = _mutated("zero_conv_campaign/exactly_on_threshold",
                    lambda d: d["snapshot"]["campaigns"][0]["days"][1].update(cost="8999.99"))
    assert _categories(case) == {"regression"}


def test_gate_detects_false_positive_on_clean_case():
    case = _mutated("zero_conv_campaign/clean_account",
                    lambda d: d["snapshot"]["campaigns"][1]["days"][0].update(conversions="0", cost="20000", clicks=60))
    assert _categories(case) == {"false_positive"}


def test_gate_detects_missing_not_enough_data():
    case = _mutated("zero_conv_campaign/just_below_threshold",
                    lambda d: d["expected_not_enough_data"][0].update(reason="source_missing"))
    assert _categories(case) == {"not_enough_data"}


# --- Формат: без ПД и без лишнего ----------------------------------------------------------------

@pytest.mark.parametrize("where, patch", [
    ("campaign", lambda d: d["snapshot"]["campaigns"][0].update(name="Кампания Иванова")),
    ("case", lambda d: d.update(client_email="x@example.com")),
    ("day", lambda d: d["snapshot"]["campaigns"][0]["days"][0].update(query="купить окна")),
    ("tag", lambda d: d.update(tags=["mystery"])),
])
def test_loader_rejects_unknown_keys(tmp_path, where, patch):
    data = copy.deepcopy(BY_NAME["zero_conv_campaign/target_spend_without_conversions"].data)
    patch(data)
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "case.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        cases = load_cases(tmp_path)
        cases[0].view()


def test_clean_case_cannot_expect_findings(tmp_path):
    data = copy.deepcopy(BY_NAME["zero_conv_campaign/target_spend_without_conversions"].data)
    data["tags"] = ["clean"]
    (tmp_path / "case.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(tmp_path)


def test_cases_are_found_recursively():
    assert len(CASES) == len(list(CASES_DIR.rglob("*.json"))) >= 12
