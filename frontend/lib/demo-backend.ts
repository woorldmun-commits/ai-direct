// DEMO only: a tiny in-memory stand-in for the backend. It applies decisions the way
// `POST /recommendations/{id}/actions` does (API_CONTRACT §4, §6), computes `allowed_actions`, and assembles
// `GET /today` (§8). Screens never compute business values themselves; with a real API this file goes away.

import type {
  ApiError,
  AuditScope,
  ConnectionStatus,
  HistoryEvent,
  IntegrationItem,
  Provider,
  Recommendation,
  RecommendationListItem,
  RejectReason,
  StatusCounts,
  TodayResponse,
  UserAction,
} from "./contract";
import { ruleName } from "./contract";
import { DEMO_NOW, LAST_AUDIT_AT, P7, TODAY_DATE, USER, WEEK, WEEK_VALUES, actual, estimated, pctChange, unavailable } from "./demo";
import type { Value } from "./value";

const ACTIVE = new Set(["new", "requires_decision", "accepted", "postponed"]);

// BigInt() calls instead of literals: tsconfig targets ES2017.
const B0 = BigInt(0);
const B1 = BigInt(1);
const B100 = BigInt(100);

/** Sum of Decimal strings with 2 places, in integer kopecks (no float). */
function kop(amount: string): bigint {
  const [i, f = ""] = amount.split(".");
  const sign = i.startsWith("-") ? -B1 : B1;
  return sign * (BigInt(i.replace("-", "")) * B100 + BigInt((f + "00").slice(0, 2)));
}
function fromKop(k: bigint): string {
  const neg = k < B0;
  const a = neg ? -k : k;
  return `${neg ? "-" : ""}${a / B100}.${String(a % B100).padStart(2, "0")}`;
}

export function allowedActions(r: Recommendation): UserAction[] {
  if (r.status === "accepted") return ["mark_done_manually", "postpone", "reject"];
  if (r.status === "new" || r.status === "requires_decision" || r.status === "postponed") {
    return r.action_level === "inspect_only" ? ["check", "postpone"] : ["accept", "mark_done_manually", "postpone", "reject"];
  }
  return [];
}

export const withAllowed = (r: Recommendation): Recommendation => ({ ...r, allowed_actions: allowedActions(r) });

export type ActionPayload = { reason?: RejectReason; comment?: string; until?: string };

/** Applies one decision. Times come from the "server" (here: the browser clock). */
export function applyAction(r: Recommendation, action: UserAction, p: ActionPayload = {}): Recommendation {
  const at = new Date().toISOString();
  const actor = { user_id: "u_demo", name: USER.name };
  const push = (event: HistoryEvent["event"]) => [...r.history, { event, at, actor }];
  switch (action) {
    case "view":
      return r.status === "new" ? { ...r, status: "requires_decision", history: push("viewed") } : r;
    case "accept":
      return {
        ...r,
        status: "accepted",
        execution: { ...r.execution, accepted_at: at, before_state: { captured_at: "accept", reliability: "normal", read_at: at, parameters: {} } },
        decision: { event: "accepted", at, actor },
        history: push("accepted"),
      };
    case "mark_done_manually":
      return {
        ...r,
        status: "applied",
        execution: {
          ...r.execution,
          execution_mode: "manual",
          verification_status: "pending",
          done_at: at,
          before_state: r.execution.before_state ?? { captured_at: "mark_done_manually", reliability: "reduced", read_at: at, parameters: {} },
        },
        decision: { event: "manual_claimed", at, actor },
        measurement: {
          status: "pending",
          verdict: null,
          method: "uncontrolled_before_after",
          windows: { before: P7, after: { from: "2026-10-03", to: "2026-10-09" } },
          before: {},
          after: {},
          counts_in_saved_total: false,
        },
        history: push("manual_claimed"),
      };
    case "check":
      return {
        ...r,
        status: "applied",
        execution: { ...r.execution, execution_mode: "none", verification_status: "not_required", done_at: at },
        decision: { event: "recommendation_checked", at, actor },
        history: push("recommendation_checked"),
      };
    case "postpone":
      return { ...r, status: "postponed", postponed_until: p.until ?? "2026-10-09", decision: { event: "postponed", at, actor }, history: push("postponed") };
    case "reject":
      return {
        ...r,
        status: "rejected",
        decision: { event: "rejected", reason: p.reason, comment: p.comment ?? null, at, actor },
        history: push("rejected"),
      };
  }
}

export function toListItem(r: Recommendation): RecommendationListItem {
  return {
    id: r.id,
    version_id: r.version_id,
    title: r.title,
    ad_account: r.ad_account,
    object: r.object,
    action_level: r.action_level,
    action: r.action,
    status: r.status,
    execution_mode: r.execution.execution_mode,
    verification_status: r.execution.verification_status,
    exposure: r.exposure,
    exposure_overlap: r.exposure_overlap,
    can_save: r.can_save,
    data_status: r.safety.data_status,
    period: r.exposure.period,
    computed_at: r.computed_at,
    created_at: r.created_at,
    updated_at: r.history[r.history.length - 1]?.at ?? r.created_at,
  };
}

const amountKop = (v: Value) => (v.amount === null ? null : kop(v.amount));

/** Backend order: active first, then by exposure descending, `unavailable` last. */
export function sortForList(items: Recommendation[]): Recommendation[] {
  return [...items].sort((a, b) => {
    const act = Number(ACTIVE.has(b.status)) - Number(ACTIVE.has(a.status));
    if (act) return act;
    const ka = amountKop(a.exposure);
    const kb = amountKop(b.exposure);
    if (ka === null || kb === null) return ka === null ? (kb === null ? 0 : 1) : -1;
    return kb > ka ? 1 : kb < ka ? -1 : 0;
  });
}

const BOTH = "yandex_direct+yandex_metrika";

function summary(values: Value[], formula: string, version: string) {
  const included = values.filter((v) => v.amount !== null);
  const total = included.reduce((s, v) => s + kop(v.amount as string), B0);
  const totalValue: Value = included.length
    ? { ...estimated(0, "rub", BOTH, formula, version), amount: fromKop(total) }
    : unavailable("rub", BOTH, "no_data", P7, version);
  return {
    total: totalValue,
    // One finding per campaign in the demo, so nothing overlaps; the field is still shown.
    overlap: { ...estimated(0, "rub", BOTH, "Σ карточек − итог", version) },
    version,
    formula,
    components: [] as { issue_type: string; amount: Value }[],
    coverage: { included: included.length, unavailable: values.length - included.length },
  };
}

/**
 * The demo plays the full v1.0 product, so it also fills the fields §8 announces for later (`saved`, counts by
 * status, `recent_actions`, …). Screens written against `TodayResponse` must still work without them.
 */
export type DemoToday = TodayResponse & Required<Pick<TodayResponse, "access" | "can_save" | "saved" | "conversions" | "recent_actions" | "changes">> & {
  counts: { active: number } & StatusCounts;
};

export function buildToday(recs: Recommendation[], sources: SourcesScenario = "fresh"): DemoToday {
  const active = recs.filter((r) => ACTIVE.has(r.status));
  const exposure = summary(active.map((r) => r.exposure), "Σ по кабинетам max(...) — без двойного учёта", "exposure_total@1");
  const byRule = new Map<string, Value[]>();
  for (const r of active) byRule.set(ruleName(r.evidence.rule_version), [...(byRule.get(ruleName(r.evidence.rule_version)) ?? []), r.exposure]);
  exposure.components = [...byRule].map(([rule, vs]) => ({ issue_type: rule, amount: summary(vs, "Σ по правилу", "exposure_total@1").total }));

  const measured = recs.filter((r) => r.measurement?.counts_in_saved_total && r.measurement.saved);
  const savedKop = measured.reduce((s, r) => s + kop(r.measurement!.saved!.amount as string), B0);
  const saved: Value = measured.length
    ? { ...estimated(0, "rub", BOTH, "Σ замеров с подтверждённым выполнением", "measurement@1", { from: "2026-09-01", to: TODAY_DATE }), amount: fromKop(savedKop) }
    : unavailable("rub", BOTH, "no_data");

  const count = (s: string) => recs.filter((r) => r.status === s).length;
  const events = recs
    .flatMap((r) => r.history.filter((h) => (h.actor !== "system" && h.event !== "viewed") || h.event.startsWith("verification") || h.event === "measured").map((h) => ({ recommendation_id: r.id, title: r.title, event: h.event, at: h.at })))
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, 5);

  const d = (i: number) => ({ spend: WEEK.spend[i], conv: WEEK.conversions[i] });
  const [y, t] = [d(5), d(6)];
  const day = { from: "2026-09-30", to: "2026-10-01" };
  const f = "(1 октября − 30 сентября) / 30 сентября × 100";

  return {
    access: "paid",
    last_audit_at: LAST_AUDIT_AT,
    data_status: active.some((r) => r.exposure.data_status === "partial") ? "partial" : "complete",
    audit_scope: AUDIT_SCOPE,
    spent: WEEK_VALUES.spend,
    exposure,
    can_save: summary(active.map((r) => r.can_save), "Σ «можно сэкономить» без двойного учёта", "exposure_total@1"),
    saved,
    conversions: WEEK_VALUES.conversions,
    counts: { active: active.length, new: count("new"), requires_decision: count("requires_decision"), accepted: count("accepted"), postponed: count("postponed") },
    top: sortForList(active).slice(0, 3).map(toListItem),
    recent_actions: events,
    changes: {
      period: day,
      spent_delta_pct: actual(pctChange(y.spend, t.spend), "pct", "yandex_direct", day, { formula: f }),
      conversions_delta_pct: actual(pctChange(y.conv, t.conv), "pct", "yandex_metrika", day, { formula: f, data_status: "partial" }),
      cpa_delta_pct: actual(pctChange(y.spend / y.conv, t.spend / t.conv), "pct", BOTH, day, { formula: f, data_status: "partial" }),
    },
    data_freshness: {
      last_snapshot_at: "2026-10-02T06:58:40+03:00",
      ...(Object.fromEntries(integrations(sources).map((i) => [i.provider, { status: i.status, data_to: i.data_to, last_success_at: i.last_success_at }])) as Omit<
        TodayResponse["data_freshness"],
        "last_snapshot_at"
      >),
    },
  };
}

// --- Data freshness scenarios (demo switch `?sources=`) -------------------------------------------
export type SourcesScenario = "fresh" | "stale" | "no_access";
export const parseSources = (s: string | null | undefined): SourcesScenario => (s === "stale" || s === "no_access" ? s : "fresh");

function item(provider: Provider, status: ConnectionStatus, last: string | null, dataTo: string | null, account: string): IntegrationItem {
  return {
    provider,
    status,
    account,
    last_success_at: last,
    data_to: dataTo,
    error_code: status === "connected" ? null : status,
    ad_accounts: provider === "yandex_direct" ? [{ id: "acc_demo", login: "demo-client", selected: true, status: "active" }] : [],
  };
}

export function integrations(s: SourcesScenario): IntegrationItem[] {
  const direct = item("yandex_direct", "connected", "2026-10-02T06:58:12+03:00", "2026-10-01", "demo-client");
  if (s === "stale") return [direct, item("yandex_metrika", "api_error", "2026-10-01T20:03:40+03:00", "2026-09-30", "counter 12345678")];
  if (s === "no_access") return [direct, item("yandex_metrika", "permission_missing", "2026-09-29T06:55:00+03:00", null, "counter 12345678")];
  return [direct, item("yandex_metrika", "connected", "2026-10-02T06:55:31+03:00", "2026-10-01", "counter 12345678")];
}

export { DEMO_NOW };

// --- Agency clients (Ctrl+K «Переключить клиента…») ---------------------------------------------
export const WORKSPACES = [
  { id: "ws_demo", name: "Демо-аккаунт", href: "/demo", note: "текущий" },
  { id: "ws_okna", name: "Окна-Профи", href: "/demo?state=no_data", note: "Директ не подключён" },
  { id: "ws_flowers", name: "Цветы 24", href: "/demo?state=empty", note: "проблем не найдено" },
];

/** `audit_scope` of GET /today (§8): what the last audit checked — rules@versions, window, accounts, campaigns. */
export const AUDIT_SCOPE: AuditScope = {
  rules: ["high_cpa_target@1", "zero_conv_campaign@1", "zero_conv_placements@1"],
  period: P7,
  ad_accounts: { checked: 1, excluded: 0 },
  campaigns: 3,
};

export const DEMO_ERROR: ApiError = {
  error: { code: "internal", message: "Не удалось загрузить данные. Мы уже знаем о проблеме.", request_id: "3f1c9a7e-5b2d-4e8a-9c41-7d2f0b6a1e93" },
};
