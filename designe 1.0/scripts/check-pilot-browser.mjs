import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname,'..');
const base = process.env.BASE_URL || 'http://127.0.0.1:3130';
(async()=>{
  const fixture = JSON.parse(await fs.readFile(path.join(root,'artifacts/.runtime/fixture.json'),'utf8'));
  const out = path.join(root,'artifacts/pilot'); await fs.mkdir(out,{recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const passed = [], errors = [];
  async function context(who){
    const ctx = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    if(who) await ctx.addCookies([{name:'session',value:fixture.tokens[who],url:base,httpOnly:true,sameSite:'Lax'}]);
    await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
    await ctx.addInitScript(()=>{window.__violations=[];document.addEventListener('securitypolicyviolation',e=>window.__violations.push(e.violatedDirective));});
    const p = await ctx.newPage(); p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    return {ctx,p};
  }
  try {
    for(const who of [null,'expired','revoked']){
      const {ctx,p} = await context(who); await p.goto(base+'/workspace/overview',{waitUntil:'networkidle'});
      assert.equal(new URL(p.url()).pathname,'/login','no valid session must lead to /login');
      assert.equal(await p.locator('.ix-kpi').count(),0);
      await ctx.close();passed.push((who||'missing')+' session sent to /login without any cabinet data');
    }
    const {ctx,p}=await context('owner');
    const r = await p.goto(base+'/workspace/overview',{waitUntil:'networkidle'});
    assert.match(r.headers()['cache-control'],/no-store/);
    assert.match(await p.locator('meta[name=robots]').getAttribute('content'),/noindex/);
    assert.equal(await p.locator('.ix-kpi').count(),4);
    assert.match(await p.locator('main').innerText(),/Яндекс Директ/);
    assert(!(await p.locator('main').innerText()).includes('secret-b1'));
    assert(!/telegram/i.test(await p.locator('body').innerText()),'Telegram must not appear');
    const html=await p.content();assert(!html.includes(fixture.tokens.owner));assert(!html.includes('127.0.0.1:3121'));
    await p.screenshot({path:path.join(out,'workspace-1440.png'),fullPage:true});
    for(const width of [834,390,320]){
      await p.setViewportSize({width,height:1000});
      assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow at '+width);
      await p.screenshot({path:path.join(out,`workspace-${width}.png`),fullPage:true});
    }
    await p.setViewportSize({width:1440,height:1000});
    await p.goto(base+'/workspace/recommendations?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    await p.getByRole('link',{name:/Подробнее →/}).first().click();
    await p.locator('.ix-drawerbox').waitFor();
    assert(await p.getByRole('heading',{name:'Расчёт и последствия'}).isVisible());
    assert.match(await p.locator('.ix-drawerbox').innerText(),/не подтверждённая экономия/);
    assert.deepEqual(await p.evaluate(()=>window.__violations),[]);
    await ctx.close();passed.push('Actual FastAPI/RLS → SSR → overview KPIs and passport drawer, Decimal Value metadata, 834/390/320 layouts, no token leak');
    for(const [who,ws] of [['viewer','a2'],['owner','b1']]){
      const {ctx,p}=await context(who);await p.goto(base+'/workspace/overview?workspace='+fixture.workspaces[ws],{waitUntil:'networkidle'});
      assert(await p.getByRole('heading',{name:'Нет доступа'}).isVisible());
      assert.equal(await p.locator('.ix-kpi').count(),0);await ctx.close();passed.push(`${who} cannot view foreign workspace ${ws}`);
    }
    const member=await context('member');await member.p.goto(base+'/workspace/overview',{waitUntil:'networkidle'});
    assert(await member.p.getByRole('heading',{name:'Пока нет рабочих пространств'}).isVisible());await member.ctx.close();passed.push('No workspace membership state');
    const empty=await context('empty');await empty.p.goto(base+'/workspace/overview',{waitUntil:'networkidle'});
    assert(await empty.p.locator('.ix-value-na').count()>=2);
    assert.match(await empty.p.locator('main').innerText(),/Аудит ещё не выполнен/);
    await empty.p.goto(base+'/workspace/campaigns',{waitUntil:'networkidle'});
    assert(await empty.p.getByRole('heading',{name:/Построчный список кампаний пока не передаётся API/}).isVisible());
    await empty.ctx.close();passed.push('Real empty workspace: unavailable values, no zero substitution, no invented campaigns or findings');
    const menu=await context('owner');await menu.p.setViewportSize({width:390,height:900});await menu.p.goto(base+'/workspace/overview',{waitUntil:'networkidle'});
    const trigger=menu.p.getByRole('button',{name:'Открыть меню',exact:true}).first();await trigger.click();
    assert.equal(await menu.p.locator('#ix-sidebar').getAttribute('aria-modal'),'true');
    await menu.p.keyboard.press('Escape');assert.equal(await trigger.getAttribute('aria-expanded'),'false');
    await trigger.click();await menu.p.setViewportSize({width:750,height:900});await menu.p.waitForTimeout(150);
    assert.equal(await menu.p.locator('#ix-sidebar').getAttribute('aria-modal'),'true','750px remains the specified mobile layout');
    await menu.p.setViewportSize({width:768,height:900});await menu.p.waitForTimeout(150);
    assert.equal(await menu.p.locator('#ix-sidebar').getAttribute('aria-modal'),null,'menu resets on desktop resize');
    await menu.ctx.close();passed.push('Mobile menu: dialog semantics, Esc, resize reset');
    assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(out,'checks.json'),JSON.stringify({passed,errors,backend:'Actual FastAPI + disposable PostgreSQL with synthetic accounts; not real advertising accounts'},null,2));
    console.log('PASS',passed.length,'pilot/browser groups; no page/console errors.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
