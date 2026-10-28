import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
function load(file,dependencies={}){const exports={};new Function('exports','require',ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports,name=>{assert(name in dependencies,name);return dependencies[name];});return exports;}
const {isBillingCatalog,isCheckoutAttempt,isBillingRecovery,checkoutUrl}=load('../lib/billing-contract.ts');
const catalog={items:[{id:'control',name:'Контроль',plan:'start',amount_minor:299000,accounts:1},{id:'business',name:'Бизнес',plan:'business',amount_minor:499000,accounts:5},{id:'agency',name:'Агентство',plan:'business_plus',amount_minor:999000,accounts:15}],unit:'workspace',currency:'RUB',period_days:30,grace_days:3,auto_renew:false,checkout_enabled:false,test:null,terms_sha256:null};
assert(isBillingCatalog(catalog));
assert(!isBillingCatalog({...catalog,checkout_enabled:true}));
assert(!isBillingCatalog({...catalog,items:[catalog.items[0],catalog.items[0],catalog.items[2]]}));
assert(!isBillingCatalog({...catalog,items:catalog.items.map(p=>({...p,amount_minor:'299000'}))}));
assert(!isBillingCatalog({...catalog,items:catalog.items.map(p=>({...p,plan:'unknown'}))}));
assert(!isBillingCatalog({...catalog,auto_renew:true}));
assert(isCheckoutAttempt({request_id:'46a165c1-395c-4d8f-8770-4c974b711f64',sku:'control',terms_sha256:'a'.repeat(64)}));
assert(!isCheckoutAttempt({request_id:'bad',sku:'control',terms_sha256:'a'.repeat(64)}));
assert.equal(checkoutUrl('https://yoomoney.ru/checkout/payments/v2/contract'), 'https://yoomoney.ru/checkout/payments/v2/contract');
for(const url of ['http://yoomoney.ru','https://yoomoney.ru.evil.test','https://user:pass@yoomoney.ru','javascript:alert(1)','https://yoomoney.ru:8443/'])assert.equal(checkoutUrl(url),null);
const {workspacePath}=load('../lib/workspace-path.ts');
assert(workspacePath('/billing/plans','GET'));
for(const method of ['POST','DELETE'])assert(!workspacePath('/billing/plans',method));
for(const path of ['/workspaces/ws_1/billing/orders','/workspaces/ws_1/billing/orders/46a165c1-395c-4d8f-8770-4c974b711f64/checkout','/workspaces/ws_1/billing/orders/46a165c1-395c-4d8f-8770-4c974b711f64/refresh'])assert(workspacePath(path,'POST'));
for(const path of ['/workspaces/ws_1/billing/orders?url=evil','/workspaces/ws_1/billing/orders/../../me','/workspaces/ws_1/billing/orders/46a165c1-395c-4d8f-8770-4c974b711f64/delete'])assert(!workspacePath(path,'POST'));
let calls=0;
const {relayBillingWebhook}=load('../lib/billing-webhook.ts',{'./api-origin':{apiOrigin:()=> 'http://127.0.0.1:8081'},'./auth-proxy':{readLimited:async(stream,limit)=>{const raw=await new Response(stream).text();if(raw.length>limit)throw Error();return raw;}}});
const original=globalThis.fetch;
try{
 globalThis.fetch=async(url,options)=>{calls++;assert.equal(String(url),'http://127.0.0.1:8081/api/v1/billing/yookassa/webhook');assert.deepEqual(Object.keys(options.headers).sort(),['Accept','Content-Type']);assert.equal(options.redirect,'error');return Response.json({accepted:true});};
 const req=()=>new Request('https://example.test/api/billing/yookassa/webhook',{method:'POST',headers:{'Content-Type':'application/json',Cookie:'private=do-not-forward',Authorization:'Bearer attacker',Origin:'https://evil.test'},body:'{"type":"notification"}'});
 assert.equal((await relayBillingWebhook(req())).status,200);assert.equal(calls,1);
 assert.equal((await relayBillingWebhook(new Request('https://example.test',{method:'POST',headers:{'Content-Type':'text/plain'},body:'{}'}))).status,415);
 assert.equal(calls,1);
 globalThis.fetch=async()=>Response.json({error:'unavailable'},{status:503});assert.equal((await relayBillingWebhook(req())).status,503);
 globalThis.fetch=async()=>{throw Error('provider secret');};assert.equal((await relayBillingWebhook(req())).status,503);
}finally{globalThis.fetch=original;}
console.log('PASS billing catalog, operation identity, hosted URL, closed BFF paths and bounded callback relay');

assert(isBillingRecovery({order:null}));
assert(isBillingRecovery({order:{id:'46a165c1-395c-4d8f-8770-4c974b711f64',request_id:'46a165c1-395c-4d8f-8770-4c974b711f64',sku:'control',terms_sha256:'a'.repeat(64)}}));
assert(!isBillingRecovery({order:{request_id:'46a165c1-395c-4d8f-8770-4c974b711f64',sku:'control',terms_sha256:'a'.repeat(64)}}));
assert(workspacePath('/workspaces/ws_1/billing/orders/current','GET'));
assert(!workspacePath('/workspaces/ws_1/billing/orders/current','POST'));
assert(!workspacePath('/workspaces/ws_1/billing/orders/current?workspace=ws_2','GET'));
console.log('PASS durable order recovery and closed current-order route');
