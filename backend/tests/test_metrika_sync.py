"""Метрика на fixtures: JSON Reports API → строгий парсер → site_goal → снимок в БД.
Метрика — диагностический источник: её отказ не ломает снимок и CPA из отчёта Директа.
Замороженное определение конверсии: изменение настроек клиента не меняет старые снимки."""

import dataclasses
import json
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.rules import RULES
from app.rules.domain import AuditSettings, Finding, NotEnoughData, Reason, Rule, run
from app.sources.conversion import ConversionDefinition
from app.sources.direct import DirectFixture
from app.sources.metrika import MetrikaFixture, MetrikaReportSpec
from app.sync.metrika_parse import GoalRow, parse_bytime
from app.sync.parse import FormatError, ReportFormatError
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_metrika, to_view, with_metrika
from app.sync.store import load_view, write_snapshot
from test_direct_sync import FROM, GOALS, TO, campaign_tsv, root  # noqa: F401 — root: фикстура
from test_schema import chain, one  # noqa: F401 — chain: фикстура
from test_snapshot_store import DATA_UNTIL, sync_run

DAYS = 37
SPEC = MetrikaReportSpec.for_definition(GOALS, FROM, TO)


def bytime(series: dict[int, list] | None = None, spec=SPEC, sampled=False, intervals=None, **query_overrides) -> str:
    """Ответ /stat/v1/data/bytime без dimensions: одна строка data, по ряду значений на метрику (цель)."""
    series = series if series is not None else {g: [1] * DAYS for g in GOALS.goal_ids}
    days = (spec.date_to - spec.date_from).days + 1
    query = {"ids": [spec.counter_id], "metrics": list(spec.metrics), "dimensions": [],
             "date1": spec.date_from.isoformat(), "date2": spec.date_to.isoformat(), "group": "day",
             "attribution": spec.attribution, **query_overrides}
    return json.dumps({
        "query": query, "sampled": sampled, "total_rows": 1,
        "time_intervals": intervals if intervals is not None else
        [[(spec.date_from + timedelta(i)).isoformat()] * 2 for i in range(days)],
        "data": [{"dimensions": [], "metrics": list(series.values())}] if series else [],
    })


def goals_json(*ids) -> str:
    return json.dumps({"goals": [{"id": i, "name": f"Заявка {i}", "type": "action"} for i in ids]})


@pytest.fixture
def metrika(tmp_path):
    def counter(counter_id=555, goals=(111, 222), report=None, unavailable=None):
        d = tmp_path / "metrika" / str(counter_id)
        d.mkdir(parents=True)
        if unavailable:
            (d / "unavailable").write_text(unavailable, encoding="utf-8")
            return
        (d / "goals.json").write_text(goals_json(*goals), encoding="utf-8")
        (d / "bytime.json").write_text(report if report is not None else bytime(), encoding="utf-8")
    counter.source = lambda: MetrikaFixture(tmp_path / "metrika")
    return counter


def parse(text, spec=SPEC, goals=GOALS.goal_ids):
    return parse_bytime(text, spec, goals)


# --- Нормальный ответ ----------------------------------------------------------------------------

def test_37_days_several_goals(metrika):
    metrika(report=bytime({111: list(range(DAYS)), 222: [0] * DAYS}))
    rows = sync_metrika(metrika.source(), GOALS, FROM, TO)
    assert len(rows) == 2 * DAYS
    assert rows[0] == GoalRow(111, FROM, Decimal(0)) and rows[DAYS - 1] == GoalRow(111, TO, Decimal(36))
    assert {r.conversions for r in rows if r.goal_id == 222} == {Decimal(0)}  # цель без конверсий — данные, не ошибка


def test_no_visits_at_all_is_zero_not_failure(metrika):
    metrika(report=bytime({}))
    rows = sync_metrika(metrika.source(), GOALS, FROM, TO)
    assert len(rows) == 2 * DAYS and all(r.conversions == 0 for r in rows)


def test_several_counters_are_independent(metrika):
    metrika(555, goals=(111, 222))
    other = ConversionDefinition(777, (333,))
    metrika(777, goals=(333,), report=bytime({333: [2] * DAYS}, spec=MetrikaReportSpec.for_definition(other, FROM, TO)))
    assert {r.goal_id for r in sync_metrika(metrika.source(), GOALS, FROM, TO)} == {111, 222}
    assert {r.goal_id for r in sync_metrika(metrika.source(), other, FROM, TO)} == {333}


def test_goal_names_are_not_stored():
    assert [f.name for f in dataclasses.fields(GoalRow)] == ["goal_id", "date", "conversions"]


# --- Ошибки API: синхронизация Метрики не удалась ------------------------------------------------

@pytest.mark.parametrize("setup, code", [
    (dict(goals=(111,)), "goal_not_found"),            # цель 222 удалили в Метрике
    (dict(counter_id=999), "counter_not_found"),         # счётчика 555 нет
    (dict(unavailable="access_denied"), "access_denied"),
    (dict(unavailable="report_unavailable"), "report_unavailable"),
])
def test_api_level_failures(metrika, setup, code):
    metrika(**setup)
    assert sync_metrika(metrika.source(), GOALS, FROM, TO) == SyncFailure("counter:555", code)


# --- Формат ответа: строже Директа ---------------------------------------------------------------

@pytest.mark.parametrize("text, code", [
    ("not json", FormatError.INVALID_JSON),
    (bytime(ids=[777]), FormatError.QUERY_MISMATCH),                                   # ответ другого счётчика
    (bytime(metrics=["ym:s:goal111reaches"]), FormatError.QUERY_MISMATCH),             # не те цели
    (bytime(date1=(FROM + timedelta(1)).isoformat()), FormatError.QUERY_MISMATCH),     # не тот период
    (bytime(group="week"), FormatError.QUERY_MISMATCH),
    (bytime(sampled=True), FormatError.SAMPLED_REPORT),
    (bytime(intervals=[[FROM.isoformat()] * 2]), FormatError.TRUNCATED_ROW),
    (bytime({111: [1] * DAYS, 222: [1] * (DAYS - 1)}), FormatError.TRUNCATED_ROW),
    (bytime({111: [1] * DAYS}), FormatError.MISSING_REQUIRED_COLUMN),                  # пропала метрика цели
    (bytime({111: [1] * DAYS, 222: [None] + [1] * (DAYS - 1)}), FormatError.MISSING_REQUIRED_VALUE),
    (bytime({111: [1] * DAYS, 222: [-1] + [1] * (DAYS - 1)}), FormatError.NEGATIVE_VALUE),
    (bytime({111: [1] * DAYS, 222: ["7"] + [1] * (DAYS - 1)}), FormatError.INVALID_NUMERIC_VALUE),
])
def test_malformed_metrika_reports(text, code):
    with pytest.raises(ReportFormatError) as e:
        parse(text)
    assert e.value.code is code


def test_malformed_report_is_a_sync_failure(metrika):
    metrika(report=bytime(sampled=True))
    assert sync_metrika(metrika.source(), GOALS, FROM, TO) == \
        SyncFailure("counter:555", "invalid_report_format", "sampled_report")


# --- Определение конверсии -----------------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(goal_ids=()), dict(goal_ids=tuple(range(1, 12))), dict(goal_ids=(222, 111)), dict(goal_ids=(111, 111)),
    dict(goal_ids=(111,), attribution="linear"),
    # устаревшие модели: Яндекс подменил бы их другой — снимок записал бы не ту модель
    dict(goal_ids=(111,), attribution="lastsign"), dict(goal_ids=(111,), attribution="last_yandex_direct_click"),
])
def test_invalid_conversion_definition(kwargs):
    with pytest.raises(ValueError):
        ConversionDefinition(counter_id=555, **kwargs)


def test_one_definition_drives_both_requests():
    d = ConversionDefinition(555, (111, 222), "automatic")
    assert d.direct_columns() == ("Conversions_111_AUTO", "Conversions_222_AUTO")
    spec = MetrikaReportSpec.for_definition(d, FROM, TO)
    assert spec.params()["attribution"] == "automatic"
    assert spec.metrics == ("ym:s:goal111reaches", "ym:s:goal222reaches")
    assert ConversionDefinition.from_json(d.to_json()) == d


def test_direct_report_for_other_attribution_is_rejected(root):
    """Отчёт с колонками старой атрибуции не выдаётся за новую: столбцы не совпадают с запросом."""
    root("acc")  # fixture Директа построена для cross_device_last_significant (…_LSCCD)
    changed = dataclasses.replace(GOALS, attribution="automatic")
    assert sync_account(DirectFixture(root.path), "acc", changed, TO) == \
        SyncFailure("acc", "invalid_report_format", "unexpected_column")


# --- Снимок из двух источников -------------------------------------------------------------------

def direct_and_metrika(root, metrika, **counter) -> Snapshot:
    root("acc")
    metrika(**counter)
    direct = sync_account(DirectFixture(root.path), "acc", GOALS, TO)
    return with_metrika(direct, sync_metrika(metrika.source(), GOALS, direct.period_from, direct.period_to))


def audit(view):
    return tuple(out for rule in RULES for out in run(rule, view, AuditSettings()))


METRIKA_RULE = Rule("site_goal_health", 1, "site_goal_health", frozenset({"yandex_metrika"}), {},
                    evaluate=lambda rule, snap, settings: ())


def test_both_sources_are_written_side_by_side(rw, chain, root, metrika):
    snap = direct_and_metrika(root, metrika)
    assert snap.sources == {"yandex_direct", "yandex_metrika"} and not snap.source_failures
    sid = write_snapshot(rw, sync_run_id=sync_run(rw, chain), workspace_id=chain["ws"], release_id=chain["release"],
                         snapshot=snap, data_until=DATA_UNTIL)
    by_source = dict(rw.execute("""SELECT source || ':' || level, count(*) FROM stat_rows WHERE snapshot_id = %s
                                   GROUP BY 1""", (sid,)).fetchall())
    assert by_source["yandex_metrika:site_goal"] == 2 * DAYS
    assert one(rw, """SELECT count(*) FROM stat_rows WHERE snapshot_id = %s AND source = 'yandex_metrika'
                      AND campaign_id IS NOT NULL""", sid) == 0  # цели сайта не привязаны к кампаниям
    view = load_view(rw, sid)
    assert view.sources == {"yandex_direct", "yandex_metrika", "direct_conversions"}
    assert run(METRIKA_RULE, view, AuditSettings()) == ()  # правило, которому нужна Метрика, вычисляется


def test_metrika_failure_keeps_snapshot_and_cpa(rw, chain, root, metrika):
    """Директ есть, Метрика отказала: снимок существует, причина в нём, CPA по отчёту Директа считается,
    правила Метрики — NOT_ENOUGH_DATA."""
    snap = direct_and_metrika(root, metrika, unavailable="access_denied")
    assert snap.sources == {"yandex_direct"} and dict(snap.source_failures) == {"yandex_metrika": "access_denied"}
    sid = write_snapshot(rw, sync_run_id=sync_run(rw, chain), workspace_id=chain["ws"], release_id=chain["release"],
                         snapshot=snap, data_until=DATA_UNTIL)
    assert one(rw, "SELECT source_failures FROM snapshots WHERE id = %s", sid) == {"yandex_metrika": "access_denied"}
    view = load_view(rw, sid)
    (finding,) = audit(view)
    assert isinstance(finding, Finding) and finding.actual == Decimal("5250.00")
    assert run(METRIKA_RULE, view, AuditSettings()) == (NotEnoughData("site_goal_health@1", Reason.SOURCE_MISSING),)


# --- Старое определение конверсии не меняется ----------------------------------------------------

def test_new_settings_do_not_change_old_snapshot(rw, chain, root, metrika):
    """Снимок хранит то, что считалось конверсией тогда. Клиент сменил цели и атрибуцию — старый снимок, его строки
    и аудит по нему прежние; новые настройки действуют только на новые синхронизации."""
    old = direct_and_metrika(root, metrika)
    sid = write_snapshot(rw, sync_run_id=sync_run(rw, chain), workspace_id=chain["ws"], release_id=chain["release"],
                         snapshot=old, data_until=DATA_UNTIL)
    before = (one(rw, "SELECT conversion_definition FROM snapshots WHERE id = %s", sid),
              rw.execute("SELECT * FROM stat_rows WHERE snapshot_id = %s ORDER BY 1, 2, 3, 4, 5, 6",
                         (sid,)).fetchall(),
              audit(load_view(rw, sid)))

    # клиент меняет настройки: другой набор целей и другая атрибуция → новая синхронизация
    new_def = ConversionDefinition(555, (222,), "automatic")
    new_run = sync_run(rw, chain)
    new = dataclasses.replace(old, conversion_definition=new_def, goal_rows=())
    new = dataclasses.replace(new, sources=frozenset({"yandex_direct"}))
    write_snapshot(rw, sync_run_id=new_run, workspace_id=chain["ws"], release_id=chain["release"],
                   snapshot=new, data_until=DATA_UNTIL)

    after = (one(rw, "SELECT conversion_definition FROM snapshots WHERE id = %s", sid),
             rw.execute("SELECT * FROM stat_rows WHERE snapshot_id = %s ORDER BY 1, 2, 3, 4, 5, 6",
                        (sid,)).fetchall(),
             audit(load_view(rw, sid)))
    assert after == before
    assert before[0] == GOALS.to_json()
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):  # и переписать определение нельзя
        rw.execute("UPDATE snapshots SET conversion_definition = %s WHERE id = %s", (Jsonb(new_def.to_json()), sid))


# --- Проверки схемы ------------------------------------------------------------------------------

@pytest.mark.parametrize("sources, definition, failures", [
    ("{yandex_direct,yandex_metrika}", None, {}),                                  # Метрика без определения
    ("{yandex_direct,yandex_metrika}", GOALS.to_json(), {"yandex_metrika": "x"}),  # и данные, и отказ сразу
    ("{yandex_direct}", None, {"yandex_direct": "access_denied"}),                 # отказ Директа — не снимок
    ("{yandex_direct}", {**GOALS.to_json(), "attribution": "linear"}, {}),
    ("{yandex_direct}", {**GOALS.to_json(), "goal_ids": []}, {}),
])
def test_snapshot_source_checks(rw, chain, sources, definition, failures):
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute("""INSERT INTO snapshots (workspace_id, sync_run_id, release_id, period_from, period_to, data_until,
                        partial_from, sources, conversion_definition, source_failures)
                      VALUES (%s, %s, %s, %s, %s, now(), %s, %s, %s, %s)""",
                   (chain["ws"], sync_run(rw, chain), chain["release"], FROM, TO, TO, sources,
                    Jsonb(definition) if definition else None, Jsonb(failures)))
