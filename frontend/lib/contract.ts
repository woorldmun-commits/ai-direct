/**
 * Business entities of the v1.0 API (docs/API_CONTRACT.md). The demo builds exactly these shapes, so wiring
 * the real `GET /api/v1/workspaces/{ws}/…` endpoints is a change of data source, not of screens.
 * Unknown fields from the server are ignored (§1); enums are the v1.0 sets.
 */
import type { DataStatus, DecimalString, Period, Value } from "./value";

// §3 — recommendation lifecycle
export type RecStatus = "new" | "requires_decision" | "accepted" | "applied" | "postponed" | "rejected";
export type ExecutionMode = "manual" | "none";
export type VerificationStatus = "not_required" | "pending" | "confirmed" | "not_confirmed";
export type ActionLevel = "inspect_only" | "review" | "change";

// §4 — user actions
export type UserAction = "view" | "accept" | "mark_done_manually" | "check" | "postpone" | "reject";
export type BlockedReason = "role_forbidden" | "access_inactive";
export type RejectReason = "wrong_data" | "irrelevant_rule" | "not_enough_context" | "too_risky" | "other";

export const REJECT_REASONS: { code: RejectReason; label: string }[] = [
  { code: "wrong_data", label: "Неверные данные" },
  { code: "irrelevant_rule", label: "Правило не подходит для этой кампании" },
  { code: "not_enough_context", label: "Недостаточно контекста для решения" },
  { code: "too_risky", label: "Слишком рискованно" },
  { code: "other", label: "Другое" },
];
export const REJECT_LABEL = Object.fromEntries(REJECT_REASONS.map((r) => [r.code, r.label])) as Record<RejectReason, string>;

export const BLOCKED_LABEL: Record<BlockedReason, string> = {
  role_forbidden: "Ваша роль не позволяет это действие",
  access_inactive: "Подписка закончилась — прошлые данные доступны только для чтения",
};

export const ACTION_LEVEL_LABEL: Record<ActionLevel, string> = {
  inspect_only: "Проверьте",
  review: "Проверьте перед изменением",
  change: "Можно изменить",
};

/** DATA_MODEL.md §8.3, v1.0 events. */
export type RecEvent =
  | "created"
  | "seen_again"
  | "viewed"
  | "delivered"
  | "accepted"
  | "postponed"
  | "rejected"
  | "recommendation_checked"
  | "manual_claimed"
  | "verification_confirmed"
  | "verification_not_confirmed"
  | "measured"
  | "measurement_skipped";

export type Actor = "system" | { user_id: string; name?: string };

export interface HistoryEvent {
  event: RecEvent;
  at: string;
  actor: Actor;
}

export interface AdAccountRef {
  id: string;
  login: string;
}

export interface ObjectRef {
  type: string;
  id: string;
  name: string;
}

// §5 — what the human changes in Direct by hand: exactly four shapes of the three v1.0 rules, `execution` is
// always `manual`. A discriminated union on `type`, so a screen has to handle each one.
export type ActionSuggestion = "set_target_cpa";
export type ZeroConversionCheck = "conversion_goals" | "strategy" | "search_queries_negative_keywords";

export interface DecreaseBidAction {
  type: "decrease_bid";
  execution: "manual";
  /** Negative Decimal string, e.g. `"-15.00"`. */
  change_pct: DecimalString;
}
export interface InvestigateCpaGrowthAction {
  type: "investigate_cpa_growth";
  execution: "manual";
  suggest: ActionSuggestion | null;
}
export interface InvestigateZeroConversionsAction {
  type: "investigate_zero_conversions";
  execution: "manual";
  checks: ZeroConversionCheck[];
  suggest: ActionSuggestion | null;
}
export interface ExcludePlacementsAction {
  type: "exclude_placements";
  execution: "manual";
  placements_count: number;
  /** `id` is opaque; `name` is the site domain or app id (not personal data), `null` when unknown. */
  placements: { id: string; name: string | null }[];
}
export type RecommendationAction =
  | DecreaseBidAction
  | InvestigateCpaGrowthAction
  | InvestigateZeroConversionsAction
  | ExcludePlacementsAction;

// §5 — list item
export interface RecommendationListItem {
  id: string;
  version_id: string;
  title: string;
  ad_account: AdAccountRef;
  object: ObjectRef;
  action_level: ActionLevel;
  action: RecommendationAction;
  status: RecStatus;
  execution_mode: ExecutionMode | null;
  verification_status: VerificationStatus | null;
  exposure: Value;
  exposure_overlap: boolean;
  can_save: Value;
  data_status: Value["data_status"];
  period: Period;
  /** When the current version (`version_id`) was calculated. */
  computed_at: string;
  created_at: string;
  updated_at: string;
}

export interface BeforeState {
  captured_at: "accept" | "mark_done_manually";
  reliability: "normal" | "reduced";
  read_at: string;
  parameters: Record<string, Value>;
}

export interface Execution {
  execution_mode: ExecutionMode | null;
  verification_status: VerificationStatus | null;
  accepted_at: string | null;
  done_at: string | null;
  before_state: BeforeState | null;
  verification_checked_at: string | null;
}

export interface Decision {
  event: "accepted" | "postponed" | "rejected" | "recommendation_checked" | "manual_claimed";
  reason?: RejectReason;
  comment?: string | null;
  at: string;
  actor: Actor;
}

// §7 — measurement
export type MeasurementVerdict = "effect" | "no_effect" | "not_confirmed" | "insufficient";
export interface Measurement {
  status: "pending" | "measured" | "skipped";
  verdict: MeasurementVerdict | null;
  method: "uncontrolled_before_after";
  windows: { before: Period; after: Period };
  before: Record<string, Value>;
  after: Record<string, Value>;
  /** Present only when `verdict = effect`; always `estimated`. */
  saved?: Value;
  counts_in_saved_total: boolean;
}

// §5 — passport
export interface Recommendation {
  id: string;
  version_id: string;
  title: string;
  ad_account: AdAccountRef;
  object: ObjectRef;
  status: RecStatus;
  postponed_until: string | null;
  action_level: ActionLevel;
  allowed_actions: UserAction[];
  blocked_actions: { action: UserAction; reason: BlockedReason }[];
  exposure: Value;
  exposure_overlap: boolean;
  can_save: Value;
  explanation: { text: string; source: "llm" | "template" };
  action: RecommendationAction;
  evidence: { facts: Record<string, Value>; meta: Record<string, string>; rule_version: string };
  safety: { safety_policy: string; candidate_level: ActionLevel; policy_reasons: string[]; data_status: Value["data_status"] };
  limitations: string[];
  execution: Execution;
  decision: Decision | null;
  measurement: Measurement | null;
  history: HistoryEvent[];
  computed_at: string;
  created_at: string;
}

// §8 — «Сегодня»
export type ConnectionStatus = "connected" | "api_error" | "token_expired" | "token_revoked" | "permission_missing" | "disconnected";
export type Provider = "yandex_direct" | "yandex_metrika";

export interface ExposureSummary {
  total: Value;
  overlap: Value;
  version?: string;
  formula?: string;
  components: { issue_type: string; amount: Value }[];
  coverage: { included: number; unavailable: number };
}

/** What the last audit checked — «Проблем не найдено — вот что проверено». */
export interface AuditScope {
  /** `rule@N` that ran. */
  rules: string[];
  period: Period;
  ad_accounts: { checked: number; excluded: number };
  campaigns: number;
}

export interface SourceFreshness {
  /** `null` — the source is not connected. */
  status: ConnectionStatus | null;
  data_to: string | null;
  last_success_at: string | null;
}

export interface StatusCounts {
  new: number;
  requires_decision: number;
  accepted: number;
  postponed: number;
}

export interface TodayResponse {
  last_audit_at: string | null;
  data_status: DataStatus;
  audit_scope: AuditScope | null;
  spent: Value;
  exposure: ExposureSummary;
  /** `active` now; counts by status come with the v1.0 events (week 4). */
  counts: { active: number } & Partial<StatusCounts>;
  top: RecommendationListItem[];
  data_freshness: { last_snapshot_at: string | null } & Record<Provider, SourceFreshness>;
  // Announced in §8 but not sent yet («появится»): the screen must work without them.
  access?: "free_audit" | "paid" | "inactive";
  can_save?: ExposureSummary;
  saved?: Value;
  conversions?: Value;
  recent_actions?: { recommendation_id: string; title: string; event: RecEvent; at: string }[];
  changes?: { period: Period; spent_delta_pct: Value; conversions_delta_pct: Value; cpa_delta_pct: Value };
}

// §8 — «Настройки → Интеграции»
export interface IntegrationItem {
  provider: Provider;
  status: ConnectionStatus;
  account: string | null;
  last_success_at: string | null;
  data_to: string | null;
  error_code: string | null;
  ad_accounts: { id: string; login: string; selected: boolean; status: string }[];
}

// §12 — errors
export interface ApiError {
  error: { code: string; reason?: string; message: string; request_id: string };
}

// UI wording for statuses and results (§3.1, §3.3). «Применена» is never shown.
export const STATUS_LABEL: Record<RecStatus, string> = {
  new: "Новая",
  requires_decision: "Требует решения",
  accepted: "Принята к выполнению",
  applied: "Выполнена",
  postponed: "Отложена",
  rejected: "Отклонена",
};

export function resultLabel(r: Pick<Recommendation, "status" | "execution">): string {
  const { execution_mode: mode, verification_status: vs } = r.execution;
  if (r.status === "accepted") return "Принята к выполнению. Внесите изменение в кабинете Директа и отметьте «Выполнено»";
  if (r.status !== "applied") return STATUS_LABEL[r.status];
  if (mode === "none") return "Проверено";
  if (vs === "confirmed") return "Выполнено вручную. Изменение подтверждено по данным Директа";
  if (vs === "not_confirmed") return "Выполнено вручную. Выполнение не подтверждено";
  return "Выполнено вручную пользователем. Результат изменения пока не подтверждён";
}

export const RULE_TITLE: Record<string, string> = {
  high_cpa: "Высокий CPA",
  high_cpa_target: "Высокий CPA",
  high_cpa_baseline: "Высокий CPA",
  zero_conv_campaign: "Нулевые конверсии",
  zero_conv_placements: "Площадки РСЯ без конверсий",
};

/** What each rule checks — for «Проблем не найдено — вот что проверено» (`audit_scope.rules`). */
export const RULE_CHECK_TEXT: Record<string, string> = {
  zero_conv_campaign: "Расход без конверсий при достаточном объёме кликов",
  high_cpa_target: "CPA выше целевого при достаточном числе конверсий",
  high_cpa_baseline: "CPA выше обычного уровня кампании при достаточном числе конверсий",
  zero_conv_placements: "Площадки РСЯ с расходом и без конверсий",
};

export const ruleName = (ruleVersion: string) => ruleVersion.split("@")[0];
