"""Площадки РСЯ: запрос CUSTOM_REPORT (только сети) → allowlist-парсер → нормализация имени → агрегация →
снимок (stat_rows level = placement, object_id = хэш имени) → SnapshotView. Сеть подменена httpx.MockTransport,
ответы — в формате Reports API (TSV со строкой столбцов). Без сети."""

import dataclasses
import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from app.sources.direct import (CAMPAIGN_REPORT, PLACEMENT_REPORT, QUERY_REPORT, DirectApi, DirectFixture,
                                RetryLater)
from app.sync.parse import FormatError, PlacementRow, ReportFormatError, StatRow, parse_report, placement_id
from app.sync.sanitize import MASK, sanitize_placement
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, to_view
from app.sync.store import load_view, write_snapshot
from test_direct_sync import CID, CONV, GOALS, TO, campaign_tsv, query_tsv, root  # noqa: F401 — root: фикстура
from test_schema import chain, one  # noqa: F401 — chain: фикстура
from test_snapshot_store import DATA_UNTIL, sync_run

FROM = TO - timedelta(36)


def placement_tsv(rows=(("avito.ru", "40", "1200.00", ("0", "0")),), conv=True) -> str:
    """rows: (площадка, клики, расход, конверсии по целям[, кампания, день[, тип сети]])."""
    lines = ["\t".join(PLACEMENT_REPORT.fields + (CONV if conv else ()))]
    for name, clicks, cost, conversions, *where in rows:
        cid, day, network = (list(where) + [CID, TO, "AD_NETWORK"][len(where):])
        lines.append("\t".join((day.isoformat(), str(cid), network, name, "1000", clicks, cost,
                                *(conversions if conv else ()))))
    return "\n".join(lines) + "\n"


def parse(text, conversions=GOALS):
    return parse_report(text, PLACEMENT_REPORT, conversions, FROM, TO)


# --- Allowlist и форма отчёта --------------------------------------------------------------------------

def test_placement_fields_are_frozen():
    """Новое поле площадки в снимке — только осознанно: тест падает, пока его не добавят сюда."""
    assert [f.name for f in dataclasses.fields(PlacementRow)] == \
        ["level", "campaign_id", "date", "impressions", "clicks", "cost", "conversions", "query", "placement"]
    assert PLACEMENT_REPORT.fields == ("Date", "CampaignId", "AdNetworkType", "Placement", "Impressions", "Clicks",
                                       "Cost")
    assert (PLACEMENT_REPORT.report_type, PLACEMENT_REPORT.level, PLACEMENT_REPORT.key) == \
        ("CUSTOM_REPORT", "placement", "PLACEMENT_REPORT")
    assert PLACEMENT_REPORT.filters == (("AdNetworkType", "EQUALS", ("AD_NETWORK",)),)
    assert (CAMPAIGN_REPORT.key, QUERY_REPORT.key) == ("CAMPAIGN_PERFORMANCE_REPORT", "SEARCH_QUERY_PERFORMANCE_REPORT")


def fake_api(handler, run_key="42"):
    return DirectApi(httpx.Client(transport=httpx.MockTransport(handler)), "y0_TOKEN", run_key)


def test_request_shape_network_only_with_conversions():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=placement_tsv())
    fake_api(handler).fetch_report("client-a", PLACEMENT_REPORT, GOALS, FROM, TO)
    (req,) = requests
    body = json.loads(req.content)["params"]
    assert req.headers["returnMoneyInMicros"] == "false" and req.headers["Client-Login"] == "client-a"
    assert body == {
        "SelectionCriteria": {"DateFrom": FROM.isoformat(), "DateTo": TO.isoformat(),
                              "Filter": [{"Field": "AdNetworkType", "Operator": "EQUALS", "Values": ["AD_NETWORK"]}]},
        "FieldNames": ["Date", "CampaignId", "AdNetworkType", "Placement", "Impressions", "Clicks", "Cost",
                       "Conversions"],
        "ReportName": "ai-direct:42:PLACEMENT_REPORT", "ReportType": "CUSTOM_REPORT",
        "DateRangeType": "CUSTOM_DATE", "Format": "TSV", "IncludeVAT": "YES",
        "Goals": ["111", "222"], "AttributionModels": ["LSCCD"],
    }


def test_campaign_report_request_unchanged():
    """Отчёт кампаний не получил ни фильтра, ни нового имени."""
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content)["params"])
        return httpx.Response(200, text=campaign_tsv())
    fake_api(handler).fetch_report("c", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert bodies[0]["SelectionCriteria"] == {"DateFrom": FROM.isoformat(), "DateTo": TO.isoformat()}
    assert bodies[0]["ReportName"] == "ai-direct:42:CAMPAIGN_PERFORMANCE_REPORT"


def test_placement_report_offline_wait():
    with pytest.raises(RetryLater) as e:
        fake_api(lambda r: httpx.Response(202, headers={"retryIn": "30"})).fetch_report(
            "c", PLACEMENT_REPORT, GOALS, FROM, TO)
    assert e.value.retry_in == 30


# --- Разбор ---------------------------------------------------------------------------------------------

def test_parse_placement_rows():
    (row,) = parse(placement_tsv((("Avito.ru", "40", "1200.50", ("1", "--")),)))
    assert row == PlacementRow("placement", CID, TO, 1000, 40, Decimal("1200.50"), Decimal(1), placement="avito.ru")
    assert isinstance(row, StatRow) and row.query is None


def test_search_row_in_network_report_is_rejected():
    """Фильтр «только сети» не сработал — ошибка формата, а не поисковые строки в данных площадок."""
    with pytest.raises(ReportFormatError) as e:
        parse(placement_tsv((("yandex.ru", "5", "10.00", ("0", "0"), CID, TO, "SEARCH"),)))
    assert e.value.code is FormatError.UNEXPECTED_VALUE


@pytest.mark.parametrize("text, code", [
    ("\t".join(PLACEMENT_REPORT.fields) + "\n", FormatError.MISSING_REQUIRED_COLUMN),   # нет столбцов конверсий
    ("\t".join(PLACEMENT_REPORT.fields + CONV + ("PlacementType",)) + "\n", FormatError.UNEXPECTED_COLUMN),
    (placement_tsv((("avito.ru", "--", "1.00", ("0", "0")),)), FormatError.MISSING_REQUIRED_VALUE),
    (placement_tsv((("avito.ru", "1", "-1.00", ("0", "0")),)), FormatError.NEGATIVE_VALUE),
])
def test_malformed_placement_report(text, code):
    with pytest.raises(ReportFormatError) as e:
        parse(text)
    assert e.value.code is code


def test_empty_placement_report_is_valid():
    """Аккаунт без сетей: строка столбцов без данных — это ноль площадок, не ошибка."""
    assert parse(placement_tsv(())) == ()


# --- Нормализация имени площадки ------------------------------------------------------------------------

@pytest.mark.parametrize("raw, clean", [
    ("avito.ru", "avito.ru"),
    ("WWW.Avito.RU.", "avito.ru"),
    ("  dzen.ru ", "dzen.ru"),
    ("com.avito.android", "com.avito.android"),       # приложение — bundle id
    ("id1234567890", "id1234567890"),                  # приложение App Store
    ("сайт.рф", "сайт.рф"),
    ("ｍａｉｌ．ｒｕ", "mail.ru"),                       # полноширинные символы → NFKC
    ("--", MASK),                                      # Reports API: значения нет
    ("", MASK),
    ("ivan@mail.ru", MASK),
    ("https://site.ru/?utm=1", MASK),
    ("site.ru/page", MASK),
    ("Иван Петров", MASK),                             # не домен и не приложение
    ("89161234567", MASK),                             # только цифры — похоже на телефон
    ("a" * 254, MASK),
    ("a..ru", MASK),
])
def test_sanitize_placement(raw, clean):
    assert sanitize_placement(raw) == clean


def test_placement_id_is_stable_positive_bigint():
    pid = placement_id("avito.ru")
    assert pid == placement_id("avito.ru") != placement_id("dzen.ru")
    assert 0 <= pid < 2 ** 63


# --- Снимок ---------------------------------------------------------------------------------------------

def write_placements(root, login, text):
    root(login)
    (root.path / login / f"{PLACEMENT_REPORT.key}.tsv").write_text(text, encoding="utf-8")


def placement_rows(snap):
    return [(r.campaign_id, r.date, r.placement, r.clicks, r.cost, r.conversions)
            for r in snap.rows if r.level == "placement"]


def test_placements_off_by_default(root):
    """Без явного включения третий отчёт не запрашивается: существующая синхронизация не меняется."""
    root("acc")
    snap = sync_account(DirectFixture(root.path), "acc", GOALS, TO)
    assert isinstance(snap, Snapshot) and not placement_rows(snap)


def test_normalized_duplicates_are_merged_and_kept_per_campaign_and_day(root):
    day = TO - timedelta(1)
    write_placements(root, "acc", placement_tsv((
        ("www.avito.ru", "10", "100.00", ("0", "0")),
        ("Avito.ru", "5", "50.00", ("1", "0")),           # та же площадка после нормализации
        ("avito.ru", "7", "70.00", ("0", "0"), 2, TO),    # другая кампания — другая строка
        ("avito.ru", "3", "30.00", ("0", "0"), CID, day),  # другой день — другая строка
        ("bad name", "1", "1.00", ("0", "0")),
        ("evil@x.ru", "2", "2.00", ("0", "0")),           # безымянные склеиваются в одну строку MASK
    )))
    snap = sync_account(DirectFixture(root.path), "acc", GOALS, TO, placements=True)
    assert placement_rows(snap) == [
        (2, TO, "avito.ru", 7, Decimal("70.00"), Decimal(0)),
        (CID, day, "avito.ru", 3, Decimal("30.00"), Decimal(0)),
        (CID, TO, MASK, 3, Decimal("3.00"), Decimal(0)),
        (CID, TO, "avito.ru", 15, Decimal("150.00"), Decimal(1)),
    ]
    assert "bad name" not in repr(snap) and "evil" not in repr(snap)
    view = to_view(snap, 1, 7, 3)
    assert [(d.campaign_id, d.date, d.placement) for d in view.placement_days] == \
        sorted([(CID, day, "avito.ru"), (CID, TO, MASK), (CID, TO, "avito.ru"), (2, TO, "avito.ru")],
               key=lambda x: (x[0], x[1], placement_id(x[2])))
    assert all(d.placement_id == placement_id(d.placement) for d in view.placement_days)
    assert view.partial_from == snap.partial_from


def test_broken_placement_report_fails_sync(root):
    write_placements(root, "acc", placement_tsv((("x.ru", "1", "1.00", ("0", "0"), CID, TO, "SEARCH"),)))
    assert sync_account(DirectFixture(root.path), "acc", GOALS, TO, placements=True) == \
        SyncFailure("acc", "invalid_report_format", "unexpected_value")


def test_sync_through_api_requests_three_reports():
    seen = []

    def handler(request):
        body = json.loads(request.content)["params"]
        seen.append(body["ReportName"])
        text = {"CAMPAIGN_PERFORMANCE_REPORT": campaign_tsv(), "SEARCH_QUERY_PERFORMANCE_REPORT": query_tsv(),
                "CUSTOM_REPORT": placement_tsv()}[body["ReportType"]]
        return httpx.Response(200, text=text)
    snap = sync_account(fake_api(handler, "7"), "client-a", GOALS, TO, placements=True)
    assert seen == ["ai-direct:7:CAMPAIGN_PERFORMANCE_REPORT", "ai-direct:7:SEARCH_QUERY_PERFORMANCE_REPORT",
                    "ai-direct:7:PLACEMENT_REPORT"]
    assert placement_rows(snap) == [(CID, TO, "avito.ru", 40, Decimal("1200.00"), Decimal(0))]


# --- Запись в БД и чтение для аудита --------------------------------------------------------------------

def test_write_and_load_placements(rw, chain, root):
    write_placements(root, "acc", placement_tsv((("avito.ru", "40", "1200.00", ("0", "0")),
                                                 ("dzen.ru", "9", "90.00", ("0", "1")))))
    snap = sync_account(DirectFixture(root.path), "acc", GOALS, TO, placements=True)
    run_id = sync_run(rw, chain)
    snapshot_id = write_snapshot(rw, sync_run_id=run_id, workspace_id=chain["ws"], release_id=chain["release"],
                                 snapshot=snap, data_until=DATA_UNTIL)
    stored = rw.execute("""SELECT object_id, campaign_id, clicks, cost FROM stat_rows
                           WHERE snapshot_id = %s AND level = 'placement' ORDER BY clicks""",
                        (snapshot_id,)).fetchall()
    assert stored == [(placement_id("dzen.ru"), CID, 9, Decimal("90.00")),
                      (placement_id("avito.ru"), CID, 40, Decimal("1200.00"))]
    loaded = load_view(rw, snapshot_id)
    expected = to_view(snap, snapshot_id, chain["ws"], chain["account"])
    # из БД имён нет (справочник имён площадок — отдельный DDL), остальное совпадает
    assert loaded == dataclasses.replace(
        expected, placement_days=tuple(dataclasses.replace(d, placement=None) for d in expected.placement_days))
    assert loaded.partial_from == snap.partial_from
