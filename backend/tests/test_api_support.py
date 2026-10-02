"""Общее для тестов API: приложение на реальной БД (роль app_rw, пул из одного соединения — чтобы проверять, в каком
состоянии соединение вернулось), сессии и два агентства с данными. Тестов здесь нет."""

import itertools
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api import create_app
from app.api.deps import session_hash
from app.api.settings import Settings
from test_schema import connected, key, one, value

ORIGIN = "https://app.example.test"
_n = itertools.count(1)


def dsn(db, role: str) -> str:
    """Строка подключения роли из фабрики conftest (pgserver локально, TEST_DATABASE_URL в CI)."""
    with db(role) as conn:
        info = conn.info
        params = {"password": info.password} if info.password else {}
        return psycopg.conninfo.make_conninfo(info.dsn, **params)


def settings(db, role: str = "app_rw", **overrides) -> Settings:
    base = dict(database_url=dsn(db, role), allowed_origins=frozenset({ORIGIN}), pool_min_size=1, pool_max_size=1,
                pool_timeout=3.0)
    return Settings(**{**base, **overrides})


@contextmanager
def client_for(app):
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def api(db):
    app = create_app(settings(db))
    with client_for(app) as c:
        c.app_ = app
        yield c


def user(rw) -> int:
    return one(rw, "INSERT INTO users (email) VALUES (%s) RETURNING id", f"api{next(_n)}@example.test")


def session(rw, user_id: int, *, expires_in=timedelta(days=1), revoked=False) -> str:
    """Сессия как после входа (app/auth/login.py): в cookie — токен, в БД — sha256."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    created = min(now, now + expires_in) - timedelta(hours=1)
    rw.execute("""INSERT INTO sessions (token_hash, user_id, created_at, expires_at, revoked_at)
                  VALUES (%s, %s, %s, %s, %s)""",
               (session_hash(token), user_id, created, now + expires_in, now if revoked else None))
    return token


def cookie(token: str) -> dict:
    return {"Cookie": f"session={token}"}


def recommendation(rw, ws: int, login: str, amount: str) -> dict:
    """Минимальная доказательная цепочка до рекомендации в данном workspace (как chain в test_schema)."""
    n = next(_n)
    account = one(rw, "INSERT INTO direct_accounts (direct_connection_id, is_selected) VALUES (%s, true) RETURNING id",
                  connected(rw, "direct", ws, login))
    release = one(rw, "INSERT INTO releases (commit_sha, build_id) VALUES (%s, %s) RETURNING id", "c" * 40, f"api{n}")
    audit = one(rw, """INSERT INTO audit_runs (workspace_id, release_id, kind, task_key, data_cutoff, settings, rules_run)
                       VALUES (%s, %s, 'scheduled', gen_random_uuid()::text, '2026-09-30', '{}', '{high_cpa_target@1}')
                       RETURNING id""", ws, release)
    issue = one(rw, """INSERT INTO issues (workspace_id, direct_account_id, issue_key, issue_type, object_type, object_id)
                       VALUES (%s, %s, %s, 'high_cpa', 'campaign', %s) RETURNING id""",
                ws, account, key(ws, account, "high_cpa", n), 50000 + n)
    lost = value(amount=amount, calculation_type="estimated", formula="(cpa - target_cpa) * conversions",
                 rule_version="high_cpa_target@1")
    finding = one(rw, """INSERT INTO findings (audit_run_id, issue_id, rule_version, lost, recoverable, data_quality,
                                               evidence, action, safety_policy, candidate_level, action_level)
                         VALUES (%s, %s, 'high_cpa_target@1', %s, %s, 'medium', %s, %s, 'safety_policy@1',
                                 'review', 'review') RETURNING id""",
                  audit, issue, Jsonb(lost),
                  Jsonb(value(amount=None, calculation_type="unavailable", data_sufficiency="insufficient")),
                  Jsonb({"clicks": value(unit="count", amount=487)}), Jsonb({"type": "decrease_bid"}))
    explanation = one(rw, """INSERT INTO explanations (finding_id, source, text, release_id)
                             VALUES (%s, 'template', 'CPA выше цели', %s) RETURNING id""", finding, release)
    rec = one(rw, "INSERT INTO recommendations (issue_id, finding_id, explanation_id) VALUES (%s, %s, %s) RETURNING id",
              issue, finding, explanation)
    return {"rec": rec, "finding": finding, "account": account, "login": login}


@pytest.fixture
def world(rw):
    """Агентство A: owner, admin, viewer (только a1), member без ролей в workspace; клиенты a1 и a2 (у a2 — своя
    рекомендация). Организация B: owner, клиент b1 с рекомендацией и своим логином Директа."""
    ids = {k: user(rw) for k in ("owner", "admin", "viewer", "member", "owner_b")}
    with rw.transaction():
        ids["org_a"] = one(rw, "SELECT create_organization(%s, 'Агентство A', 'agency')", ids["owner"])
    for who, role in (("admin", "admin"), ("viewer", "member"), ("member", "member")):
        rw.execute("SELECT set_organization_member(%s, %s, %s, %s)", (ids["owner"], ids["org_a"], ids[who], role))
    for ws in ("a1", "a2"):
        ids[ws] = one(rw, "SELECT create_workspace(%s, %s, %s)", ids["owner"], ids["org_a"], f"Клиент {ws}")
    rw.execute("SELECT set_workspace_member(%s, %s, %s, 'viewer')", (ids["owner"], ids["a1"], ids["viewer"]))
    with rw.transaction():
        ids["org_b"] = one(rw, "SELECT create_organization(%s, 'Бизнес B', 'business')", ids["owner_b"])
    ids["b1"] = one(rw, "SELECT create_workspace(%s, %s, 'Клиент b1')", ids["owner_b"], ids["org_b"])
    n = next(_n)
    ids["rec_a1"] = recommendation(rw, ids["a1"], f"client-a1-{n}", "12500.00")
    ids["rec_a2"] = recommendation(rw, ids["a2"], f"client-a2-{n}", "300.00")
    ids["rec_b1"] = recommendation(rw, ids["b1"], f"secret-b1-{n}", "99999.00")
    return ids


def ws(ids: dict, name: str) -> str:
    return f"ws_{ids[name]}"


def pooled_workspace_setting(app) -> str:
    """Что лежит в app.workspace_id у соединения, которое пул выдаст следующим (пул из одного соединения)."""
    with app.state.pool.connection() as conn:
        return conn.execute("SELECT current_setting('app.workspace_id', true)").fetchone()[0] or ""
