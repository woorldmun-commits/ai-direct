"""Юридическая доказательность (D16): принятие хранит хэш точного текста версии, язык, IP и User-Agent;
мандат агентства по клиенту — отдельный документ с workspace, только от owner/admin агентства; всё append-only."""

import hashlib
from datetime import datetime, timezone

import psycopg
import pytest

from app.legal.documents import VERSIONS, UnknownDocument, record_acceptance, text_path, text_sha256
from app.tenancy import workspace_scope
from test_schema import new_workspace, one

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
SHA = "a" * 64
INSERT = """INSERT INTO legal_acceptances (user_id, document, version, accepted_at, document_sha256, locale, ip,
                                           user_agent, workspace_id)
            VALUES (%(user)s, %(document)s, '2026-10-01', now(), %(sha)s, %(locale)s, %(ip)s, %(ua)s, %(ws)s)"""


@pytest.fixture
def agency(rw):
    """Агентство с клиентом: owner (может подтвердить мандат) и member (не может)."""
    owner = one(rw, "INSERT INTO users (email) VALUES ('agency-owner@example.test') RETURNING id")
    ws = new_workspace(rw, "Клиент агентства", user=owner, kind="agency")
    org = one(rw, "SELECT organization_id FROM workspaces WHERE id = %s", ws)
    member = one(rw, "INSERT INTO users (email) VALUES ('agency-member@example.test') RETURNING id")
    rw.execute("INSERT INTO organization_memberships (user_id, organization_id, org_role) VALUES (%s, %s, 'member')",
               (member, org))
    rw.execute("INSERT INTO workspace_memberships (user_id, workspace_id, ws_role) VALUES (%s, %s, 'approver')",
               (member, ws))
    return {"owner": owner, "member": member, "ws": ws}


def row(agency, **kw):
    base = {"user": agency["owner"], "document": "offer", "sha": SHA, "locale": "ru-RU", "ip": None, "ua": None,
            "ws": None}
    return {**base, **kw}


# --- реестр текстов ------------------------------------------------------------------------------

def test_every_published_version_has_a_text_and_hash_is_of_its_bytes():
    for document, versions in VERSIONS.items():
        for version in versions:
            assert text_sha256(document, version) == hashlib.sha256(text_path(document, version).read_bytes()).hexdigest()


@pytest.mark.parametrize("document, version, locale", [("offer", "2026-09-01", "ru-RU"), ("nda", "2026-10-01", "ru-RU"),
                                                       ("offer", "2026-10-01", "en-US")])
def test_unpublished_text_cannot_be_accepted(document, version, locale):
    with pytest.raises(UnknownDocument):
        text_sha256(document, version, locale)


# --- ограничения БД ------------------------------------------------------------------------------

@pytest.mark.parametrize("kw", [
    dict(sha=None),                                   # хэш текста обязателен для новых записей
    dict(locale=None),                                # язык показанного текста — тоже
    dict(sha="A" * 64), dict(sha="ab"),               # только 64 hex в нижнем регистре
    dict(document="agency_client_mandate"),           # мандат без workspace
    dict(ws=1),                                       # пользовательский документ с workspace
    dict(ua="x" * 257),                               # User-Agent ≤ 256
    dict(locale="русский"),
])
def test_acceptance_shape(rw, agency, kw):
    with pytest.raises(psycopg.errors.CheckViolation):
        rw.execute(INSERT, row(agency, **kw))


def test_ip_is_inet(rw, agency):
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        rw.execute(INSERT, row(agency, ip="not-an-ip"))
    rw.execute(INSERT, row(agency, ip="2001:db8::1", ua="Mozilla/5.0"))


def test_mandate_only_from_agency_owner_or_admin(rw, agency):
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="agency_client_mandate"):
        rw.execute(INSERT, row(agency, user=agency["member"], document="agency_client_mandate", ws=agency["ws"]))
    rw.execute(INSERT, row(agency, document="agency_client_mandate", ws=agency["ws"]))


def test_mandate_is_not_for_business_workspaces(rw):
    owner = one(rw, "INSERT INTO users (email) VALUES ('biz@example.test') RETURNING id")
    ws = new_workspace(rw, "Бизнес", user=owner, kind="business")
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation):
        rw.execute(INSERT, row({"owner": owner}, document="agency_client_mandate", ws=ws))


@pytest.mark.parametrize("sql", ["UPDATE legal_acceptances SET document_sha256 = %(sha)s WHERE id = %(id)s",
                                 "DELETE FROM legal_acceptances WHERE id = %(id)s"])
def test_acceptance_is_append_only(db, rw, agency, sql):
    rw.execute(INSERT, row(agency))
    acceptance = one(rw, "SELECT max(id) FROM legal_acceptances WHERE user_id = %s", agency["owner"])
    for role in ("app_system", "app_migrator"):  # у приложения нет прав, у владельца — триггер append-only
        with db(role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql, {"sha": "b" * 64, "id": acceptance})


# --- запись принятия кодом -----------------------------------------------------------------------

def test_record_mandate_in_own_workspace(db, agency):
    with db("app_rw") as app, workspace_scope(app, agency["ws"]):
        record_acceptance(app, user_id=agency["owner"], document="agency_client_mandate", version="2026-10-01",
                          accepted_at=NOW, ip="198.51.100.1", user_agent="UA", workspace_id=agency["ws"])
        sha, ip = app.execute("""SELECT document_sha256, host(ip) FROM legal_acceptances
                                 WHERE workspace_id = %s""", (agency["ws"],)).fetchone()
    assert (sha, ip) == (text_sha256("agency_client_mandate", "2026-10-01"), "198.51.100.1")


def test_mandate_cannot_be_recorded_from_another_workspace(db, rw, agency):
    other = new_workspace(rw, "Другой")
    with db("app_rw") as app, workspace_scope(app, other):
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
            record_acceptance(app, user_id=agency["owner"], document="agency_client_mandate", version="2026-10-01",
                              accepted_at=NOW, workspace_id=agency["ws"])


@pytest.mark.parametrize("kw, error", [
    (dict(document="agency_client_mandate"), ValueError),                  # мандат без workspace
    (dict(document="offer", workspace_id=1), ValueError),                  # оферта — не по workspace
    (dict(document="offer", version="2026-09-01"), UnknownDocument),        # такого текста не публиковали
    (dict(document="offer", ip="999.1.1.1"), ValueError),
])
def test_record_acceptance_validates_before_db(rw, agency, kw, error):
    args = dict(user_id=agency["owner"], version="2026-10-01", accepted_at=NOW) | kw
    with pytest.raises(error):
        record_acceptance(rw, **args)
