// DEMO DATA — development only. Never shown as real figures: every screen carries the «Демо-данные» badge.
// In production these numbers come from the backend (rules/ and audit/); the frontend never computes them.

import type { Campaign, Client, Kpi, MetricValue, Period, SeriesPoint, Source, Unit } from "@/lib/types/domain";

export const SNAPSHOT = "snap_2026-10-01_4815";

export const P7: Period = { from: "2026-09-25", to: "2026-10-01", label: "последние 7 дней" };
export const P30: Period = { from: "2026-09-02", to: "2026-10-01", label: "последние 30 дней" };

type Opts = { source?: Source[]; period?: Period; rule?: string | null; partial?: boolean; kind?: MetricValue["money_kind"] };

function base(unit: Unit, o: Opts) {
  return {
    unit,
    source: o.source ?? (["yandex_direct"] as Source[]),
    period: o.period ?? P7,
    data_status: o.partial ? ("partial" as const) : ("complete" as const),
    rule_version: o.rule ?? null,
    snapshot_id: SNAPSHOT,
    money_kind: o.kind,
  };
}

export const actual = (amount: number, unit: Unit, o: Opts = {}): MetricValue => ({
  ...base(unit, o),
  calculation_type: "actual",
  amount,
  data_sufficiency: "sufficient",
  formula: null,
});
export const estimated = (amount: number, unit: Unit, formula: string, o: Opts = {}): MetricValue => ({
  ...base(unit, o),
  calculation_type: "estimated",
  amount,
  data_sufficiency: "sufficient",
  formula,
});
export const unavailable = (unit: Unit, missing: string, o: Opts = {}): MetricValue => ({
  ...base(unit, o),
  calculation_type: "unavailable",
  amount: null,
  data_sufficiency: "insufficient",
  formula: null,
  missing,
});

export const CLIENTS: Client[] = [
  { id: "romashka", name: "ООО «Ромашка»", accounts: 3, projects: 3, spend: 900_950, problems: 3, recommendations: 2, status: "attention" },
  { id: "planeta", name: "ООО «Планета»", accounts: 2, projects: 2, spend: 586_600, problems: 2, recommendations: 2, status: "active" },
  { id: "vkusno", name: "Сеть магазинов «Вкусно»", accounts: 2, projects: 3, spend: 443_800, problems: 2, recommendations: 2, status: "attention" },
  { id: "stil", name: "Интернет-магазин «Стиль»", accounts: 1, projects: 1, spend: 468_050, problems: 1, recommendations: 1, status: "active" },
  { id: "ivanov", name: "ИП Иванов", accounts: 1, projects: 1, spend: 82_600, problems: 1, recommendations: 0, status: "active" },
];

type Row = [id: string, name: string, client: string, account: string, status: Campaign["status"], spend: number, impressions: number, clicks: number, conv: number, problems: number];
const ROWS: Row[] = [
  ["c-msk", "Поиск — Москва", "romashka", "romashka-direct", "active", 412_250, 210_000, 9_800, 85, 1],
  ["c-rsya-msk", "РСЯ — Москва", "romashka", "romashka-direct", "active", 186_400, 1_240_000, 7_450, 212, 0],
  ["c-regions", "Поиск — Регионы", "romashka", "romashka-regions", "active", 238_000, 150_000, 6_900, 410, 1],
  ["c-retarget", "Ретаргетинг", "romashka", "romashka-rtg", "active", 64_300, 380_000, 2_100, 160, 1],
  ["c-brand", "Брендовые запросы", "planeta", "planeta-main", "limited", 92_100, 48_000, 5_600, 520, 1],
  ["c-goods", "Товарная кампания", "planeta", "planeta-main", "active", 318_000, 960_000, 14_200, 690, 1],
  ["c-spb", "Поиск — Санкт-Петербург", "planeta", "planeta-spb", "active", 176_500, 98_000, 4_300, 205, 0],
  ["c-leads", "Поиск — Лиды", "vkusno", "vkusno-direct", "active", 141_000, 86_000, 8_400, 260, 0],
  ["c-delivery", "Поиск — Доставка", "vkusno", "vkusno-direct", "active", 205_000, 120_000, 6_100, 330, 1],
  ["c-promo", "РСЯ — Акции", "vkusno", "vkusno-rsya", "active", 97_800, 890_000, 3_900, 0, 1],
  ["c-master", "Мастер кампаний", "stil", "stil-direct", "active", 263_000, 1_500_000, 11_800, 412, 0],
  ["c-catalog", "Поиск — Каталог", "stil", "stil-direct", "active", 121_400, 70_000, 3_800, 196, 0],
  ["c-smart", "Смарт-баннеры", "stil", "stil-direct", "paused", 83_650, 610_000, 2_700, 100, 1],
  ["c-services", "Поиск — Услуги", "ivanov", "ivanov-direct", "active", 58_700, 31_000, 1_450, 64, 0],
  ["c-reach", "РСЯ — Охват", "ivanov", "ivanov-direct", "active", 23_900, 420_000, 950, 6, 1],
];

/** Below this many conversions CPA is not shown as a number (safety: data sufficiency). */
export const MIN_CONVERSIONS = 10;

export const CAMPAIGNS: Campaign[] = ROWS.map(([id, name, client_id, account, status, spend, impressions, clicks, conversions, problems]) => ({
  id,
  name,
  client_id,
  account,
  status,
  spend,
  impressions,
  clicks,
  ctr: Math.round((clicks / impressions) * 1000) / 10,
  conversions,
  cpa: conversions >= MIN_CONVERSIONS ? Math.round(spend / conversions) : null,
  problems,
}));

const sumOf = (k: "spend" | "clicks" | "impressions" | "conversions") => CAMPAIGNS.reduce((a, c) => a + c[k], 0);
export const TOTALS = {
  spend: sumOf("spend"),
  clicks: sumOf("clicks"),
  impressions: sumOf("impressions"),
  conversions: sumOf("conversions"),
};

const M30 = { period: P30 };
export const TODAY_KPIS: Kpi[] = [
  { id: "spend", label: "Расход", value: actual(TOTALS.spend, "rub", { ...M30, kind: "spend" }), delta: 12 },
  {
    id: "at_risk",
    label: "Потенциально неэффективно",
    value: estimated(112_000, "rub", "Σ под риском по находкам без пересечений (без двойного учёта)", {
      ...M30,
      source: ["yandex_direct", "yandex_metrika"],
      kind: "at_risk",
    }),
    delta: -6,
    goodWhenDown: true,
  },
  { id: "cpa", label: "CPA", value: actual(Math.round(TOTALS.spend / TOTALS.conversions), "rub", { ...M30, source: ["yandex_direct", "yandex_metrika"] }), delta: -8, goodWhenDown: true },
  { id: "conv", label: "Конверсии", value: actual(TOTALS.conversions, "count", { ...M30, source: ["yandex_metrika"] }), delta: 18 },
];

export const ANALYTICS_KPIS: Kpi[] = [
  TODAY_KPIS[0],
  TODAY_KPIS[2],
  { id: "ctr", label: "CTR", value: actual(Math.round((TOTALS.clicks / TOTALS.impressions) * 1000) / 10, "pct", M30), delta: 4 },
  TODAY_KPIS[3],
  {
    id: "cr",
    label: "Конверсия в заявку",
    value: actual(Math.round((TOTALS.conversions / TOTALS.clicks) * 1000) / 10, "pct", { ...M30, source: ["yandex_direct", "yandex_metrika"] }),
    delta: 6,
  },
  {
    id: "roi",
    label: "ROI",
    value: unavailable("pct", "Нет данных о выручке: передайте доход в цели Метрики или загрузите данные CRM.", M30),
    delta: null,
  },
];

// Deterministic demo series for 90 days, scaled so the last 30 days add up to TOTALS.
function wave(i: number, seed: number) {
  return Math.sin(i / 3.1 + seed) * 0.09 + Math.sin(i / 7.3 + seed * 2) * 0.06 + Math.cos(i / 1.7 + seed) * 0.03;
}
function buildSeries(): SeriesPoint[] {
  const days = 90;
  const end = new Date("2026-10-01");
  const raw = Array.from({ length: days * 2 }, (_, i) => {
    const trend = 0.82 + (i / (days * 2)) * 0.3;
    return { s: trend * (1 + wave(i, 1)), c: trend * (1 + wave(i, 2.4)) * (i > days * 2 - 20 ? 1.06 : 1) };
  });
  const last30 = raw.slice(-30);
  const ks = TOTALS.spend / last30.reduce((a, r) => a + r.s, 0);
  const kc = TOTALS.conversions / last30.reduce((a, r) => a + r.c, 0);
  return Array.from({ length: days }, (_, i) => {
    const cur = raw[days + i];
    const prev = raw[i];
    const d = new Date(end);
    d.setDate(end.getDate() - (days - 1 - i));
    const spend = Math.round(cur.s * ks);
    const conversions = Math.max(1, Math.round(cur.c * kc));
    const prevSpend = Math.round(prev.s * ks * 0.9);
    const prevConversions = Math.max(1, Math.round(prev.c * kc * 0.85));
    return {
      date: d.toISOString().slice(0, 10),
      spend,
      conversions,
      cpa: Math.round(spend / conversions),
      prevSpend,
      prevConversions,
      prevCpa: Math.round(prevSpend / prevConversions),
    };
  });
}
export const SERIES = buildSeries();

export const TARGET_CPA = 700;

/** Spend share by account type for the sources donut (Яндекс Директ only — other platforms are not connected). */
export const SPEND_BY_TYPE = [
  { name: "Поиск", value: CAMPAIGNS.filter((c) => c.name.startsWith("Поиск") || c.name.startsWith("Бренд")).reduce((a, c) => a + c.spend, 0) },
  { name: "РСЯ", value: CAMPAIGNS.filter((c) => c.name.startsWith("РСЯ") || c.name.startsWith("Смарт")).reduce((a, c) => a + c.spend, 0) },
  { name: "Товарные и мастер", value: CAMPAIGNS.filter((c) => c.name.startsWith("Товар") || c.name.startsWith("Мастер")).reduce((a, c) => a + c.spend, 0) },
  { name: "Ретаргетинг", value: CAMPAIGNS.filter((c) => c.name.startsWith("Ретар")).reduce((a, c) => a + c.spend, 0) },
];

/** The money model on «Сегодня»: separate kinds, never summed into one «lost» figure. Computed by the backend. */
export const MONEY = {
  spend: TODAY_KPIS[0].value,
  at_risk: TODAY_KPIS[1].value,
  recoverable: estimated(46_300, "rub", "Σ ожидаемого эффекта рекомендаций, которые можно применить (без пересечений)", { period: P30, source: ["yandex_direct", "yandex_metrika"], kind: "recoverable" }),
};

/** Campaign-level KPIs as the backend would return them. */
export function campaignKpis(id: string): Kpi[] {
  const c = CAMPAIGNS.find((x) => x.id === id);
  if (!c) return [];
  const DM: Source[] = ["yandex_direct", "yandex_metrika"];
  return [
    { id: "spend", label: "Расход", value: actual(c.spend, "rub", { period: P30, kind: "spend" }), delta: null },
    { id: "conv", label: "Конверсии", value: actual(c.conversions, "count", { period: P30, source: ["yandex_metrika"] }), delta: null },
    {
      id: "cpa",
      label: "CPA",
      value: c.cpa === null ? unavailable("rub", `За период ${c.conversions} конверсий, нужно минимум ${MIN_CONVERSIONS}.`, { period: P30, source: DM }) : actual(c.cpa, "rub", { period: P30, source: DM }),
      delta: null,
    },
    { id: "ctr", label: "CTR", value: actual(c.ctr, "pct", { period: P30 }), delta: null },
  ];
}

/** Demo daily spend for one campaign: the account series scaled by the campaign's share. */
export function campaignSeries(id: string) {
  const c = CAMPAIGNS.find((x) => x.id === id);
  const share = c ? c.spend / TOTALS.spend : 0;
  return SERIES.slice(-30).map((p) => ({ date: p.date, spend: Math.round(p.spend * share) }));
}
