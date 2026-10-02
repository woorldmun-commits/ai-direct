"""Golden-набор правил v1.0 и гейт выпуска (docs/AI_GOVERNANCE.md §4). Прогон — pytest (tests/test_evals.py).

Кейс — один JSON-файл в evals/cases/<семейство>/<имя>.json (подкаталог на семейство правила; новое правило
добавляет свой каталог, раннер собирает все cases/**/*.json). Данные синтетические и БЕЗ ПД: только ID, даты и
числа — неизвестные ключи отвергаются, поэтому названия кампаний, тексты запросов и т. п. в кейс не попадут.

{
  "description": "что проверяет кейс",
  "tags": ["problem" | "clean" | "boundary" | "partial" | "autostrategy" | "not_enough_data", ...],
  "settings": {"target_cpa": "3000"},                    // замороженные настройки workspace; {} — target не задан
  "snapshot": {
    "period_to": "2026-09-30",                            // последний день снимка
    "history_days": 37,                                   // необязательно: глубина снимка (period_from)
    "partial_from": "2026-09-28",                         // необязательно: с этого дня данные досчитываются
    "sources": ["yandex_direct", "direct_conversions"],
    "campaigns": [{
      "id": 101,
      "strategy": "manual",                               // необязательно, только для гейта: manual · auto_cpa · …
      "history_days": 37,                                 // необязательно: дни с нулями до period_to
      "days": [{"date": "2026-09-30", "cost": "42000", "clicks": 70, "conversions": "0"}]  // null — неизвестно
    }]
  },
  "expected": [{                                          // ровно эти выводы, не больше и не меньше
    "rule_version": "zero_conv_campaign@1", "object_type": "campaign", "object_id": 101,
    "candidate_level": "inspect_only", "action_level": "inspect_only",
    "action": {"type": "investigate_zero_conversions", ...}, "exposure": "42000.00"
  }],
  "expected_not_enough_data": [{"rule_version": "...", "reason": "...", "object_type": "campaign", "object_id": 101}]
}                                                         // необязательно: эти «недостаточно данных» должны быть

Гейт (gate()) — список нарушений по категориям; пустой список = кейс прошёл:
  regression       — ожидаемый вывод пропал или изменились действие / уровень / exposure;
  level_raised     — уровень действия выше ожидаемого;
  false_positive   — вывод, которого нет в ожидаемых (на «чистом» кейсе — любой вывод);
  invariant        — данные partial → уровень не выше review; не ручная стратегия → ставка/бюджет не на change;
  not_enough_data  — ожидаемое «недостаточно данных» не выдано.
Намеренное изменение ожидаемого вывода — правка кейса в том же PR с объяснением."""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable

from app.audit.policy import LEVELS, decide
from app.audit.values import to_value
from app.rules import RULES
from app.rules.domain import (BID_OR_BUDGET_ACTIONS, AuditSettings, CampaignDay, Finding, NotEnoughData, SnapshotView,
                              run)

CASES_DIR = Path(__file__).parent / "cases"
SNAPSHOT_ID, WORKSPACE_ID, ACCOUNT_ID = 1, 1, 1  # синтетические: на выводы влияют только через issue_key
PARTIAL_DAYS = 3  # по умолчанию досчитываются последние 3 дня — как окно досчёта синхронизации
MAX_LEVEL_WHEN_PARTIAL = "review"

_CASE_KEYS = {"description", "tags", "settings", "snapshot", "expected", "expected_not_enough_data"}
_SNAPSHOT_KEYS = {"period_to", "history_days", "partial_from", "sources"}
_CAMPAIGN_KEYS = {"id", "strategy", "history_days", "days"}
_DAY_KEYS = {"date", "cost", "clicks", "conversions"}
_EXPECTED_KEYS = {"rule_version", "object_type", "object_id", "candidate_level", "action_level", "action", "exposure"}
_NED_KEYS = {"rule_version", "reason", "object_type", "object_id"}
TAGS = {"problem", "clean", "boundary", "partial", "autostrategy", "not_enough_data"}


def _keys(obj: dict, allowed: set[str], where: str, required: set[str] = frozenset()) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{where}: ожидается объект")
    if extra := set(obj) - allowed:
        raise ValueError(f"{where}: неизвестные ключи {sorted(extra)} (данные кейса — только ID, даты и числа)")
    if missing := set(required) - set(obj):
        raise ValueError(f"{where}: нет ключей {sorted(missing)}")


# --- Снимок ---------------------------------------------------------------------------------------

def _campaign_days(period_to: date, campaigns: list[dict]) -> tuple[CampaignDay, ...]:
    out = []
    for c in campaigns:
        _keys(c, _CAMPAIGN_KEYS, f"campaign {c.get('id')}", {"id", "days"})
        days = {period_to - timedelta(i): (Decimal(0), 0, Decimal(0)) for i in range(c.get("history_days", 37))}
        for d in c["days"]:
            _keys(d, _DAY_KEYS, f"campaign {c['id']} day", _DAY_KEYS)
            conv = None if d["conversions"] is None else Decimal(d["conversions"])
            days[date.fromisoformat(d["date"])] = (Decimal(d["cost"]), int(d["clicks"]), conv)
        out += [CampaignDay(int(c["id"]), day, *values) for day, values in sorted(days.items())]
    return tuple(out)


# Раздел снимка → (поле SnapshotView, построитель). Новое правило с новыми данными (площадки РСЯ и т. п.)
# добавляет сюда свой раздел и ключ в _SNAPSHOT_KEYS.
SECTIONS: dict[str, tuple[str, Callable]] = {"campaigns": ("campaign_days", _campaign_days)}


@dataclass(frozen=True)
class Case:
    name: str
    data: dict

    @property
    def tags(self) -> set[str]:
        return set(self.data.get("tags", ()))

    def settings(self) -> AuditSettings:
        s = self.data.get("settings", {})
        _keys(s, {"target_cpa"}, f"{self.name}: settings")
        return AuditSettings(target_cpa=Decimal(s["target_cpa"]) if s.get("target_cpa") is not None else None)

    def view(self) -> tuple[SnapshotView, date]:
        s = self.data["snapshot"]
        _keys(s, _SNAPSHOT_KEYS | set(SECTIONS), f"{self.name}: snapshot", {"period_to", "sources"})
        period_to = date.fromisoformat(s["period_to"])
        fields = {field: build(period_to, s.get(key, [])) for key, (field, build) in SECTIONS.items()}
        view = SnapshotView(snapshot_id=SNAPSHOT_ID, workspace_id=WORKSPACE_ID, direct_account_id=ACCOUNT_ID,
                            period_from=period_to - timedelta(s.get("history_days", 37) - 1), period_to=period_to,
                            sources=frozenset(s["sources"]), **fields)
        partial_from = s.get("partial_from")
        return view, (date.fromisoformat(partial_from) if partial_from else period_to - timedelta(PARTIAL_DAYS - 1))

    def strategies(self) -> dict[int, str]:
        return {int(c["id"]): c.get("strategy", "unknown") for c in self.data["snapshot"].get("campaigns", [])}


def load_cases(root: Path = CASES_DIR) -> list[Case]:
    cases = []
    for path in sorted(root.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = path.relative_to(root).with_suffix("").as_posix()
        _keys(data, _CASE_KEYS, name, {"description", "snapshot", "expected"})
        if unknown := set(data.get("tags", ())) - TAGS:
            raise ValueError(f"{name}: неизвестные теги {sorted(unknown)}")
        if "clean" in data.get("tags", ()) and data["expected"]:
            raise ValueError(f"{name}: у «чистого» кейса не может быть ожидаемых выводов")
        for e in data["expected"]:
            _keys(e, _EXPECTED_KEYS, f"{name}: expected", _EXPECTED_KEYS)
        for e in data.get("expected_not_enough_data", []):
            _keys(e, _NED_KEYS, f"{name}: expected_not_enough_data", {"rule_version", "reason"})
        cases.append(Case(name, data))
    return cases


# --- Прогон ---------------------------------------------------------------------------------------

def _json(x) -> object:
    """Действие в том виде, в каком оно попадёт в jsonb (кортежи → списки)."""
    return json.loads(json.dumps(x, default=str))


@dataclass(frozen=True)
class Outcome:
    rule_version: str
    object_type: str
    object_id: int
    candidate_level: str
    action_level: str
    action: dict
    exposure: Decimal
    partial: bool  # хотя бы одно число вывода — за дни, которые ещё досчитываются

    @property
    def key(self) -> tuple:
        return self.rule_version, self.object_type, self.object_id


def evaluate(case: Case) -> tuple[list[Outcome], list[NotEnoughData]]:
    """Как аудит: все зарегистрированные правила → политика безопасности → Value (data_status)."""
    view, partial_from = case.view()
    settings = case.settings()
    findings, skipped = [], []
    for rule in RULES:
        for out in run(rule, view, settings):
            if isinstance(out, NotEnoughData):
                skipped.append(out)
                continue
            assert isinstance(out, Finding)
            d = decide(out)
            values = [to_value(f, SNAPSHOT_ID, partial_from) for f in (out.lost, *out.evidence.values())]
            findings.append(Outcome(out.rule_version, out.object_type, out.object_id, d.candidate_level, d.level,
                                    _json(dict(out.action)), values[0].amount,
                                    any(v.data_status == "partial" for v in values)))
    return findings, skipped


def _rank(level: str) -> int:
    return LEVELS.index(level)


def gate(case: Case) -> list[tuple[str, str]]:
    """Нарушения гейта по кейсу: [(категория, описание)]. Пусто — кейс прошёл."""
    findings, skipped = evaluate(case)
    actual = {o.key: o for o in findings}
    expected = {(e["rule_version"], e["object_type"], e["object_id"]): e for e in case.data["expected"]}
    violations = []
    for key, e in expected.items():
        o = actual.get(key)
        if o is None:
            violations.append(("regression", f"{key}: ожидаемый вывод пропал"))
            continue
        if _rank(o.action_level) > _rank(e["action_level"]):
            violations.append(("level_raised", f"{key}: {e['action_level']} → {o.action_level}"))
        for name, got, want in (("candidate_level", o.candidate_level, e["candidate_level"]),
                                ("action_level", o.action_level, e["action_level"]),
                                ("action", o.action, e["action"]),
                                ("exposure", o.exposure, Decimal(e["exposure"]))):
            if got != want:
                violations.append(("regression", f"{key}: {name} {want!r} → {got!r}"))
    for key in actual.keys() - expected.keys():
        violations.append(("false_positive", f"{key}: лишний вывод" + (" на чистом кейсе" if "clean" in case.tags
                                                                         else "")))
    strategies = case.strategies()
    for o in findings:
        if o.partial and _rank(o.action_level) > _rank(MAX_LEVEL_WHEN_PARTIAL):
            violations.append(("invariant", f"{o.key}: данные partial, а уровень {o.action_level}"))
        if (strategies.get(o.object_id, "unknown") != "manual" and o.action["type"] in BID_OR_BUDGET_ACTIONS
                and o.action_level == "change"):
            violations.append(("invariant", f"{o.key}: ставка/бюджет на change без ручной стратегии"))
    got_skipped = {(s.rule_version, s.reason.value, s.object_type, s.object_id) for s in skipped}
    for e in case.data.get("expected_not_enough_data", []):
        want = (e["rule_version"], e["reason"], e.get("object_type"), e.get("object_id"))
        if want not in got_skipped:
            violations.append(("not_enough_data", f"нет ожидаемого «недостаточно данных» {want}"))
    return violations
