// DEMO DATA — workspace, team, agents, integrations, billing config, assistant answers.

import type { Agent, AssistantAnswer, Integration, Invoice, Plan, Subscription, Usage, Workspace } from "@/lib/types/domain";
import type { Role } from "@/lib/permissions";
import { actual, estimated, P7, unavailable } from "./data";

export const USER = { name: "Алексей", fullName: "Алексей К.", email: "alexey@example.com", role: "owner" as Role, initials: "АК" };

export const WORKSPACES: Workspace[] = [
  { id: "pilot", name: "Пилот Медиа", kind: "agency" },
  { id: "own", name: "Мой бизнес", kind: "business" },
];

export const TEAM: { name: string; email: string; role: Role; last: string }[] = [
  { name: "Алексей К.", email: "alexey@example.com", role: "owner", last: "сейчас" },
  { name: "Мария С.", email: "maria@example.com", role: "analyst", last: "сегодня, 09:40" },
  { name: "Дмитрий П.", email: "dmitry@example.com", role: "viewer", last: "вчера" },
];

export const AGENTS: Agent[] = [
  { id: "collector", name: "Data collector", role: "Сбор данных", kind: "deterministic", status: "passed", description: "Собирает статистику из рекламных кабинетов и Метрики, фиксирует неизменяемый снимок.", input: "API Директа и Метрики", output: "Снимок данных snap_2026-10-01_4815", last: "Сегодня, 10:42 · 15 кампаний, 9 кабинетов" },
  { id: "audit", name: "Audit agent", role: "Поиск отклонений", kind: "deterministic", status: "passed", description: "Проверяет кампании по правилам: CPA к цели, расход без конверсий, лимиты бюджета.", input: "Снимок данных", output: "Находки с расчётом и версией правила", last: "8 находок" },
  { id: "safety", name: "Safety agent", role: "Можно ли делать вывод", kind: "deterministic", status: "active", description: "Проверяет свежесть и достаточность данных, конверсии, период и источник. Блокирует выводы на слабых данных.", input: "Находки", output: "Разрешено / только проверка / заблокировано", last: "1 вывод заблокирован: мало конверсий" },
  { id: "root", name: "Root cause agent", role: "Возможная причина", kind: "llm", status: "passed", description: "Формулирует гипотезу о причине только из доступных фактов. Не вводит новых чисел.", input: "Находки + факты", output: "Гипотеза причины с уровнем уверенности", last: "7 гипотез" },
  { id: "explain", name: "Explain agent", role: "Объяснение", kind: "llm", status: "passed", description: "Объясняет проблему человеческим языком. Использует только числа из доказательств.", input: "Факты + гипотеза", output: "Текст для карточки и отчёта", last: "Готово: 7 объяснений" },
  { id: "engine", name: "Recommendation engine", role: "Действие", kind: "deterministic", status: "passed", description: "Формирует действие по детерминированным правилам: на сколько снизить ставку, какие площадки исключить.", input: "Находки, прошедшие Safety", output: "Рекомендация с изменением «до → после»", last: "6 рекомендаций" },
  { id: "human", name: "Human approval", role: "Решение человека", kind: "human", status: "waiting", description: "Ни одно изменение не вносится без подтверждения пользователя с нужной ролью.", input: "Рекомендация", output: "Подтверждено / отложено / отклонено", last: "3 рекомендации ждут решения" },
  { id: "measure", name: "Measurement agent", role: "Замер результата", kind: "deterministic", status: "waiting", description: "Сравнивает метрики за 7 дней до и после изменения и выносит вердикт.", input: "Исполненное действие", output: "Эффект / нет эффекта / не подтверждено", last: "1 замер идёт до 6 октября" },
];

export const INTEGRATIONS: Integration[] = [
  { id: "yandex_direct", name: "Яндекс Директ", description: "Кампании, расходы, ставки, поисковые запросы", status: "connected", accounts: 9, last_sync: "2026-10-02T10:42" },
  { id: "yandex_metrika", name: "Яндекс Метрика", description: "Цели, конверсии и поведение на сайте", status: "connected", accounts: 5, last_sync: "2026-10-02T10:38" },
  { id: "vk_ads", name: "VK Реклама", description: "Кампании и расходы VK Ads", status: "soon", accounts: 0, last_sync: null },
  { id: "telegram_ads", name: "Telegram Ads", description: "Продвижение в каналах Telegram", status: "soon", accounts: 0, last_sync: null },
  { id: "ozon", name: "Ozon Performance", description: "Реклама товаров на маркетплейсе", status: "soon", accounts: 0, last_sync: null },
  { id: "wildberries", name: "Wildberries Реклама", description: "Реклама товаров на маркетплейсе", status: "soon", accounts: 0, last_sync: null },
];

/** Account-level sync problems shown on the integrations page. */
export const SYNC_ERRORS = [
  { integration: "Яндекс Директ", account: "planeta-spb", message: "Не удалось получить данные из Яндекс Директ: доступ к кабинету отозван.", at: "2026-10-02T10:42", reference: "SYNC-7F3A-2210" },
];

// Plans are configuration, not component constants. Prices stay null until commercial terms are approved:
// the model (per ad account / per seat) is not chosen yet, so the UI shows entitlements, not a price.
export const PLANS: Plan[] = [
  { id: "audit", name: "Аудит", description: "Бесплатная проверка одного кабинета", price: { amount: 0, per: "разово" }, entitlements: { clients: 1, ad_accounts: 1, seats: 1, connections: 2 }, features: ["Аудит за 30 дней", "Находки с доказательствами", "Без изменений в кабинете"] },
  { id: "business", name: "Business", description: "Для собственного бизнеса", price: null, entitlements: { clients: 1, ad_accounts: 3, seats: 3, connections: 4 }, features: ["Ежедневный аудит", "Рекомендации и подтверждение", "Замер результата"] },
  { id: "agency", name: "Agency", description: "Для агентств и команд", price: null, entitlements: { clients: 10, ad_accounts: 25, seats: 5, connections: 8 }, features: ["Клиенты и кабинеты", "Роли и права", "Отчёты для клиентов"], highlighted: true },
  { id: "enterprise", name: "Enterprise", description: "Индивидуальные условия", price: null, entitlements: { clients: null, ad_accounts: null, seats: null, connections: null }, features: ["Без лимитов", "SLA и выделенный менеджер", "Договор и закрывающие документы"] },
];

export const SUBSCRIPTION: Subscription = { plan_id: "agency", status: "trial", renews_at: null, trial_ends_at: "2026-10-30" };
export const USAGE: Usage = { clients: 5, ad_accounts: 9, seats: 3, connections: 2 };
export const INVOICES: Invoice[] = [];

export const SUGGESTED_QUESTIONS = [
  "Почему CPA вырос?",
  "Какие кампании сейчас теряют бюджет?",
  "Что изменилось за последние 7 дней?",
  "Какие рекомендации требуют моего внимания?",
];

const DM = { source: ["yandex_direct", "yandex_metrika"] as ("yandex_direct" | "yandex_metrika")[] };

export const ANSWERS: AssistantAnswer[] = [
  {
    question: SUGGESTED_QUESTIONS[0],
    answer:
      "Основной вклад в рост CPA дала кампания «Поиск — Москва»: CPA 4 850 ₽ при цели 3 000 ₽. Ставки выросли после смены стратегии 24 сентября, а конверсия сайта не изменилась. В среднем по всем кампаниям CPA за 30 дней — 680 ₽, это на 8% ниже прошлого периода.",
    facts: [
      { label: "CPA «Поиск — Москва»", value: actual(4_850, "rub", DM) },
      { label: "Цель CPA", value: actual(3_000, "rub", { source: ["user_input"] }) },
      { label: "CPA по всем кампаниям, 30 дней", value: actual(680, "rub", { ...DM, period: { from: "2026-09-02", to: "2026-10-01", label: "последние 30 дней" } }) },
    ],
    sufficiency: "sufficient",
    links: [
      { label: "Рекомендация: снизить ставку на 15%", href: "/recommendations?open=r-cpa-msk" },
      { label: "Кампания «Поиск — Москва»", href: "/campaigns/c-msk" },
    ],
  },
  {
    question: SUGGESTED_QUESTIONS[1],
    answer:
      "Расход без результата сейчас в двух местах: 18 площадок РСЯ в «РСЯ — Акции» и 37 нерелевантных запросов в «Поиск — Доставка». Ещё в «Поиск — Москва» каждая заявка дороже цели. Суммы ниже — оценки под риском за 7 дней, они не складываются в «потери».",
    facts: [
      { label: "РСЯ — Акции, под риском", value: estimated(23_400, "rub", "Σ расход площадок без конверсий", DM) },
      { label: "Поиск — Москва, под риском", value: estimated(38_850, "rub", "(CPA − цель) × конверсии", DM) },
      { label: "Поиск — Доставка, под риском", value: estimated(8_900, "rub", "Σ расход запросов без конверсий", { ...DM, partial: true }) },
    ],
    sufficiency: "sufficient",
    links: [
      { label: "Все рекомендации", href: "/recommendations" },
      { label: "Кампания «РСЯ — Акции»", href: "/campaigns/c-promo" },
    ],
  },
  {
    question: SUGGESTED_QUESTIONS[2],
    answer:
      "За 7 дней: AdPilot нашёл 3 новые проблемы, 1 вывод заблокирован из-за нехватки конверсий («РСЯ — Охват»), идёт замер по снижению ставки в «Поиск — Санкт-Петербург» — итог будет 6 октября.",
    facts: [
      { label: "Новых находок", value: actual(3, "count", { period: P7 }) },
      { label: "Конверсии «РСЯ — Охват»", value: actual(6, "count", { source: ["yandex_metrika"] }) },
    ],
    sufficiency: "sufficient",
    links: [
      { label: "История решений", href: "/history" },
      { label: "AI-агенты", href: "/agents" },
    ],
  },
  {
    question: SUGGESTED_QUESTIONS[3],
    answer:
      "Решения ждут 3 рекомендации: снизить ставку в «Поиск — Москва» (высокий приоритет), увеличить бюджет «Брендовых запросов» и проверить посадочную страницу «Товарной кампании». Ещё 2 новые рекомендации пока не просмотрены.",
    facts: [
      { label: "Требуют решения", value: actual(3, "count") },
      { label: "Новые", value: actual(2, "count") },
    ],
    sufficiency: "sufficient",
    links: [{ label: "Открыть рекомендации", href: "/recommendations" }],
  },
];

export const INSUFFICIENT_ANSWER = (question: string): AssistantAnswer => ({
  question,
  answer: "Недостаточно данных, чтобы сделать вывод. AdPilot отвечает только по данным подключённых кабинетов и не придумывает числа.",
  facts: [{ label: "Данные для ответа", value: unavailable("count", "Подключите источник, где есть эти данные, или уточните вопрос: кампания, период, метрика.") }],
  sufficiency: "insufficient",
  links: [{ label: "Подключить источник", href: "/integrations" }],
});

export const REPORTS = [
  { id: "w39", kind: "weekly" as const, title: "Еженедельный отчёт", period: "22–28 сентября 2026", client: "Все клиенты", status: "ready" as const, created: "2026-09-29T08:00" },
  { id: "sep", kind: "monthly" as const, title: "Ежемесячный отчёт", period: "Сентябрь 2026", client: "Все клиенты", status: "ready" as const, created: "2026-10-01T08:00" },
  { id: "w39-rom", kind: "weekly" as const, title: "Еженедельный отчёт", period: "22–28 сентября 2026", client: "ООО «Ромашка»", status: "ready" as const, created: "2026-09-29T08:00" },
  { id: "w40", kind: "weekly" as const, title: "Еженедельный отчёт", period: "29 сентября — 5 октября 2026", client: "Все клиенты", status: "scheduled" as const, created: "2026-10-06T08:00" },
];
