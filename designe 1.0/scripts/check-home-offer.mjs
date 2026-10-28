import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const base=process.env.INROU_QA_BASE||'http://127.0.0.1:3154';
const out=path.resolve(import.meta.dirname,process.env.INROU_HOME_QA_OUT||'../../docs/home-rebuild-2026-10-25');
await fs.mkdir(out,{recursive:true});
const report={started:new Date().toISOString(),matrix:[],checks:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
const check=async(name,fn)=>{try{await fn();report.checks.push({name,pass:true});}catch(e){report.checks.push({name,pass:false,error:e.message});}};
try{
 const ctx=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
 await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
 await ctx.addInitScript(()=>localStorage.setItem('inrou-theme','system'));
 const page=await ctx.newPage();
 page.on('pageerror',e=>report.errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'&&/hydration|server rendered|react.dev\/errors/i.test(m.text()))report.errors.push(m.text());});
 for(const width of [320,375,390,768,1024,1440,1920,2560])for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:width<768?844:1000});
  await page.emulateMedia({colorScheme:theme});
  const res=await page.goto(base+'/',{waitUntil:'networkidle',timeout:120000});
  await page.evaluate(()=>document.fonts.ready);
  const state=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,theme:document.documentElement.dataset.theme,headings:document.querySelectorAll('h1').length,canvas:document.querySelector('.home-redesign').getBoundingClientRect().width,invalidImages:[...document.images].filter(i=>i.complete&&!i.naturalWidth).length}));
  report.matrix.push({width,expectedTheme:theme,status:res.status(),...state});
  assert.equal(res.status(),200);assert.equal(state.overflow,false,`overflow ${width} ${theme}`);assert.equal(state.theme,theme);assert.equal(state.headings,1);assert.equal(state.invalidImages,0);
  if([390,1440].includes(width))await page.screenshot({path:path.join(out,`home-${width}-${theme}.png`),animations:'disabled'});
  if(width===1440&&theme==='light')await page.screenshot({path:path.join(out,'home-desktop-full.png'),fullPage:true,animations:'disabled'});
  console.log(`${width} ${theme}`);
 }
 const wide=report.matrix.filter(x=>x.width>=1920&&x.theme==='light');assert.equal(wide[0].canvas,wide[1].canvas);
 await check('project illustration loads with an intrinsic aspect ratio and accessible description',async()=>{
  const image=page.locator('.home-hero-visual img');
  assert.ok(await image.evaluate(e=>e.complete&&e.naturalWidth>0));
  assert.equal(await image.getAttribute('width'),'1536');
  assert.equal(await image.getAttribute('height'),'1024');
  assert.match(await image.getAttribute('alt'),/Рекламные данные/);
 });
 await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({colorScheme:'light'});await page.goto(base+'/',{waitUntil:'networkidle'});
 await check('product preview switches all three views by keyboard',async()=>{
  await page.getByRole('button',{name:'Рекомендации',exact:true}).focus();await page.keyboard.press('Enter');
  await page.locator('.home-preview-recommendation').waitFor();
  assert.equal(await page.getByRole('button',{name:'Рекомендации',exact:true}).getAttribute('aria-pressed'),'true');
  await page.getByRole('button',{name:'Источники',exact:true}).click();await page.locator('.home-preview-sources').waitFor();
  assert.match(await page.locator('.home-preview-sources').textContent(),/Ваши аккаунты не подключены/);
  await page.getByRole('button',{name:'Расходы',exact:true}).click();await page.locator('.home-preview-cost').waitFor();
 });
 await check('subscription price and all in-page links are visible and valid',async()=>{
  for(const href of await page.locator('a[href^="#"]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href'))))assert.ok(await page.locator(href).count(),href);
  await page.locator('.home-header-actions>a[href="#plans"]').click();
  await page.waitForFunction(()=>{const y=document.querySelector('#plans').getBoundingClientRect().top;return y>=-20&&y<innerHeight;});
  assert.ok(await page.locator('.home-plan-price').isVisible());
  assert.match(await page.locator('.home-plan-price').textContent(),/2\s*990/);
  assert.match(await page.locator('.home-plan-card>small').textContent(),/Оплата пока не подключена/);
  assert.equal(await page.locator('.home-plan-card a[href="/signup"]').count(),1);
  assert.equal(await page.locator('.home-redesign a[href^="/demo"]').count(),0,'Homepage preview must work when demo routes are disabled');
  await page.screenshot({path:path.join(out,'subscription-desktop.png'),animations:'disabled'});
 });
 await check('recommendation CTA selects the corresponding on-page demo view',async()=>{
  await page.locator('.home-decision-copy a[href="#product-preview"]').click();
  await page.locator('.home-preview-recommendation').waitFor();
  await page.waitForFunction(()=>{const y=document.querySelector('#product-preview').getBoundingClientRect().top;return y>=-20&&y<innerHeight;});
 });
 await check('FAQ opens with keyboard and keeps answer readable',async()=>{
  const summary=page.locator('.home-faq summary').first();await summary.focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('.home-faq details').first().getAttribute('open'),'');
  assert.match(await page.locator('.home-faq details').first().textContent(),/Директ остаётся/);
 });
 await check('mobile menu traps focus, closes with Escape and returns focus',async()=>{
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/',{waitUntil:'networkidle'});
  const trigger=page.getByRole('button',{name:'Открыть меню'});await trigger.click();
  const dialog=page.getByRole('dialog');await dialog.waitFor();
  assert.ok(await dialog.evaluate(e=>e.contains(document.activeElement)));
  await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
  assert.equal(await trigger.evaluate(e=>e===document.activeElement),true);
 });
 await check('mobile menu subscription link reaches subscription section',async()=>{
  await page.getByRole('button',{name:'Открыть меню'}).click();
  await page.getByRole('dialog').getByRole('link',{name:'Подписка'}).click();
  await page.getByRole('dialog').waitFor({state:'detached'});
  await page.waitForFunction(()=>{const y=document.querySelector('#plans').getBoundingClientRect().top;return y>=-20&&y<innerHeight;});
 });
 await check('mobile menu demo link closes menu and reaches embedded preview',async()=>{
  await page.goto(base+'/',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Открыть меню'}).click();
  await page.getByRole('dialog').getByRole('link',{name:'Посмотреть демо'}).click();
  await page.getByRole('dialog').waitFor({state:'detached'});
  await page.waitForFunction(()=>{const y=document.querySelector('#product-preview').getBoundingClientRect().top;return y>=-20&&y<innerHeight;});
 });
 await check('200 percent page zoom stays inside mobile viewport',async()=>{
  await page.goto(base+'/',{waitUntil:'networkidle'});
  await page.evaluate(()=>{document.documentElement.style.zoom='2';});
  await page.setViewportSize({width:780,height:900});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 });
 await ctx.close();
}catch(e){report.errors.push(e.stack);}finally{await browser.close();report.finished=new Date().toISOString();report.pass=!report.errors.length&&report.matrix.length===16&&report.checks.every(x=>x.pass);await fs.writeFile(path.join(out,'home-browser-report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({pass:report.pass,cases:report.matrix.length,checks:report.checks,errors:report.errors},null,2));if(!report.pass)process.exitCode=1;
