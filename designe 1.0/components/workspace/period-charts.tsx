import type {WorkspaceInsights} from '@/lib/insights-contract';
import {BudgetSummary, LeadDistribution} from './metric-cards';

export function PeriodCharts({data}:{data:WorkspaceInsights}){
 return <div className="pilot-grid launch-charts"><BudgetSummary budget={data.budget}/><LeadDistribution counts={data.lead_quality.counts} period={data.period}/></div>;
}
