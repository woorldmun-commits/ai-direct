export type BusinessFields = {
 name:string; industry_code:string; business_model:'b2b'|'b2c'; products:string[]; geography:string[];
 currency:'RUB'; timezone:'Europe/Moscow'; goal:string; conversion_definition:string;
 average_order_value:string|null; gross_margin_pct:string|null; sales_cycle_days:number|null;
 budget_limit:string|null; seasonality:string|null; advantages:string[]; crm_available:boolean;
};
export type IntelligenceRecommendation = {id:string;title:string;status:'requires_decision'|'approved'|'postponed'|'rejected'|'cancelled';revision:1;state_version:number;facts:string[];hypotheses:string[];risks:string[];next_step:string};
export type IntelligenceRun = {id:string;status:'completed'|'partial'|'failed';created_at:string;question:string;result:unknown;profile_revision:number|null;recommendations?:IntelligenceRecommendation[];data_mode?:'synthetic'|'imported'};
export type IntelligenceData = {
 enabled:boolean; mode:'synthetic'|'import_only';can_write:boolean;
 profile:null|{revision:number;fields:BusinessFields;provenance:Record<string,{origin:'user_confirmed';actor_id:number;updated_at:string}>};
 industries:{code:string;name:string;version:string;review_status:string;sources:{url:string;title:string}[];limitations:string[]}[];
 imports:{id:string;data_mode:'synthetic'|'imported';created_at:string;period_start:string;period_end:string}[];
 runs:IntelligenceRun[];next_cursor?:string|null;limits:{external_llm:false;external_execution:false};
};
export const object = (v:unknown):v is Record<string,unknown> => !!v && typeof v==='object' && !Array.isArray(v);
const text=(v:unknown):v is string=>typeof v==='string'&&v.length<=12000;
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.length<=100&&v.every(text);
const uuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const integer=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>=0;
const instant=(v:unknown)=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}T/.test(v)&&Number.isFinite(Date.parse(v));
const date=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
const decimal=(v:unknown)=>v===null||typeof v==='string'&&v.length<=100&&/^-?\d+(\.\d+)?$/.test(v);
export function isBusinessFields(v:unknown):v is BusinessFields {
 return object(v)&&['name','industry_code','goal','conversion_definition'].every(k=>text(v[k]))
  &&['b2b','b2c'].includes(String(v.business_model))&&strings(v.products)&&strings(v.geography)&&strings(v.advantages)
  &&v.currency==='RUB'&&v.timezone==='Europe/Moscow'&&typeof v.crm_available==='boolean'
  &&decimal(v.average_order_value)&&decimal(v.gross_margin_pct)&&decimal(v.budget_limit)
  &&(v.sales_cycle_days===null||integer(v.sales_cycle_days))&&(v.seasonality===null||text(v.seasonality));
}
function recommendation(v:unknown):v is IntelligenceRecommendation {
 return object(v)&&text(v.id)&&text(v.title)&&['requires_decision','approved','postponed','rejected','cancelled'].includes(String(v.status))
  &&v.revision===1&&integer(v.state_version)&&strings(v.facts)&&strings(v.hypotheses)&&strings(v.risks)&&text(v.next_step);
}
export function isIntelligence(v:unknown):v is IntelligenceData {
 if(!object(v)||typeof v.enabled!=='boolean'||typeof v.can_write!=='boolean'||!['synthetic','import_only'].includes(String(v.mode))
  ||!object(v.limits)||v.limits.external_llm!==false||v.limits.external_execution!==false
  ||!(v.next_cursor===undefined||v.next_cursor===null||uuid(v.next_cursor)))return false;
 if(v.profile!==null&&(!object(v.profile)||!integer(v.profile.revision)||v.profile.revision<1||!isBusinessFields(v.profile.fields)||!object(v.profile.provenance)
  ||!Object.values(v.profile.provenance).every(p=>object(p)&&p.origin==='user_confirmed'&&integer(p.actor_id)&&instant(p.updated_at))))return false;
 return Array.isArray(v.industries)&&v.industries.length<=100&&v.industries.every(i=>object(i)&&text(i.code)&&text(i.name)&&text(i.version)&&text(i.review_status)&&strings(i.limitations)
  &&Array.isArray(i.sources)&&i.sources.length<=100&&i.sources.every(s=>object(s)&&text(s.url)&&/^https:\/\//.test(s.url)&&text(s.title)))
  &&Array.isArray(v.imports)&&v.imports.length<=100&&v.imports.every(i=>object(i)&&uuid(i.id)&&['synthetic','imported'].includes(String(i.data_mode))&&instant(i.created_at)&&date(i.period_start)&&date(i.period_end)&&i.period_start<i.period_end)
  &&Array.isArray(v.runs)&&v.runs.length<=100&&v.runs.every(r=>object(r)&&uuid(r.id)&&['completed','partial','failed'].includes(String(r.status))&&instant(r.created_at)&&text(r.question)
   &&'result'in r&&(r.profile_revision===null||integer(r.profile_revision))&&(r.recommendations===undefined||Array.isArray(r.recommendations)&&r.recommendations.length<=100&&r.recommendations.every(recommendation)));
}
export type IntelligenceMetric = {value:string|null;status:'actual'|'estimated'|'unavailable'|'insufficient';unit:string;currency:string|null;reason_code:string|null};
export function isIntelligenceMetric(v:unknown):v is IntelligenceMetric {
 return object(v)&&['actual','estimated','unavailable','insufficient'].includes(String(v.status))&&text(v.unit)&&(v.currency===null||text(v.currency))
  &&(v.reason_code===null||text(v.reason_code))&&(['unavailable','insufficient'].includes(String(v.status))?v.value===null:typeof v.value==='string'&&decimal(v.value));
}
export function syntheticImport(after=false) {
 return {data_mode:'synthetic',period_start:after?'2026-10-08':'2026-10-01',period_end:after?'2026-10-15':'2026-10-08',currency:'RUB',timezone:'Europe/Moscow',
  attribution_model:'last_click',attribution_window:'30d',conversion_definition:'lead',cost_definition:'ad_spend_without_vat',account_ids:[],
  values:{cost:after?'12000':'10000',impressions:'10000',clicks:after?'400':'500',conversions:after?'20':'50',leads:after?'20':'50',qualified_leads:null,sales:null,new_customers:null,attributed_revenue:null,net_revenue:null,cogs:null,other_variable_costs:null}};
}
