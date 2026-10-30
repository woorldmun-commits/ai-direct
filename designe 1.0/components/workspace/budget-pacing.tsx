import {Gauge,ArrowUpRight} from 'lucide-react';
import type {BudgetPacing} from '@/lib/budget-pacing';
import {ValueView} from '@/components/value-view';
import {formatPeriod} from '@/lib/value';
import './metric-cards.css';

const labels={on_track:'В пределах линейного плана',ahead:'Темп выше плана',behind:'Темп ниже плана',exceeded:'Бюджет уже превышен',complete:'Период завершён'};
const reasons:Record<string,string>={no_plan:'Задайте план расходов на нужный период.',connection_unavailable:'Подключите и проверьте все выбранные аккаунты.',coverage_missing:'Нужны снимки каждого выбранного аккаунта.',stale_data:'Обновите данные: снимкам больше 72 часов.',no_final_days:'Ещё нет окончательных дней внутри плана.'};
export function BudgetPacingCard({data}:{data:BudgetPacing}) {
  if(!data.available)return <section className="pilot-card metric-pacing" aria-label="Темп расходования бюджета"><div className="metric-card-top"><span><Gauge size={18} aria-hidden="true"/> ТЕМП БЮДЖЕТА</span></div><h2>Проверьте расход до конца периода</h2><p className="metric-empty">{reasons[data.reason]??'Для расчёта нужны полные сопоставимые данные за окончательные дни плана.'}</p><p className="metric-note">Недостающие данные не заменяются нулём.</p></section>;
  const scenario={...data.actual,period:data.period,amount:data.projected_total,source:'yandex_direct+user_input',calculation_type:'estimated' as const,data_sufficiency:'sufficient' as const,unavailable_reason:null,rule_version:data.method,formula:'Расход за окончательные дни / число этих дней × число дней плана'};
  const spentPct=Math.min(100,Number(data.spent)/Number(data.plan)*100),daysPct=data.days_observed/data.days_total*100;
  return <section className="pilot-card metric-pacing" aria-label="Темп расходования бюджета" data-status={data.status}>
    <div className="metric-card-top"><span><Gauge size={18} aria-hidden="true"/> ТЕМП БЮДЖЕТА</span><span className="metric-label">Линейный сценарий</span></div>
    <div className="metric-pacing-heading"><div><h2>{labels[data.status]}</h2><p className="metric-note">{formatPeriod(data.period)} · окончательные данные по {data.observed_to}</p></div><ArrowUpRight size={24} aria-hidden="true"/></div>
    <div className="metric-pacing-track"><span>Бюджет использован</span><meter min={0} max={100} value={spentPct} aria-label="Доля использованного бюджета"/><strong>{(Number(data.spent)/Number(data.plan)*100).toFixed(1)}%</strong></div>
    <div className="metric-pacing-track"><span>Период с данными</span><meter min={0} max={100} value={daysPct} aria-label="Доля периода с окончательными данными"/><strong>{data.days_observed} / {data.days_total} дней</strong></div>
    <div className="metric-pacing-values"><div><span className="metric-note">При сохранении среднего темпа</span><ValueView v={scenario}/></div><div><span className="metric-note">Остаток на день после {data.observed_to}</span>{data.remaining_daily===null?<strong>Период завершён</strong>:<ValueView v={{...scenario,amount:data.remaining_daily,formula:'max(План − расход за окончательные дни, 0) / оставшиеся после них дни'}}/>}</div><div><span className="metric-note">Расход за окончательные дни</span><ValueView v={data.actual}/></div></div>
    <details><summary>Как рассчитано и что не учтено</summary><p>Сценарий = расход за {data.days_observed} окончательных дней / {data.days_observed} × {data.days_total}. Линейный план на эти дни: {data.expected_to_date} ₽. Отклонение: {data.deviation_pct}%.</p><ul>{data.limitations.map(s=><li key={s}>{s}</li>)}</ul></details>
  </section>;
}
