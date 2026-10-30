import {isValue} from './pilot-contract';
import type {Value} from './value';
export type BudgetPacing={available:false;reason:string;method:'linear_budget_pacing@1'}|{
  available:true;reason:null;method:'linear_budget_pacing@1';status:'on_track'|'ahead'|'behind'|'exceeded'|'complete';
  period:{from:string;to:string};plan:string;actual:Value;observed_to:string;days_observed:number;days_total:number;
  spent:string;expected_to_date:string;projected_total:string;remaining_daily:string|null;deviation_pct:string;limitations:string[];
};
export function isBudgetPacing(v:unknown):v is BudgetPacing {
  if(!v||typeof v!=='object'||!('available' in v)||!('method' in v)||v.method!=='linear_budget_pacing@1'||!('reason' in v))return false;
  if(v.available===false)return typeof v.reason==='string'&&v.reason.length<=100;
  if(v.available!==true||v.reason!==null)return false;
  const p=v as Record<string,unknown>,money=(s:unknown)=>typeof s==='string'&&/^\d{1,16}\.\d{2}$/.test(s),day=(s:unknown)=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;
  const period=p.period as Record<string,unknown>|undefined;
  return typeof p.status==='string'&&['on_track','ahead','behind','exceeded','complete'].includes(p.status)&&isValue(p.actual)&&p.actual.amount===p.spent&&p.actual.unit==='rub'&&p.actual.calculation_type==='actual'&&p.actual.data_status==='complete'
    &&money(p.plan)&&Number(p.plan)>0&&['spent','expected_to_date','projected_total'].every(k=>money(p[k]))&&(p.remaining_daily===null||money(p.remaining_daily))
    &&typeof p.deviation_pct==='string'&&/^-?\d{1,16}\.\d{2}$/.test(p.deviation_pct)
    &&!!period&&day(period.from)&&day(period.to)&&day(p.observed_to)&&String(period.from)<=String(p.observed_to)&&String(p.observed_to)<=String(period.to)
    &&p.actual.period.from===period.from&&p.actual.period.to===p.observed_to
    &&Number.isSafeInteger(p.days_observed)&&Number(p.days_observed)>0&&Number.isSafeInteger(p.days_total)&&Number(p.days_total)>=Number(p.days_observed)&&Number(p.days_total)<=367
    &&Number(p.days_total)===(Date.parse(String(period.to))-Date.parse(String(period.from)))/86400000+1&&Number(p.days_observed)===(Date.parse(String(p.observed_to))-Date.parse(String(period.from)))/86400000+1
    &&Array.isArray(p.limitations)&&p.limitations.length<=10&&p.limitations.every(s=>typeof s==='string'&&s.length<=1000);
}
