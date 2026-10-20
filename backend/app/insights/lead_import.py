"""Strict minimized CSV, atomic caller transaction; errors never echo row values."""
import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

REQUIRED = {'external_id', 'created_on', 'status', 'updated_on', 'direct_account_id'}
OPTIONAL = {'acquired_on', 'campaign_id', 'amount', 'currency', 'refund_amount'}
STATUSES = {'new', 'qualified', 'rejected', 'won', 'lost', 'refunded'}
MAX_ROWS = 500
MAX_BYTES = 48000
MONEY = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?')
ACCOUNT = re.compile(r'acc_([1-9][0-9]{0,18})')
DAY = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


class InvalidImport(ValueError):
    pass


def day(raw: str) -> date:
    if not DAY.fullmatch(raw):
        raise InvalidImport('date_format')
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise InvalidImport('date_format') from None


def money(raw: str) -> Decimal:
    if not MONEY.fullmatch(raw):
        raise InvalidImport('amount_format')
    return Decimal(raw).quantize(Decimal('.01'))


@dataclass(frozen=True)
class Lead:
    external_id: UUID
    created_on: date
    acquired_on: date | None
    updated_on: date
    direct_account_id: int
    campaign_id: int | None
    status: str
    amount: Decimal | None
    refund_amount: Decimal


def parse(text: str, today: date) -> list[Lead]:
    if len(text.encode('utf-8')) > MAX_BYTES or '\x00' in text:
        raise InvalidImport('csv_size')
    reader = csv.DictReader(io.StringIO(text.removeprefix('\ufeff')), strict=True)
    try:
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or not REQUIRED <= set(fields) <= REQUIRED | OPTIONAL:
            raise InvalidImport('csv_columns')
        out, ids = [], set()
        for row in reader:
            if len(out) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
                raise InvalidImport('csv_rows')
            try:
                uid = UUID(row['external_id'])
            except ValueError:
                raise InvalidImport('external_id_uuid') from None
            if str(uid) != row['external_id'] or uid in ids:
                raise InvalidImport('duplicate_or_invalid_id')
            ids.add(uid)
            account = ACCOUNT.fullmatch(row['direct_account_id'])
            if not account or int(account[1]) > 2**63-1:
                raise InvalidImport('account_format')
            created, updated = day(row['created_on']), day(row['updated_on'])
            acquired = day(row['acquired_on']) if row.get('acquired_on') else None
            if updated < created or updated > today or (acquired and acquired > created):
                raise InvalidImport('date_order')
            campaign = row.get('campaign_id') or None
            if campaign and (not re.fullmatch(r'[1-9][0-9]{0,18}', campaign) or int(campaign) > 2**63-1):
                raise InvalidImport('campaign_format')
            status = row['status']
            if status not in STATUSES:
                raise InvalidImport('status_enum')
            amount = money(row['amount']) if row.get('amount') else None
            refund = money(row['refund_amount']) if row.get('refund_amount') else Decimal('0.00')
            if row.get('currency') not in (None, '', 'RUB') or (amount is not None and row.get('currency') != 'RUB'):
                raise InvalidImport('currency_rub')
            if refund and (amount is None or refund > amount):
                raise InvalidImport('refund_amount')
            out.append(Lead(uid, created, acquired, updated, int(account[1]),
                            int(campaign) if campaign else None, status, amount, refund))
    except csv.Error:
        raise InvalidImport('csv_format') from None
    if not out:
        raise InvalidImport('csv_empty')
    return out


def store(conn, ws: int, rows: list[Lead], text: str, frm: date | None, to: date | None,
          complete: bool) -> dict:
    # Serializes imports and plan writes with deletion; monotonic status updates cannot race.
    conn.execute('SELECT pg_advisory_xact_lock(%s)', (ws,))
    accounts = {r[0] for r in conn.execute('''SELECT a.id FROM direct_accounts a
                JOIN direct_connections c ON c.id=a.direct_connection_id
                WHERE c.workspace_id=%s AND a.is_selected''', (ws,)).fetchall()}
    if any(r.direct_account_id not in accounts for r in rows):
        raise InvalidImport('account_not_selected')
    if frm and any(not frm <= (r.acquired_on or r.created_on) <= to for r in rows):
        raise InvalidImport('row_outside_period')
    if complete and any(r.acquired_on is None for r in rows):
        raise InvalidImport('acquisition_date_required')
    for r in rows:
        old = conn.execute('''SELECT created_on,acquired_on,direct_account_id,campaign_id,updated_on,status,
                      amount,refund_amount FROM workspace_leads WHERE workspace_id=%s AND external_id=%s''',
                           (ws, r.external_id)).fetchone()
        expected = (r.created_on, r.acquired_on, r.direct_account_id, r.campaign_id)
        current = (r.updated_on, r.status, r.amount, r.refund_amount)
        if old and (old[:4] != expected or old[4] > r.updated_on or (old[4] == r.updated_on and old[4:] != current)):
            raise InvalidImport('conflicting_or_stale_update')
        conn.execute('''INSERT INTO workspace_leads (workspace_id,external_id,created_on,acquired_on,updated_on,
                       direct_account_id,campaign_id,status,amount,refund_amount)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id,external_id)
                       DO UPDATE SET updated_on=EXCLUDED.updated_on,status=EXCLUDED.status,
                                     amount=EXCLUDED.amount,refund_amount=EXCLUDED.refund_amount''',
                     (ws, r.external_id, r.created_on, r.acquired_on, r.updated_on, r.direct_account_id,
                      r.campaign_id, r.status, r.amount, r.refund_amount))
    fingerprint = hashlib.sha256(text.encode()).hexdigest()
    conn.execute('''INSERT INTO workspace_lead_imports
                    (workspace_id,fingerprint,period_from,period_to,cohort_complete,imported_ids)
                    VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (workspace_id) DO UPDATE SET
                    fingerprint=EXCLUDED.fingerprint,period_from=EXCLUDED.period_from,period_to=EXCLUDED.period_to,
                    cohort_complete=EXCLUDED.cohort_complete,imported_ids=EXCLUDED.imported_ids,imported_at=now()''',
                 (ws, fingerprint, frm, to, complete, [r.external_id for r in rows]))
    return {'accepted_rows': len(rows), 'cohort_complete_declared': complete,
            'source': 'user_input', 'status': 'imported'}
