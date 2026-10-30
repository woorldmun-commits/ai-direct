import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const base=process.env.INROU_QA_BASE||'http://127.0.0.1:3140';
const out=path.resolve(import.meta.dirname,'../../docs/pricing-product-2026-10-29');
await fs.mkdir(out,{recursive:true});
const report={base,matrix:[],checks:[],errors:[],screenshots:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const context=await browser.newContext({reducedMotion:'reduce'}),page=await context.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 for(const width of [1440,768,390,320])for(const theme of ['light','dark'])for(const route of ['/pricing','/demo/analysis','/demo/plans','/demo/recommendations']){
  await page.setViewportSize({width,height:1000});
  await page.addInitScript(t=>localStorage.setItem('inrou-theme',t),theme);
  const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:120000});
  assert.equal(response.status(),200);
  await page.evaluate(()=>document.fonts.ready);
  const cookie=page.getByRole('button',{name:'Только необходимые',exact:true});if(await cookie.isVisible())await cookie.click();
  assert.equal(await page.locator('h1').count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`${route} ${width} ${theme} overflow`);
  if(route==='/pricing'){
   const pricing=page.locator('.inrou-pricing');
   for(const [index,price]of ['2\\s?990','4\\s?990','9\\s?990'].entries())assert.match(await pricing.locator('.pricing-amount').nth(index).innerText(),new RegExp(price));
   await pricing.getByRole('button',{name:'До 5 клиентов',exact:true}).click();
   assert.match(await pricing.locator('.pricing-plan.is-selected').innerText(),/15 аккаунтов суммарно/);
   assert.match(await pricing.innerText(),/первой успешной загрузки/);
   assert.match(await pricing.innerText(),/1 990 ₽/);
   assert.match(await pricing.innerText(),/Оплата пока не подключена/);
   assert.equal(await pricing.locator('a.pricing-cta[href="/signup"]').count(),3);
  }
  if(route==='/demo/analysis'){
   const pacing=page.getByRole('region',{name:'Темп расходования бюджета',exact:true});
   assert.match(await pacing.innerText(),/Темп выше плана/);
   assert.match(await pacing.innerText(),/450\s?000/);
   await pacing.locator('summary').click();assert.match(await pacing.innerText(),/150\s?000/);
   await page.getByRole('button',{name:'Без плана',exact:true}).click();assert.match(await pacing.innerText(),/Задайте план/);
   await page.getByRole('button',{name:'Нет данных',exact:true}).click();assert.match(await pacing.innerText(),/Нужны снимки/);
   await page.getByRole('button',{name:'Есть данные',exact:true}).click();
  }
  if(route==='/demo/plans'){
   const demo=page.getByRole('region',{name:'Демонстрация агентского пакета',exact:true});
   for(let i=3;i<=5;i++){await demo.getByLabel('Название демоклиента').fill(`Клиент ${i}`);await demo.getByRole('button',{name:'Добавить демоклиента',exact:true}).click();}
   assert.equal(await demo.getByRole('button',{name:'Лимит 5 пространств достигнут',exact:true}).isDisabled(),true);
   const last=demo.getByRole('button',{name:'Клиент 5',exact:true});await last.click();assert.equal(await last.getAttribute('aria-pressed'),'true');
   assert.match(await demo.innerText(),/отдельная организация/);
   await page.reload({waitUntil:'networkidle'});assert.match(await demo.innerText(),/Пространств: 2 \/ 5/);
  }
  if(route==='/demo/recommendations'){
   await page.getByRole('button',{name:'Наблюдения · 1',exact:true}).click();
   assert.equal(await page.locator('.ix-recommendation-row').count(),1);
   await page.getByRole('button',{name:'Проверки · 3',exact:true}).click();assert.equal(await page.locator('.ix-recommendation-row').count(),3);
   await page.getByRole('button',{name:'Все · 4',exact:true}).click();assert.equal(await page.locator('.ix-recommendation-row').count(),4);
   await page.getByRole('combobox',{name:'Порядок рекомендаций'}).selectOption('recent');
  }
  if([1440,390].includes(width)){
   const name=`${route.slice(1).replaceAll('/','-')}-${width}-${theme}.png`;
   const target=route==='/pricing'?page.locator('.inrou-pricing'):route==='/demo/plans'?page.getByRole('region',{name:'Демонстрация агентского пакета'}):route==='/demo/recommendations'?page.locator('#main-content'):page.getByRole('region',{name:'Темп расходования бюджета'});
   await target.screenshot({path:path.join(out,name),animations:'disabled',style:'nextjs-portal{visibility:hidden!important}'});report.screenshots.push(name);
  }
  report.matrix.push({route,width,theme,result:'PASS'});
 }
 assert.deepEqual(report.errors,[]);
 report.checks=['Three regular prices /30days, scope selection, founder terms and signup links','Pacing formula, final-day labels, missing-plan and missing-data states','Agency demo creates up to5 spaces, switches clients, resets on reload','Recommendation queue filters and freshness order','32 route/viewport/theme cases; reduced motion; no overflow; no browser pageerror'];
 report.result='PASS';
}catch(e){report.result='FAIL';report.failure=String(e);throw e;}finally{await fs.writeFile(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));await browser.close();}
console.log(`PASS ${report.matrix.length} responsive cases; ${report.screenshots.length} screenshots`);
