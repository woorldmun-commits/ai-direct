import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

// Local QA only: compare synthetic /demo fixtures; never authenticate or call the backend.
const root = path.resolve(import.meta.dirname, '../..');
const runtime = process.env.PLAYWRIGHT_MODULE || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const require = createRequire(path.join(runtime, 'package.json'));
const {chromium} = require(runtime);
const {PNG} = require('pngjs');
const pixelmatchModule = require('pixelmatch');
const pixelmatch = pixelmatchModule.default ?? pixelmatchModule;
const base = new URL(process.env.BASE_URL || 'http://127.0.0.1:3130');
assert(['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname), 'Use a local demo server only');
const archive = path.join(root, 'INROU_FINAL_HANDOFF');
const output = path.join(root, 'docs/design-implementation/screens/reference-19');
const hash = data => createHash('sha256').update(data).digest('hex');
const states = [
  ['overview', 'Обзор'], ['analysis', 'Анализ'], ['recommendations', 'Рекомендации'],
  ['campaigns', 'Кампании'], ['connections', 'Подключения'], ['impact', 'Эффект'],
  ['reports', 'Отчёты'], ['alerts', 'Сигналы'], ['ai', 'AI-аналитик'], ['history', 'История'],
  ['team', 'Команда'], ['plans', 'Тарифы'], ['settings', 'Настройки'], ['business-profile', 'Бизнес-профиль'],
  ['recommendations', 'Рекомендации', 'drawer'], ['analysis', 'Анализ', 'dark'],
  ['overview', 'Обзор', 'mobile'], ['analysis', 'Анализ', 'mobile'], ['recommendations', 'Рекомендации', 'mobile-drawer'],
];
const files = (await fs.readdir(path.join(archive, 'visual/verified_prototype_screenshots'))).filter(f => f.endsWith('.png')).sort();
assert.equal(files.length, states.length, 'All 19 immutable reference PNGs are required');

function compare(before, after) {
  assert.equal(before.width, after.width, 'Different widths cannot be compared');
  const width = before.width, height = Math.max(before.height, after.height);
  const padded = image => {
    const result = new PNG({width, height}); result.data.fill(255);
    PNG.bitblt(image, result, 0, 0, image.width, image.height, 0, 0); return result;
  };
  const a = padded(before), b = padded(after), diff = new PNG({width, height});
  const changedPixels = pixelmatch(a.data, b.data, diff.data, width, height, {threshold: 0.1, includeAA: false});
  const pair = new PNG({width: width * 2, height});
  PNG.bitblt(a, pair, 0, 0, width, height, 0, 0); PNG.bitblt(b, pair, 0, 0, width, height, width, 0);
  return {diff, pair, changedPixels, percent: changedPixels / (width * height) * 100, heightDelta: after.height - before.height};
}

// Check the comparison itself: identical input, a changed pixel, and unequal heights.
const sample = new PNG({width: 2, height: 2}); sample.data.fill(255);
assert.equal(compare(sample, sample).changedPixels, 0);
const changed = PNG.sync.read(PNG.sync.write(sample)); changed.data.fill(0, 0, 3);
assert.equal(compare(sample, changed).changedPixels, 1);
assert.equal(compare(sample, new PNG({width: 2, height: 3})).heightDelta, 1);

async function geometry(page, live) {
  return page.evaluate(live => {
    const prefix = live ? '.ix-' : '.';
    const read = selector => {
      const el = document.querySelector(selector); if (!el) return null;
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return {x: r.x, y: r.y, width: r.width, height: r.height, font: s.font, padding: s.padding,
        radius: s.borderRadius, border: s.border, shadow: s.boxShadow, color: s.color, background: s.backgroundColor};
    };
    const scope = document.querySelector(live ? '.ix' : 'body'), css = getComputedStyle(scope);
    return {viewport: {width: innerWidth, height: innerHeight}, scroll: {x: scrollX, y: scrollY},
      pageWidth: document.documentElement.scrollWidth, pageHeight: document.documentElement.scrollHeight,
      tokens: Object.fromEntries(['bg', 'panel', 'ink', 'muted', 'line', 'accent', 'wine', 'sage', 'shadow', 'shadow2'].map(k => [k, css.getPropertyValue('--' + k).trim()])),
      body: read(live ? '.ix' : 'body'), sidebar: read(prefix + 'sidebar'), main: read(prefix + 'main'),
      top: read(prefix + 'top'), heading: read('h1'), card: read(prefix + 'card'), drawer: read(prefix + 'drawerbox'),
      drawerScroll: document.querySelector(prefix + 'drawerbox')?.scrollTop ?? null,
      chart: read(prefix + 'chart'), lines: [...document.querySelectorAll(prefix + 'chart polyline')].map(el => el.getAttribute('points')),
      fontAvailability: {inter: document.fonts.check('14px Inter'), georgia: document.fonts.check('14px Georgia')},
    };
  }, live);
}

await fs.mkdir(output, {recursive: true});
const sourceFiles = execFileSync('git', ['ls-files', '-co', '--exclude-standard', '-z', '--', 'designe 1.0'], {cwd: root, encoding: 'utf8'}).split('\0').filter(Boolean).sort();
const sourceHashes = {};
for (const file of new Set(sourceFiles)) {
  try { sourceHashes[file] = hash(await fs.readFile(path.join(root, file))); } catch (e) { if (e.code !== 'ENOENT') throw e; }
}
const buildFile = path.join(root, 'designe 1.0/.next/BUILD_ID');
const buildTime = (await fs.stat(buildFile)).mtimeMs;
for (const file of Object.keys(sourceHashes).filter(f => /\.(tsx?|css)$/.test(f) && !f.includes('/scripts/'))) {
  assert((await fs.stat(path.join(root, file))).mtimeMs <= buildTime, `Build is stale: ${file}; rebuild and restart the local server`);
}
const browser = await chromium.launch({channel: 'msedge', headless: true});
const report = {started: new Date().toISOString(), revision: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(),
  dirty: true, sourceHashes, buildId: (await fs.readFile(buildFile, 'utf8')).trim(), browser: browser.version(), os: `${os.platform()} ${os.release()}`,
  base: base.origin, locale: 'ru-RU', timezone: 'Europe/Moscow', dpr: 1, reducedMotion: 'reduce',
  method: 'pixelmatch threshold=0.1 includeAA=false; equal widths; unequal heights padded white, never resized/cropped; no acceptance threshold',
  fixture: 'demo-01 / synthetic / 01–31.03.2025; original defaults; comparison enabled; scroll 0; drawer scroll 0',
  referenceHtmlSha256: hash(await fs.readFile(path.join(archive, 'reference/index.html'))), results: [], errors: []};
try {
  for (let i = 0; i < states.length; i++) {
    const [slug, label, variant = 'light'] = states[i], id = String(i + 1).padStart(2, '0');
    assert(files[i].startsWith(id + '_'), `Missing reference ${id}`);
    const archivedBuffer = await fs.readFile(path.join(archive, 'visual/verified_prototype_screenshots', files[i]));
    const before = PNG.sync.read(archivedBuffer), mobile = variant.includes('mobile'), drawer = variant.includes('drawer');
    const viewport = {width: mobile ? 390 : 1440, height: mobile ? 844 : 960};
    assert.equal(before.width, viewport.width);
    const context = await browser.newContext({viewport, deviceScaleFactor: 1, locale: report.locale, timezoneId: report.timezone, reducedMotion: 'reduce', colorScheme: 'light'});
    try {
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        return ['file:', 'data:'].includes(url.protocol) || url.origin === base.origin ? route.continue() : route.abort();
      });
      await context.addCookies([{name: 'inrou-consent', value: 'v1:necessary', url: base.origin}]);
      await context.addInitScript(() => {
        if (location.protocol !== 'file:') localStorage.setItem('inrou-theme', 'light');
        window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective));
      });
      const reference = await context.newPage(), actual = await context.newPage();
      for (const page of [reference, actual]) {
        page.on('pageerror', e => report.errors.push({id, message: e.message}));
        page.on('console', m => { if (m.type() === 'error') report.errors.push({id, message: m.text()}); });
      }
      await reference.goto(pathToFileURL(path.join(archive, 'reference/index.html')).href);
      await reference.evaluate(label => window.go(label), label);
      const response = await actual.goto(new URL('/demo/' + slug, base).href, {waitUntil: 'networkidle'});
      assert.equal(response.status(), 200, 'Demo must be enabled locally with INROU_DEMO=1');
      await actual.locator('.ix-page h1').waitFor();
      if (variant === 'dark') {
        await reference.locator('#theme').click();
        await actual.getByRole('button', {name: /Переключить тему/}).click();
        await actual.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
      }
      if (drawer) {
        await reference.evaluate(() => window.openRec(0));
        await actual.getByRole('button', {name: 'Подробнее →'}).first().click();
        await actual.getByRole('dialog').waitFor();
      }
      for (const page of [reference, actual]) {
        await page.mouse.move(0, 0);
        await page.evaluate(async () => { await document.fonts.ready; window.scrollTo(0, 0); });
      }
      const expectedGeometry = await geometry(reference, false), actualGeometry = await geometry(actual, true);
      assert.equal(actualGeometry.scroll.y, 0); assert([null, 0].includes(actualGeometry.drawerScroll));
      assert(actualGeometry.pageWidth <= viewport.width, `Page overflow: ${id}`);
      assert.deepEqual(await actual.evaluate(() => window.__csp), [], `CSP ${id}`);
      const renderedBuffer = await reference.screenshot({fullPage: true, animations: 'disabled'});
      const afterBuffer = await actual.screenshot({fullPage: true, animations: 'disabled'});
      const rendered = PNG.sync.read(renderedBuffer), after = PNG.sync.read(afterBuffer);
      const originalDiff = compare(before, after), environmentDiff = compare(rendered, after), archiveDrift = compare(before, rendered);
      const dir = path.join(output, id + '-' + slug + '-' + variant); await fs.mkdir(dir, {recursive: true});
      const artifacts = {'before.png': archivedBuffer, 'after.png': afterBuffer, 'diff.png': PNG.sync.write(originalDiff.diff),
        'side-by-side.png': PNG.sync.write(originalDiff.pair), 'reference-edge.png': renderedBuffer, 'diff-edge.png': PNG.sync.write(environmentDiff.diff)};
      const artifactHashes = {};
      for (const [name, bytes] of Object.entries(artifacts)) { await fs.writeFile(path.join(dir, name), bytes); artifactHashes[name] = hash(bytes); }
      const result = {id, slug, label, variant, route: '/demo/' + slug, viewport, source: files[i], sourceSha256: hash(archivedBuffer),
        before: {width: before.width, height: before.height}, after: {width: after.width, height: after.height},
        referenceEdge: {width: rendered.width, height: rendered.height}, changedPixels: originalDiff.changedPixels, percent: originalDiff.percent,
        heightDelta: originalDiff.heightDelta, edgePercent: environmentDiff.percent, archiveDriftPercent: archiveDrift.percent,
        expectedGeometry, actualGeometry, artifacts: path.relative(output, dir).replaceAll('\\', '/'), artifactHashes};
      report.results.push(result);
      console.log(`${id} ${slug} ${variant}: archive ${result.percent.toFixed(2)}%, same Edge ${result.edgePercent.toFixed(2)}%, height ${result.heightDelta >= 0 ? '+' : ''}${result.heightDelta}px`);
      if (drawer) {
        await actual.keyboard.press('Escape'); await actual.getByRole('dialog').waitFor({state: 'detached'});
        assert.equal(await actual.evaluate(() => document.activeElement?.textContent), 'Подробнее →', 'Restore focus to drawer opener');
      }
    } finally { await context.close(); }
  }
  assert.equal(report.results.length, 19);
  assert.deepEqual(report.errors, []);
} finally {
  report.finished = new Date().toISOString();
  await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(report, null, 2) + '\n');
  await browser.close();
}
const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
await fs.writeFile(path.join(output, 'index.html'), `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>INROU — 19 визуальных сравнений</title><style>body{font:16px/1.5 system-ui;margin:24px;max-width:1500px}img{width:100%;height:auto}section{margin:32px 0}a{margin-right:16px}</style><h1>INROU: 19 состояний</h1><p>Слева неизменённый PNG архива, справа текущая реализация. Синтетические данные; визуальная приёмка ожидается. Процент — измерение, не допуск.</p>${report.results.map(r => `<section><h2>${r.id}. ${escape(r.label)} / ${r.variant}</h2><p>PNG: ${r.percent.toFixed(2)}%; тот же Edge: ${r.edgePercent.toFixed(2)}%; ΔH: ${r.heightDelta}px</p>${['before.png', 'after.png', 'diff.png', 'reference-edge.png', 'diff-edge.png'].map(name => `<a href="${r.artifacts}/${name}">${name}</a>`).join('')}<img loading="lazy" src="${r.artifacts}/side-by-side.png" alt="${escape(r.label)}: эталон и реализация"></section>`).join('')}</html>`);
console.log(`CAPTURED 19/19; no page errors, CSP violations or horizontal overflow. Visual approval PENDING. ${output}`);
