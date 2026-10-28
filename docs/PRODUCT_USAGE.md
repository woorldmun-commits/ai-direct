# Product usage aggregates

From `backend`, run `python -m scripts.product_usage --workspace 123 --from-at 2026-10-01T00:00:00+03:00 --to-at 2026-10-08T00:00:00+03:00`.
Supply an authorized `app_rw` connection in `INROU_USAGE_DATABASE_URL`, never in command arguments or Git.
The command is for operators; selecting a workspace is not end-user authorization. Do not expose it as an unauthenticated API.

It reuses the parent join in the existing weekly report, explicit workspace filters and `workspace_scope`.
All queries run in one read-only transaction. The session scope is restored afterwards.
No user IDs, workspace IDs, recommendation IDs, payloads, email addresses or client names are exported.

- Every event belongs to the timestamp window `[from-at,to-at)`. Timezone-aware timestamps are required.
- `events` counts domain records; `unique_recommendations` deduplicates recommendation identity within each type.
- Categories overlap; do not sum unique counts across categories into unique people or useful decisions.
- `recommendation_created/resolved/measured` are existing transactional outbox records, not delivery attempts.
- `rejected/postponed/checked/done` come from the append-only recommendation event history.
- Audit first/last timestamps refer only to recorded audits in the requested window, not a measured completion duration.
- `seen_again` is repeated rule detection, not a human view; it is intentionally omitted.
- Zero means no retained matching records, not proven absence of usage. Outbox cleanup can limit historical lifecycle counts.

Time to first audit is `null`: the activation start is not defined by these records.
Registration/connection funnel, views of evidence, retention cohorts, free-to-paid conversion and usefulness require separately validated definitions.
These counts neither establish causal savings nor measure advertising performance.
