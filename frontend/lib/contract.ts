/**
 * Business entities of the v1.0 API (docs/API_CONTRACT.md). The demo builds exactly these shapes, so wiring
 * the real `GET /api/v1/workspaces/{ws}/…` endpoints is a change of data source, not of screens.
 * Unknown fields from the server are ignored (§1); enums are the v1.0 sets.
 */
import type { Period, Value } from "./value";

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

/** What the rule asks the human to change by hand. Only `decrease_bid` + `change_pct` is spelled out in §5. */
export interface RecommendationAction {
  type: string;
  change_pct?: string;
  placements_count?: number;
}

// §5 — list item
export interface RecommendationListItem {
  id: string;
  version_id: string;
  title: string;
  ad_account: AdAccountRef;
  object: ObjectRef;
  action_level: ActionLevel;
  status: RecStatus;
  execution_mode: ExecutionMode | null;
  verification_status: VerificationStatus | null;
  exposure: Value;
  exposure_overlap: boolean;
  can_save: Value;
  data_status: Value["data_status"];
  period: Period;
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

export interface TodayResponse {
  access: "free_audit" | "paid" | "inactive";
  today: string;
  last_audit_at: string | null;
  spent: Value;
  exposure: ExposureSummary;
  can_save: ExposureSummary;
  saved: Value;
  conversions: Value;
  counts: { new: number; requires_decision: number; accepted: number; postponed: number };
  top: RecommendationListItem[];
  recent_actions: { recommendation_id: string; title: string; event: RecEvent; at: string }[];
  changes: { period: Period; spent_delta_pct: Value; conversions_delta_pct: Value; cpa_delta_pct: Value };
  data_freshness: Record<Provider, { status: ConnectionStatus; data_to: string | null }>;
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

export const ruleName = (ruleVersion: string) => ruleVersion.split("@")[0];
