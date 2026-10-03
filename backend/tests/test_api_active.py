"""Одно определение «активной рекомендации» для GET …/today и GET …/recommendations (app/api/active.py):
открытая проблема на выбранном кабинете, проверенном ПОСЛЕДНИМ аудитом, без решения человека (postponed — до даты).
Удержанная «недостаточно данных» — активна, но insufficient и вне итога exposure. Обе ручки — на одних и тех же
данных; плюс устойчивость списка к неизвестной форме действия и data_status «Сегодня»."""

from datetime import date, datetime, timezone

import pytest
from psycopg.types.json import Jsonb

from app.api.active import status_of, today_msk
from test_api_isolation import recs
from test_api_support import api, cookie, recommendation, session, user, world  # noqa: F401 — фикстуры
from test_schema import new_workspace, one


def both(api, rw, ids, name="a1"):
    """(тело «Сегодня», элементы «Рекомендаций») одного workspace глазами owner."""
    token = session(rw, ids["owner"])
    today = api.get(f"/api/v1/workspaces/ws_{ids[name]}/today", headers=cookie(token)).json()
    return today, recs(api, token, ids, name).json()["items"]


def assert_active(api, rw, ids, rec_ids: list[int], name="a1"):
    today, items = both(api, rw, ids, name)
    assert today["counts"] == {"active": len(rec_ids)}
    assert sorted(i["id"] for i in items) == sorted(i["id"] for i in today["top"]) == sorted(f"rec_{r}" for r in rec_ids)
    return today, items


def event(rw, rec: dict, kind: str, actor: int, payload: dict):
    rw.execute("""INSERT INTO recommendation_events (recommendation_id, type, actor_user_id, payload)
                  VALUES (%s, %s, %s, %s)""", (rec["rec"], kind, actor, Jsonb(payload)))


def newer_audit(rw, rec: dict, ws: int, *, include: bool, skipped=()) -> int:
    """Новый (последний) аудит workspace: кабинет рекомендации в нём со своим снимком или исключён."""
    audit = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings,
                                               rules_run, rules_skipped, excluded_accounts, created_at)
                       VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, '2026-09-30', '{}', '{high_cpa_target@1}',
                               %s, %s, now() + interval '1 minute') RETURNING id""",
                ws, rec["release"], Jsonb(list(skipped)),
                Jsonb([] if include else [{"account": rec["account"], "reason": "direct_unavailable",
                                           "detail": "access_denied"}]))
    if include:
        snapshot = one(rw, "SELECT snapshot_id FROM audit_run_snapshots WHERE audit_run_id = %s", rec["audit"])
        rw.execute("INSERT INTO audit_run_snapshots (audit_run_id, direct_account_id, snapshot_id) VALUES (%s, %s, %s)",
                   (audit, rec["account"], snapshot))
    return audit


def test_new_recommendation_is_active_in_both(api, rw, world):
    today, items = assert_active(api, rw, world, [world["rec_a1"]["rec"]])
    assert items[0]["status"] == "new" and items[0]["data_sufficiency"] == "sufficient"
    assert today["exposure"]["total"]["amount"] == items[0]["exposure"]["amount"] == "12500.00"


@pytest.mark.parametrize("kind, payload", [("rejected", {"reason": "too_risky"}),
                                           ("postponed", {"until": "2999-01-01"})])
def test_decided_recommendation_is_not_active_in_both(api, rw, world, kind, payload):
    event(rw, world["rec_a1"], kind, world["owner"], payload)
    today, _ = assert_active(api, rw, world, [])
    assert today["exposure"]["total"]["amount"] is None


def test_postponed_until_passed_date_is_active_again(api, rw, world):
    event(rw, world["rec_a1"], "postponed", world["owner"], {"until": "2026-01-01"})
    _, items = assert_active(api, rw, world, [world["rec_a1"]["rec"]])
    assert items[0]["status"] == "new"


def test_account_excluded_from_last_audit_is_not_counted(api, rw, world):
    """Кабинет исключён из последнего аудита (нет доступа): его рекомендации — ни в итоге, ни в счётчиках, ни в
    списке, даже если более старый аудит его видел."""
    newer_audit(rw, world["rec_a1"], world["a1"], include=False)
    today, _ = assert_active(api, rw, world, [])
    assert today["exposure"]["total"]["amount"] is None and today["exposure"]["coverage"]["included"] == 0


def test_last_audit_that_did_not_confirm_is_not_active(api, rw, world):
    """Кабинет в последнем аудите, но проблему тот не подтвердил и не удержал «недостаточно данных» — не активна."""
    newer_audit(rw, world["rec_a1"], world["a1"], include=True)
    assert_active(api, rw, world, [])


@pytest.mark.parametrize("object_level", [True, False])  # по объекту проблемы или всему правилу кабинета
def test_held_by_not_enough_data_is_active_but_insufficient(api, rw, world, object_level):
    rec = world["rec_a1"]
    held = {"account": rec["account"], "rule": "high_cpa_target@1", "reason": "volume_insufficient",
            "object_type": "campaign" if object_level else None, "object_id": rec["object_id"] if object_level else None}
    newer_audit(rw, rec, world["a1"], include=True, skipped=[held])
    today, items = assert_active(api, rw, world, [rec["rec"]])
    for item in (items[0], today["top"][0]):
        assert item["data_sufficiency"] == "insufficient" and item["action_level"] == "inspect_only"
        assert item["exposure"]["amount"] is None and item["exposure"]["unavailable_reason"] == "volume_insufficient"
        assert item["can_save"]["amount"] is None and item["exposure_overlap"]["amount"] is None
        assert item["action"]["type"] == "investigate" and item["action"]["topic"] == "high_cpa"
        assert "недостаточно данных" in item["title"] and "12" not in item["title"]
    e = today["exposure"]
    assert e["total"]["amount"] is None and e["coverage"] == {"included": 0, "unavailable": 1}


def test_unknown_action_form_does_not_break_the_list(api, rw, world, caplog):
    """Сохранённая форма действия вне контракта: у этой карточки action = null (и предупреждение в лог), остальные
    карточки и итог — как обычно; не 500 на весь список."""
    bad = recommendation(rw, world["a1"], f"bad-{world['a1']}", "700.00", action={"type": "pause_campaign"},
                         same_audit=world["rec_a1"])
    token = session(rw, world["owner"])
    r = recs(api, token, world, "a1")
    assert r.status_code == 200
    actions = {i["id"]: i["action"] for i in r.json()["items"]}
    assert actions[f"rec_{bad['rec']}"] is None
    assert actions[f"rec_{world['rec_a1']['rec']}"]["type"] == "lower_cpa"
    assert "action outside contract" in caplog.text
    today = api.get(f"/api/v1/workspaces/ws_{world['a1']}/today", headers=cookie(token))
    assert today.status_code == 200 and today.json()["counts"] == {"active": 2}


def test_card_overlaps_add_up_to_total(api, rw, world):
    """Σ (exposure карточки − её exposure_overlap) = итог exposure (две карточки разных кабинетов не пересекаются)."""
    recommendation(rw, world["a1"], f"second-{world['a1']}", "700.00", same_audit=world["rec_a1"])
    today, items = both(api, rw, world)
    total = sum(float(i["exposure"]["amount"]) - float(i["exposure_overlap"]["amount"]) for i in items)
    assert f"{total:.2f}" == today["exposure"]["total"]["amount"] == "13200.00"


def test_today_data_status_counts_partial_spent(api, rw, world):
    """Карточка — за завершённые дни, а расход «Сегодня» за окно задевает дни досчёта: data_status — partial."""
    today, items = both(api, rw, world)
    assert items[0]["data_status"] == "complete" and today["spent"]["data_status"] == "partial"
    assert today["data_status"] == "partial"


def test_as_of_without_audit_is_moscow_date(api, rw):
    owner = user(rw)
    ws_id = new_workspace(rw, "no-audit", user=owner)
    body = api.get(f"/api/v1/workspaces/ws_{ws_id}/today", headers=cookie(session(rw, owner))).json()
    assert body["exposure"]["total"]["period"]["to"] == today_msk().isoformat()


def test_today_msk_and_status_of():
    late_utc = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)  # в Москве уже 3 октября
    assert today_msk(late_utc) == date(2026, 10, 3) != late_utc.date()
    d = date(2026, 10, 3)
    assert [status_of(e, u, d) for e, u in ((None, None), ("unpostponed", None), ("postponed", "2026-10-04"),
                                            ("postponed", "2026-10-03"), ("rejected", None), ("done", None),
                                            ("checked", None), ("measured", None))] == [
        "new", "new", "postponed", "new", "rejected", "applied", "applied", "applied"]
