export const DEMO_SERIES = [
  { date: '30.09', spend: 36120, conversions: 128, revenue: 187450 },
  { date: '01.10', spend: 41950, conversions: 142, revenue: 219300 },
  { date: '02.10', spend: 52100, conversions: 191, revenue: 278400 },
  { date: '03.10', spend: 46780, conversions: 179, revenue: 260500 },
  { date: '04.10', spend: 59820, conversions: 216, revenue: 319800 },
  { date: '05.10', spend: 48760, conversions: 184, revenue: 298600 },
  { date: '06.10', spend: 57162, conversions: 208, revenue: 328380 },
];
export type Metric = 'spend' | 'conversions' | 'cpa' | 'revenue';
export const METRICS: { key: Metric; label: string; growth: string; color: string }[] = [
  { key: 'spend', label: 'Расходы', growth: '12%', color: '#9560ff' },
  { key: 'conversions', label: 'Конверсии', growth: '18%', color: '#10c5e9' },
  { key: 'cpa', label: 'CPA', growth: '21%', color: '#377cff' },
  { key: 'revenue', label: 'Выручка', growth: '32%', color: '#ffbd65' },
];
export const money = (value: number) => `${Math.round(value).toLocaleString('ru-RU')} ₽`;
export const totals = (days = 7) => {
  const values = DEMO_SERIES.slice(-days);
  const spend = values.reduce((s, d) => s + d.spend, 0);
  const conversions = values.reduce((s, d) => s + d.conversions, 0);
  return { spend, conversions, cpa: spend / conversions, revenue: values.reduce((s, d) => s + d.revenue, 0) };
};
export const effectComparison = (days = 7) => {
  const after = totals(days);
  const baseline = [103, 114, 154, 144, 174, 149, 168].slice(-days).reduce((sum, value) => sum + value, 0);
  return { after, baseline, beforeCPA: after.spend / baseline, growth: ((after.conversions / baseline - 1) * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 }), cpaChange: ((after.cpa / (after.spend / baseline) - 1) * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) };
};
export const recommendations = [
  { id: 1, title: 'Снизить ставку в РСЯ', campaign: 'Кампания «РСЯ — Новые»', description: 'Текущая ставка: 120 ₽ · Рекомендуется: 102 ₽ (−15%)', priority: 'Высокий', effect: '+8%', icon: 'down', reason: 'Стоимость конверсии выше среднего на 24%. Снижение ставки на 15% поможет сократить неэффективные расходы. Перед применением проверьте актуальные данные рекламного кабинета.' },
  { id: 2, title: 'Увеличить бюджет на Поиск', campaign: 'Кампания «Поиск — Товары»', description: 'Текущий бюджет: 50 000 ₽ · Рекомендуется: 60 000 ₽ (+20%)', priority: 'Высокий', effect: '+32%', icon: 'up', reason: 'Кампания стабильно приносит конверсии ниже целевого CPA и ограничена дневным бюджетом. Ожидаемый рост рассчитан по демонстрационным данным и не является гарантией.' },
  { id: 3, title: 'Обновить креативы', campaign: 'РСЯ / Баннеры', description: 'CTR: 0,8% · Рекомендуется: 1,2%+', priority: 'Средний', effect: '+15%', icon: 'target', reason: 'Частота показов выросла, а кликабельность снизилась. Подготовьте новые изображения и протестируйте их на небольшой доле аудитории.' },
  { id: 4, title: 'Проверить автотаргетинг', campaign: 'Кампания «Авто — РСЯ»', description: 'Высокий расход при низком CTR', priority: 'Средний', effect: '+6%', icon: 'shield', reason: 'Часть поисковых запросов не соответствует товарам. Проверьте категории автотаргетинга и исключите нерелевантные запросы.' },
];
