export type BillingPlan = {id:'control'|'business'|'agency';name:string;plan:'start'|'business'|'business_plus';amount_minor:number;accounts:number;workspaces?:number;regular_amount_minor?:number;offer_periods_remaining?:number};
export type BillingCatalog = {items:BillingPlan[];unit:'workspace'|'subscription';currency:'RUB';period_days:30;grace_days:3;auto_renew:false;checkout_enabled:boolean;test:boolean|null;terms_sha256:string|null};
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function isBillingCatalog(v:unknown):v is BillingCatalog {
 if(!record(v)||typeof v.unit!=='string'||!['workspace','subscription'].includes(v.unit)||v.currency!=='RUB'||v.period_days!==30||v.grace_days!==3||v.auto_renew!==false||typeof v.checkout_enabled!=='boolean'||!(v.test===null||typeof v.test==='boolean')||!(v.terms_sha256===null||typeof v.terms_sha256==='string'&&/^[a-f0-9]{64}$/.test(v.terms_sha256)))return false;
 if(v.checkout_enabled&&(typeof v.test!=='boolean'||v.terms_sha256===null))return false;
 const codes={control:'start',business:'business',agency:'business_plus'};
 return Array.isArray(v.items)&&v.items.length===3&&new Set(v.items.map(p=>record(p)?p.id:null)).size===3&&v.items.every(p=>record(p)&&typeof p.id==='string'&&Object.hasOwn(codes,p.id)&&p.plan===codes[p.id as keyof typeof codes]&&typeof p.name==='string'&&p.name.length>0&&p.name.length<=80&&Number.isSafeInteger(p.amount_minor)&&Number(p.amount_minor)>0&&Number.isSafeInteger(p.accounts)&&Number(p.accounts)>0&&(p.workspaces===undefined||Number.isSafeInteger(p.workspaces)&&Number(p.workspaces)>=1&&Number(p.workspaces)<=5)&&(p.offer_periods_remaining===undefined||p.id==='control'&&p.amount_minor===199000&&p.regular_amount_minor===299000&&Number.isSafeInteger(p.offer_periods_remaining)&&Number(p.offer_periods_remaining)>=1&&Number(p.offer_periods_remaining)<=3));
}
export type CheckoutAttempt={request_id:string;sku:BillingPlan['id'];terms_sha256:string;id?:string;expected_amount_minor?:number};
export function isCheckoutAttempt(v:unknown):v is CheckoutAttempt {
 return record(v)&&typeof v.request_id==='string'&&uuid.test(v.request_id)&&['control','business','agency'].includes(String(v.sku))&&typeof v.terms_sha256==='string'&&/^[a-f0-9]{64}$/.test(v.terms_sha256)&&(v.id===undefined||typeof v.id==='string'&&uuid.test(v.id))&&(v.expected_amount_minor===undefined||Number.isSafeInteger(v.expected_amount_minor)&&Number(v.expected_amount_minor)>0&&Number(v.expected_amount_minor)<=999000);
}
export function isBillingRecovery(v:unknown):v is {order:CheckoutAttempt|null} {
 return record(v)&&(v.order===null||isCheckoutAttempt(v.order)&&typeof v.order.id==='string');
}
export function checkoutUrl(v:unknown):string|null {
 if(typeof v!=='string')return null;
 try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&['yoomoney.ru','yookassa.ru'].includes(u.hostname)?u.href:null;}catch{return null;}
}
