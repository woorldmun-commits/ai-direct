# Workspace insights — implemented contract

Implementation in isolated adpilot-metrics worktree; parent integrates shared registration/schema.

## Registration / migration

- Add `from app.api.workspace_insights import router as insights_router` and `app.include_router(insights_router, prefix=PREFIX)` in `backend/app/api/app.py`.
- Append EXACT SQL from `backend/migrations/versions/0006_workspace_insights.sql` to canonical `backend/db/schema.sql` once; existing deployments apply migration runner. Do not change released versions.
- Three workspace-FK tables use ON DELETE CASCADE; `delete_workspace_data` retains its existing security boundary. Direct account fit is enforced by DB trigger as well as import validation. New tables have RLS (app_rw context, app_system bypass); UPDATE grants exclude tenant/cohort identity columns. app_deleter has no new direct table rights.
- Tests apply 0006 only if table absent so isolated base schema works. Once canonical integration is done this guard does nothing. Test API fixture attaches router for isolated execution.

## Routes

All routes require session and CurrentWorkspace; foreign workspace is 404. Writes permit owner/admin/approver/analyst; viewer denied. Existing middleware requires approved Origin and bounded request body. No ad-platform writes, external CRM, LLM, email or scheduler added.

`GET /api/v1/workspaces/ws_N/insights`

- `period:{from,to}` = saved budget-plan period, else last explicit import period, else seven complete days before today (MSK).
- `ad_accounts:[{id:'acc_N'}]` = selected current-workspace accounts (no login/name).
- `health:{checks:[{id,status,reason,action}],freshness}`. Four checks: direct, freshness, goals, metrika; statuses ok/attention/unavailable; no opaque score. Freshness and missing goals are checked per selected account, not only global latest snapshot. Definition presence does NOT validate goal quality.
- `budget:{plan:null|{period,amount,currency:'RUB'},actual:Value,variance:Value,reason}`. Whole-period actual; no extrapolated current-month final spend. Variance = actual minus declared plan, may be negative. Selected accounts, one latest sealed snapshot each; all must fully cover period before partial_from. Missing rows/snapshots => unavailable, not zero.
- `lead_quality:{counts:{total,qualified,unresolved,matched},coverage:{matched_pct,qualification_complete,cohort_complete,completeness_source:'user_input'},qcpl:Value,reason}`.
- `summary:{period,generated_at,delivery:'manual_pull',facts:[{id,label,value,detail}],limitations:[string]}`. Deterministic facts only. This is a period report generated on demand; no scheduled weekly delivery is claimed.

`POST /.../budget-plan` body `{period_from:'YYYY-MM-DD',period_to:'YYYY-MM-DD',amount:'1000.00'}`. Positive RUB Decimal, max 12 integer and 2 fractional digits; period <=366 inclusive days. One latest editable plan per workspace. Returns period/amount/currency.

`POST /.../lead-import` body `{csv:'...',period_from?:'YYYY-MM-DD',period_to?:'YYYY-MM-DD',cohort_complete?:false}`. Period pair optional together; required for complete declaration and must end before today MSK. Max 48,000 UTF-8 CSV bytes and 500 rows; upstream body limit also applies. Error responses contain fixed reason codes, no raw values. Atomic request transaction; per-workspace advisory lock serializes with imports/deletion. Replaying identical rows is idempotent. Same UUID updates latest status; acquired/created/account/campaign identity immutable. Older updated_on and conflicting same-day status are rejected (use a later update date).

Response `{accepted_rows,cohort_complete_declared,source:'user_input',status:'imported'}`. No lead identifiers returned.

## CSV, minimized local connector

Mandatory columns (order arbitrary): `external_id,created_on,status,updated_on,direct_account_id`.
Optional: `acquired_on,campaign_id,amount,currency,refund_amount`.
Only these headers allowed: phones, names, email, notes and contact fields rejected. IDs must be canonical UUID pseudonyms; create a stable project-specific UUID mapping before import. No lead IDs or rows sent to LLM. Dates strict ISO date. Account is `acc_N` from insights; must be selected in same workspace. Optional campaign_id is a positive internal advertising campaign id. Amount/refund Decimal RUB only, refund <= amount; these optional amounts are not presented as verified revenue or ROI.

Status mapping:

| CSV status | Meaning | qCPL qualified denominator |
|---|---|---|
| new | Not qualified yet | no; blocks completed qualification |
| qualified | Fit confirmed | yes |
| rejected | Not a suitable lead | no |
| won | Qualified lead became sale | yes |
| lost | Qualified opportunity lost later | yes |
| refunded | Qualified sale later refunded | yes; this is qCPL, not paid-order CPA |

`acquired_on` = acquisition/click cohort date aligned to Direct spend, not simply conversion creation date. It must be <= created_on. `updated_on >= created_on`, not in future.

## qCPL admissibility

A declaration means **the user asserts this file contains ALL leads acquired in the period for every imported account**, not just qualified leads or a subset of campaigns. Rekvero cannot verify CRM completeness. UI checkbox must explain this. Every row must have acquired_on within closed period; all qualifications resolved; latest complete manifest IDs must exactly match all stored cohort rows. Counts reflect unique UUIDs. Rows with no acquired_on are counted by created_on but cannot support qCPL.

Actual spend must cover precisely the same period and imported account scope (other selected accounts excluded); optional campaign IDs must match rows in those snapshots. Missing denominator, unknown scope, incomplete snapshots or unresolved leads => unavailable. qCPL = imported-account-period spend / qualified leads; source `yandex_direct+user_input`, completeness source user_input. This is a fact conditional on user declaration, not a verified CRM fact, profit, causal effect or guaranteed saving. No cohort attribution model is inferred.

## Not implemented here

Scheduled email/weekly delivery, billing/provider, CRM API connector, verified sales profit/DRR, real-account acceptance. These require provider settings/consent and external evidence. Parent owns documentation/version-scope integration, canonical-schema migration equivalence and full-suite test run.


## Дополнение 21 октября 2026

POST `/workspaces/ws_N/lead-import/preview` принимает тот же контракт, проверяет формат, выбранные аккаунты, период и конфликты обновлений, возвращает агрегированные счётчики без записи лидов/manifest. Перед подтверждённым импортом проверки повторяются. Ошибки не отражают значения строк. Форма инвалидирует предпросмотр при изменении полей.

GET `/workspaces/ws_N/weekly-report` возвращает `insights` за последние 7 завершённых дней МСК и `decisions` (type/count событий за тот же интервал). План другого периода не используется. Это число событий, не число уникальных проблем. Интерфейс: `/workspace?view=reports&workspace=ws_N`, отчёт читается на сайте, скачивание TXT дополнительно. Доставка во внешние каналы не включается по выбору владельца.

Существующий `/insights` сохраняет выбор периода по плану/импорту. qCPL и его ограничения не меняются. Для paid запуска нужны отдельные провайдер и подтверждённый платёжный контур; пользователь оставил реальные платежи отключёнными.
