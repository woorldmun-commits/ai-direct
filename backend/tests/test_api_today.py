"""GET /workspaces/{ws}/today (API_CONTRACT.md §8) на реальной БД: снимок настоящей синхронизацией → настоящий аудит
→ HTTP. Итог — exposure_total@1 без двойного счёта; топ-3 по уровню действия, exposure, уверенности; свежесть;
изоляция (чужой workspace — 404); пустой workspace — unavailable, а не 0; любое число — сериализованный Value."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest

from app.rules.domain import SPEND_CAMPAIGN, Fact, Finding, Rule, frozen, issue_key, windows
from app.sources.direct import PLACEMENT_REPORT
from app.sync.parse import placement_id
from app.worker.sync import PLACEMENTS_REPORT_ENV
from app.worker import audit as audit_module
from test_api_headers import assert_secure
from test_api_support import api, cookie, session, user, world  # noqa: F401 — фикстуры
from test_direct_sync import CID, TO, root  # noqa: F401 — root: фикстура
from test_metrika_sync import metrika  # noqa: F401 — фикстура
from test_schema import chain, new_workspace, one  # noqa: F401 — chain: фикстура
from test_worker_audit import audit, sync
from test_placements_sync import placement_tsv
from test_worker_sync import ws  # noqa: F401 — фикстура

VALUE_KEYS = {"amount", "unit", "calculation_type", "source", "period", "data_status", "data_sufficiency", "formula",
              "rule_version"}
MONEY = re.compile(r"[0-9]+\.[0-9]{2}")


def _spend_block(rule, snap, settings):
    """Тестовое правило уровня кампании: exposure = весь расход кампании за окно (как «кампания без конверсий»)."""
    evaluation, _ = windows(snap.period_to)
    out = []
    for cid in sorted({d.campaign_id for d in snap.campaign_days}):
        cost = sum((d.cost for d in snap.campaign_days if d.campaign_id == cid and d.date in evaluation), Decimal(0))
        lost = Fact(cost, "rub", "yandex_direct", evaluation, "estimated", "sum(cost)")
        out.append(Finding(
            rule_version=rule.rule_version, issue_type=rule.family, object_type="campaign", object_id=cid,
            issue_key=issue_key(snap.workspace_id, snap.direct_account_id, rule.family, "campaign", cid),
            reason_code="test_spend", metric="cost", actual=cost, reference=Decimal(0), reference_type="target",
            delta_pct=Decimal(0), lost=lost, recoverable=lost, current_data_quality="high",
            evidence=frozen({"cost": Fact(cost, "rub", "yandex_direct", evaluation)}), evidence_meta=frozen({}),
            action=frozen({"type": "pause_for_test"}), exposure_basis=SPEND_CAMPAIGN))
    return tuple(out)


SPEND_RULE = Rule("spend_block", 1, "spend_block", frozenset({"yandex_direct"}), {}, evaluate=_spend_block)


@pytest.fixture
def audited(rw, ws):
    """Workspace после синхронизации; проблема-заглушка из chain закрыта — её вывод не из аудита по снимку."""
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (ws["issue"],))
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    ws["snapshot_id"] = sync(rw, ws)
    return ws


def get_today(api, rw, owner: int, ws_id: int):
    return api.get(f"/api/v1/workspaces/ws_{ws_id}/today", headers=cookie(session(rw, owner)))


def lost_of(rw, ws_id: int) -> dict[str, dict]:
    rows = rw.execute("""SELECT i.issue_type, f.lost FROM findings f JOIN issues i ON i.id = f.issue_id
                         WHERE i.workspace_id = %s AND i.closed_at IS NULL""", (ws_id,)).fetchall()
    return dict(rows)


def assert_value(v: dict):
    assert set(v) == VALUE_KEYS, v
    assert set(v["period"]) == {"from", "to"}
    if v["calculation_type"] == "unavailable":
        assert v["amount"] is None and v["data_sufficiency"] == "insufficient"
    else:
        assert isinstance(v["amount"], str) and MONEY.fullmatch(v["amount"]), v["amount"]
    if v["calculation_type"] == "estimated":
        assert v["formula"]


def all_values(body: dict) -> list[dict]:
    e = body["exposure"]
    return [e["total"], e["overlap"], *(c["amount"] for c in e["components"]),
            *(x for item in body["top"] for x in (item["exposure"], item["can_save"]))]


def test_today_on_real_snapshot_dedups_overlapping_cards(api, rw, audited, monkeypatch):
    """Две карточки одной кампании: «весь расход» и высокий CPA. Итог — max, а не сумма; overlap — разница."""
    monkeypatch.setattr(audit_module, "RULES", audit_module.RULES + (SPEND_RULE,))
    audit(rw, audited)
    cards = lost_of(rw, audited["ws"])
    spend, high_cpa = Decimal(cards["spend_block"]["amount"]), Decimal(cards["high_cpa"]["amount"])
    assert spend > high_cpa > 0

    r = get_today(api, rw, audited["user"], audited["ws"])
    assert r.status_code == 200
    assert_secure(r)
    body = r.json()
    e = body["exposure"]
    assert Decimal(e["total"]["amount"]) == spend
    assert Decimal(e["overlap"]["amount"]) == high_cpa
    assert e["total"]["calculation_type"] == "estimated" and e["total"]["rule_version"] == "exposure_total@1"
    assert e["version"] == "exposure_total@1" and e["formula"] == e["total"]["formula"]
    assert {c["issue_type"]: Decimal(c["amount"]["amount"]) for c in e["components"]} == {
        "spend_block": spend, "high_cpa": high_cpa}
    assert e["coverage"] == {"included": 2, "unavailable": 0}
    assert body["counts"] == {"active": 2}
    # приоритет — уровень действия: «снизить ставку» (review) выше «проверить» (inspect_only) с большим exposure
    assert [i["action_level"] for i in body["top"]] == ["review", "inspect_only"]
    assert Decimal(body["top"][1]["exposure"]["amount"]) == spend
    for v in all_values(body):
        assert_value(v)
    assert "snapshot_id" not in r.text and "snapshot_ids" not in r.text
    assert body["data_status"] == e["total"]["data_status"]
    assert body["last_audit_at"] is not None


def test_persisted_findings_declare_exposure_basis(rw, audited, monkeypatch):
    """Основа exposure пишется в evidence_meta при сохранении вывода — итог не угадывает её по суммам."""
    monkeypatch.setattr(audit_module, "RULES", audit_module.RULES + (SPEND_RULE,))
    audit(rw, audited)
    metas = dict(rw.execute("""SELECT i.issue_type, f.evidence_meta FROM findings f JOIN issues i ON i.id = f.issue_id
                               WHERE i.workspace_id = %s AND i.closed_at IS NULL""", (audited["ws"],)).fetchall())
    assert metas["high_cpa"]["exposure_basis"] == "formula" and "exposure_level" not in metas["high_cpa"]
    assert (metas["spend_block"]["exposure_basis"], metas["spend_block"]["exposure_level"]) == ("spend", "campaign")


def test_today_freshness_from_snapshots_and_connections(api, rw, audited):
    audit(rw, audited)
    rw.execute("UPDATE metrika_connections SET status = 'permission_missing' WHERE workspace_id = %s",
               (audited["ws"],))
    body = get_today(api, rw, audited["user"], audited["ws"]).json()
    f = body["data_freshness"]
    assert f["yandex_direct"] == {"status": "connected", "data_to": TO.isoformat()}
    assert f["yandex_metrika"] == {"status": "permission_missing", "data_to": TO.isoformat()}
    sealed = one(rw, "SELECT sealed_at FROM snapshots WHERE id = %s", audited["snapshot_id"])
    assert f["last_snapshot_at"] == sealed.isoformat()


def test_single_card_total_equals_card_and_overlap_is_zero(api, rw, audited):
    audit(rw, audited)
    [card] = lost_of(rw, audited["ws"]).values()
    body = get_today(api, rw, audited["user"], audited["ws"]).json()
    assert body["exposure"]["total"]["amount"] == card["amount"]
    assert body["exposure"]["overlap"]["amount"] == "0.00"
    assert body["exposure"]["total"]["data_status"] == card["data_status"]
    assert [i["exposure"]["amount"] for i in body["top"]] == [card["amount"]]


def test_decided_recommendation_leaves_today(api, rw, audited, monkeypatch):
    """«Не буду» — решение человека: рекомендация больше не активна, её сумма не входит в итог."""
    monkeypatch.setattr(audit_module, "RULES", audit_module.RULES + (SPEND_RULE,))
    audit(rw, audited)
    rec = one(rw, """SELECT r.id FROM recommendations r JOIN issues i ON i.id = r.issue_id
                     WHERE i.workspace_id = %s AND i.issue_type = 'spend_block'""", audited["ws"])
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, payload)
                  VALUES (%s, 'rejected', %s, '{"reason": "too_risky"}')""", (rec, audited["user"]))
    body = get_today(api, rw, audited["user"], audited["ws"]).json()
    cards = lost_of(rw, audited["ws"])
    assert body["counts"] == {"active": 1}
    assert body["exposure"]["total"]["amount"] == cards["high_cpa"]["amount"]
    assert [c["issue_type"] for c in body["exposure"]["components"]] == ["high_cpa"]
    assert f"rec_{rec}" not in [i["id"] for i in body["top"]]


def test_empty_workspace_is_unavailable_with_empty_top(api, rw):
    owner = user(rw)
    ws_id = new_workspace(rw, "empty", user=owner)
    r = get_today(api, rw, owner, ws_id)
    assert r.status_code == 200
    assert_secure(r)
    body = r.json()
    for key in ("total", "overlap"):
        v = body["exposure"][key]
        assert_value(v)
        assert v["amount"] is None and v["calculation_type"] == "unavailable"
    assert body["exposure"]["components"] == [] and body["exposure"]["coverage"] == {"included": 0, "unavailable": 0}
    assert body["top"] == [] and body["counts"] == {"active": 0} and body["last_audit_at"] is None
    assert body["data_freshness"] == {"last_snapshot_at": None,
                                      "yandex_direct": {"status": None, "data_to": None},
                                      "yandex_metrika": {"status": None, "data_to": None}}
    assert body["data_status"] == "complete"


def test_cards_without_audited_snapshot_do_not_count(api, rw, world):
    """Вывод вне последнего аудита кабинета (нет состава аудита) — не «активная рекомендация последнего аудита»."""
    body = get_today(api, rw, world["owner"], world["a1"]).json()
    assert body["counts"] == {"active": 0} and body["exposure"]["total"]["amount"] is None
    assert body["last_audit_at"] is not None  # аудит был — но без снимка этого кабинета


@pytest.mark.parametrize("who, target", [("owner", "b1"), ("viewer", "a2"), ("member", "a1"), ("owner_b", "a1")])
def test_foreign_workspace_is_404_like_nonexistent(api, rw, world, who, target):
    token = session(rw, world[who])
    foreign = api.get(f"/api/v1/workspaces/ws_{world[target]}/today", headers=cookie(token))
    missing = api.get("/api/v1/workspaces/ws_999999999/today", headers=cookie(token))
    assert foreign.status_code == missing.status_code == 404
    assert_secure(foreign)
    for r in (foreign, missing):
        r_json = r.json()
        r_json["error"].pop("request_id")
        assert r_json == {"error": {"code": "not_found", "message": "Не найдено."}}
    assert world["rec_b1"]["login"] not in foreign.text


def test_viewer_sees_own_workspace_today(api, rw, world):
    r = api.get(f"/api/v1/workspaces/ws_{world['a1']}/today", headers=cookie(session(rw, world["viewer"])))
    assert r.status_code == 200 and world["rec_b1"]["login"] not in r.text


def test_today_requires_session(api, world):
    r = api.get(f"/api/v1/workspaces/ws_{world['a1']}/today")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"
    assert_secure(r)


def test_foreign_workspace_cards_never_leak(api, rw, audited, monkeypatch):
    """Другой workspace с аудитом: его итог и рекомендации не видны владельцу первого и наоборот."""
    monkeypatch.setattr(audit_module, "RULES", audit_module.RULES + (SPEND_RULE,))
    audit(rw, audited)
    stranger = user(rw)
    other = new_workspace(rw, "other", user=stranger)
    assert get_today(api, rw, stranger, audited["ws"]).status_code == 404
    body = get_today(api, rw, stranger, other).json()
    assert body["top"] == [] and body["exposure"]["total"]["amount"] is None


def test_placements_pipeline_sync_audit_today(api, rw, ws, monkeypatch):
    """Конвейер площадок целиком: отчёт включён переменной → снимок с площадками и справочником имён → аудит
    (zero_conv_placements@1 рядом с high_cpa_target@1) → вывод с именами и основой exposure → «Сегодня»: итог —
    max(формульный блок 18 000, площадка 30 000) = 30 000, а не сумма 48 000."""
    monkeypatch.setenv(PLACEMENTS_REPORT_ENV, "1")
    rw.execute("UPDATE issues SET closed_at = now(), close_reason = 'resolved' WHERE id = %s", (ws["issue"],))
    rw.execute("INSERT INTO workspace_settings (workspace_id, target_cpa) VALUES (%s, 3000)", (ws["ws"],))
    (ws["root"].path / ws["login"] / f"{PLACEMENT_REPORT.key}.tsv").write_text(placement_tsv((
        ("bad-site.ru", "300", "30000.00", ("0", "0"), CID, TO - timedelta(4)),
        ("good-site.ru", "300", "9000.00", ("2", "0"), CID, TO - timedelta(4)))), encoding="utf-8")
    sync(rw, ws)
    audit(rw, ws)

    meta, action, level = rw.execute(
        """SELECT f.evidence_meta, f.action, f.action_level FROM findings f JOIN issues i ON i.id = f.issue_id
           WHERE i.workspace_id = %s AND i.issue_type = 'zero_conv_placements'""", (ws["ws"],)).fetchone()
    bad = placement_id("bad-site.ru")
    assert action == {"type": "exclude_placements", "execution": "manual", "placement_ids": [bad]}
    assert meta[f"placement_{bad}_name"] == "bad-site.ru" and level == "review"
    assert (meta["exposure_basis"], meta["exposure_level"], meta["exposure_object_ids"]) == ("spend", "placement",
                                                                                           str(bad))
    text = one(rw, """SELECT e.text FROM explanations e JOIN findings f ON f.id = e.finding_id
                      JOIN issues i ON i.id = f.issue_id WHERE i.issue_type = 'zero_conv_placements'
                        AND i.workspace_id = %s""", ws["ws"])
    assert "bad-site.ru" in text and "30 000 ₽" in text and "good-site.ru" not in text

    body = get_today(api, rw, ws["user"], ws["ws"]).json()
    e = body["exposure"]
    assert {c["issue_type"]: c["amount"]["amount"] for c in e["components"]} == {
        "zero_conv_placements": "30000.00", "high_cpa": "18000.00"}
    assert (e["total"]["amount"], e["overlap"]["amount"]) == ("30000.00", "18000.00")
