"""Запись снимка в PostgreSQL и чтение его обратно для аудита (DATA_MODEL.md §3, инвариант 1).

Одна транзакция: snapshot (building) + тексты запросов + stat_rows + snapshot → complete (sealed_at) + sync_run →
succeeded. До COMMIT снимка не видно; после — он complete и запечатан триггерами БД, а не соглашением в коде. Ключ идемпотентности — sync_run: повтор той же задачи
(retryIn, перезапуск воркера) возвращает уже записанный снимок. Досинхронизация в 14:00 — новый sync_run и новый снимок."""

from datetime import date, datetime

import psycopg
from psycopg.types.json import Jsonb

from app.rules.domain import CampaignDay, PlacementDay, SnapshotView
from app.sync.parse import PlacementRow, placement_id, query_hash
from app.sync.sanitize import MASK
from app.sync.snapshot import Snapshot, SyncFailure, capabilities

MASK_PLACEMENT_ID = placement_id(MASK)  # безымянная площадка: имени в справочнике нет и не будет


class SnapshotNotComplete(LookupError):
    """Снимка нет или он не завершён: аудит по нему не строится."""


class SyncRunStateError(RuntimeError):
    """sync_run не в состоянии, из которого можно записать результат (уже failed, чужой workspace, не существует)."""


def _existing(conn: psycopg.Connection, sync_run_id: int) -> int | None:
    row = conn.execute("SELECT id FROM snapshots WHERE sync_run_id = %s", (sync_run_id,)).fetchone()
    return row[0] if row else None


def _store_queries(conn: psycopg.Connection, workspace_id: int, last_seen: dict[str, date]) -> dict[str, int]:
    """Тексты запросов (уже санитизированы) → id. Появление записывается датой последнего дня, когда запрос был
    в отчёте, а не временем синхронизации: иначе запрос, встреченный 36 дней назад, продлевался бы каждой
    синхронизацией, и 60 дней хранения (ARCHITECTURE.md §2.4) превращались бы в 97.

    Порядок вставки — по хэшу: параллельные синхронизации одного workspace берут блокировки строк в одном
    порядке и не упираются в deadlock."""
    if not last_seen:
        return {}
    hashes = dict(sorted((query_hash(t), t) for t in last_seen))
    with conn.cursor() as cur:
        cur.executemany("""INSERT INTO search_query_texts (workspace_id, text_hash, text_sanitized) VALUES (%s, %s, %s)
                           ON CONFLICT (workspace_id, text_hash) DO NOTHING""",
                        [(workspace_id, h, t) for h, t in hashes.items()])
        rows = cur.execute("SELECT id, text_hash FROM search_query_texts WHERE workspace_id = %s AND text_hash = ANY(%s)",
                           (workspace_id, list(hashes))).fetchall()
        ids = {hashes[bytes(h)]: i for i, h in rows}
        cur.executemany("""INSERT INTO search_query_sightings (query_id, seen_on) VALUES (%s, %s)
                           ON CONFLICT DO NOTHING""",
                        sorted((ids[t], last_seen[t]) for t in ids))
    return ids


def _store_placement_names(conn: psycopg.Connection, workspace_id: int, rows) -> None:
    """Справочник имён площадок своего workspace (placement_names, под RLS): id = хэш имени, имя — нормализованный
    домен/приложение, не ПД. Только добавление: ON CONFLICT DO NOTHING — имя по id не меняется. Порядок вставки —
    по id, как у запросов: параллельные синхронизации не упираются в deadlock. Маска «***» не пишется."""
    names = sorted({placement_id(r.placement): r.placement for r in rows
                    if isinstance(r, PlacementRow) and r.placement != MASK}.items())
    if names:
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO placement_names (workspace_id, id, name) VALUES (%s, %s, %s)
                               ON CONFLICT (workspace_id, id) DO NOTHING""",
                            [(workspace_id, i, n) for i, n in names])


def write_snapshot(conn: psycopg.Connection, *, sync_run_id: int, workspace_id: int, release_id: int,
                   snapshot: Snapshot, data_until: datetime) -> int:
    if (existing := _existing(conn, sync_run_id)) is not None:
        return existing
    try:
        with conn.transaction():
            # запуск должен быть в работе; FOR UPDATE заодно выстраивает параллельные дубли одной задачи в очередь
            run = conn.execute("SELECT status FROM sync_runs WHERE id = %s AND workspace_id = %s FOR UPDATE",
                               (sync_run_id, workspace_id)).fetchone()
            if run is None or run[0] not in ("running", "waiting_report"):
                if (existing := _existing(conn, sync_run_id)) is not None:
                    return existing  # дубль дождался блокировки, а снимок уже записан
                raise SyncRunStateError(f"sync_run {sync_run_id}: нельзя записать снимок")
            snapshot_id = conn.execute(
                """INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to, data_until,
                                          partial_from, sources, conversion_definition, source_failures)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (workspace_id, sync_run_id, release_id, snapshot.period_from, snapshot.period_to, data_until,
                 snapshot.partial_from, sorted(snapshot.sources),
                 Jsonb(snapshot.conversion_definition.to_json()) if snapshot.conversion_definition else None,
                 Jsonb(dict(snapshot.source_failures)))).fetchone()[0]
            last_seen: dict[str, date] = {}
            for r in snapshot.rows:
                if r.query is not None:
                    last_seen[r.query] = max(r.date, last_seen.get(r.query, r.date))
            query_ids = _store_queries(conn, workspace_id, last_seen)
            _store_placement_names(conn, workspace_id, snapshot.rows)
            # COPY прямо в таблицу под RLS PostgreSQL не умеет: быстрый COPY во временную таблицу транзакции,
            # затем INSERT … SELECT — он проходит политику RLS (строки только своего снимка) и триггеры stat_rows.
            conn.execute("DROP TABLE IF EXISTS pg_temp.stat_rows_load")  # второй снимок в той же внешней транзакции
            conn.execute("""CREATE TEMP TABLE stat_rows_load (
                              snapshot_id bigint, source text, level text, object_id bigint, campaign_id bigint,
                              date date, impressions bigint, clicks bigint, cost numeric(14, 2),
                              conversions numeric(12, 2)) ON COMMIT DROP""")
            with conn.cursor().copy("""COPY stat_rows_load (snapshot_id, source, level, object_id, campaign_id, date,
                                         impressions, clicks, cost, conversions) FROM STDIN""") as copy:
                for r in snapshot.rows:
                    if r.level == "query":
                        object_id = query_ids[r.query]
                    elif isinstance(r, PlacementRow):  # в stat_rows — только хэш-ID; имя — в placement_names
                        object_id = placement_id(r.placement)
                    else:
                        object_id = r.campaign_id
                    copy.write_row((snapshot_id, "yandex_direct", r.level, object_id, r.campaign_id, r.date,
                                    r.impressions, r.clicks, r.cost, r.conversions))
                for g in snapshot.goal_rows:  # цель сайта: вне кампаний, только достижения
                    copy.write_row((snapshot_id, "yandex_metrika", "site_goal", g.goal_id, None, g.date,
                                    0, 0, 0, g.conversions))
            cols = "snapshot_id, source, level, object_id, campaign_id, date, impressions, clicks, cost, conversions"
            conn.execute(f"INSERT INTO stat_rows ({cols}) SELECT {cols} FROM stat_rows_load")
            conn.execute("UPDATE snapshots SET status = 'complete', sealed_at = now() WHERE id = %s", (snapshot_id,))
            done = conn.execute("""UPDATE sync_runs SET status = 'succeeded', finished_at = now()
                                   WHERE id = %s AND workspace_id = %s AND status IN ('running', 'waiting_report')""",
                                (sync_run_id, workspace_id))
            if done.rowcount != 1:
                raise SyncRunStateError(f"sync_run {sync_run_id}: нельзя записать снимок")
        return snapshot_id
    except psycopg.errors.UniqueViolation:
        # параллельный повтор той же задачи успел записать снимок первым — это тот же логический результат
        if (existing := _existing(conn, sync_run_id)) is None:
            raise
        return existing


def record_failure(conn: psycopg.Connection, sync_run_id: int, failure: SyncFailure) -> None:
    done = conn.execute("""UPDATE sync_runs SET status = 'failed', finished_at = now(), error_code = %s, error_reason = %s,
                                  provider_request_id = %s
                           WHERE id = %s AND status IN ('queued', 'running', 'waiting_report')""",
                        (failure.error_code, failure.reason, failure.request_id, sync_run_id))
    if done.rowcount != 1:
        raise SyncRunStateError(f"sync_run {sync_run_id}: уже завершён")


def load_view(conn: psycopg.Connection, snapshot_id: int) -> SnapshotView:
    """Снимок из БД → вход правил. Тот же вид, что to_view() из памяти: аудит не зависит от того, откуда снимок."""
    row = conn.execute(
        """SELECT s.workspace_id, r.direct_account_id, s.period_from, s.period_to, s.partial_from, s.sources,
                  s.conversion_definition IS NOT NULL
           FROM snapshots s JOIN sync_runs r ON r.id = s.sync_run_id
           WHERE s.id = %s AND s.status = 'complete'""", (snapshot_id,)).fetchone()
    if row is None:
        raise SnapshotNotComplete(snapshot_id)
    ws, account, period_from, period_to, partial_from, sources, has_conversions = row
    days = conn.execute("""SELECT campaign_id, date, cost, clicks, conversions FROM stat_rows
                           WHERE snapshot_id = %s AND level = 'campaign' ORDER BY campaign_id, date""",
                        (snapshot_id,)).fetchall()
    # Имя площадки — из справочника placement_names своего workspace (LEFT JOIN: нет строки — имя неизвестно, None;
    # правило всё равно видит площадку по id). Безымянная (MASK) в справочник не пишется — её узнаём по id, чтобы не
    # предложить исключить площадку, которую человек не найдёт.
    placements = conn.execute("""SELECT r.campaign_id, r.object_id, r.date, r.cost, r.clicks, r.conversions, n.name
                                 FROM stat_rows r LEFT JOIN placement_names n ON n.workspace_id = %s AND n.id = r.object_id
                                 WHERE r.snapshot_id = %s AND r.source = 'yandex_direct' AND r.level = 'placement'
                                 ORDER BY r.campaign_id, r.date, r.object_id""", (ws, snapshot_id)).fetchall()
    placement_days = tuple(PlacementDay(*p[:6], MASK if p[6] is None and p[1] == MASK_PLACEMENT_ID else p[6])
                           for p in placements)
    return SnapshotView(snapshot_id, ws, account, period_from, period_to,
                        capabilities(frozenset(sources), has_conversions), tuple(CampaignDay(*d) for d in days),
                        placement_days=placement_days, partial_from=partial_from)
