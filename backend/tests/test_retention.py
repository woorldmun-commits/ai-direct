"""Срок хранения текстов поисковых запросов: 60 дней от последнего появления в отчёте.
Удаляется только текст; снимок и агрегаты stat_rows остаются. Повторный запуск безопасен."""

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest

from app.worker.retention import purge_personal_data, purge_search_queries, retention_cutoff
from test_schema import chain, key, one  # noqa: F401 — chain: фикстура

TODAY = date(2026, 9, 30)
CUTOFF = TODAY - timedelta(days=60)


def query_seen(rw, chain, text, *days_ago) -> int:
    """Текст запроса с появлениями N дней назад (последнее — минимальное N)."""
    qid = one(rw, "INSERT INTO search_query_texts (workspace_id, text_hash, text_sanitized) VALUES (%s, %s, %s) "
                  "RETURNING id", chain["ws"], key(text, chain["ws"]), text)
    for d in days_ago:
        rw.execute("INSERT INTO search_query_sightings (query_id, seen_on) VALUES (%s, %s)", (qid, TODAY - timedelta(d)))
    return qid


def exists(rw, qid) -> bool:
    return one(rw, "SELECT count(*) FROM search_query_texts WHERE id = %s", qid) == 1


@pytest.fixture
def deleter(db):
    with db("app_deleter") as conn:
        yield conn


@pytest.mark.parametrize("days_ago, kept", [(59, True), (60, True), (61, False)])
def test_boundary(rw, chain, deleter, days_ago, kept):
    """Встреченный 59 и 60 дней назад — хранится; 61 день назад — удаляется."""
    qid = query_seen(rw, chain, f"граница {days_ago}", days_ago)
    purge_search_queries(deleter, cutoff=CUTOFF)
    assert exists(rw, qid) is kept


def test_last_occurrence_counts_not_first(rw, chain, deleter):
    """Запрос встречался 90 дней назад и вчера — срок считается от вчера."""
    qid = query_seen(rw, chain, "давний и свежий", 90, 1)
    purge_search_queries(deleter, cutoff=CUTOFF)
    assert exists(rw, qid)


def test_purge_keeps_snapshot_and_aggregates(rw, chain, deleter):
    qid = query_seen(rw, chain, "только текст", 70)
    with rw.transaction():
        sync = one(rw, "INSERT INTO sync_runs (workspace_id, direct_account_id, kind, status) "
                       "VALUES (%s, %s, 'resync', 'running') RETURNING id", chain["ws"], chain["account"])
        snap = one(rw, """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to,
                            data_until, partial_from, sources)
                          VALUES (%s, %s, %s, '2026-06-15', '2026-07-21', now(), '2026-07-19', '{yandex_direct}')
                          RETURNING id""", chain["ws"], sync, chain["release"])
        rw.execute("""INSERT INTO stat_rows (snapshot_id, source, level, object_id, campaign_id, date, clicks, cost)
                      VALUES (%s, 'yandex_direct', 'query', %s, 1, '2026-07-21', 12, 900)""", (snap, qid))
        rw.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (snap,))
    assert purge_search_queries(deleter, cutoff=CUTOFF) >= 1
    assert not exists(rw, qid)
    assert one(rw, "SELECT status FROM snapshots WHERE id = %s", snap) == "complete"
    assert one(rw, "SELECT cost FROM stat_rows WHERE snapshot_id = %s AND object_id = %s", snap, qid) == 900


def test_repeated_purge_is_safe_and_batched(rw, chain, deleter):
    ids = [query_seen(rw, chain, f"старый {i}", 100) for i in range(7)]
    assert purge_search_queries(deleter, cutoff=CUTOFF, batch_size=3) >= 7   # 3 + 3 + 1 — несколько транзакций
    assert purge_search_queries(deleter, cutoff=CUTOFF) == 0                  # повтор — без ошибок и без удалений
    assert not any(exists(rw, i) for i in ids)
    log = rw.execute("""SELECT verification FROM deletion_requests WHERE requested_by = 'system:retention'
                        AND scope = 'search_query_texts_expired' ORDER BY id DESC LIMIT 3""").fetchall()
    assert [v[0]["cutoff"] for v in log] == [CUTOFF.isoformat()] * 3             # каждая пачка — запись удаления


def test_cutoff_is_computed_in_data_timezone():
    """23:30 UTC 29-го — это уже 30-е в Москве: отсечение считается от московской даты, а не от UTC сервера."""
    assert retention_cutoff(datetime(2026, 9, 29, 23, 30, tzinfo=timezone.utc)) == CUTOFF
    with pytest.raises(ValueError):
        retention_cutoff(datetime(2026, 9, 30, 12, 0))


def test_app_role_cannot_purge(rw):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("SELECT purge_search_query_texts(%s, 100)", (CUTOFF,))


def test_text_seen_again_by_running_sync_is_kept_and_purge_does_not_wait(rw, db, chain, deleter):
    """Синхронизация (ещё не закоммичена) снова встретила старый запрос: его текст не удаляется, а очистка не ждёт
    её и не падает — остальное удаляет."""
    seen_again = query_seen(rw, chain, "снова встретился", 90)
    gone = query_seen(rw, chain, "давно не встречался", 90)
    with db("app_rw") as sync:
        sync.autocommit = False
        sync.execute("INSERT INTO search_query_sightings (query_id, seen_on) VALUES (%s, %s)", (seen_again, TODAY))
        deleter.execute("SET lock_timeout = '2s'")
        purge_search_queries(deleter, cutoff=CUTOFF)
        sync.commit()
    assert exists(rw, seen_again) and not exists(rw, gone)


# --- Персональные данные вне workspace: сессии и деактивированные пользователи — 30 дней ----------

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def user(rw, email, deactivated_days_ago=None) -> int:
    at = NOW - timedelta(days=deactivated_days_ago) if deactivated_days_ago is not None else None
    uid = one(rw, "INSERT INTO users (email, status, deactivated_at) VALUES (%s, %s, %s) RETURNING id",
              email, "deactivated" if at else "active", at)
    rw.execute("INSERT INTO yandex_identities (user_id, yandex_uid, login) VALUES (%s, %s, %s)",
               (uid, f"uid-{email}", f"login-{email}"))
    return uid


def session(rw, user_id, *, ended_days_ago, revoked=False) -> bytes:
    """Сессия, закончившаяся N дней назад: истекла или (revoked) отозвана при ещё действующем сроке."""
    ended = NOW - timedelta(days=ended_days_ago)
    token = key("session", user_id, ended_days_ago, revoked)
    rw.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, revoked_at) VALUES (%s, %s, %s, %s, %s)",
               (token, user_id, ended - timedelta(days=60),
                ended + timedelta(days=365) if revoked else ended, ended if revoked else None))
    return token


def session_exists(rw, token) -> bool:
    return one(rw, "SELECT count(*) FROM sessions WHERE token_hash = %s", token) == 1


def personal(rw, uid):
    return rw.execute("SELECT u.email, i.login, i.yandex_uid FROM users u JOIN yandex_identities i ON i.user_id = u.id "
                      "WHERE u.id = %s", (uid,)).fetchone()


def test_sessions_are_deleted_30_days_after_they_ended(rw, deleter):
    uid = user(rw, "s@x.ru")
    old, recent, revoked, active = (session(rw, uid, ended_days_ago=31), session(rw, uid, ended_days_ago=29),
                                    session(rw, uid, ended_days_ago=31, revoked=True),
                                    session(rw, uid, ended_days_ago=-10))
    assert purge_personal_data(deleter, now=NOW) >= 2
    assert [session_exists(rw, t) for t in (old, recent, revoked, active)] == [False, True, False, True]


def test_deactivated_user_is_depersonalised_after_30_days(rw, deleter):
    gone, recent, active = user(rw, "gone@x.ru", 31), user(rw, "recent@x.ru", 29), user(rw, "active@x.ru")
    purge_personal_data(deleter, now=NOW)
    # yandex_uid остаётся: по нему деактивированный не войдёт снова под тем же аккаунтом Яндекса
    assert personal(rw, gone) == ("", "", "uid-gone@x.ru")
    assert personal(rw, recent) == ("recent@x.ru", "login-recent@x.ru", "uid-recent@x.ru")
    assert personal(rw, active)[0] == "active@x.ru"
    assert one(rw, "SELECT count(*) FROM deletion_requests WHERE scope = 'personal_data_expired'") >= 1
    assert purge_personal_data(deleter, now=NOW) == 0  # повтор безопасен


def test_app_role_cannot_purge_personal_data(rw):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("SELECT purge_personal_data(%s)", (NOW,))
