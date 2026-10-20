"""Устойчивость клиентов Директа и Метрики: разбор retryIn с потолком, лимит запросов на пользователя, очередь
офлайн-отчётов (≤ 5), предел размера ответа. Сеть — httpx.MockTransport."""

import gzip
from datetime import date

import httpx
import pytest

from app.sources.direct import (CAMPAIGN_REPORT, DEFAULT_RETRY_IN, MAX_RETRY_IN, QUERY_REPORT, DirectApi,
                                DirectApiError, ReportQueue, RetryLater, retry_in)
from app.sources.http import RateLimiter, ResponseTooLarge, read_limited
from app.sources.metrika import MetrikaApi, MetrikaUnavailable

FROM, TO = date(2026, 9, 1), date(2026, 10, 7)


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    """Общие на процесс лимиты — с чистого листа в каждом тесте: иначе тесты ждали бы окно соседей (10 с)."""
    from app.sources import direct as d, metrika as m
    for limiter in (d.DIRECT_RATE, m.METRIKA_RATE):
        monkeypatch.setattr(limiter, "_calls", type(limiter._calls)(limiter._calls.default_factory))
    monkeypatch.setattr(d.REPORT_QUEUE, "_pending", {})


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def direct(handler, *, limiter=None, queue=None, token="y0_T", run_key="1"):
    return DirectApi(httpx.Client(transport=httpx.MockTransport(handler)), token, run_key,
                     limiter=limiter or RateLimiter(1000, 1), queue=queue or ReportQueue())


# --- retryIn --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("30", 30), (" 5 ", 5), ("2.5", 3), (None, DEFAULT_RETRY_IN), ("", DEFAULT_RETRY_IN), ("soon", DEFAULT_RETRY_IN),
    ("0", DEFAULT_RETRY_IN), ("-5", DEFAULT_RETRY_IN), ("nan", DEFAULT_RETRY_IN), ("inf", DEFAULT_RETRY_IN),
    ("1e9", MAX_RETRY_IN), (str(MAX_RETRY_IN + 1), MAX_RETRY_IN),
])
def test_retry_in(raw, expected):
    assert retry_in(httpx.Headers({} if raw is None else {"retryIn": raw})) == expected


def test_garbage_retry_in_on_report_not_ready_is_retry_not_crash():
    api = direct(lambda r: httpx.Response(202, headers={"retryIn": "soon"}))
    with pytest.raises(RetryLater) as e:
        api.fetch_report("client-a", CAMPAIGN_REPORT, None, FROM, TO)
    assert e.value.retry_in == DEFAULT_RETRY_IN and e.value.reason == "report_not_ready"


def test_garbage_retry_in_and_error_code_on_server_error():
    api = direct(lambda r: httpx.Response(503, json={"error": {"error_code": "x"}}, headers={"retryIn": "abc"}))
    with pytest.raises(RetryLater) as e:
        api.fetch_report("client-a", CAMPAIGN_REPORT, None, FROM, TO)
    assert e.value.retry_in == DEFAULT_RETRY_IN and e.value.reason == "api_unavailable"


# --- Лимит запросов на пользователя ---------------------------------------------------------------------

def test_rate_limiter_sliding_window():
    clock = Clock()
    limiter = RateLimiter(3, 10, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire("u1")
    assert clock.slept == []
    limiter.acquire("u2")  # другой пользователь — своё окно
    assert clock.slept == []
    clock.now = 4
    limiter.acquire("u1")  # 4-й за окно: ждём, пока выйдет самый старый (t=0 → t=10)
    assert clock.slept == [6]


def test_direct_requests_go_through_user_limiter():
    clock = Clock()
    limiter = RateLimiter(2, 10, clock=clock, sleep=clock.sleep)
    api = direct(lambda r: httpx.Response(200, text="Date\n"), limiter=limiter)
    for _ in range(3):
        api.fetch_report("client-a", CAMPAIGN_REPORT, None, FROM, TO)
    assert clock.slept == [10]


# --- Очередь офлайн-отчётов -----------------------------------------------------------------------------

def test_report_queue_holds_at_most_five_per_user():
    requests = []

    def building(r):
        requests.append(r)
        return httpx.Response(201, headers={"retryIn": "10"})

    queue = ReportQueue()
    for run in range(5):
        with pytest.raises(RetryLater, match="report_not_ready"):
            direct(building, queue=queue, run_key=str(run)).fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)
    with pytest.raises(RetryLater) as e:  # шестой отчёт того же пользователя в Директ не уходит
        direct(building, queue=queue, run_key="6").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)
    assert e.value.reason == "reports_queue_full" and len(requests) == 5
    with pytest.raises(RetryLater, match="report_not_ready"):  # опрос уже стоящего в очереди — разрешён
        direct(building, queue=queue, run_key="0").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)
    with pytest.raises(RetryLater, match="report_not_ready"):  # другой пользователь (токен) — своя очередь
        direct(building, queue=queue, run_key="7", token="y0_OTHER").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)


def test_report_queue_frees_slot_when_report_is_ready():
    ready = set()

    def handler(r):
        name = __import__("json").loads(r.content)["params"]["ReportName"]
        return httpx.Response(200, text="Date\n") if name in ready else httpx.Response(202)

    queue = ReportQueue(limit=1)
    with pytest.raises(RetryLater):
        direct(handler, queue=queue, run_key="0").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)
    with pytest.raises(RetryLater, match="reports_queue_full"):
        direct(handler, queue=queue, run_key="1").fetch_report("c", QUERY_REPORT, None, FROM, TO)
    ready.add("ai-direct:0:CAMPAIGN_PERFORMANCE_REPORT")
    direct(handler, queue=queue, run_key="0").fetch_report("c", CAMPAIGN_REPORT, None, FROM, TO)  # готов → слот свободен
    with pytest.raises(RetryLater, match="report_not_ready"):
        direct(handler, queue=queue, run_key="1").fetch_report("c", QUERY_REPORT, None, FROM, TO)


def test_report_queue_forgets_abandoned_reports():
    clock = Clock()
    queue = ReportQueue(limit=1, ttl=100, clock=clock)
    queue.waiting("u", "a")
    assert not queue.admit("u", "b")
    clock.now = 101  # синхронизация бросила отчёт (report_timeout) — слот не держится вечно
    assert queue.admit("u", "b")


# --- Размер ответа --------------------------------------------------------------------------------------

def test_read_limited_rejects_large_body_and_declared_length():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 11)))
    with pytest.raises(ResponseTooLarge):
        read_limited(http, "GET", "https://x/", max_bytes=10)
    assert read_limited(http, "GET", "https://x/", max_bytes=11).content == b"x" * 11

    declared = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, headers={"Content-Length": "999999"}, content=b"")))
    with pytest.raises(ResponseTooLarge):
        read_limited(declared, "GET", "https://x/", max_bytes=10)


def test_read_limited_decodes_gzip_once():
    body = "Date\tCost\n2026-10-01\t1.00\n"
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, content=gzip.compress(body.encode()), headers={"Content-Encoding": "gzip", "RequestId": "7"})))
    r = read_limited(http, "GET", "https://x/", max_bytes=1000)
    assert r.text == body and r.headers["RequestId"] == "7"


def test_too_large_direct_report_is_request_error(monkeypatch):
    monkeypatch.setattr("app.sources.direct.MAX_REPORT_BYTES", 10)
    api = direct(lambda r: httpx.Response(200, text="x" * 100))
    with pytest.raises(DirectApiError):  # sync: invalid_request — повтор не поможет, нужен период короче
        api.fetch_report("client-a", CAMPAIGN_REPORT, None, FROM, TO)


def test_too_large_metrika_response(monkeypatch):
    monkeypatch.setattr("app.sources.metrika.MAX_RESPONSE_BYTES", 10)
    api = MetrikaApi(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 100))),
                     "y0_M", limiter=RateLimiter(1000, 1))
    with pytest.raises(MetrikaUnavailable) as e:
        api.fetch_goals(42)
    assert e.value.error_code == "invalid_request"
