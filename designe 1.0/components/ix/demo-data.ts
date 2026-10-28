// Синтетические фикстуры из reference/index.html. Используются ТОЛЬКО в явно помеченном режиме /demo.
// Рабочий кабинет (/workspace) эти значения не импортирует (проверяется scripts/check-ix.mjs).
export const DEMO_SNAPSHOT = '31.03.2025 23:59';
export const DEMO_DATA = [35, 49, 45, 70, 66, 89, 82, 104, 97, 112, 123, 119, 146, 139];
export const DEMO_PREV = [33, 38, 44, 51, 55, 64, 60, 69, 74, 82, 84, 90, 96, 100];
export const DEMO_DAYS = ['1 марта', '3 марта', '5 марта', '7 марта', '9 марта', '11 марта', '14 марта', '16 марта', '18 марта', '20 марта', '23 марта', '25 марта', '28 марта', '31 марта'];
export const DEMO_ANOMALY = {index: 8, seriesId: 'cpa', title: 'Демонстрационная аномалия · 18 марта', rule: 'cpa_jump_demo@1 (иллюстрация)', evidence: 'Это синтетическая отметка для демонстрации интерфейса. Наличие статистической аномалии и причина изменения CPA не утверждаются.'};

// Four synthetic interval series. Integer allocation preserves the explicitly labelled demo monthly totals.
export function allocateDemo(total: number, weights: number[]) {
  const sum = weights.reduce((a, b) => a + b, 0);
  const values = weights.map(w => Math.floor(total * w / sum));
  values[values.length - 1] += total - values.reduce((a, b) => a + b, 0);
  return values;
}
const costs = allocateDemo(248640, [32, 70, 140, 100, 80, 120, 150, 100, 160, 170, 130, 150, 110, 180]);
const conversions = allocateDemo(1284, [25, 30, 50, 100, 80, 70, 90, 110, 90, 100, 140, 130, 150, 170]);
const revenue = allocateDemo(3842000, [50, 85, 110, 80, 70, 100, 80, 120, 115, 150, 100, 170, 140, 180]);
const rub = (v: number) => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(v) + ' ₽';
export const DEMO_METRIC_SERIES = [
  {id: 'cost', name: 'Расходы', color: 'var(--ix-red)', values: costs, factor: .88, format: rub},
  {id: 'conversions', name: 'Конверсии', color: 'var(--ix-blue)', values: conversions, factor: 1.34, format: (v: number) => String(Math.round(v))},
  {id: 'cpa', name: 'CPA', color: 'var(--ix-teal)', values: costs.map((v, i) => v / conversions[i]), factor: .88 / 1.34, format: rub},
  {id: 'revenue', name: 'Выручка', color: 'var(--ix-amber)', values: revenue, factor: 1.48, format: rub},
].map(({factor, format, ...s}) => {
  const prior = (values: number[], multiplier: number) => allocateDemo(Math.round(values.reduce((a, b) => a + b, 0) / multiplier), values.map((v, i) => v * .6 + values[(i + 2) % values.length] * .4));
  const previous = s.id === 'cpa' ? prior(costs, .88).map((v, i) => v / prior(conversions, 1.34)[i]) : prior(s.values, factor);
  return {...s, previous, display: s.values.map(format), previousDisplay: previous.map(format)};
});

export const DEMO_KPIS: [string, string, string][] = [
  ['Расходы', '248 640 ₽', '−12%'],
  ['Конверсии', '1 284', '+34%'],
  ['CPA', '194 ₽', '−34%'],
  ['Выручка', '3 842 000 ₽', '+48%'],
];

export const DEMO_RECS: {title: string; effect: string; level: string; note: string; icon: string}[] = [
  {title: 'Высокий CPA в кампании «Поиск | Бренд»', effect: '−48 200 ₽', level: 'Высокий', note: 'Сравнение CPA с целевым · расчёт требует проверки', icon: '◈'},
  {title: 'Нет конверсий в трёх кампаниях', effect: '−36 400 ₽', level: 'Средний', note: 'Демонстрационная рекомендация · требуется подтверждение', icon: '▣'},
  {title: 'Проверить распределение бюджета', effect: '+24 300 ₽', level: 'Гипотеза', note: 'Демонстрационная рекомендация · требуется подтверждение', icon: '◉'},
  {title: 'Оценить качество объявлений', effect: 'Не оценено', level: 'Гипотеза', note: 'Демонстрационная рекомендация · требуется подтверждение', icon: '✧'},
];

export const DEMO_CAMPAIGNS: string[][] = [
  ['Поиск | Бренд', 'Яндекс Директ', 'Активна', '60 000 ₽', '312', '192 ₽'],
  ['РСЯ | Каталог', 'Яндекс Директ', 'Активна', '40 000 ₽', '284', '141 ₽'],
  ['Поиск | Категории', 'Яндекс Директ', 'Активна', '80 000 ₽', '420', '190 ₽'],
  ['VK | Лиды', 'VK Реклама', 'Планируется', '—', '—', '—'],
  ['Авито | Продажи', 'Авито', 'Планируется', '—', '—', '—'],
];

export const DEMO_SOURCES: [string, string][] = [
  ['Яндекс Директ', 'Первый этап · доступ зависит от backend'],
  ['Яндекс Метрика', 'Диагностический источник'],
  ['VK Реклама', 'В плане'],
  ['Авито', 'В плане'],
  ['CRM / коллтрекинг', 'В плане'],
];

export const DEMO_REPORTS = ['Сводный отчёт', 'По кампаниям', 'По рекламным источникам', 'История решений', 'Качество данных', 'План / факт'];
export const DEMO_ALERTS: [string, string][] = [['Высокий CPA', 'Критический'], ['Расход без подтверждённых конверсий', 'Высокий'], ['Данные давно не обновлялись', 'Средний']];
export const DEMO_TEAM: [string, string][] = [['Владелец', 'Полный доступ'], ['Аналитик', 'Чтение и рекомендации'], ['Наблюдатель', 'Только просмотр']];
export const DEMO_PLANS: [string, string, string][] = [['Старт', '2 000 ₽ / мес', 'Стоимость из стратегии'], ['Бизнес', 'Уточняется', 'Параметры ещё не утверждены'], ['Премиум', 'Уточняется', 'Параметры ещё не утверждены']];
export const DEMO_PROFILE: [string, string][] = [['Ниша', 'Например: интернет-магазин'], ['География', 'Россия'], ['Средний чек', 'Не указан'], ['Цель рекламы', 'Заявки и продажи'], ['Сезонность', 'Не указана']];
