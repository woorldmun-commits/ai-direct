// DEMO data only: finished decision cycles from September, as the API would return them (Recommendation
// with history, execution and measurement). They feed «История решений» and «Сэкономлено ≈».

import type { HistoryEvent, Measurement, Recommendation } from "./contract";
import { AD_ACCOUNT, actual, estimated, USER } from "./demo";
import type { Period } from "./value";

const sys = "system" as const;
const me = { user_id: "u_demo", name: USER.name };
const DIRECT = "yandex_direct";
const BOTH = "yandex_direct+yandex_metrika";
const SAVED_FORMULA = "расход до − расход после, 7 дней, при той же цене клика";

const ev = (event: HistoryEvent["event"], at: string, actor: HistoryEvent["actor"] = me): HistoryEvent => ({ event, at, actor });

function measured(
  before: Period,
  after: Period,
  b: { cost: number; conv: number },
  a: { cost: number; conv: number },
  verdict: NonNullable<Measurement["verdict"]>,
  counts: boolean,
  saved?: number,
): Measurement {
  return {
    status: "measured",
    verdict,
    method: "uncontrolled_before_after",
    windows: { before, after },
    before: { cost: actual(b.cost, "rub", DIRECT, before), conversions: actual(b.conv, "count", "yandex_metrika", before) },
    after: { cost: actual(a.cost, "rub", DIRECT, after), conversions: actual(a.conv, "count", "yandex_metrika", after) },
    ...(saved !== undefined ? { saved: estimated(saved, "rub", BOTH, SAVED_FORMULA, "measurement@1", after) } : {}),
    counts_in_saved_total: counts,
  };
}

const base = {
  ad_account: AD_ACCOUNT,
  postponed_until: null,
  allowed_actions: [],
  blocked_actions: [],
  exposure_overlap: false,
  limitations: [],
};

function placements(id: string, campaign: { id: string; name: string }, count: number, spend: number, period: Period, created: string) {
  return {
    ...base,
    id,
    version_id: `rv_${id}_1`,
    title: "Площадки РСЯ без конверсий",
    object: { type: "campaign", id: campaign.id, name: campaign.name },
    action_level: "change" as const,
    exposure: estimated(spend, "rub", BOTH, "Σ расход площадок, где клики ≥ 50 и конверсии = 0", "zero_conv_placements@1", period),
    can_save: estimated(spend, "rub", BOTH, "Σ расход исключаемых площадок за период", "zero_conv_placements@1", period),
    explanation: { text: `${count} площадок РСЯ с кликами и без конверсий за 7 дней.`, source: "template" as const },
    action: { type: "exclude_placements", placements_count: count },
    evidence: {
      facts: { cost: actual(spend, "rub", DIRECT, period), conversions: actual(0, "count", "yandex_metrika", period), placements: actual(count, "count", DIRECT, period) },
      meta: {},
      rule_version: "zero_conv_placements@1",
    },
    safety: { safety_policy: "safety_policy@2", candidate_level: "change" as const, policy_reasons: [], data_status: "complete" as const },
    created_at: created,
  };
}

const MSK = { id: "51234568", name: "РСЯ · Москва" };
const REG = { id: "51234569", name: "РСЯ · Регионы" };
const SPB = { id: "51230001", name: "Поиск · Санкт-Петербург" };
const BRAND = { id: "51230002", name: "Поиск · Москва · Бренд" };

export const PAST_RECOMMENDATIONS: Recommendation[] = [
  {
    ...placements("rec_h01", MSK, 9, 21_200, { from: "2026-09-08", to: "2026-09-14" }, "2026-09-15T07:02:00+03:00"),
    status: "applied",
    execution: {
      execution_mode: "manual",
      verification_status: "confirmed",
      accepted_at: "2026-09-15T10:40:00+03:00",
      done_at: "2026-09-15T14:30:00+03:00",
      before_state: { captured_at: "accept", reliability: "normal", read_at: "2026-09-15T10:40:01+03:00", parameters: {} },
      verification_checked_at: "2026-09-16T07:05:00+03:00",
    },
    decision: { event: "manual_claimed", at: "2026-09-15T14:30:00+03:00", actor: me },
    measurement: measured(
      { from: "2026-09-08", to: "2026-09-14" },
      { from: "2026-09-16", to: "2026-09-22" },
      { cost: 21_200, conv: 0 },
      { cost: 0, conv: 0 },
      "effect",
      true,
      21_200,
    ),
    history: [
      ev("created", "2026-09-15T07:02:00+03:00", sys),
      ev("accepted", "2026-09-15T10:40:00+03:00"),
      ev("manual_claimed", "2026-09-15T14:30:00+03:00"),
      ev("verification_confirmed", "2026-09-16T07:05:00+03:00", sys),
      ev("measured", "2026-09-23T07:10:00+03:00", sys),
    ],
  },
  {
    ...placements("rec_h02", REG, 5, 9_800, { from: "2026-09-01", to: "2026-09-07" }, "2026-09-08T07:01:00+03:00"),
    status: "applied",
    execution: {
      execution_mode: "manual",
      verification_status: "confirmed",
      accepted_at: null,
      done_at: "2026-09-08T16:20:00+03:00",
      before_state: { captured_at: "mark_done_manually", reliability: "reduced", read_at: "2026-09-08T16:20:01+03:00", parameters: {} },
      verification_checked_at: "2026-09-09T07:04:00+03:00",
    },
    decision: { event: "manual_claimed", at: "2026-09-08T16:20:00+03:00", actor: me },
    measurement: measured(
      { from: "2026-09-01", to: "2026-09-07" },
      { from: "2026-09-09", to: "2026-09-15" },
      { cost: 9_800, conv: 0 },
      { cost: 0, conv: 0 },
      "effect",
      true,
      9_800,
    ),
    history: [
      ev("created", "2026-09-08T07:01:00+03:00", sys),
      ev("manual_claimed", "2026-09-08T16:20:00+03:00"),
      ev("verification_confirmed", "2026-09-09T07:04:00+03:00", sys),
      ev("measured", "2026-09-16T07:09:00+03:00", sys),
    ],
  },
  {
    ...base,
    id: "rec_h03",
    version_id: "rv_h03_1",
    title: "Расход без конверсий",
    object: { type: "campaign", ...SPB },
    status: "applied",
    action_level: "review",
    exposure: estimated(14_600, "rub", BOTH, "cost при conversions = 0 и достаточном объёме кликов", "zero_conv_campaign@1", { from: "2026-09-11", to: "2026-09-17" }),
    can_save: estimated(14_600, "rub", BOTH, "cost за период", "zero_conv_campaign@1", { from: "2026-09-11", to: "2026-09-17" }),
    explanation: { text: "Кампания тратила бюджет без конверсий при достаточном числе кликов. Проверьте цель конверсии и корректность разметки.", source: "template" },
    action: { type: "review_conversion_goal" },
    evidence: {
      facts: { cost: actual(14_600, "rub", DIRECT, { from: "2026-09-11", to: "2026-09-17" }), conversions: actual(0, "count", "yandex_metrika", { from: "2026-09-11", to: "2026-09-17" }) },
      meta: {},
      rule_version: "zero_conv_campaign@1",
    },
    safety: { safety_policy: "safety_policy@2", candidate_level: "review", policy_reasons: [], data_status: "complete" },
    execution: {
      execution_mode: "manual",
      verification_status: "not_confirmed",
      accepted_at: "2026-09-18T09:30:00+03:00",
      done_at: "2026-09-19T12:00:00+03:00",
      before_state: { captured_at: "accept", reliability: "normal", read_at: "2026-09-18T09:30:01+03:00", parameters: {} },
      verification_checked_at: "2026-09-21T07:03:00+03:00",
    },
    decision: { event: "manual_claimed", at: "2026-09-19T12:00:00+03:00", actor: me },
    measurement: measured(
      { from: "2026-09-11", to: "2026-09-17" },
      { from: "2026-09-20", to: "2026-09-26" },
      { cost: 14_600, conv: 0 },
      { cost: 13_900, conv: 0 },
      "no_effect",
      false,
    ),
    history: [
      ev("created", "2026-09-18T07:02:00+03:00", sys),
      ev("accepted", "2026-09-18T09:30:00+03:00"),
      ev("manual_claimed", "2026-09-19T12:00:00+03:00"),
      ev("verification_not_confirmed", "2026-09-21T07:03:00+03:00", sys),
      ev("measured", "2026-09-27T07:08:00+03:00", sys),
    ],
    created_at: "2026-09-18T07:02:00+03:00",
  },
  {
    ...base,
    id: "rec_h04",
    version_id: "rv_h04_1",
    title: "CPA выше цели на 40%",
    object: { type: "campaign", ...BRAND },
    status: "applied",
    action_level: "change",
    exposure: estimated(8_400, "rub", BOTH, "(cpa − target_cpa) × conversions", "high_cpa_target@1", { from: "2026-09-19", to: "2026-09-25" }),
    can_save: estimated(3_150, "rub", BOTH, "cost × |change_pct| / 100", "high_cpa_target@1", { from: "2026-09-19", to: "2026-09-25" }),
    explanation: { text: "CPA бренд-кампании на 40% выше цели при достаточном числе конверсий.", source: "template" },
    action: { type: "decrease_bid", change_pct: "-10.00" },
    evidence: {
      facts: {
        cpa: actual(4_200, "rub", BOTH, { from: "2026-09-19", to: "2026-09-25" }, { formula: "cost / conversions" }),
        target_cpa: actual(3_000, "rub", "user_input", { from: "2026-09-19", to: "2026-09-25" }),
      },
      meta: {},
      rule_version: "high_cpa_target@1",
    },
    safety: { safety_policy: "safety_policy@2", candidate_level: "change", policy_reasons: [], data_status: "complete" },
    execution: {
      execution_mode: "manual",
      verification_status: "confirmed",
      accepted_at: "2026-09-26T10:05:00+03:00",
      done_at: "2026-09-27T09:40:00+03:00",
      before_state: { captured_at: "accept", reliability: "normal", read_at: "2026-09-26T10:05:01+03:00", parameters: {} },
      verification_checked_at: "2026-09-28T07:02:00+03:00",
    },
    decision: { event: "manual_claimed", at: "2026-09-27T09:40:00+03:00", actor: me },
    measurement: {
      status: "pending",
      verdict: null,
      method: "uncontrolled_before_after",
      windows: { before: { from: "2026-09-19", to: "2026-09-25" }, after: { from: "2026-09-28", to: "2026-10-04" } },
      before: {},
      after: {},
      counts_in_saved_total: false,
    },
    history: [
      ev("created", "2026-09-26T07:01:00+03:00", sys),
      ev("accepted", "2026-09-26T10:05:00+03:00"),
      ev("manual_claimed", "2026-09-27T09:40:00+03:00"),
      ev("verification_confirmed", "2026-09-28T07:02:00+03:00", sys),
    ],
    created_at: "2026-09-26T07:01:00+03:00",
  },
  {
    ...placements("rec_h05", REG, 4, 2_900, { from: "2026-09-13", to: "2026-09-19" }, "2026-09-20T07:02:00+03:00"),
    status: "rejected",
    execution: { execution_mode: null, verification_status: null, accepted_at: null, done_at: null, before_state: null, verification_checked_at: null },
    decision: { event: "rejected", reason: "irrelevant_rule", comment: "Площадки партнёрские, оставляем для охвата", at: "2026-09-20T11:15:00+03:00", actor: me },
    measurement: null,
    history: [ev("created", "2026-09-20T07:02:00+03:00", sys), ev("viewed", "2026-09-20T11:10:00+03:00"), ev("rejected", "2026-09-20T11:15:00+03:00")],
  },
];
