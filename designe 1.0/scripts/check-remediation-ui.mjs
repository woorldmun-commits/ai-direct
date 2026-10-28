import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const root=path.resolve(import.meta.dirname,'..'),base='http://127.0.0.1:3130';
const out=path.resolve(root,'../docs/audit-remediation-2026-10-25/browser');
const runtime=process.env.PLAYWRIGHT_MODULE||path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const children=[],report={synthetic:true,build:(await fs.readFile(path.join(root,'.next/BUILD_ID'),'utf8')).trim(),pages:[],checks:[],errors:[]};
await fs.mkdir(out,{recursive:true});
for(const url of ['http://127.0.0.1:3121/api/v1/health',base+'/api/health']){
 let occupied=false;try{await fetch(url,{signal:AbortSignal.timeout(500)});occupied=true;}catch{}
 assert(!occupied,'QA ports are occupied; refusing unrelated services');
}
const start=(bin,args,env={})=>{const p=spawn(bin,args,{cwd:root,env:{...process.env,...env},windowsHide:true,stdio:['ignore','ignore','pipe']});children.push(p);return p;};
async function ready(url,child){for(let i=0;i<150;i++){assert.equal(child.exitCode,null,'Owned QA service stopped');try{if((await fetch(url,{signal:AbortSignal.timeout(1000)})).ok)return;}catch{}await new Promise(r=>setTimeout(r,200));}throw Error('Owned QA service unavailable');}
let browser;
try{
 const api=start(path.resolve(root,'../backend/.venv/Scripts/python.exe'),['scripts/pilot-fixture.py'],{TEST_DATABASE_URL:'',DATABASE_URL:'',INROU_BILLING_ENABLED:'0'});
 await ready('http://127.0.0.1:3121/api/v1/health',api);
 const web=start(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3130'],{INROU_API_URL:'http://127.0.0.1:3121',INROU_APP_ORIGIN:base,INROU_DEMO:'1'});
 await ready(base+'/api/health',web);
 const fixture=JSON.parse(await fs.readFile(path.join(root,'artifacts/.runtime/fixture.json'),'utf8'));
 browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
 await context.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
 await context.addCookies([{name:'session',value:fixture.tokens.owner,url:base,httpOnly:true,sameSite:'Lax'},{name:'inrou-consent',value:'v1:necessary',url:base}]);
 const page=await context.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 const ws=fixture.workspaces.a1;
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:900});
  for(const route of ['/agencies','/contact','/login','/login?legacy=1',`/workspace/analysis?workspace=${ws}`,`/workspace/plans?workspace=${ws}`,`/workspace/team?workspace=${ws}`,`/workspace/recommendations?workspace=${ws}`,`/workspace/creatives?workspace=${ws}`]){
   const response=await page.goto(base+route,{waitUntil:'networkidle'});
   assert.equal(response.status(),200,route);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,route+' overflow');
   if(route==='/agencies')assert.equal(await page.getByRole('link',{name:'Посмотреть условия',exact:true}).getAttribute('href'),'/pricing');
   if(route==='/contact')assert.equal(await page.getByRole('link',{name:'Посмотреть продукт',exact:true}).getAttribute('href'),'/#product-preview');
   if(route==='/login')assert.equal(await page.getByText('Войти через Яндекс ID',{exact:true}).count(),0);
   if(route==='/login?legacy=1')assert.equal(await page.locator('details.ref-auth-alternative').count(),1);
   if(route.startsWith('/workspace/plans')){await page.getByRole('heading',{name:'Оплата подписки',exact:true}).waitFor();assert.match(await page.locator('body').innerText(),/Приём платежей откроется/);assert.equal(await page.getByRole('button',{name:'Перейти к оплате в ЮKassa',exact:true}).count(),0);}
   if(route.startsWith('/workspace/team'))assert.equal(await page.getByRole('heading',{name:'Участники',exact:true}).count(),1);
   if(route.startsWith('/workspace/creatives')){const planned=page.getByText('Планируется',{exact:true});await planned.waitFor();assert.equal(await page.locator('nav.ix-context-links details').getAttribute('open'),null);}
   report.pages.push({route,width,status:response.status(),overflow:false});
   if(width===1440&&route.startsWith('/workspace/plans'))await page.screenshot({path:path.join(out,'plans-desktop.png'),fullPage:true});
  }
 }
 const viewer=await browser.newContext();
 await viewer.addCookies([{name:'session',value:fixture.tokens.viewer,url:base,httpOnly:true,sameSite:'Lax'}]);
 const restricted=await viewer.newPage();await restricted.goto(base+`/workspace/plans?workspace=${ws}`,{waitUntil:'networkidle'});
 assert.match(await restricted.locator('body').innerText(),/доступны владельцу и администратору/);report.checks.push('viewer cannot see payment controls');
 const graftBrowser=path.join(os.homedir(),'.codex/skills/gstack/browse/dist/browse.exe');
 const tab=JSON.parse(execFileSync(graftBrowser,['newtab',base+'/login','--json'],{cwd:root,encoding:'utf8',windowsHide:true,timeout:30000}));
 try{await fs.writeFile(path.join(out,'gstack-login-snapshot.txt'),execFileSync(graftBrowser,['snapshot','-i'],{cwd:root,windowsHide:true,timeout:30000}));execFileSync(graftBrowser,['screenshot',path.join(out,'gstack-login.png')],{cwd:root,windowsHide:true,timeout:30000});report.checks.push('gstack own tab: login snapshot and screenshot');}finally{execFileSync(graftBrowser,['closetab',String(tab.tabId)],{cwd:root,windowsHide:true,timeout:30000});}
 assert.deepEqual(report.errors,[]);
 report.passed=true;
}catch(error){report.passed=false;report.failure=error.message;process.exitCode=1;}finally{
 await browser?.close();for(const child of children.reverse())if(child.exitCode===null)child.kill();
 await fs.writeFile(path.join(out,'results.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({passed:report.passed,pages:report.pages.length,checks:report.checks,failure:report.failure}));
}
