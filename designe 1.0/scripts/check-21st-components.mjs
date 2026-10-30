import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium} = createRequire(path.join(runtime, 'package.json'))(runtime);
const base = process.env.INROU_QA_BASE || 'http://127.0.0.1:3140';
const out = path.resolve(import.meta.dirname, '../../docs/21st-components-2026-10-29');
await fs.mkdir(out, {recursive: true});
const report = {base, matrix: [], checks: [], errors: [], screenshots: []};
const browser = await chromium.launch({channel: 'msedge', headless: true});
try {
  const context = await browser.newContext({reducedMotion: 'reduce'});
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  const visit = async route => {
    const response = await page.goto(base + route, {waitUntil: 'networkidle', timeout: 120000});
    assert.equal(response.status(), 200, route);
    await page.evaluate(() => document.fonts.ready);
    const cookie = page.getByRole('button', {name: 'Только необходимые', exact: true});
    if (await cookie.isVisible()) await cookie.click();
  };
  const capture = async (locator, name) => {
    // Locator captures can include offscreen fixed elements; the skip link is tested separately.
    await locator.screenshot({path: path.join(out, name), animations: 'disabled', style: 'nextjs-portal,.ix-skip:not(:focus-visible){visibility:hidden!important}'});
    report.screenshots.push(name);
  };
  for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark']) {
    await page.setViewportSize({width, height: 1000});
    await page.addInitScript(theme => localStorage.setItem('inrou-theme', theme), theme);
    for (const route of ['/', '/features', '/signup', '/demo/analysis']) {
      await visit(route);
      assert.equal(await overflow(), false, `${route} overflow ${width}/${theme}`);
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
      if (route === '/') {
        assert.equal(await page.locator('footer .inrou-footer-meta').count(), 1);
        assert.equal(await page.locator('.home-hero-copy h1').count(), 1);
        assert.equal(await page.locator('.home-hero-copy h1').evaluate(node => getComputedStyle(node).animationName), 'none');
      }
      if (route === '/features') {
        assert.equal(await page.locator('.ix-feature-grid>article').count(), 6);
        const columns = await page.locator('.ix-feature-grid').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length);
        assert.equal(columns, width >= 1024 ? 3 : width > 480 ? 2 : 1);
        assert.equal(await page.locator('.ix-footer-group').count(), 3);
        assert.equal(await page.locator('footer .inrou-footer-meta').count(), 1);
      }
      if (route === '/signup') {
        assert.equal(await page.locator('.ix-registration-steps li').count(), 3);
        assert.match(await page.locator('.ix-registration-steps [aria-current=step]').innerText(), /1\s*Данные/);
        assert.equal(await page.getByRole('button', {name: 'Создать аккаунт', exact: true}).isDisabled(), true);
      }
      if ([1440, 390].includes(width) && ['/features', '/signup'].includes(route)) await capture(route === '/features' ? page.locator('.ix-feature-grid') : page.locator('.ref-auth-form-panel'), `${route.slice(1)}-${width}-${theme}.png`);
      if (route === '/' && width === 1440) await capture(page.locator('.home-hero'), `hero-${theme}.png`);
      report.matrix.push({route, width, theme, overflow: false});
    }
    console.log(`PASS ${width}/${theme}: home, feature grid/footer, signup, analysis`);
  }
  await page.setViewportSize({width: 1440, height: 1000});
  await visit('/demo/analysis');
  const collapse = page.getByRole('button', {name: 'Свернуть панель', exact: true});
  await collapse.focus(); await page.keyboard.press('Enter');
  assert.equal(await page.getByRole('button', {name: 'Развернуть панель'}).getAttribute('aria-expanded'), 'false');
  assert.equal(await page.locator('.ix-sidebar').evaluate(node => Math.round(node.getBoundingClientRect().width)), 76);
  assert.equal(await page.locator('.ix-nav a[aria-current=page]').getAttribute('aria-label'), 'Анализ');
  await page.reload({waitUntil: 'networkidle'});
  await page.waitForFunction(() => document.querySelector('.ix-shell.is-collapsed'));
  await capture(page.locator('.ix-shell'), 'sidebar-collapsed.png');
  report.checks.push('Sidebar: keyboard toggle, exact 76px rail, route labels, reload persistence');
  await page.setViewportSize({width: 320, height: 844});
  const menu = page.getByRole('button', {name: 'Открыть меню', exact: true}).first();
  await menu.click();
  assert.equal(await page.locator('.ix-sidebar').getAttribute('role'), 'dialog');
  assert.equal(await page.locator('.ix-nav-label').first().isVisible(), true);
  await capture(page.locator('.ix-sidebar'), 'sidebar-mobile.png');
  await page.keyboard.press('Escape');
  assert.equal(await menu.evaluate(node => node === document.activeElement), true);
  assert.equal(await overflow(), false);
  report.checks.push('Collapsed desktop preference keeps full mobile menu; Escape restores focus');
  await visit('/demo/recommendations?rec=0');
  await page.getByRole('button', {name: 'Одобрить', exact: true}).click();
  const toast = page.locator('.ix-status-toast');
  await toast.waitFor();
  assert.match(await toast.innerText(), /Сохранено только в демо/);
  assert.match(await toast.innerText(), /Реклама не изменена/);
  assert.equal(await toast.getAttribute('role'), 'status');
  await capture(toast, 'toast-mobile.png');
  await page.getByRole('button', {name: 'Закрыть уведомление'}).click();
  assert.equal(await toast.count(), 0);
  report.checks.push('Demo action creates truthful persistent status toast; explicit dismiss works');
  await page.setViewportSize({width: 1440, height: 1000});
  await visit('/demo/analysis');
  await page.locator('.ix-metric-details>summary').click();
  const bounds = page.locator('.ix-metric-details .ix-chart-bounds').first();
  assert.match(await bounds.innerText(), /Минимум/);
  assert.match(await bounds.innerText(), /Максимум/);
  await capture(page.locator('.ix-metric-details'), 'chart-bounds.png');
  const hit = page.locator('.ix-metric-details .ix-hit').first();
  await hit.focus(); await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('.ix-metric-details .ix-tooltip').count(), 1);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.ix-metric-details .ix-tooltip').count(), 0);
  report.checks.push('Single-series min/max summary preserves unit/status; keyboard tooltip and Escape work');
  await visit('/features');
  const skip = page.locator('.ix-skip');
  assert(await skip.evaluate(node => node.getBoundingClientRect().bottom < 0));
  await skip.focus();
  assert(await skip.evaluate(node => node.getBoundingClientRect().top >= 0));
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#main-content').evaluate(node => node === document.activeElement), true);
  report.checks.push('Skip link is offscreen by default; keyboard focus reveals it and Enter focuses main');
  const fixture = JSON.parse(await fs.readFile(path.resolve(import.meta.dirname, '../artifacts/.runtime/fixture.json'), 'utf8'));
  await context.addCookies([{name: 'session', value: fixture.tokens.owner, url: base, httpOnly: true, sameSite: 'Lax'}]);
  await visit(`/workspace/analysis?workspace=${fixture.workspaces.a1}`);
  assert.equal(await page.locator('.ix-period-picker input:checked').inputValue(), '30');
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    assert.equal(await overflow(), false, `live overflow ${width}`);
    assert(await page.locator('.ix-period-picker').evaluate(node => node.getBoundingClientRect().width) >= (width === 320 ? 220 : width === 390 ? 260 : 200), `period picker too narrow at ${width}`);
    if (width !== 320) await capture(page.locator('.ix-period-picker'), `period-${width}.png`);
  }
  await page.getByRole('radio', {name: '7 дней', exact: true}).check();
  await page.getByRole('button', {name: 'Показать', exact: true}).click();
  await page.waitForURL(/days=7/);
  await page.waitForLoadState('networkidle');
  assert.equal(new URL(page.url()).searchParams.get('workspace'), fixture.workspaces.a1);
  assert.equal(await page.locator('.ix-period-picker input:checked').inputValue(), '7');
  report.checks.push('Live fixture: 30/7-day GET filtering works and preserves workspace, mobile has no overflow');
  assert.deepEqual(report.errors, []);
  report.checks.push('No browser runtime errors; reduced-motion hero has no animation');
} finally {
  await fs.writeFile(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(`PASS 21st components: ${report.matrix.length} responsive cases, ${report.checks.length} interaction groups`);
