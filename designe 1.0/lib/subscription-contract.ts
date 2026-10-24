export type SubscriptionRead = {
  checked_at:string; workspace_status:'active'|'deactivated';
  subscription:null|{plan:'start'|'business'|'business_plus';status:'active'|'past_due'|'canceled'|'expired';price_amount:string;currency:'RUB';period_start:string;period_end:string;auto_renew:boolean};
  access:{paid:boolean;analysis_allowed:boolean;basis:'subscription'|'pilot'|'none';paid_until:string|null;pilot_until:string|null};
};
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const instant=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const optionalInstant=(v:unknown)=>v===null||instant(v);
const oneOf=(v:unknown,options:string[])=>typeof v==='string'&&options.includes(v);
export function isSubscriptionRead(v:unknown):v is SubscriptionRead {
  if(!record(v)||!instant(v.checked_at)||!oneOf(v.workspace_status,['active','deactivated'])||!record(v.access))return false;
  const a=v.access,s=v.subscription;
  if(typeof a.paid!=='boolean'||typeof a.analysis_allowed!=='boolean'||!oneOf(a.basis,['subscription','pilot','none'])||!optionalInstant(a.paid_until)||!optionalInstant(a.pilot_until))return false;
  if(a.paid!==(a.basis==='subscription')||a.paid!==(a.paid_until!==null)||a.analysis_allowed&&(v.workspace_status!=='active'||a.basis==='none'))return false;
  if(s===null)return !a.paid;
  return record(s)&&oneOf(s.plan,['start','business','business_plus'])&&oneOf(s.status,['active','past_due','canceled','expired'])
    &&typeof s.price_amount==='string'&&/^\d{1,10}\.\d{2}$/.test(s.price_amount)&&/[1-9]/.test(s.price_amount)&&s.currency==='RUB'
    &&instant(s.period_start)&&instant(s.period_end)&&Date.parse(s.period_start)<Date.parse(s.period_end)&&typeof s.auto_renew==='boolean';
}
