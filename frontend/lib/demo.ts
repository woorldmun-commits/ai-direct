// DEMO data only. It plays the backend: every figure is computed here once and handed to the screens as
// contract objects (`Value`, `Recommendation`, lib/contract.ts), never typed into markup by hand, so totals on
// different screens always agree. Screens only format what they get (`<ValueView>`).

import type { DecreaseBidAction, ExcludePlacementsAction, HistoryEvent, Recommendation } from "./contract";
import type { ActualValue, DataStatus, EstimatedValue, Period, UnavailableReason, UnavailableValue, Unit } from "./value";

export type Platform = "search" | "network";

export const TODAY_DATE = "2026-10-02";
/** Fixed demo clock, so "N minutes ago" renders the same on server and client. */
export const DEMO_NOW = "2026-10-02T09:15:00+03:00";
export const LAST_AUDIT_AT = "2026-10-02T07:01:54+03:00";
export const P7: Period = { from: "2026-09-25", to: "2026-10-01" };
export const PREV7: Period = { from: "2026-09-18", to: "2026-09-24" };
export const SEPTEMBER: Period = { from: "2026-09-01", to: "2026-09-30" };
export const DAYS = ["25", "26", "27", "28", "29", "30", "1"];
export const USER = { name: "Алексей", account: "Демо-аккаунт" };
export const AD_ACCOUNT = { id: "acc_demo", login: "demo-client" };

const DIRECT = "yandex_direct";
const BOTH = "yandex_direct+yandex_metrika";

// --- Value builders (backend role: amounts become Decimal strings once, here) ---------------------
/** Number → Decimal string with 2 places. Demo inputs are whole rubles or simple ratios. */
export const dec = (n: number) => (Math.round(n * 100) / 100).toFixed(2);
const amountOf = (n: number, unit: Unit) => (unit === "count" ? String(Math.round(n)) : dec(n));

export function actual(
  n: number,
  unit: Unit,
  source: string,
  period: Period = P7,
  opts: { formula?: string; data_status?: DataStatus; rule_version?: string } = {},
): ActualValue {
  return {
    amount: amountOf(n, unit),
    unit,
    calculation_type: "actual",
    source,
    period,
    data_status: opts.data_status ?? "complete",
    data_sufficiency: "sufficient",
    formula: opts.formula ?? null,
    rule_version: opts.rule_version ?? null,
    unavailable_reason: null,
  };
}

export function estimated(
  n: number,
  unit: Unit,
  source: string,
  formula: string,
  rule_version: string | null,
  period: Period = P7,
  data_status: DataStatus = "complete",
): EstimatedValue {
  return { amount: amountOf(n, unit), unit, calculation_type: "estimated", source, period, data_status, data_sufficiency: "sufficient", formula, rule_version, unavailable_reason: null };
}

export function unavailable(unit: Unit, source: string, reason: UnavailableReason, period: Period = P7, rule_version: string | null = null): UnavailableValue {
  return { amount: null, unit, calculation_type: "unavailable", source, period, data_status: "complete", data_sufficiency: "insufficient", formula: null, rule_version, unavailable_reason: reason };
}

/** `computed_at` of the current version: the audit that created it or saw it again last. */
export function computedAt(history: HistoryEvent[], created_at: string): string {
  return [...history].reverse().find((h) => h.event === "seen_again" || h.event === "created")?.at ?? created_at;
}

/** Demo placements for `exclude_placements` (opaque ids, site names as the sanitized directory keeps them). */
export function demoPlacements(count: number, prefix: string): ExcludePlacementsAction {
  const placements = Array.from({ length: count }, (_, i) => ({ id: `${prefix}${String(i + 1).padStart(3, "0")}`, name: `site-${prefix}${i + 1}.example` }));
  return { type: "exclude_placements", execution: "manual", placements_count: count, placements };
}

// --- Raw demo week (charts use these series; screens show Values) -----------------------------------
const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

export const TARGET_CPA = 3000;
const CPA_SEARCH = 5250;
const CONV_SEARCH = 19;
const DEV = Math.round(((CPA_SEARCH - TARGET_CPA) / TARGET_CPA) * 100);
/** Bid rule: step down 5% per full 20% of CPA deviation above target. */
const CUT = Math.floor(DEV / 20) * 5;

export const CAMPAIGNS = [
  { id: "51234567", name: "Поиск · Москва · Услуги", platform: "search" as Platform, spend: CPA_SEARCH * CONV_SEARCH, conversions: CONV_SEARCH },
  { id: "51234568", name: "РСЯ · Москва", platform: "network" as Platform, spend: 41_300, conversions: 9 },
  { id: "51234569", name: "РСЯ · Регионы", platform: "network" as Platform, spend: 39_250, conversions: 19 },
  { id: "51234570", name: "Поиск · Регионы", platform: "search" as Platform, spend: 3_900, conversions: 0 },
];

export const WEEK = {
  spend: [25_400, 26_100, 27_800, 26_300, 25_900, 27_200, 25_500],
  conversions: [7, 6, 7, 6, 7, 8, 6],
  exposure: [7_900, 8_300, 9_100, 8_400, 8_200, 9_050, 8_000],
};
export const PREV_WEEK = {
  spend: [24_100, 24_800, 25_300, 24_200, 24_700, 24_400, 24_100],
  conversions: [8, 8, 8, 7, 8, 8, 8],
  exposure: [5_600, 5_900, 6_100, 5_800, 6_000, 6_100, 5_800],
};
export const cpaSeries = (w: typeof WEEK) => w.spend.map((s, i) => Math.round(s / w.conversions[i]));

function weekTotals(w: typeof WEEK) {
  const spend = sum(w.spend);
  const conversions = sum(w.conversions);
  return { spend, conversions, exposure: sum(w.exposure), cpa: spend / conversions };
}
export const KPI = weekTotals(WEEK);
export const PREV_KPI = weekTotals(PREV_WEEK);
export const pctChange = (prev: number, cur: number) => ((cur - prev) / prev) * 100;

/** Week KPIs as Values: conversions of the last days may still be recounted by Metrika. */
export const WEEK_VALUES = {
  spend: actual(KPI.spend, "rub", DIRECT),
  conversions: actual(KPI.conversions, "count", "yandex_metrika", P7, { data_status: "partial" }),
  cpa: actual(KPI.cpa, "rub", BOTH, P7, { formula: "расход / конверсии", data_status: "partial" }),
  exposure: estimated(KPI.exposure, "rub", BOTH, "Σ по кабинету без двойного учёта", "exposure_total@1", P7, "partial"),
};
export const PREV_WEEK_VALUES = {
  spend: actual(PREV_KPI.spend, "rub", DIRECT, PREV7),
  conversions: actual(PREV_KPI.conversions, "count", "yandex_metrika", PREV7),
  cpa: actual(PREV_KPI.cpa, "rub", BOTH, PREV7, { formula: "расход / конверсии" }),
  exposure: estimated(PREV_KPI.exposure, "rub", BOTH, "Σ по кабинету без двойного учёта", "exposure_total@1", PREV7),
};
const deltaFormula = "(эта неделя − прошлая) / прошлая × 100";
export const WEEK_DELTAS = {
  spend: actual(pctChange(PREV_KPI.spend, KPI.spend), "pct", DIRECT, P7, { formula: deltaFormula }),
  conversions: actual(pctChange(PREV_KPI.conversions, KPI.conversions), "pct", "yandex_metrika", P7, { formula: deltaFormula, data_status: "partial" }),
  cpa: actual(pctChange(PREV_KPI.cpa, KPI.cpa), "pct", BOTH, P7, { formula: deltaFormula, data_status: "partial" }),
  exposure: estimated(pctChange(PREV_KPI.exposure, KPI.exposure), "pct", BOTH, deltaFormula, "exposure_total@1", P7, "partial"),
};

// --- Current recommendations (three rules of v1.0, levels as safety_policy@1 sets them) ----------
// safety_policy@1 (backend/app/audit/policy.py): the strategy is unknown, so nothing is above `review`;
// `exclude_placements` is `review` at most; little data → `inspect_only` with an `investigate` action.
const RULE_CPA = "high_cpa_target@1";
const RULE_PLACEMENTS = "zero_conv_placements@1";
const RULE_ZERO = "zero_conv_campaign@1";
const POLICY = "safety_policy@1";
const PLACEMENTS_FORMULA = "Σ расход площадок, где клики ≥ 50 и конверсии = 0";
const sys = "system" as const;

type RecInput = Omit<
  Recommendation,
  "ad_account" | "postponed_until" | "blocked_actions" | "exposure_overlap" | "data_sufficiency" | "decision" | "measurement" | "computed_at"
> &
  Partial<Pick<Recommendation, "data_sufficiency">>;

/** `exposure_overlap` is filled by the demo backend over the current set (demo-backend `withOverlap`). */
function rec(r: RecInput): Recommendation {
  return {
    ...r,
    ad_account: AD_ACCOUNT,
    postponed_until: null,
    blocked_actions: [],
    exposure_overlap: estimated(0, "rub", BOTH, "сумма карточки − её вклад в итог", "exposure_total@1", r.exposure.period),
    data_sufficiency: r.data_sufficiency ?? "sufficient",
    decision: null,
    measurement: null,
    computed_at: computedAt(r.history, r.created_at),
  };
}
const noExecution = { execution_mode: null, verification_status: null, accepted_at: null, done_at: null, before_state: null, verification_checked_at: null };

/** Levers of `decrease_bid` at `review` with an unknown strategy: manual bid or the autostrategy's target. */
const bidLevers = (cut: number): DecreaseBidAction => ({
  type: "decrease_bid",
  execution: "manual",
  change_pct: dec(-cut),
  levers: [
    { strategy: "manual", text: "снизить ставку", change_pct: dec(-cut) },
    { strategy: "auto", text: "снизить целевую цену конверсии в стратегии или проверить, на какие цели она оптимизируется" },
  ],
});

const MSK_CPA = CAMPAIGNS[1].spend / CAMPAIGNS[1].conversions;
const MSK_DEV = Math.round(((MSK_CPA - TARGET_CPA) / TARGET_CPA) * 100);
const MSK_CUT = Math.floor(MSK_DEV / 20) * 5;
const NET_MSK = { count: 14, clicks: 1_860, spend: 12_400 };
const NET_REG = { count: 6, clicks: 410, spend: 3_800 };
const ZERO = { clicks: 140, threshold: 6_000 };

const placementFacts = (p: { count: number; clicks: number; spend: number }) => ({
  cost: actual(p.spend, "rub", DIRECT),
  clicks: actual(p.clicks, "count", DIRECT),
  conversions: actual(0, "count", "yandex_metrika"),
  placements: actual(p.count, "count", DIRECT, P7, { rule_version: RULE_PLACEMENTS }),
});

export const RECOMMENDATIONS: Recommendation[] = [
  rec({
    id: "rec_cpa01",
    version_id: "rv_cpa01_2",
    title: `CPA выше цели на ${DEV}%`,
    object: { type: "campaign", id: CAMPAIGNS[0].id, name: CAMPAIGNS[0].name },
    status: "new",
    action_level: "review",
    allowed_actions: [],
    exposure: estimated((CPA_SEARCH - TARGET_CPA) * CONV_SEARCH, "rub", BOTH, "(cpa − target_cpa) × conversions", RULE_CPA, P7, "partial"),
    can_save: estimated((CPA_SEARCH * CONV_SEARCH * CUT) / 100, "rub", BOTH, "cost × |change_pct| / 100", RULE_CPA, P7, "partial"),
    explanation: {
      text: `За неделю конверсия в кампании стоила ${CPA_SEARCH} ₽ при цели ${TARGET_CPA} ₽ — на ${DEV}% дороже. Стратегия кампании AdPilot неизвестна: если ставки ручные — снизьте ставку на ${CUT}%, если автостратегия — снизьте целевую цену конверсии или проверьте цели. Через 7 дней после выполнения AdPilot сравнит CPA до и после.`,
      source: "template",
    },
    action: bidLevers(CUT),
    evidence: {
      facts: {
        cost: actual(CAMPAIGNS[0].spend, "rub", DIRECT),
        conversions: actual(CONV_SEARCH, "count", "yandex_metrika", P7, { data_status: "partial" }),
        cpa: actual(CPA_SEARCH, "rub", BOTH, P7, { formula: "cost / conversions", data_status: "partial" }),
        target_cpa: actual(TARGET_CPA, "rub", "user_input"),
        deviation_pct: actual(DEV, "pct", BOTH, P7, { formula: "(cpa − target_cpa) / target_cpa × 100", rule_version: RULE_CPA, data_status: "partial" }),
      },
      meta: { baseline_data_quality: "high" },
      rule_version: RULE_CPA,
    },
    safety: { safety_policy: POLICY, candidate_level: "change", policy_reasons: ["strategy_unknown"], data_status: "partial" },
    limitations: ["strategy_unknown"],
    execution: noExecution,
    history: [
      { event: "created", at: "2026-10-01T07:02:11+03:00", actor: sys },
      { event: "seen_again", at: LAST_AUDIT_AT, actor: sys },
    ],
    created_at: "2026-10-01T07:02:11+03:00",
  }),
  rec({
    id: "rec_cpa02",
    version_id: "rv_cpa02_1",
    title: `CPA выше цели на ${MSK_DEV}%`,
    object: { type: "campaign", id: CAMPAIGNS[1].id, name: CAMPAIGNS[1].name },
    status: "requires_decision",
    action_level: "review",
    allowed_actions: [],
    exposure: estimated((MSK_CPA - TARGET_CPA) * CAMPAIGNS[1].conversions, "rub", BOTH, "(cpa − target_cpa) × conversions", RULE_CPA),
    can_save: estimated((CAMPAIGNS[1].spend * MSK_CUT) / 100, "rub", BOTH, "cost × |change_pct| / 100", RULE_CPA),
    explanation: {
      text: `CPA кампании — ${Math.round(MSK_CPA)} ₽, на ${MSK_DEV}% выше цели ${TARGET_CPA} ₽, при ${CAMPAIGNS[1].conversions} конверсиях — данных впритык, проверьте перед изменением. Если ставки ручные — снизьте ставку на ${MSK_CUT}%, если автостратегия — снизьте целевую цену конверсии. Площадки без конверсий в этой кампании — отдельная карточка; их расход уже входит в эту сумму.`,
      source: "template",
    },
    action: bidLevers(MSK_CUT),
    evidence: {
      facts: {
        cost: actual(CAMPAIGNS[1].spend, "rub", DIRECT),
        conversions: actual(CAMPAIGNS[1].conversions, "count", "yandex_metrika"),
        cpa: actual(MSK_CPA, "rub", BOTH, P7, { formula: "cost / conversions" }),
        target_cpa: actual(TARGET_CPA, "rub", "user_input"),
        deviation_pct: actual(MSK_DEV, "pct", BOTH, P7, { formula: "(cpa − target_cpa) / target_cpa × 100", rule_version: RULE_CPA }),
      },
      meta: { baseline_data_quality: "medium" },
      rule_version: RULE_CPA,
    },
    safety: { safety_policy: POLICY, candidate_level: "change", policy_reasons: ["data_sufficiency_medium", "strategy_unknown"], data_status: "complete" },
    limitations: ["strategy_unknown"],
    execution: noExecution,
    history: [
      { event: "created", at: "2026-10-02T07:01:50+03:00", actor: sys },
      { event: "viewed", at: "2026-10-02T08:40:00+03:00", actor: { user_id: "u_demo", name: USER.name } },
    ],
    created_at: "2026-10-02T07:01:50+03:00",
  }),
  rec({
    id: "rec_net01",
    version_id: "rv_net01_1",
    title: "Площадки РСЯ без конверсий",
    object: { type: "campaign", id: CAMPAIGNS[1].id, name: CAMPAIGNS[1].name },
    status: "accepted",
    action_level: "review",
    allowed_actions: [],
    exposure: estimated(NET_MSK.spend, "rub", BOTH, PLACEMENTS_FORMULA, RULE_PLACEMENTS),
    can_save: unavailable("rub", BOTH, "no_forecast", P7, RULE_PLACEMENTS),
    explanation: {
      text: `${NET_MSK.count} площадок РСЯ получили ${NET_MSK.clicks} кликов и ни одной конверсии за 7 дней. Проверьте площадки и исключите лишние вручную в настройках кампании в Директе. Сколько это сэкономит, заранее не оцениваем: Директ может перераспределить бюджет на другие площадки — оценим по факту после замера.`,
      source: "template",
    },
    action: demoPlacements(NET_MSK.count, "msk"),
    evidence: { facts: placementFacts(NET_MSK), meta: { baseline_data_quality: "high" }, rule_version: RULE_PLACEMENTS },
    safety: { safety_policy: POLICY, candidate_level: "review", policy_reasons: [], data_status: "complete" },
    limitations: [],
    execution: {
      ...noExecution,
      accepted_at: "2026-10-01T11:20:00+03:00",
      before_state: { captured_at: "accept", reliability: "normal", read_at: "2026-10-01T11:20:01+03:00", parameters: {} },
    },
    history: [
      { event: "created", at: "2026-09-30T07:03:40+03:00", actor: sys },
      { event: "delivered", at: "2026-09-30T09:00:02+03:00", actor: sys },
      { event: "viewed", at: "2026-10-01T11:18:00+03:00", actor: { user_id: "u_demo", name: USER.name } },
      { event: "accepted", at: "2026-10-01T11:20:00+03:00", actor: { user_id: "u_demo", name: USER.name } },
      { event: "seen_again", at: LAST_AUDIT_AT, actor: sys },
    ],
    created_at: "2026-09-30T07:03:40+03:00",
  }),
  rec({
    id: "rec_net02",
    version_id: "rv_net02_1",
    title: "Площадки РСЯ без конверсий",
    object: { type: "campaign", id: CAMPAIGNS[2].id, name: CAMPAIGNS[2].name },
    status: "new",
    action_level: "inspect_only",
    allowed_actions: [],
    exposure: estimated(NET_REG.spend, "rub", BOTH, PLACEMENTS_FORMULA, RULE_PLACEMENTS),
    can_save: unavailable("rub", BOTH, "no_forecast", P7, RULE_PLACEMENTS),
    explanation: {
      text: `На ${NET_REG.count} площадках были клики, но не было конверсий. Расхода пока мало для уверенного вывода: проверьте, что это за площадки и подходит ли их аудитория, прежде чем исключать.`,
      source: "template",
    },
    action: { type: "investigate", execution: "manual", topic: "zero_conv_placements", checks: ["placements_audience", "conversion_goals"] },
    evidence: { facts: placementFacts(NET_REG), meta: { baseline_data_quality: "low" }, rule_version: RULE_PLACEMENTS },
    safety: { safety_policy: POLICY, candidate_level: "review", policy_reasons: ["data_sufficiency_low"], data_status: "complete" },
    limitations: [],
    execution: noExecution,
    history: [{ event: "created", at: LAST_AUDIT_AT, actor: sys }],
    created_at: LAST_AUDIT_AT,
  }),
  // A held problem: the rule saw spend without conversions, but the volume is too small for a conclusion —
  // the card is shown, its sum is «Недостаточно данных» and it is not in the total.
  rec({
    id: "rec_zero01",
    version_id: "rv_zero01_1",
    title: "Расход без конверсий",
    object: { type: "campaign", id: CAMPAIGNS[3].id, name: CAMPAIGNS[3].name },
    status: "new",
    action_level: "inspect_only",
    allowed_actions: [],
    data_sufficiency: "insufficient",
    exposure: unavailable("rub", BOTH, "volume_insufficient", P7, RULE_ZERO),
    can_save: unavailable("rub", BOTH, "volume_insufficient", P7, RULE_ZERO),
    explanation: {
      text: `Кампания потратила ${CAMPAIGNS[3].spend} ₽ (${ZERO.clicks} кликов) за период без конверсий. Это ниже порога достаточного объёма ${ZERO.threshold} ₽, поэтому сумму не оцениваем и в итог не включаем — продолжаем наблюдать. Проверьте цели и учёт конверсий, стратегию, поисковые запросы и минус-фразы.`,
      source: "template",
    },
    action: { type: "investigate", execution: "manual", topic: "zero_conv_campaign", checks: ["conversion_goals", "strategy", "search_queries_negative_keywords"] },
    evidence: {
      facts: {
        cost: actual(CAMPAIGNS[3].spend, "rub", DIRECT),
        clicks: actual(ZERO.clicks, "count", DIRECT),
        conversions: actual(0, "count", "yandex_metrika"),
      },
      meta: {},
      rule_version: RULE_ZERO,
    },
    safety: { safety_policy: POLICY, candidate_level: "inspect_only", policy_reasons: [], data_status: "complete" },
    limitations: [],
    execution: noExecution,
    history: [{ event: "created", at: LAST_AUDIT_AT, actor: sys }],
    created_at: LAST_AUDIT_AT,
  }),
];

// --- September (Finance) ------------------------------------------------------------------------
// 30 days of deterministic pseudo-noise; days 25–30 are the first days of the demo week.
export const MONTH = Array.from({ length: 30 }, (_, i) => {
  const w = i - 24;
  if (w >= 0 && w < 6) return { day: i + 1, spend: WEEK.spend[w], exposure: WEEK.exposure[w] };
  const spend = 24_000 + ((i * 7919) % 6000) + (i > 21 ? 1500 : 0);
  const exposure = Math.round(spend * (0.18 + ((i * 31) % 13) / 100));
  return { day: i + 1, spend, exposure };
});
export const MONTH_VALUES = {
  spend: actual(sum(MONTH.map((d) => d.spend)), "rub", DIRECT, SEPTEMBER),
  exposure: estimated(sum(MONTH.map((d) => d.exposure)), "rub", BOTH, "Σ по дневным аудитам без двойного учёта", "exposure_total@1", SEPTEMBER),
  revenue: unavailable("rub", "yandex_metrika", "source_missing", SEPTEMBER),
};
export const CAMPAIGN_SHARES = CAMPAIGNS.map((c) => ({
  ...c,
  spendValue: actual(c.spend, "rub", DIRECT),
  share: actual((c.spend / KPI.spend) * 100, "pct", DIRECT, P7, { formula: "расход кампании / расход кабинета × 100" }),
}));

export const SYSTEM_LOG = [
  { date: "02.10 07:01", text: "Аудит: 3 правила v1.0, 5 рекомендаций, снимок #4815" },
  { date: "02.10 06:58", text: "Синхронизация Яндекс Директ: 4 кампании, 37 дней" },
  { date: "02.10 06:55", text: "Синхронизация Яндекс Метрика: 2 цели" },
  { date: "01.10 20:04", text: "Досинхронизация Яндекс Директ: без ошибок" },
];
