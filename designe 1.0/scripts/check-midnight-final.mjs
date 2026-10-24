import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const root = path.resolve(import.meta.dirname, '..');
const base = 'http://127.0.0.1:3130';
const out = path.resolve(root, process.env.INROU_QA_OUT || '../docs/midnight-final-2026-10-24');
const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const require = createRequire(path.join(runtime, 'package.json'));
const {chromium} = require(runtime);
const fixture = JSON.parse(await fs.readFile(path.join(root, 'artifacts/.runtime/fixture.json'), 'utf8'));
const index = JSON.parse(await fs.readFile(path.resolve(root, '../design-inrou/docs/SCREEN_INDEX.json'), 'utf8'));
const routes = Object.values(index).flat();
assert.equal(routes.length, 54);
await fs.mkdir(path.join(out, 'screenshots'), {recursive: true});
const browser = await chromium.launch({channel: 'msedge', headless: true});
const report = {started: new Date().toISOString(), source: 'Local FastAPI + disposable PostgreSQL, synthetic QA records', build: (await fs.readFile(path.join(root, '.next/BUILD_ID'), 'utf8')).trim(), browser: browser.version(), routes: [], checks: [], failures: []};
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const sizes = [[1440,900,'light'],[768,1024,'light'],[390,844,'light'],[320,568,'light'],[1440,900,'dark']];
const major = new Set(['/', '/features', '/how-it-works', '/faq', '/login', '/app/analysis', '/app/recommendations', '/app/ai', '/app/agency', '/app/settings', '/app/reports', '/app/team', '/app/pricing']);
try {
  const auth = await browser.newContext({locale:'ru-RU', timezoneId:'Europe/Moscow', reducedMotion:'reduce'});
  const guest = await browser.newContext({locale:'ru-RU', timezoneId:'Europe/Moscow', reducedMotion:'reduce'});
  for (const ctx of [auth, guest]) {
    await ctx.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await ctx.addCookies([{name:'inrou-consent', value:'v1:necessary', url:base}]);
    await ctx.addInitScript(() => localStorage.setItem('inrou-theme', 'system'));
  }
  await auth.addCookies([{name:'session', value:fixture.tokens.owner, url:base, httpOnly:true, sameSite:'Lax'}]);
  const page = await auth.newPage(), publicPage = await guest.newPage();
  for (const [i, [title, route]] of routes.entries()) {
    const privateRoute = /^\/(app|onboarding)\//.test(route);
    const current = privateRoute ? page : publicPage;
    const target = route + (privateRoute ? '?workspace=' + fixture.workspaces.a1 : '');
    const item = {title, route, screenshots:[], sizes:[], errors:[]};
    const onError = error => item.errors.push(error.message);
    current.on('pageerror', onError);
    for (const [width,height,theme] of sizes) {
      await current.setViewportSize({width,height});
      await current.emulateMedia({colorScheme:theme});
      const response = await current.goto(base + target, {waitUntil:'networkidle'});
      await current.evaluate(() => document.fonts.ready);
      const layout = await current.evaluate(() => ({overflow:document.documentElement.scrollWidth > innerWidth + 1, width:document.documentElement.scrollWidth, h1:document.querySelector('h1')?.textContent, theme:document.documentElement.dataset.theme}));
      item.sizes.push({width,height,theme,status:response.status(),...layout});
      if (response.status() !== 200 || layout.overflow || !layout.h1 || layout.theme !== theme) report.failures.push({route,width,theme,status:response.status(),...layout});
      if (width === 1440 || major.has(route)) {
        const filename = `screenshots/${String(i+1).padStart(2,'0')}-${width}-${theme}.png`;
        await current.screenshot({path:path.join(out, filename), animations:'disabled'});
        item.screenshots.push(filename);
      }
    }
    current.off('pageerror', onError);
    if (item.errors.length) report.failures.push({route,errors:item.errors});
    report.routes.push(item);
    console.log(`${i+1}/54 ${route}`);
  }
  const check = async (name, fn) => {try {await fn(); report.checks.push({name,pass:true});} catch(error) {report.failures.push({name,error:error.message});}};
  await check('12 root links and compact geometry', async () => {
    await page.setViewportSize({width:1440,height:900});
    await page.goto(base+'/workspace/analysis?workspace='+fixture.workspaces.a1);
    assert.equal(await page.locator('.ix-nav a').count(),12);
    assert.equal(Math.round((await page.locator('.ix-sidebar').boundingBox()).width),238);
    assert.equal(await page.locator('h1').evaluate(e=>getComputedStyle(e).fontSize),'32px');
    assert.match(await page.locator('h1').evaluate(e=>getComputedStyle(e).fontFamily),/Inter/);
    assert.equal(Math.round((await page.locator('.ix-nav a').first().boundingBox()).height),40);
  });
  await check('tablet menu traps focus and Escape restores it', async () => {
    await page.setViewportSize({width:768,height:1024});
    const opener = page.locator('.ix-top button[aria-label="Открыть меню"]');
    await opener.click();
    assert(await page.locator('main').evaluate(e=>e.inert));
    for(let i=0;i<20;i++) await page.keyboard.press('Tab');
    assert(await page.locator('#ix-sidebar').evaluate(e=>e.contains(document.activeElement)));
    await page.keyboard.press('Escape');
    assert(await opener.evaluate(e=>e===document.activeElement));
  });
  await check('FAQ search and keyboard accordion', async () => {
    await publicPage.goto(base+'/faq');
    await publicPage.setViewportSize({width:1440,height:900});
    const search=await publicPage.locator('.ix-faq-search').boundingBox();
    const layout=await publicPage.locator('.ix-faq-layout').boundingBox();
    assert(Math.abs(search.width-layout.width)<2);
    await publicPage.getByRole('searchbox').fill('площадки');
    assert.equal(await publicPage.locator('details').count(),1);
    await publicPage.locator('summary').focus();await publicPage.keyboard.press('Enter');
    assert.equal(await publicPage.locator('details[open]').count(),1);
    await publicPage.getByRole('searchbox').fill('несуществующий вопрос 147');
    assert.equal(await publicPage.locator('details').count(),0);
  });
  await check('primary email login and separate legacy entry',async()=>{
    await publicPage.goto(base+'/login',{waitUntil:'networkidle'});
    assert.equal(await publicPage.locator('.ref-auth-alternative').count(),0);
    await publicPage.goto(base+'/login?legacy=1',{waitUntil:'networkidle'});
    assert.equal(await publicPage.locator('.ref-auth-alternative').count(),1);
  });
  await check('compact reports keep real TXT download and data links',async()=>{
    await page.setViewportSize({width:1440,height:900});
    await page.goto(base+'/workspace/reports?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    assert.equal(await page.locator('.ix-report-row').count(),5);
    assert((await page.locator('.ix-report-list').boundingBox()).height<440);
    assert.equal(await page.locator('#weekly-report[open]').count(),0);
    await page.getByRole('link',{name:'Недельный отчёт',exact:true}).click();
    const download = page.getByRole('button',{name:'Скачать недельный отчёт',exact:true});
    await download.waitFor();
    assert.equal(await page.locator('#weekly-report[open]').count(),1);
    const received=page.waitForEvent('download');await download.click();
    const file=await received;assert.match(file.suggestedFilename(),/^inrou-week-.*\.txt$/);
    const body=await fs.readFile(await file.path(),'utf8');
    assert.match(body,/ОГРАНИЧЕНИЯ/);assert.match(body,new RegExp(fixture.workspaces.a1));
  });
  await check('analyst panel precedes expandable methodology',async()=>{
    await page.goto(base+'/workspace/ai?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    const method=page.locator('.ix-analyst-method');
    assert.equal(await method.getAttribute('open'),null);
    const actions=page.getByRole('region',{name:'Доказательный анализ'});
    await actions.waitFor();
    assert((await actions.boundingBox()).y<(await method.boundingBox()).y);
    await method.locator('summary').focus();await page.keyboard.press('Enter');
    assert.notEqual(await method.getAttribute('open'),null);
    assert(await method.getByText('Факты за период',{exact:true}).isVisible());
  });
  await check('real campaign chart exposes dates without demo series',async()=>{
    await page.goto(base+'/workspace/analysis?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    const dates=page.locator('.ix-chart-dates').first();await dates.waitFor();
    assert.equal(await dates.locator('span').count(),7);
    assert.match(await dates.innerText(),/\d{4}-\d{2}-\d{2}/);
    await page.setViewportSize({width:320,height:568});
    assert.equal(await dates.locator('span:visible').count(),3);
  });
  await check('team keeps real identities and explicit role scope',async()=>{
    await page.goto(base+'/workspace/team?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    assert(await page.locator('.ix-member-avatar').count()>0);
    assert(await page.locator('.ix-member-roles').first().innerText().then(text=>text.includes('Организация:')));
    assert.equal(await page.locator('.ix-member-identity a').first().getAttribute('href').then(href=>href.includes('workspace='+fixture.workspaces.a1)),true);
  });
  await check('subscription uses stored price, workspace scope and manager permissions',async()=>{
    await page.setViewportSize({width:1440,height:900});
    const response=await auth.request.get(base+`/api/workspaces/${fixture.workspaces.a1}/subscription`);
    assert.equal(response.status(),200);
    assert.match(response.headers()['cache-control'],/no-store/);
    const current=await response.json();
    assert.equal(current.subscription.plan,'start');assert.equal(current.subscription.price_amount,'1990.00');
    await page.goto(base+'/app/pricing?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    const plan=page.getByRole('region',{name:'Текущая подписка'});
    assert(await plan.getByRole('heading',{name:'Старт',exact:true}).isVisible());
    assert.match(await plan.innerText(),/1\s990/);
    assert(await page.getByRole('region',{name:'Доступ к анализу'}).getByRole('heading',{name:'Анализ доступен',exact:true}).isVisible());
    await page.goto(base+'/workspace/plans?workspace='+fixture.workspaces.a2,{waitUntil:'networkidle'});
    await page.getByRole('heading',{name:'Подписка не оформлена',exact:true}).waitFor();
    await page.screenshot({path:path.join(out,'screenshots/subscription-empty-1440-dark.png')});
    const ctx=await browser.newContext({locale:'ru-RU',viewport:{width:390,height:844}});
    try{
      await ctx.addCookies([{name:'session',value:fixture.tokens.viewer,url:base,httpOnly:true}]);
      assert.equal((await ctx.request.get(base+`/api/workspaces/${fixture.workspaces.a1}/subscription`)).status(),403);
      assert.equal((await ctx.request.get(base+`/api/workspaces/${fixture.workspaces.b1}/subscription`)).status(),404);
      const viewer=await ctx.newPage();
      await viewer.goto(base+'/workspace/plans?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
      await viewer.getByRole('heading',{name:'Сведения о подписке доступны владельцу и администратору',exact:true}).waitFor();
      assert.equal(await viewer.locator('.ix-subscription').count(),0);
      await viewer.screenshot({path:path.join(out,'screenshots/subscription-viewer-390-light.png')});
    }finally{await ctx.close();}
  });
  await check('real passport: five tabs, keyboard and Escape', async () => {
    await page.setViewportSize({width:1440,height:900});
    await page.goto(base+`/workspace/recommendations?workspace=${fixture.workspaces.a1}&rec=${fixture.recommendation}`,{waitUntil:'networkidle'});
    const dialog = page.getByRole('dialog');await dialog.waitFor();
    assert.deepEqual(await dialog.getByRole('tab').allTextContents(),['Обзор','Данные','Расчёты','Риски','История']);
    await page.screenshot({path:path.join(out,'screenshots/passport-overview-1440-dark.png')});
    await dialog.getByRole('tab',{name:'Обзор',exact:true}).focus();await page.keyboard.press('End');
    assert.equal(await dialog.getByRole('tab',{name:'История',exact:true}).getAttribute('aria-selected'),'true');
    await page.screenshot({path:path.join(out,'screenshots/passport-1440-dark.png')});
    await page.setViewportSize({width:390,height:844});
    await dialog.getByRole('tab',{name:'Обзор',exact:true}).click();
    await page.screenshot({path:path.join(out,'screenshots/passport-overview-390-dark.png')});
    await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
  });
  await check('private /app requires a session and disables caching', async () => {
    const response = await guest.request.get(base+'/app/analysis',{maxRedirects:0});
    assert.equal(response.status(),307);assert.match(response.headers()['cache-control'],/no-store/);
    assert.equal(response.headers()['referrer-policy'],'no-referrer');
  });
  await check('foreign workspace denied by live server', async () => {
    const response = await auth.request.get(base+`/api/workspaces/${fixture.workspaces.b1}/today`);
    assert([403,404].includes(response.status()));
  });
  await check('real period filter updates KPI, chart and campaign drilldown', async () => {
    await page.setViewportSize({width:1440,height:900});
    await page.goto(base+'/workspace/analysis?workspace='+fixture.workspaces.a1,{waitUntil:'networkidle'});
    await page.getByRole('combobox',{name:'Период',exact:true}).selectOption('7');
    await page.getByRole('button',{name:'Показать',exact:true}).click();
    await page.waitForURL(/days=7/);
    assert.match(await page.locator('.ix-kpis [data-value]').first().innerText(),/700/);
    assert.equal(await page.locator('.ix-chart').count(),1);
    await page.getByRole('combobox',{name:'Показатель',exact:true}).selectOption('cpa');
    await page.getByRole('link',{name:'Кампания 12345',exact:true}).click();
    await page.waitForURL(/\/campaigns\/12345\?/);
    await page.getByRole('heading',{name:'Кампания 12345',exact:true}).waitFor();
    assert.equal(await page.locator('h1').innerText(),'Кампания 12345');
    assert.equal(new URL(page.url()).searchParams.get('ad_account'),fixture.account);
    await page.screenshot({path:path.join(out,'screenshots/campaign-1440-dark.png')});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(out,'screenshots/campaign-390-dark.png')});
  });
  await check('empty workspace never shows synthetic metrics', async () => {
    const ctx = await browser.newContext();
    try{
      await ctx.addCookies([{name:'session',value:fixture.tokens.empty,url:base,httpOnly:true}]);
      const empty = await ctx.newPage();
      await empty.goto(base+'/workspace/analysis?workspace='+fixture.empty_workspace,{waitUntil:'networkidle'});
      assert.equal(await empty.locator('.ix-kpis [data-value="actual"]').count(),0);
      assert.equal(await empty.locator('.ix-kpis [data-value="unavailable"]').count(),4);
      assert.equal(await empty.locator('.ix-chart').count(),0);
    }finally{await ctx.close();}
  });
  await check('viewer can read scoped campaign statistics', async () => {
    const ctx = await browser.newContext();
    try{
      await ctx.addCookies([{name:'session',value:fixture.tokens.viewer,url:base,httpOnly:true}]);
      const response = await ctx.request.get(base+`/api/workspaces/${fixture.workspaces.a1}/campaign-stats?days=7`);
      assert.equal(response.status(),200);assert.equal((await response.json()).summary.cost.amount,'700.00');
      assert.equal((await ctx.request.get(base+`/api/workspaces/${fixture.workspaces.b1}/campaign-stats?days=7`)).status(),404);
    }finally{await ctx.close();}
  });
  await check('additional responsive checkpoints on landing and analysis',async()=>{
    for(const route of ['/',`/workspace/analysis?workspace=${fixture.workspaces.a1}`])for(const [width,height] of [[360,800],[1280,800],[1536,960],[1920,1080]]){
      await page.setViewportSize({width,height});await page.goto(base+route,{waitUntil:'networkidle'});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${route} overflow at ${width}`);
    }
  });
  report.screenshots = [];
  for (const filename of await fs.readdir(path.join(out,'screenshots'))) {const bytes=await fs.readFile(path.join(out,'screenshots',filename));report.screenshots.push({filename,sha256:createHash('sha256').update(bytes).digest('hex')});}
} finally {
  report.finished = new Date().toISOString();
  await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify(report,null,2));
  await browser.close();
}
const panelMap=JSON.parse(await fs.readFile(path.resolve(root,'../design-inrou/reference/PANEL_MAP.json'),'utf8'));
const mapping=await fs.readFile(path.resolve(root,'../design-inrou/docs_final/02_PAGE_TO_PANEL_MAPPING.md'),'utf8');
const routePanels=Object.fromEntries(mapping.split('\n').flatMap(line=>{const route=line.match(/`(\/[^`]*)`/);return route?[[route[1],line.match(/\b[A-D]0[1-8]\b/g)??[]]]:[];}));
const rows = report.routes.map(item=>`<article id="${escape(item.route)}"><h2>${escape(item.title)} <code>${escape(item.route)}</code></h2><p>HTTP/overflow: ${item.sizes.every(s=>s.status===200&&!s.overflow)?'PASS':'NEEDS_WORK'} · local synthetic QA backend</p><div class="references">${(routePanels[item.route]??[]).map(id=>{const panel=panelMap.panels.find(p=>p.id===id);return panel?`<figure><img loading="lazy" src="../../design-inrou/${escape(panel.file)}"><figcaption>${id} · исходный фрагмент ${panel.native_px.join('×')} px</figcaption></figure>`:'';}).join('')}</div><div class="shots">${item.screenshots.map(s=>`<a href="${s}"><img loading="lazy" src="${s}" alt="${escape(item.route)} ${escape(s)}"></a>`).join('')}</div></article>`).join('');
await fs.writeFile(path.join(out,'gallery.html'),`<!doctype html><html lang="ru"><meta charset="utf-8"><title>INROU Midnight Sapphire · browser evidence</title><style>body{margin:24px;background:#f2eee8;color:#11253e;font:14px system-ui}h1{font:36px Georgia}.shots{display:flex;gap:12px;overflow:auto}.shots a{flex:0 0 480px}.shots img{width:100%;border:1px solid #d6cec1}article{padding:20px 0;border-bottom:1px solid #d6cec1}code{font-size:13px}</style><h1>INROU · фактические снимки браузера</h1><p>54 маршрута · пять viewport/theme checkpoints. Синтетическая тестовая БД; открытие страницы не означает готовности всех функций. Пробелы — в CURRENT_STATE.md.</p>${rows}</html>`);
console.log(`Routes ${report.routes.length}; checks ${report.checks.length}; failures ${report.failures.length}; screenshots ${report.screenshots.length}`);
assert.equal(report.failures.length,0,JSON.stringify(report.failures));
