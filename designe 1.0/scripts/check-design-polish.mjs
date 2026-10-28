import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium} = createRequire(path.join(runtime, 'package.json'))(runtime);
const base = process.env.INROU_QA_BASE || 'http://127.0.0.1:3152';
const out = path.resolve(import.meta.dirname, process.env.INROU_QA_OUT || '../../docs/design-polish-2026-10-25');
await fs.mkdir(out, {recursive:true});
const browser = await chromium.launch({channel:'msedge', headless:true});
const report = {started:new Date().toISOString(), browser:browser.version(), matrix:[], checks:[], errors:[]};
const check = async (name, fn) => {
  try {await fn();report.checks.push({name,pass:true});}
  catch (error) {report.checks.push({name,pass:false,error:error.message});}
};
try {
  const context = await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
  await context.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
  await context.addInitScript(() => localStorage.setItem('inrou-theme','system'));
  const page = await context.newPage();
  page.on('pageerror',e => report.errors.push(e.message));
  const visit = async route => {
    const response = await page.goto(base+route,{waitUntil:'domcontentloaded',timeout:120000});
    await page.locator('h1').first().waitFor({state:'visible',timeout:60000});
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => document.fonts.ready);
    return response;
  };
  const routes = ['/', '/features', '/how-it-works', '/login', '/demo/analysis', '/demo/recommendations', '/demo/midnight/overview'];
  for (const route of routes) {
    for (const [width,height,theme] of [[1440,1000,'light'],[1440,1000,'dark'],[768,1024,'light'],[390,844,'light'],[320,700,'light']]) {
      await page.setViewportSize({width,height});
      await page.emulateMedia({colorScheme:theme});
      const response = await visit(route);
      const item = {route,width,height,expectedTheme:theme,status:response.status(),...await page.evaluate(() => ({overflow:document.documentElement.scrollWidth>innerWidth+1,h1:document.querySelector('h1').textContent,theme:document.documentElement.dataset.theme,brokenImages:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src)}))};
      report.matrix.push(item);
      assert.equal(item.status,200,route);
      assert.equal(item.theme,item.expectedTheme,`${route} theme ${width}`);
      assert.equal(item.overflow,false,`${route} overflow ${width}`);
      assert.equal(item.brokenImages.length,0,route);
      const name = route==='/'?'home':route.replaceAll('/','-').slice(1);
      if (width!==768) await page.screenshot({path:path.join(out,`${name}-${width}-${theme}.png`),animations:'disabled'});
    }
    console.log(`matrix ${route}`);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.emulateMedia({colorScheme:'light'});
  await check('one mark in marketing, auth and demo',async()=>{
    for(const route of ['/','/login','/demo/analysis']) {
      await visit(route);
      assert.ok(await page.locator('.inrou-brand-mark').count());
      assert.equal(await page.locator('.inrou-brand-mark path').first().getAttribute('d'),'M7 32V20C7 12.82 12.82 7 20 7H25V13H20C16.13 13 13 16.13 13 20V32H7Z');
    }
  });
  await check('process graphic is distinct from the hero',async()=>{
    await visit('/how-it-works');
    assert.equal(await page.locator('.ix-process-art-card').count(),3);
    assert.equal(await page.locator('main .ms-artwork').count(),0);
  });
  await check('chart keyboard, tooltip, data table and finite geometry',async()=>{
    await visit('/demo/analysis');
    const hit=page.locator('.ix-chartwrap .ix-hit').first();
    await hit.focus();await page.keyboard.press('End');
    await page.locator('.ix-tooltip').waitFor();
    assert.equal(await page.locator('.ix-chartwrap').first().evaluate(e=>[...e.querySelectorAll('path,polyline')].some(n=>/NaN|Infinity/.test(n.getAttribute('d')||n.getAttribute('points')||''))),false);
    await page.keyboard.press('Escape');await page.locator('.ix-tooltip').waitFor({state:'detached'});
    await page.getByRole('button',{name:'Таблица',exact:true}).first().click();
    assert.ok(await page.getByRole('region',{name:/Таблица:/}).count());
  });
  await check('recommendation drawer keyboard tabs, Escape and focus return',async()=>{
    await visit('/demo/recommendations');
    const trigger=page.getByRole('button',{name:'Подробнее →'}).first();
    await trigger.click();
    const dialog=page.getByRole('dialog');await dialog.waitFor();
    await page.screenshot({path:path.join(out,'recommendation-drawer-1440-light.png'),animations:'disabled'});
    await dialog.getByRole('tab').first().focus();await page.keyboard.press('ArrowRight');
    assert.equal(await dialog.getByRole('tab').nth(1).getAttribute('aria-selected'),'true');
    assert.equal(await dialog.getByRole('tabpanel').filter({visible:true}).evaluate(e=>getComputedStyle(e).animationName),'none');
    await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
    assert.equal(await trigger.evaluate(e=>e===document.activeElement),true);
  });
  await check('marketing chart starts without tooltip; roving keyboard and series controls',async()=>{
    await visit('/demo/midnight/overview');
    assert.equal(await page.locator('.ms-chart-tooltip').count(),0);
    const chart=page.locator('.ms-chart').first();
    assert.equal(await chart.locator('.ms-chart-points button[tabindex="0"]').count(),1);
    await chart.locator('.ms-chart-points button').first().focus();await page.keyboard.press('End');
    assert.equal(await chart.locator('.ms-chart-points button').last().evaluate(e=>e===document.activeElement),true);
    await page.keyboard.press('Escape');assert.equal(await chart.locator('.ms-chart-tooltip').count(),0);
    for (const button of await chart.locator('.ms-legend button[aria-pressed]').all()) await button.click();
    assert.match(await chart.getByRole('status').textContent(),/Все ряды скрыты/);
  });
  await check('touch tooltip stays visible and within mobile viewport',async()=>{
    const touch=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const p=await touch.newPage();
    try {
      await p.goto(base+'/demo/analysis',{waitUntil:'domcontentloaded',timeout:120000});
      await p.waitForLoadState('networkidle');
      const hit=p.locator('.ix-hit').first();await hit.waitFor();await hit.tap();
      const tip=p.locator('.ix-tooltip');await tip.waitFor();
      const r=await tip.boundingBox();assert.ok(r.x>=0 && r.x+r.width<=391);
    } finally {await touch.close();}
  });
  await check('reduced motion disables decorative movement',async()=>{
    await visit('/');
    assert.equal(await page.locator('.home-hero h1').evaluate(e=>getComputedStyle(e).animationName),'none');
    await visit('/demo/analysis');
    assert.equal(await page.locator('.ix-chart-lines').first().evaluate(e=>getComputedStyle(e).animationName),'none');
  });
  await check('normal motion: one-time 280ms section reveal; instant keyboard chart',async()=>{
    await page.emulateMedia({reducedMotion:'no-preference'});
    await visit('/');
    await page.locator('.home-main>.home-section').nth(2).evaluate(e=>e.scrollIntoView());
    await page.waitForFunction(()=>document.getAnimations().some(a=>a.effect?.getTiming().duration===280));
    await visit('/demo/analysis');
    await page.locator('.ix-hit').first().focus();
    await page.locator('.ix-tooltip').waitFor();
    assert.equal(await page.locator('.ix-tooltip').evaluate(e=>getComputedStyle(e).animationName),'none');
    assert.equal(await page.locator('.ix-chart-lines').first().evaluate(e=>getComputedStyle(e).animationName),'none');
  });
  await context.close();
} catch(error) {report.errors.push(error.stack);}
finally {
  await browser.close();
  report.finished=new Date().toISOString();
  report.pass=report.errors.length===0&&report.checks.every(c=>c.pass)&&report.matrix.length===35;
  await fs.writeFile(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));
}
console.log(JSON.stringify({pass:report.pass,matrix:report.matrix.length,checks:report.checks,errors:report.errors},null,2));
if(!report.pass)process.exitCode=1;
