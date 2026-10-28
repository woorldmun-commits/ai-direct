import assert from 'node:assert/strict';
import {readFileSync, readdirSync, statSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Статические инварианты дизайн-системы INROU (.ix): токены эталона, честность данных, отсутствие Telegram.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => readFileSync(path.join(root, file), 'utf8');
const walk = dir => readdirSync(path.join(root, dir)).flatMap(name => {
  const rel = path.posix.join(dir, name);
  return statSync(path.join(root, rel)).isDirectory() ? walk(rel) : [rel];
});

const css = read('components/midnight/site.css');
// Current adaptation candidates from the master PNG; human visual approval remains separate.
for (const token of ['--bg-app:#F2EEE8', '--bg-page:#F2EEE8', '--surface:#FCFAF7', '--accent:#315d88', '--wine:#835626', '--shadow-card:', '--shadow-float:', '--ix-red:', '--ix-blue:', '--ix-teal:', '--ix-amber:']) assert(css.includes(token), `missing semantic design token ${token}`);
assert(css.includes('grid-template-columns:238px'), 'master workspace sidebar');
assert(css.includes('ix-detail-tabs'), 'recommendation tab styling');
assert(css.includes('prefers-reduced-motion:reduce'), 'reduced motion');

const sources = [...walk('components/ix'), ...walk('app'), 'lib/ix-live.ts'].filter(f => /\.(tsx?|css)$/.test(f) && !f.startsWith('app/legal'));
for (const file of sources) assert(!/telegram/i.test(read(file)), `Telegram must not appear: ${file}`);

// Рабочий кабинет не импортирует синтетические фикстуры демо.
for (const file of [...walk('components/ix/live'), 'lib/ix-live.ts', 'components/ix/onboarding.tsx']) assert(!/demo-data|demo-store/.test(read(file)), `live code imports demo fixtures: ${file}`);
// The new master includes marketing KPI examples; they must remain visibly synthetic.
assert(read('components/midnight/preview.tsx').includes('Иллюстрация интерфейса · синтетические данные'), 'public KPI disclaimer');
assert(read('components/midnight/preview.tsx').includes('Показатели синтетические'), 'decorative device disclaimer');

// Все 12 корневых и 2 контекстных раздела есть и в живом маршрутизаторе, и в демо.
const slugs = [...read('components/ix/nav.ts').matchAll(/slug: '([a-z-]+)'/g)].map(m => m[1]);
assert.equal(slugs.length, 14);
const rootNav = read('components/ix/nav.ts').split('export const CONTEXT_NAV')[0];
assert.equal([...rootNav.matchAll(/slug: '/g)].length, 12, 'exactly twelve root sections');
const router = read('components/ix/live/router.tsx'), demo = read('components/ix/demo-screens.tsx');
for (const slug of slugs) { assert(router.includes(`case '${slug}'`), `live router lacks ${slug}`); assert(demo.includes(`case '${slug}'`), `demo lacks ${slug}`); }

// Демо закрыто по умолчанию (аудит запуска: публичный демо-кабинет выведен из эксплуатации).
assert(/INROU_DEMO !== '1'\) notFound\(\)/.test(read('app/demo/layout.tsx')), 'demo must be disabled unless INROU_DEMO=1');
// Старый адрес кабинета остаётся редиректом.
assert(read('app/workspace/page.tsx').includes('redirect('), 'legacy /workspace redirect');
console.log(`PASS ix design system: tokens, 12 roots + 2 contexts live+demo, no Telegram, no demo fixtures in live code, demo disabled by default (${sources.length} files scanned)`);
