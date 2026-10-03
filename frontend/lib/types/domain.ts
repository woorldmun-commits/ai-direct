// Domain types. Field names follow docs/API_CONTRACT.md so the mock adapter can be swapped for the real API.
// Amounts are numbers here; the API sends decimal strings and the adapter parses them.

export type Unit = "rub" | "count" | "pct" | "ratio";
export type Source = "yandex_direct" | "yandex_metrika" | "user_input";

export interface Period {
  from: string; // ISO date
  to: string;
  label: string; // «последние 7 дней»
}

/** Which money this is. UI never sums kinds together (no universal «lost»). */
export type MoneyKind = "spend" | "at_risk" | "recoverable" | "measured" | "saved_estimate";

interface ValueBase {
  unit: Unit;
  source: Source[];
  period: Period;
  data_status: "complete" | "partial";
  rule_version: string | null;
  snapshot_id: string | null;
  money_kind?: MoneyKind;
}

/** API_CONTRACT §2: an unavailable value has no amount — the type makes showing a number impossible. */
export type MetricValue = ValueBase &
  (
    | { calculation_type: "actual"; amount: number; data_sufficiency: "sufficient"; formula: string | null }
    | { calculation_type: "estimated"; amount: number; data_sufficiency: "sufficient"; formula: string }
    | { calculation_type: "unavailable"; amount: null; data_sufficiency: "insufficient"; formula: null; missing: string }
  );

export interface Fact {
  label: string;
  value: MetricValue;
}

export interface Kpi {
  id: string;
  label: string;
  value: MetricValue;
  /** Change vs previous period, computed by the backend. null — nothing to compare. */
  delta: number | null;
  goodWhenDown?: boolean;
}

export type Severity = "high" | "medium" | "low";
export type Risk = "low" | "medium" | "high";

/** API_CONTRACT §3.1 — eight lifecycle states. */
export type RecStatus = "new" | "requires_decision" | "approved" | "applied" | "postponed" | "rejected" | "failed" | "cancelled";
export type ActionLevel = "change" | "review";
export type ExecutionMode = "api" | "manual" | "none" | null;
export type VerificationStatus = "not_required" | "pending" | "confirmed" | "not_confirmed";

export type CheckStatus = "passed" | "warning" | "failed";
export interface SafetyCheckItem {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
}
export interface SafetyCheck {
  policy: string; // safety_policy@2
  verdict: "allowed" | "review_only" | "blocked";
  checks: SafetyCheckItem[];
  reason: string | null;
}

export interface Evidence {
  period: Period;
  sources: Source[];
  rule: string;
  formula: string;
  metrics: Fact[];
  data_sufficiency: "sufficient" | "insufficient";
  snapshot_id: string;
  /** Explain agent text. Uses only numbers present in `metrics`. */
  explanation: string;
}

export interface ApprovalRequest {
  change: string;
  object: string;
  before: string;
  after: string;
  why: string;
  risk: Risk;
  reversible: boolean;
}

export interface Recommendation {
  id: string;
  title: string;
  campaign_id: string;
  campaign: string;
  client: string;
  severity: Severity;
  status: RecStatus;
  action_level: ActionLevel;
  created_at: string; // ISO datetime
  cause: string;
  facts: Fact[];
  effect: Fact;
  action: string | null; // null when safety blocked the recommendation
  evidence: Evidence;
  safety: SafetyCheck;
  approval: ApprovalRequest | null;
  execution: { mode: ExecutionMode; verification: VerificationStatus; approved_by: string | null; approved_at: string | null };
}

export type CampaignStatus = "active" | "limited" | "paused";
export interface Campaign {
  id: string;
  name: string;
  client_id: string;
  account: string;
  status: CampaignStatus;
  spend: number;
  impressions: number;
  clicks: number;
  ctr: number;
  conversions: number;
  /** null — fewer conversions than the sufficiency minimum. */
  cpa: number | null;
  problems: number;
}

export type ClientStatus = "active" | "attention" | "paused";
export interface Client {
  id: string;
  name: string;
  accounts: number;
  projects: number;
  spend: number;
  problems: number;
  recommendations: number;
  status: ClientStatus;
}

export interface Workspace {
  id: string;
  name: string;
  kind: "agency" | "business";
}

export type AgentKind = "deterministic" | "llm" | "human";
export type AgentStatus = "active" | "waiting" | "passed" | "blocked";
export interface Agent {
  id: string;
  name: string;
  role: string;
  kind: AgentKind;
  status: AgentStatus;
  description: string;
  input: string;
  output: string;
  last: string;
}

export type Verdict = "effect" | "no_effect" | "not_confirmed" | "insufficient" | "pending";
export interface Measurement {
  id: string;
  recommendation: string;
  campaign: string;
  approved_by: string;
  approved_at: string;
  executed_at: string | null;
  execution_mode: Exclude<ExecutionMode, null | "none">;
  verification: VerificationStatus;
  windows: { before: string; after: string };
  rows: { label: string; before: string; after: string }[];
  verdict: Verdict;
  saved: MetricValue | null;
  counts_in_saved_total: boolean;
}

export type IntegrationStatus = "connected" | "not_connected" | "error" | "soon";
export interface Integration {
  id: string;
  name: string;
  description: string;
  status: IntegrationStatus;
  accounts: number;
  last_sync: string | null;
  error?: { message: string; at: string; reference: string };
}

export interface Entitlements {
  clients: number | null; // null — not limited
  ad_accounts: number | null;
  seats: number | null;
  connections: number | null;
}
export type Usage = Record<keyof Entitlements, number>;

export interface Plan {
  id: string;
  name: string;
  description: string;
  /** null — commercial terms are not approved yet; UI must not invent a price. */
  price: { amount: number; per: string } | null;
  entitlements: Entitlements;
  features: string[];
  highlighted?: boolean;
}

export interface Subscription {
  plan_id: string;
  status: "trial" | "active" | "past_due" | "cancelled";
  renews_at: string | null;
  trial_ends_at: string | null;
}

export interface Invoice {
  id: string;
  date: string;
  amount: number;
  status: "paid" | "open";
}

export interface AssistantAnswer {
  question: string;
  answer: string;
  facts: Fact[];
  sufficiency: "sufficient" | "insufficient";
  links: { label: string; href: string }[];
}

export interface SeriesPoint {
  date: string;
  spend: number;
  conversions: number;
  cpa: number;
  prevSpend: number;
  prevConversions: number;
  prevCpa: number;
}
