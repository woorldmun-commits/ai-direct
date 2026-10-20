import type {WorkspaceInsights} from '@/lib/insights-contract';
import {ValueView} from '@/components/value-view';
import {budgetBars} from '@/lib/chart-geometry';
import {formatPeriod} from '@/lib/value';

export function PeriodCharts({data}:{data:WorkspaceInsights}){
 const {actual,plan}=data.budget;
 const comparable=actual.amount!==null&&plan!==null&&plan.period.from===actual.period.from&&plan.period.to===actual.period.to;
 const bars=comparable?budgetBars(actual.amount!,plan.amount):null;
 const planValue=plan?{...actual,amount:plan.amount,source:'user_input',calculation_type:'actual' as const,data_sufficiency:'sufficient' as const,data_status:'complete' as const,unavailable_reason:null,formula:null,rule_version:null}:null;
 const counts=data.lead_quality.counts;
 const leads=[['Квалифицированные',counts.qualified],['Без окончательного статуса',counts.unresolved],['Остальные',counts.total-counts.qualified-counts.unresolved]] as const;
 return <div className="pilot-grid launch-charts"><section className="pilot-card"><h2>План и фактический расход</h2><p>{formatPeriod(data.period)}</p>{bars&&planValue?<figure><figcaption>Один период, одна шкала расходов</figcaption><div className="launch-bar-row"><span>План</span><meter min={0} max={100} value={bars[1]} aria-label="План расходов"/><ValueView v={planValue}/></div><div className="launch-bar-row"><span>Факт</span><meter min={0} max={100} value={bars[0]} aria-label="Фактический расход"/><ValueView v={actual}/></div></figure>:<p>Для сравнения задайте план на тот же период, что и фактический расход. До этого диаграмма недоступна.</p>}</section><section className="pilot-card"><h2>Статусы импортированных заявок</h2><p>{counts.total} заявок · {formatPeriod(data.period)}</p>{counts.total>0?<figure><figcaption>Состав загруженного набора, не конверсионная воронка</figcaption>{leads.map(([label,value])=><div className="launch-bar-row" key={label}><span>{label}</span><meter min={0} max={counts.total} value={value} aria-label={label}/><strong>{value}</strong></div>)}</figure>:<p>Импортируйте заявки за период, чтобы увидеть распределение по статусам.</p>}<p className="ap-footnote">Полнота CRM автоматически не проверяется.</p></section></div>;
}
