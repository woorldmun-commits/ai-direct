"""Повреждённые ответы Яндекса (Директ, OAuth) превращаются в ошибки источника, а не в падения или «вечные» паузы."""

from datetime import timedelta

import httpx
import pytest

from app.auth.yandex_oauth import MAX_TOKEN_LIFETIME, OAuthError, refresh
from app.sources.campaigns import get_campaign_contexts
from app.sources.direct import (DEFAULT_RETRY_IN, MAX_RETRY_IN, DirectApiError, RetryLater, raise_for_direct_error,
                                retry_interval)
from test_direct_api import FakeReports, api
from test_login import APP, NOW


def client(status, json=None, headers=None):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=json, headers=headers)))


# --- Директ: retryIn и код ошибки ------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("17", 17), (None, DEFAULT_RETRY_IN), ("", DEFAULT_RETRY_IN), ("0", DEFAULT_RETRY_IN), ("-5", DEFAULT_RETRY_IN),
    ("1.5", DEFAULT_RETRY_IN), ("abc", DEFAULT_RETRY_IN), ("9" * 50, MAX_RETRY_IN), (str(MAX_RETRY_IN + 1), MAX_RETRY_IN),
])
def test_retry_interval_is_positive_and_bounded(raw, expected):
    assert retry_interval(raw) == expected


@pytest.mark.parametrize("code", ["oops", -1, None, 1.5, {"x": 1}])
def test_malformed_error_code_is_not_a_crash(code):
    r = httpx.Response(400, json={"error": {"error_code": code}}, request=httpx.Request("POST", "https://x"))
    with pytest.raises(DirectApiError):
        raise_for_direct_error(r, "c")


def test_string_error_code_from_server_is_understood():
    r = httpx.Response(500, json={"error": {"error_code": "1000"}}, headers={"retryIn": "bad"},
                       request=httpx.Request("POST", "https://x"))
    with pytest.raises(RetryLater) as e:
        raise_for_direct_error(r, "c")
    assert e.value.retry_in == DEFAULT_RETRY_IN


@pytest.mark.parametrize("result", [None, [], {"Campaigns": "x"}, {"Campaigns": [{"Id": "1"}]}, {"Campaigns": [{"Id": 0}]}])
def test_check_access_rejects_malformed_success(result):
    with pytest.raises(DirectApiError):
        api(FakeReports((200, "", {}), campaigns=(200, {"result": result}))).check_access("c")


@pytest.mark.parametrize("campaigns", ["x", [1], [{"Id": "not-int"}]])
def test_campaign_contexts_with_malformed_body_raise_source_error(campaigns):
    with pytest.raises(DirectApiError):
        get_campaign_contexts(client(200, {"result": {"Campaigns": campaigns}}), "t", None, [1])


# --- OAuth: токены и срок жизни --------------------------------------------------------------------------

def token_body(**over):
    return {"access_token": "a", "refresh_token": "r", "expires_in": 3600, **over}


@pytest.mark.parametrize("over", [
    {"access_token": ""}, {"access_token": "a b"}, {"access_token": "токен"}, {"access_token": 5},
    {"refresh_token": "r\n"}, {"expires_in": 0}, {"expires_in": -1}, {"expires_in": "3600s"}, {"expires_in": 1.5},
    {"expires_in": True}, {"expires_in": MAX_TOKEN_LIFETIME + 1},
])
def test_malformed_token_response_is_bad_response(over):
    with pytest.raises(OAuthError, match="bad_response"):
        refresh(client(200, token_body(**over)), APP, "good-refresh", NOW)


def test_numeric_string_lifetime_and_missing_refresh_are_accepted():
    body = token_body(expires_in="3600")
    del body["refresh_token"]
    t = refresh(client(200, body), APP, "good-refresh", NOW)
    assert (t.refresh_token, t.expires_at) == (None, NOW + timedelta(hours=1))


def test_untrusted_error_code_is_replaced_by_http_status():
    with pytest.raises(OAuthError) as e:
        refresh(client(403, {"error": "x" * 65}), APP, "good-refresh", NOW)
    assert str(e.value) == "http_403"
