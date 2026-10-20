import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const {chromium} = require('C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = path.resolve(__dirname,'..');
const base = process.env.BASE_URL || 'http://127.0.0.1:3120';
(async()=>{
  const fixture = JSON.parse(await fs.readFile(path.join(root,'artifacts/.runtime/fixture.json'),'utf8'));
  const out = path.join(root,'artifacts/pilot'); await fs.mkdir(out,{recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const passed = [], errors = [];
  async function context(who){
    const ctx = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    if(who) await ctx.addCookies([{name:'session',value:fixture.tokens[who],url:base,httpOnly:true,sameSite:'Lax'}]);
    await ctx.addCookies([{name:'adpilot-consent',value:'v1:necessary',url:base}]);
    await ctx.addInitScript(()=>{window.__violations=[];document.addEventListener('securitypolicyviolation',e=>window.__violations.push(e.violatedDirective));});
    const p = await ctx.newPage(); p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    return {ctx,p};
  }
  try {
    for(const who of [null,'expired','revoked']){
      const {ctx,p} = await context(who); const r=await p.goto(base+'/workspace',{waitUntil:'networkidle'});
      assert(await p.getByRole('heading',{name:'Нужен доступ участника пилота'}).isVisible());
      assert.match(r.headers()['cache-control'],/no-store/);
      assert.match(await p.locator('meta[name=robots]').getAttribute('content'),/noindex/);
      assert.equal(await p.locator('.pilot-metric').count(),0);
      await ctx.close();passed.push((who||'missing')+' session denied without demo fallback');
    }
    const {ctx,p}=await context('owner');
    await p.goto(base+'/workspace',{waitUntil:'networkidle'});
    assert.equal(await p.locator('.pilot-metric').count(),3);
    assert(await p.locator('.pilot-recommendation').count()>0);
    assert.match(await p.locator('.pilot-main').innerText(),/Яндекс Директ/);
    assert(!(await p.locator('.pilot-main').innerText()).includes('secret-b1'));
    const html=await p.content();assert(!html.includes(fixture.tokens.owner));assert(!html.includes('127.0.0.1:3121'));
    const shown=await p.locator('.pilot-recommendation').count();
    await p.screenshot({path:path.join(out,'workspace-1440.png'),fullPage:true});
    for(const width of [834,390,320]){
      await p.setViewportSize({width,height:1000});
      assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await p.screenshot({path:path.join(out,`workspace-${width}.png`),fullPage:true});
    }
    await p.getByText('Основание и ограничения',{exact:true}).first().click();
    assert(await p.getByText('Версия рекомендации',{exact:true}).first().isVisible());
    assert.match(await p.locator('.pilot-main').innerText(),/Карточки нельзя суммировать/);
    assert.deepEqual(await p.evaluate(()=>window.__violations),[]);
    await ctx.close();passed.push(`Actual FastAPI/RLS → SSR → ${shown} recommendation(s), Decimal Value metadata, mobile layouts, no token leak`);
    for(const [who,ws] of [['viewer','a2'],['owner','b1']]){
      const {ctx,p}=await context(who);await p.goto(base+'/workspace?workspace='+fixture.workspaces[ws],{waitUntil:'networkidle'});
      assert(await p.getByRole('heading',{name:'Рабочее пространство недоступно'}).isVisible());
      assert.equal(await p.locator('.pilot-metric').count(),0);await ctx.close();passed.push(`${who} cannot view foreign workspace ${ws}`);
    }
    const member=await context('member');await member.p.goto(base+'/workspace',{waitUntil:'networkidle'});
    assert(await member.p.getByRole('heading',{name:'Пока нет рабочих пространств'}).isVisible());await member.ctx.close();passed.push('No workspace membership state');
    const empty=await context('empty');await empty.p.goto(base+'/workspace',{waitUntil:'networkidle'});
    assert.equal(await empty.p.locator('[data-value=unavailable]').count(),2);
    assert(await empty.p.getByRole('heading',{name:'Активных рекомендаций нет'}).isVisible());
    assert.match(await empty.p.locator('.pilot-main').innerText(),/Аудит ещё не выполнен/);
    await empty.ctx.close();passed.push('Real empty workspace: unavailable values, no zero substitution, no invented findings');
    const menu=await context(null);await menu.p.setViewportSize({width:390,height:900});await menu.p.goto(base,{waitUntil:'networkidle'});
    const trigger=menu.p.getByRole('button',{name:'Открыть меню',exact:true});await trigger.click();
    await menu.p.setViewportSize({width:750,height:900});await menu.p.waitForTimeout(120);
    assert.equal(await menu.p.locator('.ap-landing-menu').getAttribute('aria-expanded'),'false');
    await menu.p.setViewportSize({width:390,height:900});assert.equal(await trigger.getAttribute('aria-expanded'),'false');
    await menu.p.goto(base+'/demo/changes',{waitUntil:'networkidle'});
    assert(await menu.p.getByRole('heading',{name:'Накопленный модельный эффект'}).isVisible());
    await menu.p.getByRole('button',{name:'Прогноз',exact:true}).click();
    assert.match(await menu.p.locator('.ap-padded').innerText(),/Выручка и экономия показаны отдельно/);
    await menu.ctx.close();passed.push('Mobile menu resize reset; cumulative and separate forecast semantics');
    assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(out,'checks.json'),JSON.stringify({passed,errors,backend:'Actual FastAPI + disposable PostgreSQL with synthetic accounts; not real advertising accounts'},null,2));
    console.log('PASS',passed.length,'pilot/browser groups; no page/console errors.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
