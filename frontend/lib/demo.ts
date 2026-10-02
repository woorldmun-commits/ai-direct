// DEMO data only. Every derived figure is computed here, never typed by hand,
// so totals on different screens always agree.

export type Priority = "critical" | "medium" | "low";
export type Platform = "search" | "network";
export type Quality = "Высокая" | "Средняя" | "Низкая";
export type RecStatus = "new" | "in_progress" | "done" | "postponed" | "rejected";

export interface Problem {
  id: string;
  priority: Priority;
  campaign: string;
  platform: Platform;
  title: string;
  reason: string;
  /** Estimated spend with signs of inefficiency (internal name kept, API calls it `exposure`). */
  loss: number;
  /** "campaign" covers the whole campaign's spend; "object" covers part of it (placements, queries). */
  level: "campaign" | "object";
  recommendation: string;
  action: string;
  days: number;
  conversions: number;
  quality: Quality;
  facts: { label: string; value: string }[];
  calc: string;
  rule: string;
  checks: string[];
  ai: string;
  status: RecStatus;
}

export const PERIOD = "23–29 сентября";
export const PREV_PERIOD = "16–22 сентября";
export const DAYS = ["23", "24", "25", "26", "27", "28", "29"];
export const SYNC = { direct: "10:42", metrika: "10:38", date: "30 сентября 2026" };
export const USER = { name: "Алексей", account: "Демо-аккаунт" };

export const TARGET_CPA = 3000;

// Bid rule: step down 5% per full 20% of CPA deviation above target.
export function bidCut(deviationPct: number): number {
  return Math.floor(deviationPct / 20) * 5;
}

function fmt(n: number) {
  return new Intl.NumberFormat("ru-RU").format(n);
}

export const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

const CPA_SEARCH = 5250;
const CONV_SEARCH = 19;
const DEV = Math.round(((CPA_SEARCH - TARGET_CPA) / TARGET_CPA) * 100);
const CUT = bidCut(DEV);

export const CAMPAIGNS = [
  { name: "Поиск · Москва · Услуги", platform: "search" as Platform, spend: CPA_SEARCH * CONV_SEARCH, conversions: CONV_SEARCH },
  { name: "РСЯ · Москва", platform: "network" as Platform, spend: 41_300, conversions: 9 },
  { name: "Поиск · Регионы", platform: "search" as Platform, spend: 43_150, conversions: 19 },
];

export const PROBLEMS: Problem[] = [
  {
    id: "cpa",
    priority: "critical",
    campaign: CAMPAIGNS[0].name,
    platform: "search",
    title: "CPA выше целевого уровня",
    reason: `CPA ${fmt(CPA_SEARCH)} ₽ при цели ${fmt(TARGET_CPA)} ₽ — на ${DEV}% выше`,
    loss: (CPA_SEARCH - TARGET_CPA) * CONV_SEARCH,
    level: "campaign",
    recommendation: `Снизить ставку на ${CUT}%`,
    action: "Снизить ставку",
    days: 7,
    conversions: CONV_SEARCH,
    quality: "Высокая",
    facts: [
      { label: "CPA", value: `${fmt(CPA_SEARCH)} ₽` },
      { label: "Цель", value: `${fmt(TARGET_CPA)} ₽` },
      { label: "Отклонение", value: `+${DEV}%` },
    ],
    calc: `floor(${DEV} / 20) × 5% = ${CUT}%`,
    rule: "bid_cpa v3",
    checks: ["7 дней данных", `${CONV_SEARCH} конверсий (нужно ≥ 10)`],
    ai: `За неделю конверсия в этой кампании стоила ${fmt(CPA_SEARCH)} ₽ — на ${DEV}% дороже цели. Снижение ставки на ${CUT}% уменьшит цену клика; через 7 дней система сравнит CPA до и после.`,
    status: "new",
  },
  {
    id: "network",
    priority: "medium",
    campaign: CAMPAIGNS[1].name,
    platform: "network",
    title: "Расход без конверсий",
    reason: "14 площадок РСЯ: 1 860 кликов, 0 конверсий за 7 дней",
    loss: 12_400,
    level: "object",
    recommendation: "Исключить 14 площадок без конверсий",
    action: "Исключить площадки",
    days: 7,
    conversions: 0,
    quality: "Высокая",
    facts: [
      { label: "Расход", value: "12 400 ₽" },
      { label: "Клики", value: "1 860" },
      { label: "Конверсии", value: "0" },
    ],
    calc: "Σ расход площадок, где клики ≥ 50 и конверсии = 0",
    rule: "zero_conv_placements v2",
    checks: ["7 дней данных", "1 860 кликов (нужно ≥ 50 на площадку)"],
    ai: "Эти площадки получили заметное число кликов, но ни одной конверсии. Исключение остановит расход на них; остальная часть РСЯ продолжит работать.",
    status: "new",
  },
  {
    id: "queries",
    priority: "low",
    campaign: CAMPAIGNS[2].name,
    platform: "search",
    title: "Нерелевантные запросы",
    reason: "23 запроса с расходом и без конверсий",
    loss: 3_800,
    level: "object",
    recommendation: "Добавить 23 минус-слова",
    action: "Проверить запросы",
    days: 7,
    conversions: 0,
    quality: "Средняя",
    facts: [
      { label: "Расход", value: "3 800 ₽" },
      { label: "Запросы", value: "23" },
      { label: "Конверсии", value: "0" },
    ],
    calc: "Σ расход запросов без конверсий за период",
    rule: "irrelevant_queries v1",
    checks: ["7 дней данных", "Часть запросов скрыта Директом — данные неполные"],
    ai: "По этим запросам были клики без конверсий. Проверьте список перед добавлением минус-слов: часть запросов может быть полезной.",
    status: "in_progress",
  },
];

export const WEEK = {
  spend: [25_400, 26_100, 27_800, 26_300, 25_900, 27_200, 25_500],
  conversions: [7, 6, 7, 6, 7, 8, 6],
  losses: [7_900, 8_300, 9_100, 8_400, 8_200, 9_050, 8_000],
};
export const PREV_WEEK = {
  spend: [24_100, 24_800, 25_300, 24_200, 24_700, 24_400, 24_100],
  conversions: [8, 8, 8, 7, 8, 8, 8],
  losses: [5_600, 5_900, 6_100, 5_800, 6_000, 6_100, 5_800],
};

function totals(w: typeof WEEK) {
  const spend = sum(w.spend);
  const conversions = sum(w.conversions);
  return {
    spend,
    conversions,
    losses: sum(w.losses),
    cpa: Math.round(spend / conversions),
    cpaDaily: w.spend.map((s, i) => Math.round(s / w.conversions[i])),
  };
}

export const KPI = totals(WEEK);
export const PREV_KPI = totals(PREV_WEEK);

/**
 * Total without double counting (mirrors exposure_total@1): a campaign-level finding already covers
 * the campaign's spend, so object-level findings in the same campaign are not added on top of it.
 * The demo has one finding per campaign, so overlap is 0, but the arithmetic always adds up:
 * sum(cards) − overlap = total.
 */
export function exposureTotal(problems: Problem[]): { total: number; cards: number; overlap: number; covered: Set<string> } {
  const cards = sum(problems.map((p) => p.loss));
  const covered = new Set<string>();
  let total = 0;
  for (const camp of new Set(problems.map((p) => p.campaign))) {
    const items = problems.filter((p) => p.campaign === camp);
    const top = items.filter((p) => p.level === "campaign").sort((a, b) => b.loss - a.loss)[0];
    if (top) {
      total += top.loss;
      items.filter((p) => p !== top).forEach((p) => covered.add(p.id));
    } else {
      total += sum(items.map((p) => p.loss));
    }
  }
  return { total, cards, overlap: cards - total, covered };
}

export const TOTAL_LOSS = exposureTotal(PROBLEMS).total;
// "Можно сэкономить": findings backed by a high-confidence recommendation, deduplicated the same way.
export const RECOVERABLE = exposureTotal(PROBLEMS.filter((p) => p.quality === "Высокая")).total;

export const SAVINGS = [
  { title: "Исключены 9 площадок РСЯ", campaign: "РСЯ · Москва", value: 21_200, period: "15–21 сентября" },
  { title: "Добавлены 17 минус-слов", campaign: "Поиск · Регионы", value: 9_800, period: "8–14 сентября" },
];
export const SAVED = sum(SAVINGS.map((s) => s.value));

// 30 days of September, deterministic pseudo-noise.
// Days 23–29 are the demo week itself, so the chart agrees with WEEK.
export const MONTH = Array.from({ length: 30 }, (_, i) => {
  const w = i - 22;
  if (w >= 0 && w < WEEK.spend.length) return { day: i + 1, spend: WEEK.spend[w], loss: WEEK.losses[w] };
  const spend = 24_000 + ((i * 7919) % 6000) + (i > 21 ? 1500 : 0);
  const loss = Math.round(spend * (0.18 + ((i * 31) % 13) / 100));
  return { day: i + 1, spend, loss };
});
export const MONTH_SPEND = sum(MONTH.map((d) => d.spend));
export const MONTH_LOSS = sum(MONTH.map((d) => d.loss));

export type HistoryKind = "found" | "rec" | "action" | "measure";
export const HISTORY: { date: string; kind: HistoryKind; title: string; detail: string; amount?: number }[] = [
  { date: "30 сентября, 10:45", kind: "found", title: "Найдена проблема: CPA выше цели", detail: `${CAMPAIGNS[0].name} · ${PERIOD}`, amount: PROBLEMS[0].loss },
  { date: "30 сентября, 10:45", kind: "rec", title: `Создана рекомендация: снизить ставку на ${CUT}%`, detail: "Правило bid_cpa v3 · уверенность высокая" },
  { date: "22 сентября, 09:12", kind: "measure", title: "Замер эффекта: исключение площадок РСЯ", detail: "Расчётный эффект · 7 дней до и после, без контрольной группы", amount: SAVINGS[0].value },
  { date: "15 сентября, 14:30", kind: "action", title: "Вы исключили 9 площадок РСЯ", detail: "Изменение внесено вручную в Яндекс Директе" },
  { date: "15 сентября, 10:40", kind: "rec", title: "Создана рекомендация: исключить 9 площадок", detail: "Правило zero_conv_placements v2" },
  { date: "15 сентября, 09:05", kind: "measure", title: "Замер эффекта: минус-слова", detail: "Расчётный эффект · 7 дней до и после, без контрольной группы", amount: SAVINGS[1].value },
  { date: "8 сентября, 16:20", kind: "action", title: "Вы добавили 17 минус-слов", detail: "Поиск · Регионы" },
];

export const SYSTEM_LOG = [
  { date: "30.09 10:45", text: "Rule engine 3.2: 3 проблемы, снимок #4815" },
  { date: "30.09 10:42", text: "Синхронизация Яндекс Директ: 3 кампании, 7 дней" },
  { date: "30.09 10:38", text: "Синхронизация Яндекс Метрика: 2 цели" },
  { date: "29.09 10:41", text: "Синхронизация Яндекс Директ: без ошибок" },
];

export const PRIORITY_LABEL: Record<Priority, string> = {
  critical: "Критичная",
  medium: "Средняя",
  low: "Низкая",
};

export const STATUS_LABEL: Record<RecStatus, string> = {
  new: "Новая",
  in_progress: "В работе",
  done: "Выполнена",
  postponed: "Отложена",
  rejected: "Отклонена",
};
