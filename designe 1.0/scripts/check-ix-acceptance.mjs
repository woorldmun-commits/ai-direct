import assert from 'node:assert/strict';
import {execFileSync, spawn} from 'node:child_process';
import {createHash, randomUUID} from 'node:crypto';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

// Local synthetic QA only. No configurable remote server or production credentials.
const root = path.resolve(import.meta.dirname, '..');
const base = 'http://127.0.0.1:3130';
const runtime = process.env.PLAYWRIGHT_MODULE || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const require = createRequire(path.join(runtime, 'package.json'));
const {chromium} = require(runtime);
const fixture = JSON.parse(await fs.readFile(path.join(root, 'artifacts/.runtime/fixture.json'), 'utf8'));
const out = path.join(root, process.env.INROU_QA_OUT || '../docs/pixel-fidelity-2026-10-23/direct/routes');
await fs.mkdir(out, {recursive: true});
const report = {started: new Date().toISOString(), synthetic: true, approval: 'PENDING',
  buildId: (await fs.readFile(path.join(root, '.next/BUILD_ID'), 'utf8')).trim(),
  widths: [320, 375, 390, 768, 1024, 1280, 1440, 1920, 2560], results: [], failures: [], interactions: [], performance: []};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
report.sourceHashes = {};
const inputs = execFileSync('git', ['ls-files', '-co', '--exclude-standard', '-z', '--', 'designe 1.0'], {cwd: path.dirname(root), encoding: 'utf8'}).split('\0').filter(Boolean);
for (const file of new Set(inputs)) {
  try { report.sourceHashes[file] = hash(await fs.readFile(path.join(root, '..', file))); }
  catch (e) { if (e.code !== 'ENOENT') throw e; }
}
// Refuse to connect a QA UI to anything except the disposable backend.
const health = await fetch('http://127.0.0.1:3121/api/v1/health');
assert(health.ok, 'Start scripts/pilot-fixture.py before this test');
const server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3130'], {
  cwd: root, windowsHide: true, stdio: 'ignore', env: {...process.env, NODE_ENV: 'production', NEXT_TELEMETRY_DISABLED: '1',
    INROU_DEMO: '1', INROU_API_URL: 'http://127.0.0.1:3121', INROU_APP_ORIGIN: base},
});
let browser;
const check = async (name, fn) => {
  try { await fn(); report.interactions.push({name, pass: true}); }
  catch (e) { report.failures.push({name, error: e.message}); }
};
try {
  let ready = false;
  for (let i = 0; i < 60; i++) {
    assert.equal(server.exitCode, null, 'Local QA server failed to start');
    try { ready = (await fetch(base + '/login')).ok; } catch {}
    if (ready) break;
    await new Promise(r => setTimeout(r, 300));
  }
  assert(ready, 'Local server did not start');
  execFileSync(process.execPath,['scripts/check-midnight-states.mjs'],{cwd:root,env:process.env,windowsHide:true,stdio:'inherit'});
  report.interactions.push({name:'check-midnight-states.mjs',pass:true});
  browser = await chromium.launch({channel: 'msedge', headless: true});
  report.browser = browser.version();
  const ctx = await browser.newContext({viewport: {width: 1440, height: 960}, locale: 'ru-RU', timezoneId: 'Europe/Moscow', reducedMotion: 'reduce'});
  await ctx.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  await ctx.addCookies([{name: 'session', value: fixture.tokens.owner, url: base, httpOnly: true, sameSite: 'Lax'}, {name: 'inrou-consent', value: 'v1:necessary', url: base}]);
  await ctx.addInitScript(() => { window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective)); });
  const page = await ctx.newPage();
  const publicCtx = await browser.newContext({viewport:{width:1440,height:900},locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
  await publicCtx.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  await publicCtx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
  await publicCtx.addInitScript(()=>{window.__csp=[];document.addEventListener('securitypolicyviolation',e=>window.__csp.push(e.violatedDirective));});
  const publicPage = await publicCtx.newPage();
  const ws = fixture.workspaces.a1;
  const me = await ctx.request.get(base + '/api/workspaces/' + ws + '/members');
  assert.equal(me.status(), 200);
  const member = (await me.json()).items[0].user.id;
  await check('AI history pagination and legacy cursor bookmark', async () => {
    const api = `${base}/api/workspaces/${ws}/intelligence`;
    const current = await (await ctx.request.get(api)).json();
    const profile = await ctx.request.post(api + '/profile', {headers: {Origin: base}, data: {
      expected_revision: current.profile?.revision ?? 0,
      fields: {name: 'Синтетический бизнес', industry_code: 'generic', business_model: 'b2b', products: ['Услуги'], geography: ['Москва'],
        currency: 'RUB', timezone: 'Europe/Moscow', goal: 'Проверка истории', conversion_definition: 'qualified_lead',
        average_order_value: null, gross_margin_pct: null, sales_cycle_days: null, budget_limit: null, seasonality: null, advantages: [], crm_available: false},
    }});
    assert.equal(profile.status(), 200);
    const imported = await ctx.request.post(api + '/import', {headers: {Origin: base}, data: {
      data_mode: 'synthetic', period_start: '2026-10-01', period_end: '2026-10-08', currency: 'RUB', timezone: 'Europe/Moscow',
      attribution_model: 'last', attribution_window: '30d', conversion_definition: 'qualified_lead', cost_definition: 'ad_cost_excluding_vat',
      account_ids: [], values: {cost: '10000', clicks: '500', conversions: '50'},
    }});
    assert.equal(imported.status(), 200);
    const importId = (await imported.json()).id;
    for (let i = 0; i < 6; i++) {
      const run = await ctx.request.post(api + '/analyze', {headers: {Origin: base}, data: {question: 'metrics', import_id: importId, idempotency_key: randomUUID()}});
      assert.equal(run.status(), 200, `synthetic analysis ${i}: ${await run.text()}`);
    }
    const first = await (await ctx.request.get(api)).json();
    assert.equal(first.runs.length, 5); assert(first.next_cursor);
    await page.goto(`${base}/workspace/ai?workspace=${ws}`, {waitUntil: 'networkidle'});
    await page.getByRole('link', {name: 'Предыдущие анализы'}).click();
    await page.waitForURL(/\/workspace\/ai\?.*cursor=/);
    await page.getByRole('heading', {name: /^Рассчитать показатели ·/}).first().waitFor();
    assert.equal(await page.getByRole('heading', {name: /^Рассчитать показатели ·/}).count(), 1);
    const second = await (await ctx.request.get(api + '?cursor=' + first.next_cursor)).json();
    assert.equal(second.runs.length, 1);
    assert(!first.runs.some(r => r.id === second.runs[0].id));
    await page.goto(`${base}/workspace?workspace=${ws}&view=analyst&analysis_cursor=${first.next_cursor}`, {waitUntil: 'networkidle'});
    assert.equal(new URL(page.url()).searchParams.get('cursor'), first.next_cursor);
    await page.getByRole('heading', {name: /^Рассчитать показатели ·/}).first().waitFor();
    assert.equal(await page.getByRole('heading', {name: /^Рассчитать показатели ·/}).count(), 1);
    await page.goto(`${base}/workspace/ai?workspace=${ws}&cursor=not-a-uuid`, {waitUntil: 'networkidle'});
    await page.getByRole('heading', {name: 'Данные требуют проверки'}).waitFor();
  });
  assert.equal(report.failures.length, 0, JSON.stringify(report.failures));
  const nav = ['overview', 'analysis', 'recommendations', 'campaigns', 'connections', 'impact', 'reports', 'alerts', 'ai', 'history', 'team', 'plans', 'settings', 'business-profile', 'data-health', 'onboarding-review'];
  const publics = ['/', ...['features', 'how-it-works', 'agencies', 'business', 'pricing', 'faq', 'contact', 'about', 'security', 'integrations', 'legal', 'login', 'signup', 'forgot-password', 'verify-email', 'reset-password'].map(s => '/' + s)];
  const legalSlugs = [...(await fs.readFile(path.join(root, 'lib/site.ts'), 'utf8')).matchAll(/slug: ["']([^"']+)["']/g)].map(m => m[1]);
  const details = ['campaigns/unavailable', 'connections/yandex_direct', 'connections/yandex_metrika', 'reports/weekly', 'alerts/freshness', `team/${member}`, 'history/' + fixture.recommendation, 'recommendations/' + fixture.recommendation];
  const routes = [...publics, ...legalSlugs.map(s => '/legal/' + s), ...nav.map(s => '/workspace/' + s + '?workspace=' + ws),
    ...details.map(s => '/workspace/' + s + '?workspace=' + ws), ...['organization', 'business-profile', 'connect', 'first-audit'].map(s => '/onboarding/' + s + '?workspace=' + ws), '/demo/states', ...nav.filter(s=>!['data-health','onboarding-review'].includes(s)).map(s=>'/demo/'+s), ...['landing','overview','recommendation'].map(s=>'/demo/midnight/'+s)];
  report.expectedRoutes=routes.length;
  const axeSource = process.env.AXE_PATH ? await fs.readFile(process.env.AXE_PATH, 'utf8') : null;
  report.axe = axeSource ? 'WCAG 2 A/AA + 2.1 A/AA' : 'UNAVAILABLE: set AXE_PATH to an installed axe.min.js';
  let routeErrors = [];
  let consoleErrors=[];
  for(const p of [page,publicPage]){p.on('pageerror',e=>routeErrors.push(e.message));p.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});}
  for (const theme of ['light', 'dark']) {
    await page.goto(base + '/login');
    await page.evaluate(theme => localStorage.setItem('inrou-theme', theme), theme);
    await publicPage.goto(base+'/login');await publicPage.evaluate(theme=>localStorage.setItem('inrou-theme',theme),theme);
    for (let i = 0; i < routes.length; i++) {
      const route = routes[i], id = String(i + 1).padStart(2, '0');
      routeErrors = [];consoleErrors=[];
      const routePage=/^\/(workspace|onboarding)(\/|$)/.test(route)?page:publicPage;
      const response = await routePage.goto(base + route, {waitUntil: 'networkidle'});
      await routePage.locator('h1').first().waitFor();
      await routePage.evaluate(() => document.fonts.ready);
      const result = {id, route: route.replace(member, ':member'), theme, authContext:routePage===page?'owner':'logged-out', status: response.status(), widths: [], screenshots: [], a11y: []};
      for (const width of report.widths) {
        await routePage.setViewportSize({width, height: ({375: 812, 390: 844, 1024: 768, 1440: 900})[width] ?? (width < 768 ? 844 : 960)});
        await routePage.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const size = await routePage.evaluate(() => ({width: innerWidth, content: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,theme:document.documentElement.dataset.theme,
          canvas:(document.querySelector('.ix-shell,.home-redesign,.ms-public-main,.ix-pub,.ix-auth-shell,.mc-error-page,.ms-app'))?.getBoundingClientRect().toJSON(),available:document.documentElement.clientWidth,
          motion: [...document.querySelectorAll('.ix-page,.ix-card,.ix-skeleton')].every(e => getComputedStyle(e).animationName === 'none' && getComputedStyle(e).transitionDuration === '0s')}));
        result.widths.push(size);
        if(size.theme!==theme)report.failures.push({route:result.route,theme,width,error:'theme mismatch'});
        if(size.canvas&&size.canvas.width>1408.5)report.failures.push({route:result.route,theme,width,error:'canvas exceeds1408',canvas:size.canvas});
        if (size.content > width) report.failures.push({route: result.route, theme, width, overflow: size.content});
        if (!size.motion) report.failures.push({route: result.route, theme, width, error: 'reduced motion'});
        if ([320, 390, 768, 1440, 2560].includes(width)) {
          const file = `${id}-${theme}-${width}.png`;
          const bytes = await routePage.screenshot({path: path.join(out, file), fullPage: true, animations: 'disabled'});
          result.screenshots.push({file, sha256: createHash('sha256').update(bytes).digest('hex')});
          if (axeSource && [390, 1440].includes(width)) {
            // Evaluation runs the installed audit in this local page; no external scripts or CSP changes.
            await routePage.evaluate(axeSource);
            const audit = await routePage.evaluate(async () => { const r = await window.axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}}); return {violations: r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.map(n => ({target: n.target, summary: n.failureSummary}))})), incomplete: r.incomplete.map(v => v.id)}; });
            result.a11y.push({width, ...audit});
            if (audit.violations.length) report.failures.push({route: result.route, theme, width, axe: audit.violations.map(v => v.id)});
          }
        }
      }
      result.pageErrors = [...routeErrors];result.consoleErrors=[...consoleErrors]; result.csp = await routePage.evaluate(() => window.__csp);
      if (response.status() !== 200 || routeErrors.length || result.csp.length || consoleErrors.length) report.failures.push({route: result.route, theme, authContext:routePage===page?'owner':'logged-out', status: response.status(), errors: routeErrors, csp: result.csp});
      report.results.push(result);
      console.log(`${theme} ${id}/${routes.length}: ${result.route} (${result.widths.length} widths)`);
    }
  }
  await check('canonical workspace selection preserves recommendation', async () => {
    await page.goto(`${base}/workspace/recommendations?rec=${fixture.recommendation}`, {waitUntil: 'networkidle'});
    assert.equal(new URL(page.url()).searchParams.get('rec'), fixture.recommendation);
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape'); await page.getByRole('dialog').waitFor({state: 'detached'});
  });
  await check('mobile menu focus trap, Escape, overlay, navigation', async () => {
    await page.setViewportSize({width: 390, height: 844});
    await page.goto(`${base}/workspace/overview?workspace=${ws}`, {waitUntil: 'networkidle'});
    const opener = page.locator('.ix-top').getByRole('button', {name: 'Открыть меню'});
    await opener.click();
    assert(await page.locator('main').evaluate(e => e.inert));
    assert(await page.locator('.ix-mobilebottom').evaluate(e => e.inert));
    for (let i = 0; i < 20; i++) await page.keyboard.press('Tab');
    assert(await page.locator('#ix-sidebar').evaluate(e => e.contains(document.activeElement)));
    await page.keyboard.press('Escape'); assert(await opener.evaluate(e => e === document.activeElement));
    await opener.click(); await page.locator('.ix-scrim').click({position: {x: 380, y: 200}});
    await page.waitForFunction(() => document.querySelector('#ix-sidebar')?.getAttribute('aria-modal') === null);
    assert.equal(await page.locator('#ix-sidebar').getAttribute('aria-modal'), null);
    await opener.click(); await page.locator('.ix-nav').getByRole('link', {name: 'Кампании', exact: true}).click();
    await page.waitForURL(/\/workspace\/campaigns/);
    await page.locator('#ix-sidebar').waitFor({state: 'attached'});
    await page.waitForFunction(() => document.querySelector('#ix-sidebar')?.getAttribute('aria-modal') === null);
    assert.equal(await page.locator('#ix-sidebar').getAttribute('aria-modal'), null);
  });
  await check('register alias and private headers', async () => {
    const r = await ctx.request.get(base + '/register', {maxRedirects: 0});
    assert.equal(r.status(), 307); assert.equal(new URL(r.headers().location, base).pathname, '/signup');
    assert.match(r.headers()['cache-control'], /no-store/);
  });
  await check('theme persists on reload', async () => {
    await page.setViewportSize({width: 1440, height: 960});
    await page.goto(base + '/demo/settings', {waitUntil: 'networkidle'});
    await page.getByRole('button', {name: /Переключить тему/}).first().click();
    const pref = await page.evaluate(() => localStorage.getItem('inrou-theme'));
    await page.reload({waitUntil: 'networkidle'}); assert.equal(await page.evaluate(() => localStorage.getItem('inrou-theme')), pref);
  });
  await check('chart filters share the URL, KPI, series and table selection', async () => {
    await page.goto(base + '/demo/analysis', {waitUntil: 'networkidle'});
    await page.getByRole('combobox', {name: 'Период', exact: true}).selectOption('Неделя');
    await page.waitForURL(/period=week/);
    await page.getByRole('heading', {name: 'Нет недельного среза'}).waitFor();
    assert.equal(await page.locator('.ix-chart').count(), 0);
    assert(!(await page.locator('.ix-kpis').innerText()).includes('248 640'));
    await page.reload({waitUntil: 'networkidle'});
    assert.equal(await page.getByRole('combobox', {name: 'Период', exact: true}).inputValue(), 'Неделя');
    await page.getByRole('combobox', {name: 'Период', exact: true}).selectOption('Месяц');
    await page.getByText('Параметры графика', {exact: true}).click();
    await page.getByRole('button', {name: 'Сравнение с прошлым периодом'}).click();
    await page.waitForURL(/compare=0/);
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === 'Сравнение с прошлым периодом' && b.getAttribute('aria-pressed') === 'false'));
    assert(!(await page.locator('.ix-kpis').innerText()).includes('к прошлому периоду'));
    await page.getByRole('button', {name: 'Недостаточно данных', exact: true}).click();
    await page.waitForURL(/insufficient=1/);
    await page.getByRole('heading', {name: 'Недостаточно данных для графика'}).waitFor();
    const cpa = page.locator('.ix-kpi').filter({has: page.getByText(/^CPA/)});
    assert.match(await cpa.innerText(), /Недостаточно данных/);
    await page.getByRole('combobox', {name: 'Площадка'}).selectOption('VK Реклама');
    await page.waitForURL(/platform=/);
    await page.getByRole('heading', {name: 'Нет данных источника'}).waitFor();
    assert.equal(await page.locator('.ix-chart').count(), 0);
    assert(!(await page.locator('.ix-kpis').innerText()).includes('248 640'));
    await page.goto(base + '/demo/analysis', {waitUntil: 'networkidle'});
    const point = page.locator('.ix-hit').nth(8);
    await point.focus();
    await page.getByRole('status').filter({hasText: 'cpa_jump_demo@1'}).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.ix-tooltip').count(), 0);
  });
  await check('team details respect server role and tenant restrictions', async () => {
    const restricted = await browser.newContext();
    try {
      await restricted.addCookies([{name: 'session', value: fixture.tokens.viewer, url: base, httpOnly: true, sameSite: 'Lax'}]);
      const p = await restricted.newPage();
      await p.goto(`${base}/workspace/team/${member}?workspace=${ws}`, {waitUntil: 'networkidle'});
      assert.match(await p.locator('main').innerText(), /недоступен|Нет доступа/);
      assert(!(await p.locator('main').innerText()).includes('api1@example.test'));
      const response = await restricted.request.get(`${base}/api/workspaces/${fixture.workspaces.b1}/members`);
      assert.equal(response.status(), 404);
    } finally { await restricted.close(); }
  });
  await check('Logged-out, expired and revoked sessions redirect without workspace data',async()=>{
    for(const token of [null,fixture.tokens.expired,fixture.tokens.revoked]){
      const isolated=await browser.newContext();
      try{
        if(token)await isolated.addCookies([{name:'session',value:token,url:base,httpOnly:true}]);
        const p=await isolated.newPage();await p.goto(`${base}/workspace/overview?workspace=${ws}`,{waitUntil:'networkidle'});
        assert.equal(new URL(p.url()).pathname,'/login');
        assert(!((await p.locator('body').innerText()).includes('api1@example.test')));
      }finally{await isolated.close();}
    }
  });
  await check('Unknown pages and legacy aliases retain routing semantics',async()=>{
    for(const route of ['/missing-midnight-page','/legal/missing'])assert.equal((await ctx.request.get(base+route)).status(),404);
    const missing=await ctx.request.get(base+'/workspace/missing?workspace='+ws);
    assert([200,404].includes(missing.status()));
    const missingHtml=await missing.text();assert(missingHtml.includes('Эта страница не найдена')&&/name="robots" content="noindex/.test(missingHtml));
    for(const [route,target]of [['/register','/signup'],['/demo','/demo/overview'],['/prisma-preview','/'],['/onboarding','/onboarding/organization']]){
      const response=await ctx.request.get(base+route,{maxRedirects:0});assert([307,308].includes(response.status()));assert.equal(new URL(response.headers().location,base).pathname,target);
    }
  });
  await check('Wide canvas remains identical at1440,1920 and2560',async()=>{
    for(const route of ['/','/features','/demo/overview','/demo/recommendations','/demo/settings']){
      await page.goto(base+route,{waitUntil:'networkidle'});const widths=[];
      for(const width of [1440,1920,2560]){
        await page.setViewportSize({width,height:1080});widths.push(await page.locator('.ix-shell,.home-redesign,.ms-public-main,.ix-pub').first().evaluate(e=>e.getBoundingClientRect().width));
      }
      assert(Math.max(...widths)-Math.min(...widths)<=16,'Only reserved scrollbar gutter may affect1440 threshold');
      assert(Math.abs(widths[1]-widths[2])<.1,'1920 and2560 share the same fixed maximum');
    }
  });
  for (const route of ['/', '/workspace/overview?workspace=' + ws]) {
    await page.setViewportSize({width: 1440, height: 960});
    const cdp = await ctx.newCDPSession(page); await cdp.send('Performance.enable');
    await page.goto(base + route, {waitUntil: 'networkidle'});
    const metrics = await cdp.send('Performance.getMetrics');
    const navigation = await page.evaluate(() => performance.getEntriesByType('navigation')[0].toJSON());
    report.performance.push({route, navigation, metrics: metrics.metrics});
    await cdp.detach();
  }
  await publicCtx.close();
  await ctx.close();
  const env = {...process.env, PLAYWRIGHT_MODULE: runtime};
  for (const script of ['check-pilot-browser.mjs', 'check-insights-browser.mjs', 'check-recommendation-cycle-browser.mjs']) {
    await check(script, () => new Promise((resolve, reject) => {
      const child = spawn(process.execPath, ['scripts/' + script], {cwd: root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
      let log = ''; child.stdout.on('data', d => { log += d; process.stdout.write(d); }); child.stderr.on('data', d => { log += d; });
      child.on('error', reject); child.on('exit', async code => { await fs.writeFile(path.join(out, script + '.log'), log); if (code === 0) resolve(); else reject(new Error(script + ' exit ' + code)); });
    }));
  }
} catch(e) {
  report.failures.push({name:'fatal acceptance runtime',error:e.stack||e.message});
} finally {
  await browser?.close(); server.kill();
  for (const [file, expected] of Object.entries(report.sourceHashes)) {
    const actual = await fs.readFile(path.join(root, '..', file)).then(hash, () => null);
    if (actual !== expected) report.failures.push({file, error: 'Source changed during QA'});
  }
  const referenceFile = path.join(root, '../INROU_MIDNIGHT_SAPPHIRE_FINAL_CODEX_V2/INROU_MIDNIGHT_SAPPHIRE_FINAL_V2/references/new/INROU_MIDNIGHT_SAPPHIRE_APPROVED.png');
  const referenceBytes = await fs.readFile(referenceFile);
  report.referenceReceipt = {file: 'INROU_MIDNIGHT_SAPPHIRE_FINAL_CODEX_V2/INROU_MIDNIGHT_SAPPHIRE_FINAL_V2/references/new/INROU_MIDNIGHT_SAPPHIRE_APPROVED.png', sha256: hash(referenceBytes), exactPixelComparison: false, reason: 'Supplied Midnight Sapphire montage and7crops are the visual authority; resized crop comparisons cannot establish full-resolution 1:1.'};
  report.expectedRouteThemes=(report.expectedRoutes||0)*2;
  report.completedWidthChecks=report.results.reduce((sum,r)=>sum+r.widths.length,0);
  if(!report.expectedRoutes||report.results.length!==report.expectedRouteThemes||report.completedWidthChecks!==report.expectedRouteThemes*report.widths.length)report.failures.push({name:'Incomplete route coverage',expected:report.expectedRouteThemes,actual:report.results.length,widthChecks:report.completedWidthChecks});
  report.complete=report.failures.length===0;
  report.finished = new Date().toISOString();
  await fs.writeFile(path.join(out, 'results.json'), JSON.stringify(report, null, 2) + '\n');
  await fs.writeFile(path.join(out, 'index.html'), `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>INROU — Midnight Sapphire · весь проект</title><style>body{font:16px/1.5 system-ui;margin:24px}img{max-width:100%;height:auto}section{margin:40px 0}</style><h1>INROU — Midnight Sapphire · маршруты проекта</h1><p>Проверка всего проекта на локальной синтетической БД. Реальные auth/API обработчики сохранены. Совпадение1:1 и утверждение владельцем не заявляются.</p>${report.results.map(r => `<section><h2>${r.id} · ${r.route} · ${r.theme}</h2>${r.screenshots.map(s => `<p><a href="${s.file}">${s.file}</a></p><img loading="lazy" src="${s.file}" alt="${r.id} ${r.theme}">`).join('')}</section>`).join('')}</html>`);
}
assert.equal(report.failures.length, 0, JSON.stringify(report.failures));
console.log(`PASS ${report.results.length} route/theme combinations; ${report.results.length * report.widths.length} width checks. Baselines PENDING.`);
