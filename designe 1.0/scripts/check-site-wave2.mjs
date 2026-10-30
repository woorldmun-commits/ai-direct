import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium} = createRequire(path.join(runtime, 'package.json'))(runtime);
const base = process.env.INROU_QA_BASE || 'http://127.0.0.1:3140';
const out = path.resolve(process.env.INROU_QA_OUT || path.resolve(import.meta.dirname, '../../docs/pricing-product-2026-10-29/wave2-regression'));
await fs.mkdir(out, {recursive: true});
const report = {base, matrix: [], checks: [], errors: [], screenshots: []};
const browser = await chromium.launch({channel: 'msedge', headless: true});
try {
  const context = await browser.newContext({reducedMotion: 'reduce'});
  const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  const screenshot = async (locator, name) => {await locator.screenshot({path: path.join(out, name), animations: 'disabled', style: 'nextjs-portal{visibility:hidden!important}'});report.screenshots.push(name);};
  for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark']) for (const route of ['/', '/pricing', '/features']) {
    await page.setViewportSize({width, height: width < 768 ? 844 : 1000});
    await page.addInitScript(theme => localStorage.setItem('inrou-theme', theme), theme);
    const response = await page.goto(base + route, {waitUntil: 'networkidle', timeout: 120000});
    assert.equal(response.status(), 200);
    await page.evaluate(() => document.fonts.ready);
    const cookie = page.getByRole('button', {name: 'Только необходимые', exact: true});
    if (await cookie.isVisible()) await cookie.click();
    assert.equal(await page.locator('h1').count(), 1);
    assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `overflow ${route} ${width} ${theme}`);
    if (route === '/' || route === '/pricing') {
      const pricing = page.locator('.inrou-pricing');
      assert.equal(await pricing.locator('.pricing-plan').count(), 3);
      await pricing.getByRole('button', {name: 'До 5 аккаунтов', exact: true}).click();
      assert.match(await pricing.locator('.pricing-plan.is-selected h2').innerText(), /Бизнес/);
      assert.equal(await pricing.locator('.pricing-cta').count(), 3);
      for (const cta of await pricing.locator('.pricing-cta').all()) assert.ok(['/signup','/#product-preview'].includes(await cta.getAttribute('href'))||(await cta.getAttribute('href')).startsWith('mailto:'));
      assert.match(await pricing.locator('.pricing-plan').first().innerText(), /2\s?990/);
      assert.equal(await pricing.locator('.pricing-negotiated').count(), 0);
      assert.match(await pricing.innerText(), /Оплата пока не подключена/);
      if ([1440, 390].includes(width) && route === '/pricing') await screenshot(pricing, `pricing-${width}-${theme}.png`);
    }
    if (route === '/' || route === '/features') {
      const orbit = page.locator('.orbit-features');
      await orbit.getByRole('button', {name: 'Яндекс Метрика', exact: true}).click();
      assert.match(await orbit.locator('.orbit-output strong').innerText(), /Конверсии/);
      assert.match(await orbit.locator('.orbit-description').innerText(), /Яндекс Метрика/);
      const range = orbit.getByRole('slider');
      await range.fill('0');
      assert.match(await range.getAttribute('aria-valuetext'), /1 марта/);
      await range.focus();await page.keyboard.press('ArrowRight');
      assert.equal(await range.inputValue(), '1');
      assert.match(await range.getAttribute('aria-valuetext'), /3 марта/);
      assert.match(await orbit.locator('.orbit-history').innerText(), /не прогноз/);
      assert.equal(await orbit.locator('polyline').getAttribute('points').then(p => p.split(' ').length), 14);
      if ([1440, 390].includes(width) && route === '/features') await screenshot(orbit, `orbit-${width}-${theme}.png`);
    }
    if (route === '/') {
      assert.equal(await page.locator('.home-hero-glass').count(), 1);
      const trigger = page.getByRole('button', {name: 'Как начать · 4 шага', exact: true});
      await trigger.click();
      const dialog = page.getByRole('dialog');
      await dialog.waitFor();
      assert.equal(await page.evaluate(() => !!document.querySelector('dialog:modal')), true);
      for (let i = 0; i < 9; i++) {await page.keyboard.press('Tab');assert.equal(await page.evaluate(() => document.querySelector('dialog').contains(document.activeElement)), true);}
      assert.equal(await dialog.evaluate(el => el.scrollWidth > el.clientWidth + 1), false);
      if ([1440, 390].includes(width)) {
        await screenshot(dialog, `tour-${width}-${theme}.png`);
      }
      for (const heading of ['Начните с источников', 'Проверьте основание', 'Решение остаётся за вами']) {
        await dialog.getByRole('button', {name: 'Далее', exact: true}).click();
        await page.getByRole('heading', {name: heading, exact: true}).waitFor();
      }
      assert.ok(['/signup','/#product-preview'].includes(await dialog.locator('a.product-tour-next').getAttribute('href'))||(await dialog.locator('a.product-tour-next').getAttribute('href')).startsWith('mailto:'));
      await dialog.getByRole('button', {name: 'Назад', exact: true}).click();
      await page.getByRole('heading', {name: 'Проверьте основание', exact: true}).waitFor();
      await page.keyboard.press('Escape');
      await page.locator('dialog').waitFor({state: 'detached'});
      assert.equal(await trigger.evaluate(el => el === document.activeElement), true);
      assert.equal(await page.evaluate(() => document.body.style.overflow), '');
      await trigger.click();
      await page.getByRole('heading', {name: 'Добро пожаловать в INROU', exact: true}).waitFor();
      await page.getByRole('button', {name: 'Пропустить', exact: true}).click();
      assert.equal(await page.locator('dialog').count(), 0);
      if ([1440, 390].includes(width)) await screenshot(page.locator('.home-hero'), `hero-${width}-${theme}.png`);
    }
    report.matrix.push({route, width, theme, overflow: false, status: 200});
    console.log(`PASS ${route} ${width} ${theme}`);
  }
  report.checks.push('Shared pricing selection, 30-day terms, signup CTA; no invented annual discount');
  report.checks.push('Source diagram selection, keyboard range input and plotted historical fixture agree');
  report.checks.push('Native modal: focus containment, four steps, back, skip, Escape, focus return, body scroll restoration');
  report.checks.push('Responsive hero, pricing, orbit and dialog; one h1; both themes and reduced motion');
  assert.deepEqual(report.errors, []);
} finally {
  await fs.writeFile(path.join(out, 'browser-report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(`PASS site wave 2: ${report.matrix.length} responsive cases, ${report.checks.length} interaction groups`);
