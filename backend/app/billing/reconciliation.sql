-- Purchase consistency only. Settlement fees/payout registers require a separate finance import.
SELECT o.id, o.status, o.provider_status, o.currency, o.amount_minor,
       (p.amount * 100)::bigint AS ledger_minor, o.refunded_minor, o.verified_at
FROM billing_orders o
LEFT JOIN payments p ON p.provider_payment_id = o.provider_payment_id
WHERE o.status = 'review_required'
   OR (o.status = 'succeeded' AND o.provider_status <> 'succeeded')
   OR (o.status IN ('creating','pending') AND o.created_at < now()-interval '24 hours')
   OR (o.provider_status = 'succeeded' AND
       (p.id IS NULL OR (p.amount * 100)::bigint <> o.amount_minor
        OR (o.refunded_minor = 0 AND p.status <> 'succeeded')
        OR (o.refunded_minor > 0 AND p.status <> 'refunded')))
ORDER BY o.created_at;
