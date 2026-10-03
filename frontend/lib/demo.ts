// DEMO data only. Every derived figure is computed here, never typed by hand,
// so totals on different screens always agree.

export type Priority = "critical" | "medium" | "low";
export type Platform = "search" | "network";
export type Quality = "Высокая" | "Средняя" | "Низкая";
// PRD §5 states that matter in a single-owner demo. "checked" closes a «проверить» recommendation.
export type RecStatus = "new" | "needs_decision" | "applied" | "checked" | "postponed" | "rejected";
/** apply — the change can go through the API on complete data; check — data is thin, a human verifies. */
export type RecKind = "apply" | "check";

export interface Problem {
  id: string;
  priority: Priority;
  campaign: string;
  platform: Platform;
  title: string;
  reason: string;
  loss: number;
  saveable: number;
  recommendation: string;
  action: string;
  kind: RecKind;
  change?: { what: string; before: string; after: string };
  days: number;
  conversions: number;
  quality: Quality;
  facts: { label: string; value: string }[];
  calc: string;
  rule: string;
  checks: string[];
  limits: string;
  ai: string;
  status: RecStatus;
}

export const PERIOD = "23–29 сентября";
export const PREV_PERIOD = "16–22 сентября";
export const DAYS = ["23", "24", "25", "26", "27", "28", "29"];
export const SYNC = { direct: "10:42", metrika: "10:38", date: "30 сентября 2026" };
export const SNAPSHOT = { id: "4815", engine: "3.2.0" };
export const USER = { name: "Алексей", account: "Демо-аккаунт", workspace: "ООО «Пример»" };

export const TARGET_CPA = 3000;

// Bid rule: step down 5% per full 20% of CPA deviation above target.
export function bidCut(deviationPct: number): number {
  return Math.floor(deviationPct / 20) * 5;
}

function fmt(n: number) {
  return new Intl.NumberFormat("ru-RU").format(n);
}
function fmt2(n: number) {
  return new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);

const CPA_SEARCH = 5250;
const CONV_SEARCH = 19;
const DEV = Math.round(((CPA_SEARCH - TARGET_CPA) / TARGET_CPA) * 100);
const CUT = bidCut(DEV);
const BID = 42;

export const CAMPAIGNS = [
  { name: "Поиск · Москва · Услуги", platform: "search" as Platform, spend: CPA_SEARCH * CONV_SEARCH, conversions: CONV_SEARCH, clicks: 2_310 },
  { name: "РСЯ · Москва", platform: "network" as Platform, spend: 41_300, conversions: 9, clicks: 6_940 },
  { name: "Поиск · Регионы", platform: "search" as Platform, spend: 43_150, conversions: 19, clicks: 2_080 },
];

export const PROBLEMS: Problem[] = [
  {
    id: "cpa",
    priority: "critical",
    campaign: CAMPAIGNS[0].name,
    platform: "search",
    title: "CPA выше целевого",
    reason: `CPA ${fmt(CPA_SEARCH)} ₽ при цели ${fmt(TARGET_CPA)} ₽ — на ${DEV}% выше`,
    loss: (CPA_SEARCH - TARGET_CPA) * CONV_SEARCH,
    saveable: Math.round(CPA_SEARCH * CONV_SEARCH * (CUT / 100)),
    recommendation: `Снизить ставку на ${CUT}%`,
    action: "Снизить ставку",
    kind: "apply",
    change: { what: "Максимальная ставка", before: `${fmt2(BID)} ₽`, after: `${fmt2(BID * (1 - CUT / 100))} ₽` },
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
    checks: ["7 полных дней данных", `${CONV_SEARCH} конверсий (нужно ≥ 10)`],
    limits: "Оценка исходит из того, что цена клика снизится пропорционально ставке. Сезонность не учитывается.",
    ai: `За неделю конверсия в этой кампании стоила ${fmt(CPA_SEARCH)} ₽ — на ${DEV}% дороже цели. Снижение ставки на ${CUT}% уменьшит цену клика; через 7 дней система сравнит CPA до и после.`,
    status: "needs_decision",
  },
  {
    id: "network",
    priority: "medium",
    campaign: CAMPAIGNS[1].name,
    platform: "network",
    title: "Расход без конверсий",
    reason: "14 площадок РСЯ: 1 860 кликов, 0 конверсий за 7 дней",
    loss: 12_400,
    saveable: 12_400,
    recommendation: "Исключить 14 площадок без конверсий",
    action: "Исключить площадки",
    kind: "apply",
    change: { what: "Площадки РСЯ без конверсий", before: "14 показываются", after: "14 исключены" },
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
    checks: ["7 полных дней данных", "1 860 кликов (нужно ≥ 50 на площадку)"],
    limits: "Площадка может приводить отложенные конверсии вне окна 7 дней.",
    ai: "Эти площадки получили заметное число кликов, но ни одной конверсии. Исключение остановит расход на них; остальная часть РСЯ продолжит работать.",
    status: "needs_decision",
  },
  {
    id: "queries",
    priority: "low",
    campaign: CAMPAIGNS[2].name,
    platform: "search",
    title: "Нерелевантные запросы",
    reason: "23 запроса с расходом и без конверсий",
    loss: 3_800,
    saveable: 0,
    recommendation: "Проверить 23 запроса и добавить минус-слова",
    action: "Проверить запросы",
    kind: "check",
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
    limits: "Директ показывает не все запросы, поэтому применение через API отключено: нужна ручная проверка.",
    ai: "По этим запросам были клики без конверсий. Проверьте список перед добавлением минус-слов: часть запросов может быть полезной.",
    status: "new",
  },
];

export const WEEK = {
  spend: [25_400, 26_100, 27_800, 26_300, 25_900, 27_200, 25_500],
  conversions: [7, 6, 7, 6, 7, 8, 6],
  losses: [7_900, 8_300, 9_100, 8_400, 8_200, 9_050, 8_000],
  clicks: [1_610, 1_640, 1_720, 1_650, 1_600, 1_690, 1_620],
  impressions: [41_200, 42_000, 44_100, 42_600, 41_900, 43_300, 41_700],
};
export const PREV_WEEK = {
  spend: [24_100, 24_800, 25_300, 24_200, 24_700, 24_400, 24_100],
  conversions: [8, 8, 8, 7, 8, 8, 8],
  losses: [5_600, 5_900, 6_100, 5_800, 6_000, 6_100, 5_800],
  clicks: [1_640, 1_660, 1_700, 1_630, 1_650, 1_640, 1_620],
  impressions: [40_100, 40_600, 41_300, 39_800, 40_400, 40_200, 39_900],
};

function totals(w: typeof WEEK) {
  const spend = sum(w.spend);
  const conversions = sum(w.conversions);
  const clicks = sum(w.clicks);
  return {
    spend,
    conversions,
    clicks,
    losses: sum(w.losses),
    cpa: Math.round(spend / conversions),
    ctr: Math.round((clicks / sum(w.impressions)) * 1000) / 10,
    cpaDaily: w.spend.map((s, i) => Math.round(s / w.conversions[i])),
  };
}

export const KPI = totals(WEEK);
export const PREV_KPI = totals(PREV_WEEK);

export const TOTAL_LOSS = sum(PROBLEMS.map((p) => p.loss));
/** «Можно сэкономить ≈» — forecast backed only by `apply` recommendations. */
export const SAVEABLE = sum(PROBLEMS.map((p) => p.saveable));

/** Measured 7 days after a human decision; spend before minus spend after, conversions held. */
export const MEASURES = [
  {
    id: "m-network",
    title: "Исключены 9 площадок РСЯ",
    campaign: "РСЯ · Москва",
    decided: "15.09",
    window: "15–21 сентября",
    rule: "zero_conv_placements v2",
    rows: [
      { label: "Расход, 7 дней", before: "39 600 ₽", after: "18 400 ₽" },
      { label: "Конверсии", before: "9", after: "9" },
    ],
    value: 21_200,
    outcome: "Результат измерен",
  },
  {
    id: "m-queries",
    title: "Добавлены 17 минус-слов",
    campaign: "Поиск · Регионы",
    decided: "08.09",
    window: "8–14 сентября",
    rule: "irrelevant_queries v1",
    rows: [
      { label: "Расход, 7 дней", before: "52 950 ₽", after: "43 150 ₽" },
      { label: "Конверсии", before: "18", after: "19" },
    ],
    value: 9_800,
    outcome: "Результат измерен",
  },
];
export const SAVED = sum(MEASURES.map((s) => s.value));

export type HistoryKind = "found" | "rec" | "action" | "measure";
export const HISTORY: { date: string; kind: HistoryKind; title: string; detail: string; amount?: number }[] = [
  { date: "30.09 10:45", kind: "found", title: "Найдена проблема: CPA выше цели", detail: `${CAMPAIGNS[0].name} · ${PERIOD}`, amount: PROBLEMS[0].loss },
  { date: "30.09 10:45", kind: "rec", title: `Рекомендовано: снизить ставку на ${CUT}%`, detail: "bid_cpa v3 · уверенность высокая" },
  { date: "22.09 09:12", kind: "measure", title: "Замер: исключение площадок РСЯ", detail: "7 дней после решения · результат измерен", amount: MEASURES[0].value },
  { date: "15.09 14:30", kind: "action", title: "Вы исключили 9 площадок РСЯ", detail: "Изменение внесено вручную в Яндекс Директе" },
  { date: "15.09 10:40", kind: "rec", title: "Рекомендовано: исключить 9 площадок", detail: "zero_conv_placements v2" },
  { date: "15.09 09:05", kind: "measure", title: "Замер: минус-слова", detail: "7 дней после решения · результат измерен", amount: MEASURES[1].value },
  { date: "08.09 16:20", kind: "action", title: "Вы добавили 17 минус-слов", detail: "Поиск · Регионы" },
];

export const SYSTEM_LOG = [
  { date: "30.09 10:45", text: `Rule engine ${SNAPSHOT.engine}: 3 проблемы, снимок #${SNAPSHOT.id}` },
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
  needs_decision: "Требует решения",
  applied: "Применена",
  checked: "Проверена",
  postponed: "Отложена",
  rejected: "Отклонена",
};

export const isOpen = (s: RecStatus) => s === "new" || s === "needs_decision";
