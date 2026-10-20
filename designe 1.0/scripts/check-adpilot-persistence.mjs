import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {initialState,restoreState} from '../components/reference/model.ts';
for(const field of ['platform','account','status','id','name']){
 const raw=structuredClone(initialState);raw.campaigns[0][field]=field==='id'||field==='name'?'':'unknown';
 assert.equal(restoreState(raw),initialState,field+' must be validated');
}
const duplicate=structuredClone(initialState);duplicate.campaigns.push({...duplicate.campaigns[0]});assert.equal(restoreState(duplicate),initialState);
const missingOwner=structuredClone(initialState);missingOwner.members=[];assert.equal(restoreState(missingOwner),initialState);
const owner=structuredClone(initialState);owner.profile.email='new-owner@example.ru';assert.equal(restoreState(owner).members[0].email,owner.profile.email);
const invalidContext=structuredClone(initialState);invalidContext.queries=[{question:'q',answer:'a',context:3}];assert.equal(restoreState(invalidContext),initialState);
const legacy=structuredClone(initialState);legacy.queries=[{question:'q',answer:'a'}];assert.notEqual(restoreState(legacy),initialState);
const ownerCollision=structuredClone(initialState);ownerCollision.members.push({name:'Duplicate',email:ownerCollision.profile.email.toUpperCase(),role:'Аналитик'});assert.equal(restoreState(ownerCollision),initialState);
const require=createRequire(import.meta.url);
let chromium;
try{({chromium}=require('playwright'));}catch{
 ({chromium}=createRequire(process.env.PLAYWRIGHT_PACKAGE||'C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json')('playwright'));
}
const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
const base=process.env.BASE_URL||'http://127.0.0.1:3117',key='adpilot-reference-v2';
const open=async(context,path)=>{const p=await context.newPage();await p.goto(base+path,{waitUntil:'networkidle'});return p;};
try{
 const context=await browser.newContext();
 await context.addCookies([{name:'adpilot-consent',value:'v1:necessary',url:base}]);
 const a=await open(context,'/demo/settings'),b=await open(context,'/demo/settings');
 await a.getByLabel('Имя',{exact:true}).fill('Сохранено в первой вкладке');
 await a.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
 await b.waitForFunction(()=>document.querySelector('.ap-settings input')?.value==='Сохранено в первой вкладке');
 await b.getByRole('button',{name:'Сохранить настройки',exact:true}).click();
 await a.reload({waitUntil:'networkidle'});
 assert.equal(await a.getByLabel('Имя',{exact:true}).inputValue(),'Сохранено в первой вкладке');
 await a.goto(base+'/demo/recommendations',{waitUntil:'networkidle'});
 await b.goto(base+'/demo/recommendations?rec=2',{waitUntil:'networkidle'});
 await a.getByRole('button',{name:'Применить',exact:true}).click();
 await b.getByRole('button',{name:'Применить в демо',exact:true}).click();
 await a.waitForFunction(key=>JSON.parse(localStorage.getItem(key)).applied.length===2,key);
 const saved=await a.evaluate(key=>JSON.parse(localStorage.getItem(key)),key);
 assert.deepEqual(saved.applied,[1,2]);
 assert.equal(saved.events.filter(e=>e.title==='Применена рекомендация'&&e.id!=='a').length,2);
 await a.reload({waitUntil:'networkidle'});
 assert(await a.getByRole('button',{name:'Применена',exact:true}).isDisabled());
 await context.close();
 const blocked=await browser.newContext();
 await blocked.addCookies([{name:'adpilot-consent',value:'v1:necessary',url:base}]);
 await blocked.addInitScript(()=>{Storage.prototype.getItem=()=>{throw new DOMException('Blocked','SecurityError');};Storage.prototype.setItem=()=>{throw new DOMException('Blocked','QuotaExceededError');};});
 const p=await open(blocked,'/demo/recommendations');
 await p.getByRole('button',{name:'Применить',exact:true}).click();
 assert(await p.getByRole('button',{name:'Применена',exact:true}).isDisabled());
 await p.getByRole('link',{name:'Кампании',exact:true}).click();
 await p.getByLabel('Выбрать Поиск | Бренд',{exact:true}).check();
 await p.getByRole('button',{name:'Приостановить',exact:true}).click();
 await p.getByRole('link',{name:'История',exact:true}).click();
 await p.getByRole('heading',{name:'Кампании приостановлены',exact:true}).waitFor();
 await p.getByRole('heading',{name:'Применена рекомендация',exact:true}).first().waitFor();
 await p.locator('#cabinet-menu a[href="/demo/recommendations"]').click();
 assert(await p.getByRole('button',{name:'Применена',exact:true}).isDisabled());
 await blocked.close();
 console.log('PASS: cross-tab settings synchronization, two recommendation updates and events, reload, storage-unavailable state and sequential log updates');
}finally{await browser.close();}
