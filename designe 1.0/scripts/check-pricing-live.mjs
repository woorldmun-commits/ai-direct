import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const base=process.env.INROU_QA_BASE||'http://127.0.0.1:3141';
const fixture=JSON.parse(await fs.readFile(new URL('../artifacts/.runtime/pricing-upgrade/fixture.json',import.meta.url),'utf8'));
assert.equal(fixture.synthetic,true);
const out=path.resolve(import.meta.dirname,'../../docs/pricing-product-2026-10-29');await fs.mkdir(out,{recursive:true});
const report={base,synthetic:true,checks:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const context=await browser.newContext({reducedMotion:'reduce',viewport:{width:1440,height:1000}});
 await context.addCookies([{name:'session',value:fixture.tokens.agency,url:base}]);
 const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 const response=await page.goto(`${base}/workspace/plans?workspace=${fixture.agency}`,{waitUntil:'networkidle',timeout:120000});assert.equal(response.status(),200);
 assert.match(await page.locator('main').innerText(),/Клиентские пространства/);
 const panel=page.getByRole('region',{name:'Клиенты агентства'});await panel.getByLabel('Название клиента').fill('Синтетический клиент · проверка');
 const created=page.waitForResponse(r=>r.url().includes('/billing/clients')&&r.request().method()==='POST');
 await panel.getByRole('button',{name:'Создать отдельное пространство',exact:true}).click();assert.equal((await created).status(),200);
 await panel.getByRole('link',{name:'Синтетический клиент · проверка',exact:true}).waitFor();
 const link=await panel.getByRole('link',{name:'Синтетический клиент · проверка',exact:true}).getAttribute('href');
 const child=new URL(link,base).searchParams.get('workspace');assert.match(child,/^ws_\d+$/);
 report.checks.push('Real SSR Plans with synthetic backend; client created by authenticated owner and appears after refresh');
 await page.goto(`${base}/workspace/plans?workspace=${child}`,{waitUntil:'networkidle'});
 assert.match(await page.locator('main').innerText(),/Доступ этого клиента оплачивается/);
 assert.equal(await page.getByRole('heading',{name:'Оплата подписки',exact:true}).count(),0);
 report.checks.push('Created child receives agency subscription; separate checkout hidden');
 await context.addCookies([{name:'session',value:fixture.tokens.pending,url:base}]);
 await page.goto(`${base}/workspace/plans?workspace=${fixture.pending}`,{waitUntil:'networkidle'});
 assert.match(await page.locator('main').innerText(),/7 дней ещё не начались/);
 await page.route(`**/api/workspaces/${fixture.pending}/direct`,async route=>{
  const result=await route.fetch();const status=await result.json();assert.equal(status.trial_pending,true);assert.equal(status.analysis_access,false);
  // Only provider availability is substituted. No OAuth or external API is used.
  await route.fulfill({json:{...status,enabled:true}});
 });
 await page.goto(`${base}/workspace/connections?workspace=${fixture.pending}`,{waitUntil:'networkidle'});
 assert.equal(await page.getByLabel('Логин рекламного кабинета').isVisible(),true);
 assert.equal(await page.getByRole('button',{name:'Разрешить доступ через Яндекс',exact:true}).isVisible(),true);
 report.checks.push('Fresh pending-trial status from backend keeps Direct form visible; only provider-enabled flag mocked');
 await page.screenshot({path:path.join(out,'pending-connect-desktop.png'),fullPage:true,animations:'disabled'});
 await context.addCookies([{name:'session',value:fixture.tokens.agency,url:base}]);
 await page.goto(`${base}/workspace/plans?workspace=${fixture.agency}`,{waitUntil:'networkidle'});
 await page.screenshot({path:path.join(out,'agency-live-synthetic-desktop.png'),fullPage:true,animations:'disabled'});
 assert.deepEqual(report.errors,[]);report.result='PASS';
}catch(e){report.result='FAIL';report.failure=String(e);throw e;}finally{await fs.writeFile(path.join(out,'live-browser-report.json'),JSON.stringify(report,null,2));await browser.close();}
console.log('PASS real SSR Plans, real synthetic client creation and pending-trial connect form');
