'use client';
import {useState} from 'react';
import type {Value} from '@/lib/value';
import {BudgetSummary, LeadDistribution, PeriodComparison} from '@/components/workspace/metric-cards';
import {DEMO_DAYS, DEMO_METRIC_SERIES} from './demo-data';
import {BudgetPacingCard} from '@/components/workspace/budget-pacing';
import type {BudgetPacing} from '@/lib/budget-pacing';

const period = {from: '2025-03-01', to: '2025-03-31'};
const demoValue = (amount: string | null): Value => ({unit: 'rub', source: 'yandex_direct', period, data_status: 'complete', rule_version: null, formula: null, ...(amount === null ? {calculation_type: 'unavailable', amount: null, data_sufficiency: 'insufficient', unavailable_reason: 'no_data'} : {calculation_type: 'actual', amount, data_sufficiency: 'sufficient', unavailable_reason: null})});

export function DemoMetrics({compare = true, unavailable = false}: {compare?: boolean; unavailable?: boolean}) {
  const [state, setState] = useState('ready');
  const missing = unavailable || state === 'empty';
  const budget = {actual: demoValue(missing ? null : '248640'), variance: demoValue(missing || state === 'no-plan' ? null : '-51360'), plan: state === 'no-plan' ? null : {period, amount: '300000', currency: 'RUB'}};
  const series = DEMO_METRIC_SERIES[0];
  const pacing:BudgetPacing=missing?{available:false,reason:'coverage_missing',method:'linear_budget_pacing@1'}:state==='no-plan'?{available:false,reason:'no_plan',method:'linear_budget_pacing@1'}:{available:true,reason:null,method:'linear_budget_pacing@1',status:'ahead',period:{from:'2025-03-01',to:'2025-03-30'},plan:'300000.00',actual:{...demoValue('150000.00'),period:{from:'2025-03-01',to:'2025-03-10'}},observed_to:'2025-03-10',days_observed:10,days_total:30,spent:'150000.00',expected_to_date:'100000.00',projected_total:'450000.00',remaining_daily:'7500.00',deviation_pct:'50.00',limitations:['Синтетический пример: 150 000 ₽ за 10 дней при плане 300 000 ₽ на 30 дней.','Линейный сценарий не учитывает сезонность, расписание и предварительные дни. Реклама не изменяется.']};
  return <section id="demo-budget" className="metric-demo-section" aria-label="Демонстрация бюджета и качества заявок">
    <div className="ix-head"><div><h2>Бюджет и качество заявок</h2><p className="metric-note">Синтетический пример · март 2025 · не данные вашего кабинета</p></div><div className="ix-actions" role="group" aria-label="Состояние демонстрационных карточек">{[['ready', 'Есть данные'], ['no-plan', 'Без плана'], ['empty', 'Нет данных']].map(([id, label]) => <button key={id} type="button" className="ix-btn" aria-pressed={state === id} onClick={() => setState(id)}>{label}</button>)}</div></div>
    <div className="ix-grid ix-split metric-demo-cards"><BudgetSummary budget={budget}/><LeadDistribution period={period} counts={missing ? {total: 0, qualified: 0, unresolved: 0, matched: 0} : {total: 240, qualified: 144, unresolved: 60, matched: 210}}/></div>
    <BudgetPacingCard data={pacing}/>
    <PeriodComparison title="Расходы по интервалам" note="Синтетические интервалы марта · одна шкала в рублях для обоих периодов. Эти интервалы не являются ежедневным рядом." compare={compare} points={missing ? [] : series.values.map((value, i) => ({label: DEMO_DAYS[i].replace(' марта', ''), current: value, previous: series.previous[i], display: series.display[i], previousDisplay: series.previousDisplay[i]}))}/>
  </section>;
}
