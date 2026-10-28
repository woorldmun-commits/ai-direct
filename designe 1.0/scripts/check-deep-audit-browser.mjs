import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir, writeFile} from 'node:fs/promises';

const require = createRequire('C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium} = require('playwright');
const base = process.env.BASE_URL || 'http://127.0.0.1:3117';
const output = process.env.OUTPUT_DIR || '../docs/deep-audit-fixes-2026-10-26/browser';
await mkdir(output, {recursive: true});
const browser = await chromium.launch({channel: 'msedge', headless: true});
const context = await browser.newContext({viewport: {width: 804, height: 900}, reducedMotion: 'reduce'});
await context.addCookies([{name: 'inrou-consent', value: 'v1:necessary', domain: new URL(base).hostname, path: '/'}]);
const page = await context.newPage(), checks = [], errors = [];
page.on('pageerror', e => errors.push(e.message));
try {
  for (const theme of ['light', 'dark']) {
    for (const width of [320, 390, 767, 768, 804, 860, 861, 1023, 1024, 1279, 1280, 1440]) {
      await page.setViewportSize({width, height: 900});
      await page.goto(base + '/features', {waitUntil: 'networkidle'});
      await page.evaluate(theme => {localStorage.setItem('inrou-theme', theme); document.documentElement.dataset.theme = theme;}, theme);
      const nav = page.getByRole('navigation', {name: 'Главная навигация'});
      const menu = page.getByRole('button', {name: 'Открыть меню', exact: true});
      if (width < 1280) {
        assert(await menu.isVisible(), `menu ${width}`);
        await menu.click();
        assert(await nav.isVisible());
        await page.getByRole('button', {name: 'Закрыть меню', exact: true}).focus();
        await page.keyboard.press('Escape');
        assert(!(await nav.isVisible()));
        assert(await menu.evaluate(e => e === document.activeElement));
      } else assert(await nav.isVisible());
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      assert(!overflow, `${theme} ${width} overflow`);
      checks.push({theme, width, route: '/features', nav: 'pass', overflow: false});
      if ([390, 804, 1440].includes(width)) await page.screenshot({path: `${output}/features-${theme}-${width}.png`, fullPage: true});
    }
  }
  for (const route of ['/features', '/how-it-works', '/agencies', '/business', '/pricing', '/integrations', '/security', '/faq', '/contact', '/about', '/methodology', '/methodology/zero-conversions', '/methodology/high-cpa', '/methodology/placements']) {
    const response = await page.goto(base + route, {waitUntil: 'networkidle'});
    assert.equal(response.status(), 200, route);
    assert.equal(await page.locator('h1').count(), 1, route);
    assert.equal(await page.locator('link[rel="canonical"]').getAttribute('href').then(href => new URL(href).pathname), route);
    assert(await page.locator('meta[name="description"]').getAttribute('content'));
    assert((await page.locator('meta[property="og:image"]').first().getAttribute('content')).includes('/social-preview.png'));
    assert.equal(await page.locator('a[href="/demo"], a[href^="/app/"]').count(), 0, route + ' public links');
    checks.push({route, status: response.status(), metadata: 'pass', publicLinks: 'pass'});
  }
  for (const route of ['/cases', '/blog']) {
    await page.goto(base + route);
    assert((await page.locator('meta[name="robots"]').getAttribute('content')).includes('noindex'));
  }
  await page.goto(base + '/features');
  await page.getByRole('link', {name: 'Посмотреть интерфейс', exact: true}).click();
  await page.waitForURL('**/#product-preview');
  assert(await page.locator('#product-preview').isVisible());
  assert.deepEqual(errors, []);
  console.log(`PASS ${checks.length} navigation/layout/metadata cases; demo CTA; placeholder noindex; no page errors`);
} finally {
  await writeFile(output + '/checks.json', JSON.stringify({base, checks, errors}, null, 2));
  await browser.close();
}
