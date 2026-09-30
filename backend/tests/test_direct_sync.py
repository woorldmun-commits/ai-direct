"""Синхронизация Директа на fixtures: сырой TSV → allowlist-парсер → санитизация → 37-дневный снимок → SnapshotView →
правила → Value. Без сети и без БД."""

import dataclasses
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.audit.values import to_value
from app.contract import Value
from app.rules import RULES
from app.rules.domain import AuditSettings, Finding, NotEnoughData, Reason, run
from app.sources.conversion import ConversionDefinition
from app.sources.direct import CAMPAIGN_REPORT, QUERY_REPORT, REPORT_HEADERS, DirectFixture
from app.sync.parse import FormatError, ReportFormatError, StatRow, parse_report, query_hash
from app.sync.sanitize import sanitize
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_accounts, to_view

TO = date(2026, 9, 30)
FROM = TO - timedelta(36)
GOALS = ConversionDefinition(counter_id=555, goal_ids=(111, 222))
CONV = GOALS.direct_columns()
CID = 12345


def campaign_tsv(days=37, eval_cost="42000.00", eval_conv=("5", "3"), base_cost="115200.00", base_conv=("20", "10"),
                 skip=(), cid=CID, columns=None) -> str:
    """Отчёт кампании в формате Reports API: строка столбцов + строки данных. Нулевые дни Директ не отдаёт —
    поэтому, чтобы задать глубину истории, в первый день кладём 1 показ."""
    columns = columns or CAMPAIGN_REPORT.fields + CONV
    first = TO - timedelta(days - 1)
    rows = {first: ("1", "0", "0.00", ("--",) * len(CONV))}
    rows[TO - timedelta(7)] = ("5000", "700", base_cost, base_conv)
    rows[TO] = ("3000", "300", eval_cost, eval_conv)
    lines = ["\t".join(columns)]
    for d, (impr, clicks, cost, conv) in sorted(rows.items()):
        if d >= first and d not in skip:
            lines.append("\t".join((d.isoformat(), str(cid), impr, clicks, cost, *conv[:len(columns) - 5])))
    return "\n".join(lines) + "\n"


def query_tsv(queries=(("купить диван", "100.00", ("0", "0")),)) -> str:
    """queries: (текст, расход, конверсии по целям[, кампания, день])."""
    lines = ["\t".join(QUERY_REPORT.fields + CONV)]
    for text, cost, conv, *where in queries:
        cid, day = where or (CID, TO)
        lines.append("\t".join((day.isoformat(), str(cid), text, "10", "3", cost, *conv)))
    return "\n".join(lines) + "\n"


@pytest.fixture
def root(tmp_path):
    def account(login, campaign=None, query=None, unavailable=None):
        d = tmp_path / login
        d.mkdir()
        if unavailable:
            (d / "unavailable").write_text(unavailable, encoding="utf-8")
            return
        (d / f"{CAMPAIGN_REPORT.report_type}.tsv").write_text(campaign or campaign_tsv(), encoding="utf-8")
        (d / f"{QUERY_REPORT.report_type}.tsv").write_text(query or query_tsv(), encoding="utf-8")
    account.path = tmp_path
    return account


def snapshot_of(root, **kw) -> Snapshot:
    root("acc", **kw)
    snap = sync_account(DirectFixture(root.path), "acc", GOALS, TO)
    assert isinstance(snap, Snapshot), snap
    return snap


def audit(snap: Snapshot, settings: AuditSettings):
    view = to_view(snap, snapshot_id=84721, workspace_id=7, direct_account_id=3)
    return tuple(out for rule in RULES for out in run(rule, view, settings))


# --- Нормальный аккаунт, 37 дней -----------------------------------------------------------------

def test_normal_account_end_to_end(root):
    snap = snapshot_of(root)
    assert (snap.period_from, snap.period_to, snap.partial_from) == (FROM, TO, TO - timedelta(2))
    assert snap.sources == {"yandex_direct"} and snap.conversion_definition == GOALS
    assert to_view(snap, 1, 7, 3).sources == {"yandex_direct", "direct_conversions"}
    campaign = [r for r in snap.rows if r.level == "campaign"]
    assert [r.date for r in campaign] == [FROM, TO - timedelta(7), TO]
    assert campaign[-1] == StatRow("campaign", CID, TO, 3000, 300, Decimal("42000.00"), Decimal(8))

    (finding,) = audit(snap, AuditSettings())  # пример PRD §4.1 проходит через весь конвейер
    assert (finding.rule_version, finding.actual, finding.reference) == \
        ("high_cpa_baseline@1", Decimal("5250.00"), Decimal("3840.00"))
    values = {name: to_value(fact, 84721, snap.partial_from, finding.rule_version)
              for name, fact in finding.evidence.items()}
    assert all(isinstance(v, Value) for v in values.values())
    assert values["cost"].data_status == "partial"          # оцениваемый период задевает окно дозачёта
    assert values["baseline_cost"].data_status == "complete"


def test_less_than_37_days_of_history(root):
    snap = snapshot_of(root, campaign=campaign_tsv(days=36))
    assert audit(snap, AuditSettings()) == \
        (NotEnoughData("high_cpa_baseline@1", Reason.BASELINE_HISTORY_INSUFFICIENT, "campaign", CID),)


def test_campaign_paused_mid_history_keeps_baseline(root):
    """Дни паузы Директ не отдаёт; пропуск внутри окна — не «новый аккаунт»."""
    snap = snapshot_of(root, campaign=campaign_tsv(skip={TO - timedelta(20)}))
    (finding,) = audit(snap, AuditSettings())
    assert finding.reference_type == "baseline"


def test_zero_conversions_shown_as_dashes(root):
    snap = snapshot_of(root, campaign=campaign_tsv(eval_conv=("--", "--")))
    assert [r.conversions for r in snap.rows if r.level == "campaign" and r.date == TO] == [Decimal(0)]
    assert audit(snap, AuditSettings(target_cpa=Decimal(3000))) == \
        (NotEnoughData("high_cpa_target@1", Reason.NO_CONVERSIONS, "campaign", CID),)


def test_without_metrika_conversions_are_none_and_rules_are_not_computed(root):
    root("acc", campaign=campaign_tsv(columns=CAMPAIGN_REPORT.fields),
         query="\t".join(QUERY_REPORT.fields) + "\n")
    snap = sync_account(DirectFixture(root.path), "acc", None, TO)
    assert snap.sources == {"yandex_direct"} and snap.conversion_definition is None
    assert all(r.conversions is None for r in snap.rows)
    assert audit(snap, AuditSettings()) == (NotEnoughData("high_cpa_baseline@1", Reason.SOURCE_MISSING),)


# --- Несколько аккаунтов и частичная доступность -------------------------------------------------

def test_multiple_client_logins_do_not_mix(root):
    root("alpha", campaign=campaign_tsv(cid=1))
    root("beta", campaign=campaign_tsv(cid=2))
    result = sync_accounts(DirectFixture(root.path), ("alpha", "beta"), GOALS, TO)
    assert {r.campaign_id for r in result["alpha"].rows if r.level == "campaign"} == {1}
    assert {r.campaign_id for r in result["beta"].rows if r.level == "campaign"} == {2}


def test_partially_available_account(root):
    root("alpha")
    root("gone", unavailable="access_denied")
    result = sync_accounts(DirectFixture(root.path), ("alpha", "gone"), GOALS, TO)
    assert isinstance(result["alpha"], Snapshot)
    assert result["gone"] == SyncFailure("gone", "access_denied")


# --- Формат и allowlist --------------------------------------------------------------------------

def test_stored_fields_are_frozen():
    """Новое поле в снимке — только осознанно: тест падает, пока его не добавят в этот список."""
    assert [f.name for f in dataclasses.fields(StatRow)] == \
        ["level", "campaign_id", "date", "impressions", "clicks", "cost", "conversions", "query"]
    assert CAMPAIGN_REPORT.fields == ("Date", "CampaignId", "Impressions", "Clicks", "Cost")
    assert QUERY_REPORT.fields == ("Date", "CampaignId", "Query", "Impressions", "Clicks", "Cost")
    assert GOALS.direct_columns() == ("Conversions_111_LSCCD", "Conversions_222_LSCCD")
    assert REPORT_HEADERS["returnMoneyInMicros"] == "false"


def test_api_payload_with_new_column_is_rejected(root):
    """API вернул столбец, которого мы не запрашивали, — ошибка, а не молчаливое хранение нового поля."""
    text = campaign_tsv(columns=CAMPAIGN_REPORT.fields + CONV + ("AvgCpc",)).replace("\n", "\t1.00\n")
    with pytest.raises(ReportFormatError, match="AvgCpc") as e:
        parse_report(text, CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is FormatError.UNEXPECTED_COLUMN


def test_api_payload_with_missing_column_is_rejected():
    text = campaign_tsv(columns=("Date", "CampaignId", "Impressions", "Clicks") + CONV)
    with pytest.raises(ReportFormatError, match="Cost") as e:
        parse_report(text, CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is FormatError.MISSING_REQUIRED_COLUMN


HEADER = "\t".join(CAMPAIGN_REPORT.fields + CONV)


def test_dashes_in_conversions_mean_zero():
    (row,) = parse_report(f"{HEADER}\n{TO}\t{CID}\t10\t2\t150.00\t--\t1\n", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert (row.cost, row.conversions) == (Decimal("150.00"), Decimal(1))


@pytest.mark.parametrize("column, cells", [
    ("Impressions", "--\t2\t150.00"), ("Clicks", "10\t--\t150.00"), ("Cost", "10\t2\t--"),
])
def test_dashes_in_base_metrics_are_not_silently_zero(column, cells):
    """Отсутствие базовой метрики — не ноль: иначе непроверенное значение стало бы фактом в снимке."""
    with pytest.raises(ReportFormatError, match=column) as e:
        parse_report(f"{HEADER}\n{TO}\t{CID}\t{cells}\t0\t0\n", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is FormatError.MISSING_REQUIRED_VALUE


def test_money_stays_decimal_to_the_cent():
    (row,) = parse_report(f"{HEADER}\n{TO}\t{CID}\t10\t3\t0.10\t0\t0\n", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert isinstance(row.cost, Decimal)
    assert row.cost * 3 == Decimal("0.30")  # во float было бы 0.30000000000000004


@pytest.mark.parametrize("line, code", [
    (f"{TO}\t--\t1\t1\t1.00\t0\t0", FormatError.MISSING_REQUIRED_VALUE),   # без ID объекта строку не сохранить
    (f"{TO}\tabc\t1\t1\t1.00\t0\t0", FormatError.INVALID_NUMERIC_VALUE),
    (f"{TO + timedelta(1)}\t{CID}\t1\t1\t1.00\t0\t0", FormatError.DATE_OUT_OF_RANGE),
    (f"30.09.2026\t{CID}\t1\t1\t1.00\t0\t0", FormatError.INVALID_DATE),
    (f"{TO}\t{CID}\t1\t1\t-5.00\t0\t0", FormatError.NEGATIVE_VALUE),
    (f"{TO}\t{CID}\t1\t1\t1.00\t-1\t0", FormatError.NEGATIVE_VALUE),        # отрицательные конверсии
    (f"{TO}\t{CID}\t1\t1\tabc\t0\t0", FormatError.INVALID_NUMERIC_VALUE),
    (f"{TO}\t{CID}\t1\t1\tNaN\t0\t0", FormatError.INVALID_NUMERIC_VALUE),
    (f"{TO}\t{CID}\t1.5\t1\t1.00\t0\t0", FormatError.INVALID_NUMERIC_VALUE),
    (f"{TO}\t{CID}\t1\t1\t1.00\t0", FormatError.TRUNCATED_ROW),
    (f"{TO}\t{CID}\t1\t1\t1.00\t0\t0\tлишнее", FormatError.EXTRA_CELLS),
])
def test_malformed_rows_have_structured_codes(line, code):
    with pytest.raises(ReportFormatError) as e:
        parse_report(f"{HEADER}\n{line}\n", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is code


def test_empty_response_and_reordered_columns_are_rejected():
    with pytest.raises(ReportFormatError) as e:
        parse_report("", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is FormatError.EMPTY_REPORT
    reordered = "\t".join(("CampaignId", "Date") + CAMPAIGN_REPORT.fields[2:] + CONV)
    with pytest.raises(ReportFormatError) as e:
        parse_report(reordered + "\n", CAMPAIGN_REPORT, GOALS, FROM, TO)
    assert e.value.code is FormatError.COLUMN_ORDER_CHANGED


# --- Санитизация поисковых запросов --------------------------------------------------------------

@pytest.mark.parametrize("raw, clean", [
    ("купить диван", "купить диван"),
    ("купить квартиру", "купить квартиру"),                   # «кв» внутри слова — не маркер
    ("диван +7 916 123-45-67", "диван ***"),
    ("диван 8 (916) 123 45 67 доставка", "диван *** доставка"),
    ("ремонт ivan.petrov@mail.ru", "ремонт ***"),
    ("отзывы https://shop.ru/item?id=5&ref=abc", "отзывы ***"),
    ("заказ 1234567 статус", "заказ *** статус"),
    ("проверка инн 7707083893", "проверка ***"),
    ("доставка ул ленина 5", "доставка ***"),
    ("москва д. 12 кв. 4", "москва ***"),
    ("диван 2024", "диван 2024"),                              # 4 цифры — не идентификатор
])
def test_sanitize(raw, clean):
    assert sanitize(raw) == clean


# --- Зернистость запросов (regression к ключу stat_rows) -----------------------------------------

def query_rows(snap):
    return [(q.campaign_id, q.date, q.query, q.cost) for q in snap.rows if q.level == "query"]


def test_same_query_different_campaigns_is_two_rows(root):
    snap = snapshot_of(root, query=query_tsv((("диван", "100.00", ("0", "0"), 1, TO),
                                              ("диван", "40.00", ("0", "0"), 2, TO))))
    assert query_rows(snap) == [(1, TO, "диван", Decimal("100.00")), (2, TO, "диван", Decimal("40.00"))]


def test_same_query_same_campaign_different_dates_is_two_rows(root):
    day = TO - timedelta(1)
    snap = snapshot_of(root, query=query_tsv((("диван", "100.00", ("0", "0"), CID, day),
                                              ("диван", "40.00", ("0", "0"), CID, TO))))
    assert query_rows(snap) == [(CID, day, "диван", Decimal("100.00")), (CID, TO, "диван", Decimal("40.00"))]


def test_same_query_campaign_date_split_by_hidden_dimension_is_one_row(root):
    """Reports API неявно группирует строки по полям, которых мы не запрашиваем (тип площадки, условие показа):
    одно наблюдение приходит несколькими строками. AdNetworkType не храним — строки складываются в одну,
    а не порождают дубль ключа stat_rows."""
    snap = snapshot_of(root, query=query_tsv((("диван", "100.00", ("1", "0")), ("диван", "40.00", ("0", "1")))))
    (row,) = [r for r in snap.rows if r.level == "query"]
    assert (row.cost, row.clicks, row.impressions, row.conversions) == (Decimal("140.00"), 6, 20, Decimal(2))


def test_queries_are_sanitized_before_snapshot_and_merged(root):
    snap = snapshot_of(root, query=query_tsv((
        ("звонок 8 916 123 45 67", "100.00", ("1", "0")),
        ("звонок 8 903 765 43 21", "50.00", ("0", "0")),
        ("почта a.b@example.ru", "10.00", ("0", "0")),
    )))
    queries = [r for r in snap.rows if r.level == "query"]
    assert [(q.query, q.cost, q.conversions) for q in queries] == \
        [("звонок ***", Decimal("150.00"), Decimal(1)), ("почта ***", Decimal("10.00"), Decimal(0))]
    dump = repr(snap)
    for pii in ("916", "123 45 67", "903", "@example.ru"):
        assert pii not in dump
    assert query_hash("звонок ***") == query_hash(sanitize("звонок 8 916 123 45 67"))


# --- Fact → Value --------------------------------------------------------------------------------

def test_every_finding_fact_converts_to_valid_value(root):
    snap = snapshot_of(root)
    for settings in (AuditSettings(), AuditSettings(target_cpa=Decimal(3000))):
        (finding,) = audit(snap, settings)
        assert isinstance(finding, Finding)
        for fact in (*finding.evidence.values(), finding.lost, finding.recoverable):
            v = to_value(fact, 84721, snap.partial_from, finding.rule_version)
            assert v.amount == fact.amount and v.snapshot_id == 84721
