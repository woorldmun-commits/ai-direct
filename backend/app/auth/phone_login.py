"""Atomic SMS identity, consent and session registration. Provider I/O happens elsewhere."""

import hashlib
import secrets
from datetime import datetime, timedelta

from app.auth.phone import verify_code_in_transaction
from app.auth.providers import PhoneServices
from app.legal.documents import is_published, record_acceptance

DOCUMENTS = frozenset({"offer", "pd_consent", "marketing"})
REQUIRED = frozenset({"offer", "pd_consent"})
SESSION_TTL = timedelta(days=30)


def sign_in_phone(
    conn,
    services: PhoneServices,
    *,
    phone: str,
    code: str,
    ip: str,
    now: datetime,
    accepted: dict,
    user_agent: str | None = None,
):
    """Errors returned after commit so invalid-attempt counters are not rolled back."""
    with conn.transaction():
        number = verify_code_in_transaction(
            conn, config=services.config, phone=phone, code=code, ip=ip, now=now, consume=False
        )
        if number is None:
            return {"error": "invalid_code"}
        identity = services.identity_hash(number)
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (identity.hex(),))
        row = conn.execute(
            "SELECT u.id, u.status FROM phone_identities p JOIN users u ON u.id = p.user_id WHERE p.phone_hash = %s",
            (identity,),
        ).fetchone()
        valid_acceptance = accepted.keys() <= DOCUMENTS and all(
            isinstance(v, str) and is_published(k, v) for k, v in accepted.items()
        )
        if not valid_acceptance or (row is None and not REQUIRED <= accepted.keys()):
            return {"error": "acceptance_required"}
        if row and row[1] != "active":
            return {"error": "user_deactivated"}
        if row is None:
            uid = conn.execute("INSERT INTO users (email) VALUES (NULL) RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO phone_identities VALUES (%s, %s, %s)", (uid, identity, number[-4:]))
        else:
            uid = row[0]
        for document, version in sorted(accepted.items()):
            record_acceptance(
                conn, user_id=uid, document=document, version=version, accepted_at=now, ip=ip, user_agent=user_agent
            )
        verified = verify_code_in_transaction(
            conn, config=services.config, phone=phone, code=code, ip=ip, now=now, consume=True
        )
        if verified is None:
            raise RuntimeError("code lost under its transaction lock")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (%s,%s,%s,%s)",
            (hashlib.sha256(token.encode()).digest(), uid, now, now + SESSION_TTL),
        )
        return {"user_id": uid, "token": token, "phone": f"+7 ••• ••• {number[-4:-2]} {number[-2:]}"}
