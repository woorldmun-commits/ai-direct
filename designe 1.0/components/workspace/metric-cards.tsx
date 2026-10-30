import type {CSSProperties, ReactNode} from 'react';
import {ArrowDownRight, ArrowUpRight, ArrowRight, BarChart3, Database, Target} from 'lucide-react';
import {ValueView} from '@/components/value-view';
import type {WorkspaceInsights} from '@/lib/insights-contract';
import {budgetBars, leadShares} from '@/lib/chart-geometry';
import {formatPeriod, isPositive, sourceLabel} from '@/lib/value';
import './metric-cards.css';

export function MetricTrend({text, direction, tone = 'neutral'}: {text: string; direction: 'up' | 'down'; tone?: 'good' | 'bad' | 'neutral'}) {
  const Icon = direction === 'up' ? ArrowUpRight : ArrowDownRight;
  return <span className={`metric-trend metric-trend--${tone}`}><Icon size={16} aria-hidden="true"/>{text}</span>;
}

export function BudgetSummary({budget}: {budget: WorkspaceInsights['budget']}) {
  const {actual, plan, variance} = budget;
  const comparable = plan !== null && actual.amount !== null && plan.period.from === actual.period.from && plan.period.to === actual.period.to;
  const bars = comparable ? budgetBars(actual.amount!, plan.amount) : null;
  const planValue = plan ? {...actual, amount: plan.amount, period: plan.period, source: 'user_input', calculation_type: 'actual' as const, data_sufficiency: 'sufficient' as const, data_status: 'complete' as const, unavailable_reason: null, formula: null, rule_version: null} : null;
  const varianceClass = variance.amount !== null && isPositive(variance.amount) ? 'metric-attention' : undefined;
  return <section className="pilot-card metric-budget" aria-label="Сводка бюджета">
    <div className="metric-card-top"><span><Target size={18} aria-hidden="true"/> БЮДЖЕТ ПЕРИОДА</span><span className="metric-label">План / факт</span></div>
    <h2>План и фактический расход</h2><p className="metric-note">{formatPeriod(actual.period)}</p>
    <div className="metric-hero-number"><ValueView v={actual}/></div>
    <p className="metric-note">Фактический расход · {sourceLabel(actual.source)}</p>
    {bars && planValue ? <figure className="metric-budget-bars"><figcaption className="metric-note">Один период, одна шкала расходов</figcaption>{[['План', bars[1], planValue], ['Факт', bars[0], actual]].map(([label, width, value]) => <div className="metric-budget-row" key={String(label)}><span>{String(label)}</span><meter min={0} max={100} value={Number(width)} aria-label={`${label} расходов`}/><ValueView v={value as typeof actual}/></div>)}</figure> : <p className="metric-empty">Для сравнения задайте план на тот же период, что и фактический расход. До этого диаграмма недоступна.</p>}
    <dl className="metric-breakdown"><div><dt>План периода</dt><dd>{planValue ? <ValueView v={planValue}/> : 'Не задан'}</dd></div><div><dt>Факт минус план</dt><dd className={varianceClass}><ValueView v={variance} signed/></dd></div></dl>
    <p className="metric-note">Отклонение от плана не является оценкой эффективности или экономии.</p>
  </section>;
}

export function LeadDistribution({counts, period}: {counts: WorkspaceInsights['lead_quality']['counts']; period: WorkspaceInsights['period']}) {
  const shares = leadShares(counts);
  const labels = ['Квалифицированные', 'Без окончательного статуса', 'Остальные'];
  const values = [counts.qualified, counts.unresolved, counts.total - counts.qualified - counts.unresolved];
  return <section className="pilot-card metric-leads" aria-label="Состав импортированных заявок">
    <div className="metric-card-top"><span><Database size={18} aria-hidden="true"/> КАЧЕСТВО ЗАЯВОК</span><span className="metric-label">Импорт</span></div>
    <h2>Статусы импортированных заявок</h2><p className="metric-note">{formatPeriod(period)}</p>
    {shares ? <><div className="metric-lead-total"><strong>{counts.total.toLocaleString('ru-RU')}</strong><span>заявок в загруженном наборе</span></div><div className="metric-segmented" role="img" aria-label={labels.map((label, i) => `${label}: ${values[i]}, ${shares[i].toLocaleString('ru-RU', {maximumFractionDigits: 1})}%`).join('; ')}>{shares.map((share, i) => <span key={labels[i]} className={`metric-segment metric-segment--${i}`} style={{flex: share} as CSSProperties}/>)}</div><dl className="metric-lead-legend">{labels.map((label, i) => <div key={label}><dt><i className={`metric-segment--${i}`} aria-hidden="true"/>{label}</dt><dd><strong>{values[i].toLocaleString('ru-RU')}</strong><span>{shares[i].toLocaleString('ru-RU', {maximumFractionDigits: 1})}%</span></dd></div>)}</dl></> : <p className="metric-empty">{counts.total === 0 ? 'Импортируйте заявки за период, чтобы увидеть распределение по статусам.' : 'Состав заявок требует проверки. Распределение не построено.'}</p>}
    <p className="metric-note">Состав загруженного набора, не конверсионная воронка. Полнота CRM автоматически не проверяется.</p>
  </section>;
}

export type ComparisonPoint = {label: string; current: number | null; previous?: number | null; display: ReactNode; previousDisplay?: ReactNode};
export function PeriodComparison({points, title, note, compare = false}: {points: ComparisonPoint[]; title: string; note: string; compare?: boolean}) {
  const available = points.flatMap(p => [p.current, ...(compare ? [p.previous ?? null] : [])]).filter((v): v is number => v !== null && Number.isFinite(v) && v >= 0);
  const maximum = Math.max(0, ...available);
  const height = (v: number | null | undefined) => v === null || v === undefined || !Number.isFinite(v) || v < 0 ? undefined : maximum === 0 ? 0 : v / maximum * 100;
  return <section className="ix-card metric-comparison"><div className="metric-card-top"><h2><BarChart3 size={19} aria-hidden="true"/> {title}</h2><ArrowRight size={18} aria-hidden="true"/></div><p className="metric-note">{note}</p>
    {available.length ? <><div className="metric-comparison-legend"><span><i/>Текущий период</span>{compare && <span><i/>Предыдущий период</span>}</div><div className="metric-column-chart" role="img" aria-label={`${title}. ${compare ? 'Сопоставление текущего и предыдущего периода.' : 'Текущий период.'} Точные значения доступны в таблице ниже.`}>{points.map((point, i) => <div className="metric-column" key={i}><div className="metric-column-pair"><span style={{height: `${height(point.current) ?? 0}%`}} data-missing={height(point.current) === undefined}/>{compare && <span style={{height: `${height(point.previous) ?? 0}%`}} data-missing={height(point.previous) === undefined}/>}</div><span>{point.label}</span></div>)}</div><details className="metric-values"><summary>Точные значения и пропуски</summary><div className="ix-tablewrap" tabIndex={0} role="region" aria-label={title}><table><thead><tr><th scope="col">Дата / интервал</th><th scope="col">Текущий период</th>{compare && <th scope="col">Предыдущий период</th>}</tr></thead><tbody>{points.map((point, i) => <tr key={i}><th scope="row">{point.label}</th><td>{point.display}</td>{compare && <td>{point.previousDisplay ?? 'Нет данных'}</td>}</tr>)}</tbody></table></div></details></> : <p className="metric-empty">Нет сопоставимых наблюдений. Пропуски не заменяются нулями.</p>}
  </section>;
}
