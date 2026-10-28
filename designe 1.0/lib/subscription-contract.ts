export type SubscriptionRead = {
  checked_at:string; workspace_status:'active'|'deactivated';
  limits?:{unit:'workspace';accounts:number;accounts_used:number};
  trial?:null|{started_at:string;ends_at:string;active:boolean};
  subscription:null|{plan:'start'|'business'|'business_plus';status:'active'|'past_due'|'canceled'|'expired';price_amount:string;currency:'RUB';period_start:string;period_end:string;auto_renew:boolean};
  access:{paid:boolean;analysis_allowed:boolean;basis:'subscription'|'pilot'|'trial'|'none';paid_until:string|null;pilot_until:string|null};
};
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const instant=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const optionalInstant=(v:unknown)=>v===null||instant(v);
const oneOf=(v:unknown,options:string[])=>typeof v==='string'&&options.includes(v);
export function isSubscriptionRead(v:unknown):v is SubscriptionRead {
  if(!record(v)||!instant(v.checked_at)||!oneOf(v.workspace_status,['active','deactivated'])||!record(v.access))return false;
  if(v.limits!==undefined&&(!record(v.limits)||v.limits.unit!=='workspace'||!Number.isSafeInteger(v.limits.accounts)||Number(v.limits.accounts)<1||!Number.isSafeInteger(v.limits.accounts_used)||Number(v.limits.accounts_used)<0))return false;
  const a=v.access,s=v.subscription;
  if(typeof a.paid!=='boolean'||typeof a.analysis_allowed!=='boolean'||!oneOf(a.basis,['subscription','pilot','trial','none'])||!optionalInstant(a.paid_until)||!optionalInstant(a.pilot_until))return false;
  if(v.trial!==undefined&&v.trial!==null&&(!record(v.trial)||!instant(v.trial.started_at)||!instant(v.trial.ends_at)||typeof v.trial.active!=='boolean'
    ||Date.parse(v.trial.ends_at)-Date.parse(v.trial.started_at)!==7*86400000
    ||v.trial.active!==(Date.parse(v.trial.started_at)<=Date.parse(v.checked_at)&&Date.parse(v.checked_at)<Date.parse(v.trial.ends_at))))return false;
  if(a.basis==='trial'&&(!record(v.trial)||v.trial.active!==true))return false;
  if(a.paid!==(a.basis==='subscription')||a.paid!==(a.paid_until!==null)||a.analysis_allowed&&(v.workspace_status!=='active'||a.basis==='none'))return false;
  if(s===null)return !a.paid;
  return record(s)&&oneOf(s.plan,['start','business','business_plus'])&&oneOf(s.status,['active','past_due','canceled','expired'])
    &&typeof s.price_amount==='string'&&/^\d{1,10}\.\d{2}$/.test(s.price_amount)&&/[1-9]/.test(s.price_amount)&&s.currency==='RUB'
    &&instant(s.period_start)&&instant(s.period_end)&&Date.parse(s.period_start)<Date.parse(s.period_end)&&typeof s.auto_renew==='boolean';
}
