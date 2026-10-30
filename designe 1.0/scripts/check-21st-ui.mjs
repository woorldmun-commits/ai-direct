import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium} = createRequire(path.join(runtime, 'package.json'))(runtime);
const base = process.env.INROU_QA_BASE || 'http://127.0.0.1:3140';
const out = path.resolve(import.meta.dirname, '../../docs/21st-ui-2026-10-28');
await fs.mkdir(out, {recursive: true});
const report = {base, matrix: [], checks: [], errors: [], screenshots: []};
const browser = await chromium.launch({channel: 'msedge', headless: true});
try {
  const context = await browser.newContext({reducedMotion: 'reduce'});
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  const screenshot = async (locator, name) => {await locator.screenshot({path: path.join(out, name), animations: 'disabled', style: 'nextjs-portal{visibility:hidden!important}'}); report.screenshots.push(name);};
  const overflow = async () => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark']) {
    await page.setViewportSize({width, height: width < 768 ? 844 : 1000});
    await page.addInitScript(theme => {localStorage.setItem('inrou-theme', theme);}, theme);
    const response = await page.goto(base + '/', {waitUntil: 'networkidle', timeout: 120000});
    assert.equal(response.status(), 200);
    await page.evaluate(() => document.fonts.ready);
    const cookie = page.getByRole('button', {name: 'Только необходимые', exact: true});
    if (await cookie.isVisible()) await cookie.click();
    assert.equal(await page.locator('.home-feature-card').count(), 5);
    assert.equal(await page.locator('.home-stats-bento>article').count(), 4);
    assert.equal(await overflow(), false, `home overflow ${width}/${theme}`);
    assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
    await page.getByRole('button', {name: 'Бюджет и заявки', exact: true}).click();
    const demo = page.locator('.home-metrics-preview');
    assert.equal(await demo.locator('.metric-budget meter').count(), 2);
    assert.equal(await demo.locator('.metric-segment').count(), 3);
    assert.deepEqual(await demo.locator('.metric-segment').evaluateAll(items => items.map(item => Number(item.style.flexGrow))), [60, 25, 15]);
    assert.equal(await overflow(), false, `expanded home overflow ${width}/${theme}`);
    assert.match(await demo.locator('.metric-budget').innerText(), /248\s?640/);
    await demo.getByRole('button', {name: 'Без плана', exact: true}).click();
    assert.equal(await demo.locator('.metric-budget meter').count(), 0);
    assert.match(await demo.locator('.metric-budget').innerText(), /Не задан/);
    await demo.getByRole('button', {name: 'Нет данных', exact: true}).click();
    assert.equal(await demo.locator('.metric-segment').count(), 0);
    assert.equal(await demo.locator('.metric-column').count(), 0);
    assert.match(await demo.locator('.metric-budget').innerText(), /Недостаточно данных/);
    assert.equal(await overflow(), false, `empty home overflow ${width}/${theme}`);
    await demo.getByRole('button', {name: 'Есть данные', exact: true}).click();
    await demo.locator('.metric-values summary').click();
    assert.equal(await demo.locator('tbody tr').count(), 14);
    if ([1440, 390].includes(width)) {
      await screenshot(demo, `metrics-${width}-${theme}.png`);
      await screenshot(page.locator('.home-capabilities'), `bento-${width}-${theme}.png`);
    }
    report.matrix.push({route: '/', width, theme, ready: true, noPlan: true, empty: true, overflow: false});
    console.log(`PASS home ${width} ${theme}: cards, all states, exact values, no overflow`);
  }
  await page.setViewportSize({width: 1440, height: 1000});
  await page.goto(base + '/demo/analysis', {waitUntil: 'networkidle', timeout: 120000});
  assert.equal(await page.locator('.ix-kpi').count(), 4);
  const kpis = page.locator('.ix-kpi');
  assert.match(await kpis.nth(0).locator('.metric-trend--neutral').innerText(), /12%/);
  assert.match(await kpis.nth(2).locator('.metric-trend--good').innerText(), /34%/);
  await page.locator('.ix-chart-options summary').click();
  await page.getByRole('button', {name: 'Сравнение с прошлым периодом', exact: true}).click();
  await page.waitForURL(/compare=0/);
  await page.waitForFunction(() => !document.querySelector('.metric-trend'));
  assert.equal(await page.locator('.metric-trend').count(), 0);
  assert.equal(await page.locator('.metric-column-pair>span').count(), 14);
  report.checks.push('KPI semantic tones; disabling comparison removes prior-period bars and deltas');
  await page.getByRole('button', {name: 'Недостаточно данных', exact: true}).click();
  await page.waitForURL(/insufficient=1/);
  await page.waitForFunction(() => !document.querySelector('.metric-segment'));
  assert.equal(await page.locator('.metric-segment').count(), 0);
  report.checks.push('Insufficient demo data never renders a lead distribution');
  await page.goto(base + '/demo/analysis', {waitUntil: 'networkidle'});
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    assert.equal(await overflow(), false, `demo analysis overflow ${width}`);
    report.matrix.push({route: '/demo/analysis', width, overflow: false});
    if (width === 1440) await screenshot(page.locator('.ix-kpis'), 'kpis-desktop.png');
  }
  await page.goto(base + '/', {waitUntil: 'networkidle'});
  await page.locator('.home-feature-budget>a').click();
  assert.equal(await page.getByRole('button', {name: 'Бюджет и заявки', exact: true}).getAttribute('aria-pressed'), 'true');
  await page.getByRole('button', {name: 'Источники', exact: true}).focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.home-preview-sources').count(), 1);
  report.checks.push('Feature CTA opens matching preview; tabs work from keyboard');
  assert.deepEqual(report.errors, []);
  report.checks.push('No browser runtime errors; reduced motion respected during captures');
} finally {
  await fs.writeFile(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(`PASS 21st UI: ${report.matrix.length} responsive cases and ${report.checks.length} interaction checks`);
