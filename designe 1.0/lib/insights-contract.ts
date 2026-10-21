import {isValue} from './pilot-contract';
import type {Value} from './value';

export type WorkspaceInsights={
 period:{from:string;to:string};ad_accounts?:{id:string}[];
 health:{checks:{id:string;status:'ok'|'attention'|'unavailable';reason:string;action:string}[]};
 budget:{plan:null|{period:{from:string;to:string};amount:string;currency:string};actual:Value;variance:Value};
 lead_quality:{counts:{total:number;qualified:number;unresolved:number;matched:number};coverage:{matched_pct:string|null;qualification_complete:boolean;cohort_complete:boolean};qcpl:Value;reason:string|null};
 summary:{period:{from:string;to:string};generated_at:string;delivery:string;facts:{id:string;label:string;value:Value|null;detail:string}[];limitations:string[]};
};
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown):v is string=>typeof v==='string'&&v.length<=8000;
const day=(v:unknown)=>text(v)&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
const period=(v:unknown)=>record(v)&&day(v.from)&&day(v.to)&&String(v.from)<=String(v.to);
const count=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>=0;
export function isInsights(v:unknown):v is WorkspaceInsights{
 if(!record(v)||!period(v.period)||!record(v.health)||!Array.isArray(v.health.checks)||v.health.checks.length>100
  ||!v.health.checks.every(c=>record(c)&&text(c.id)&&['ok','attention','unavailable'].includes(String(c.status))&&text(c.reason)&&text(c.action))
  ||!record(v.budget)||!isValue(v.budget.actual)||!isValue(v.budget.variance))return false;
 const plan=v.budget.plan;if(plan!==null&&(!record(plan)||!period(plan.period)||!text(plan.amount)||!/^\d{1,12}(\.\d{1,2})?$/.test(plan.amount)||plan.currency!=='RUB'))return false;
 const leads=v.lead_quality;
 if(!record(leads)||!record(leads.counts)||!['total','qualified','unresolved','matched'].every(k=>count((leads.counts as Record<string,unknown>)[k]))
  ||!record(leads.coverage)||!(leads.coverage.matched_pct===null||text(leads.coverage.matched_pct)&&/^\d{1,3}(\.\d{1,6})?$/.test(leads.coverage.matched_pct)&&Number(leads.coverage.matched_pct)<=100)
  ||typeof leads.coverage.qualification_complete!=='boolean'||typeof leads.coverage.cohort_complete!=='boolean'||!isValue(leads.qcpl)||!(leads.reason===null||text(leads.reason)))return false;
 if(Number(leads.counts.qualified)>Number(leads.counts.total)||Number(leads.counts.matched)>Number(leads.counts.total)||Number(leads.counts.unresolved)+Number(leads.counts.qualified)>Number(leads.counts.total))return false;
 const summary=v.summary;
 return record(summary)&&period(summary.period)&&text(summary.generated_at)&&Number.isFinite(Date.parse(summary.generated_at))&&summary.delivery==='manual_pull'
  &&Array.isArray(summary.facts)&&summary.facts.length<=100&&summary.facts.every(f=>record(f)&&text(f.id)&&text(f.label)&&(f.value===null||isValue(f.value))&&text(f.detail))
  &&Array.isArray(summary.limitations)&&summary.limitations.every(text)
  &&(v.ad_accounts===undefined||Array.isArray(v.ad_accounts)&&v.ad_accounts.length<=1000&&v.ad_accounts.every(a=>record(a)&&text(a.id)&&/^acc_[1-9]\d{0,18}$/.test(a.id)));
}
export type ManualAction={type:'investigate'|'decrease_bid'|'lower_cpa'|'exclude_placements';execution:'manual';checks?:string[];change_pct?:string;strategy?:string;placements?:{id:string;name:string|null}[]|null;levers?:{strategy:string;lever:string;change_pct:string|null}[]};
function isAction(v:unknown):v is ManualAction|null{
 if(v===null)return true;
 if(!record(v)||v.execution!=='manual')return false;
 const pct=(s:unknown)=>text(s)&&/^-\d{1,3}(\.\d{1,2})?$/.test(s)&&Number(s)<0&&Number(s)>=-100;
 const placements=(a:unknown)=>a===null||Array.isArray(a)&&a.length<=10000&&a.every(p=>record(p)&&text(p.id)&&/^\d{1,19}$/.test(p.id)&&(p.name===null||text(p.name)));
 if(v.type==='investigate')return Array.isArray(v.checks)&&v.checks.length<=10&&v.checks.every(c=>['conversion_goals','strategy','search_queries_negative_keywords','network_placements'].includes(String(c)))&&placements(v.placements);
 if(v.type==='decrease_bid')return pct(v.change_pct);
 if(v.type==='exclude_placements')return Array.isArray(v.placements)&&placements(v.placements);
 return v.type==='lower_cpa'&&['unknown','manual','auto'].includes(String(v.strategy))&&Array.isArray(v.levers)&&v.levers.length<=10&&v.levers.every(l=>record(l)&&['manual','auto'].includes(String(l.strategy))&&['decrease_bid','lower_target_cpa','check_conversion_goals'].includes(String(l.lever))&&(l.lever==='decrease_bid'?pct(l.change_pct):l.change_pct===null));
}
export type Measurement={id:string;policy:string;status:'pending'|'complete'|'skipped';reason:string|null;next_check_on:string|null;before_period:{from:string;to:string};after_period:{from:string;to:string};result:null|{verdict:'effect'|'no_effect'|'not_confirmed'|'insufficient';before:Record<string,Value>;after:Record<string,Value>;computed_at:string;counted_in_saved_total:false}};
export const decisionLabels:Record<string,string>={done:'Заявлено ручное выполнение',checked:'Проверено специалистом',rejected:'Отклонено',postponed:'Отложено',measured:'Выполнен замер',measurement_skipped:'Замер пропущен'};
export type WeeklyReportData={insights:WorkspaceInsights;decisions:{type:string;count:number}[]};
export function isWeeklyReport(v:unknown):v is WeeklyReportData{
 return record(v)&&isInsights(v.insights)&&Array.isArray(v.decisions)&&v.decisions.length<=6&&v.decisions.every(d=>record(d)&&text(d.type)&&Object.hasOwn(decisionLabels,d.type)&&count(d.count));
}
export type RecommendationActivity={items:{id:string;title:string;status:string;execution_mode:'manual'|null;updated_at:string;measurement:Measurement|null}[];next_cursor:string|null};
export function isMeasurement(v:unknown):v is Measurement|null{
 if(v===null)return true;
 if(!record(v)||!text(v.id)||!/^measurement_[1-9]\d{0,18}$/.test(v.id)||!text(v.policy)||!['pending','complete','skipped'].includes(String(v.status))||!period(v.before_period)||!period(v.after_period)||!(v.reason===null||text(v.reason))||!(v.next_check_on===null||day(v.next_check_on)))return false;
 const r=v.result;
 if(r===null)return v.status!=='complete';
 return v.status==='complete'&&record(r)&&['effect','no_effect','not_confirmed','insufficient'].includes(String(r.verdict))&&record(r.before)&&record(r.after)&&Object.values(r.before).every(isValue)&&Object.values(r.after).every(isValue)&&text(r.computed_at)&&Number.isFinite(Date.parse(r.computed_at))&&r.counted_in_saved_total===false;
}
export function isActivity(v:unknown):v is RecommendationActivity{
 return record(v)&&(v.next_cursor===null||text(v.next_cursor)&&/^[1-9]\d{0,18}$/.test(v.next_cursor))&&Array.isArray(v.items)&&v.items.length<=50&&v.items.every(i=>record(i)&&text(i.id)&&/^rec_[1-9]\d{0,18}$/.test(i.id)&&text(i.title)&&text(i.status)&&(i.execution_mode===null||i.execution_mode==='manual')&&text(i.updated_at)&&Number.isFinite(Date.parse(i.updated_at))&&isMeasurement(i.measurement));
}
export type RecommendationPassport={
 id:string;version_id:string;state_version:string;status:string;title?:string;action_level:string;
 action:ManualAction|null;object:{type:string;id:string;name:string|null};evidence_current:boolean;evidence:Record<string,Value>;explanation:{text:string;source:string}|null;exposure:Value;can_save:Value;computed_at:string;allowed_actions:string[];
 history:{id:string;type:string;actor_id:string|null;created_at:string;version_id:string|null}[];
 latest_measurement:Measurement|null;verification:{status:string;reason:string};
};
export function isPassport(v:unknown):v is RecommendationPassport{
 return record(v)&&text(v.id)&&/^rec_[1-9]\d{0,18}$/.test(v.id)&&text(v.version_id)&&/^rv_[1-9]\d{0,18}$/.test(v.version_id)
 &&text(v.state_version)&&/^(initial|ev_[1-9]\d{0,18})$/.test(v.state_version)&&text(v.status)&&text(v.action_level)
 &&Array.isArray(v.allowed_actions)&&v.allowed_actions.every(a=>text(a)&&['reject','postpone','check','mark_done_manually'].includes(a))
 &&Array.isArray(v.history)&&v.history.length<=1000&&v.history.every(h=>record(h)&&text(h.id)&&text(h.type)&&text(h.created_at)&&Number.isFinite(Date.parse(h.created_at))&& (h.actor_id===null||text(h.actor_id))&&(h.version_id===null||text(h.version_id)))
 &&record(v.evidence)&&Object.values(v.evidence).every(isValue)&&isValue(v.exposure)&&isValue(v.can_save)
 &&isAction(v.action)&&record(v.object)&&text(v.object.type)&&text(v.object.id)&&(v.object.name===null||text(v.object.name))&&typeof v.evidence_current==='boolean'
 &&text(v.computed_at)&&Number.isFinite(Date.parse(v.computed_at))
 &&(v.explanation===null||record(v.explanation)&&text(v.explanation.text)&&text(v.explanation.source))
 &&(v.title===undefined||text(v.title))
 &&record(v.verification)&&text(v.verification.status)&&text(v.verification.reason)&&isMeasurement(v.latest_measurement);
}
