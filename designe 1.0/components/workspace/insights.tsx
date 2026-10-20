import {PeriodCharts} from './period-charts';
import { ValueView } from '@/components/value-view';
import type { WorkspaceInsights } from '@/lib/insights-contract';
import { formatPeriod } from '@/lib/value';
import { BudgetForm, LeadImportForm } from './actions';

const reasons:Record<string,string>={no_imported_leads:'Заявки ещё не импортированы.',cohort_completeness_unverified:'Нужен полный набор заявок за период привлечения.',acquisition_date_missing:'Укажите дату привлечения для каждой заявки.',qualification_incomplete:'Завершите квалификацию новых заявок.',scope_or_period_unmatched:'Проверьте совпадение периода и рекламных аккаунтов.',no_qualified_leads:'За период нет квалифицированных заявок.',campaign_rows_missing:'В источнике отсутствуют данные по кампаниям.',no_selected_accounts:'Выберите рекламные аккаунты.'};
export function InsightsPanel({ workspace, data }: { workspace: string; data: WorkspaceInsights }) {
  const plan = data.budget.plan;
  const planValue = plan ? {...data.budget.actual, amount: plan.amount, period: plan.period, source:'user_input', calculation_type:'actual' as const, data_status:'complete' as const, data_sufficiency:'sufficient' as const, unavailable_reason:null, rule_version:null, formula:null} : null;
  return <section id="insights" className="workspace-insights">
    <div className="pilot-section-title"><h2>Контроль данных и бюджета</h2><span>{formatPeriod(data.period)}</span></div>
    <PeriodCharts data={data}/>
    <div className="pilot-grid">{data.health.checks.map(check => <article className="pilot-card" key={check.id}>
      <h3>{check.id === 'direct' ? 'Директ' : check.id === 'metrika' ? 'Метрика' : check.id === 'goals' ? 'Цели' : 'Свежесть данных'}</h3>
      <span className={check.status === 'ok' ? 'pilot-ok' : 'pilot-warning'}>{check.status === 'ok' ? 'Проверка пройдена' : check.status === 'attention' ? 'Требует внимания' : 'Нет данных для проверки'}</span>
      <p>{check.action}</p>
    </article>)}</div>
    <div className="pilot-grid"><article className="pilot-card"><h3>План расходов</h3>{planValue ? <ValueView v={planValue} caption/> : <p>Пока не задан</p>}<details><summary>Задать или изменить план</summary><BudgetForm workspace={workspace} period={data.period}/></details></article>
      <article className="pilot-card"><h3>Фактический расход</h3><ValueView v={data.budget.actual} caption/></article>
      <article className="pilot-card"><h3>Факт минус план</h3><ValueView v={data.budget.variance} caption/><p>Отрицательное значение означает расход ниже плана за указанный период.</p></article></div>
    <article id="lead-quality" className="pilot-card"><h2>Качество заявок</h2><div className="pilot-grid"><div><h3>Стоимость квалифицированной заявки</h3><ValueView v={data.lead_quality.qcpl} caption/></div><div><p>Заявок: {data.lead_quality.counts.total} · Квалифицированных: {data.lead_quality.counts.qualified}</p><p>Без окончательного статуса: {data.lead_quality.counts.unresolved} · Сопоставлено: {data.lead_quality.counts.matched}</p></div></div>{data.lead_quality.reason && <p className="pilot-warning">{reasons[data.lead_quality.reason]??'Для расчёта нужны полные и сопоставимые данные Директа и заявок.'}</p>}<p>Полнота когорты: {data.lead_quality.coverage.cohort_complete ? 'заявлена пользователем' : 'не подтверждена'}. Полнота CRM автоматически не проверяется.</p><details><summary>Импортировать или обновить статусы</summary><LeadImportForm workspace={workspace} period={data.period} accounts={(data.ad_accounts ?? []).map(account => account.id)}/></details></article>
    <article className="pilot-card"><h2>Сводка за период</h2><p>Формируется при открытии страницы. Доставка по расписанию пока не подключена.</p>{data.summary.facts.map(fact => <div key={fact.id}><h3>{fact.label}</h3>{fact.value && <ValueView v={fact.value} caption/>}<p>{fact.detail}</p></div>)}<ul>{data.summary.limitations.filter(limit=>!limit.startsWith('qCPL недоступен:')).map((limit, index) => <li key={index}>{limit}</li>)}</ul></article>
  </section>;
}
