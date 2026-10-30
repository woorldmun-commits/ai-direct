import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const require = createRequire(import.meta.url);
function load(path, mocks = {}, globals = {}, expose = '') {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  const js = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  const exports = {};
  vm.runInNewContext(js + expose, {exports, require: name => {
    if (Object.hasOwn(mocks, name)) return mocks[name];
    if (name === 'react/jsx-runtime') return require(name);
    if (name.endsWith('.css')) return {};
    throw new Error('Unexpected import: ' + name);
  }, ...globals});
  return exports;
}

const privatePage = load('../lib/private-page.ts').isPrivatePage;
const document = {cookie: '', title: 'INROU', getElementById: () => null,
  createElement: () => ({}), head: {appendChild: () => {document.getElementById = () => ({});}}};
const window = {}, location = {pathname: '/', origin: 'https://example.test'};
const metrika = load('../components/cookie-banner.tsx', {
  'next/link': {}, '@/lib/private-page': {isPrivatePage: privatePage}, react: {}, 'next/navigation': {},
}, {document, window, location, process: {env: {NEXT_PUBLIC_YM_ID: '12345'}}}, '\nexports.track = loadMetrika;');
metrika.track(); assert.equal(window.ym, undefined);
document.cookie = 'inrou-consent=v1:all';
metrika.track(); metrika.track();
assert.equal(window.ym.a.length, 1); assert.equal(window.ym.a[0][1], 'init');
for (const pathname of ['/features', '/features', '/pricing', '/features']) {location.pathname = pathname; metrika.track();}
assert.equal(window.ym.a.length, 4);
assert.equal(window.ym.a[1][2], 'https://example.test/features');
for (const root of ['/app', '/workspace', '/onboarding', '/login', '/signup', '/register', '/verify-email', '/forgot-password', '/reset-password']) {
  for (const path of [root, root + '/nested']) {location.pathname = path; metrika.track();}
  assert.equal(window.ym.a.length, 4);
}
location.pathname = '/about'; document.cookie = 'inrou-consent=v1:necessary'; metrika.track();
assert.equal(window.ym.a.length, 4);
console.log('PASS consent, SPA hits, deduplication and private route exclusion');

let today, apiError = false;
const element = (tag, attributes = {}) => function MockElement({children}) {return React.createElement(tag, attributes, children);};
const mocks = {
  'next/link': {default: ({children, ...props}) => React.createElement('a', props, children)},
  '@/components/brand-mark': {BrandMark: () => null}, 'next/image': {default: () => null},
  './product-tour': {ProductTour: () => null},
  'next/navigation': {notFound: () => {throw new Error('404');}, redirect: () => {throw new Error('redirect');}},
  '@/components/workspace/direct-connect': {}, '@/components/workspace/intelligence': {},
  '@/lib/intelligence-contract': {},
  '@/lib/ix-live': {resolveWorkspace: async () => ({ok: true, selected: {id: 1}, workspaces: []}),
    safe: async value => apiError ? {ok: false, code: 'unavailable'} : {ok: true, data: await value}, stamp: value => String(value)},
  '@/lib/pilot': {pilotGet: async () => today}, '@/lib/pilot-contract': {isToday: () => true},
  './live/parts': {AuditLimitations: () => null, ErrorState: () => React.createElement('p', {role: 'alert'}, 'Unavailable'), sourceState: () => ({label: 'Source'})},
  './ui': {Card: element('article'), LinkBtn: element('a'), RowLine: element('section', {'data-row': ''}),
    StateBlock: element('section'), Tag: element('span')},
};
const {Onboarding} = load('../components/ix/onboarding.tsx', mocks);
for (const [audit, active, expected] of [['2026-10-26T00:00:00Z', 0, 'Готово'], [null, 0, 'Не выполнено'], ['2026-10-26T00:00:00Z', 3, 'Готово']]) {
  today = {data_freshness: {yandex_direct: {status: 'connected', data_to: '2026-10-25'}}, data_status: 'complete', last_audit_at: audit, counts: {active}};
  const html = renderToStaticMarkup(await Onboarding({step: 'first-audit', workspace: '1'}));
  const index = html.indexOf('Проверка рекомендаций');
  const row = html.slice(index, html.indexOf('</section>', index));
  assert(row.includes(expected), row);
  if (audit) assert(row.includes('Активных рекомендаций: ' + active));
}
apiError = true;
const errorHtml = renderToStaticMarkup(await Onboarding({step: 'first-audit', workspace: '1'}));
assert(errorHtml.includes('role="alert"')); assert(!errorHtml.includes('Проверка рекомендаций'));
const {methodBySlug} = load('../lib/methodology.ts');
assert.equal(methodBySlug('__proto__'), undefined);
assert.equal(methodBySlug('missing'), undefined);
assert.equal(methodBySlug('high-cpa').title, 'CPA выше ориентира');
console.log('PASS rendered onboarding: zero findings, pending audit, active findings and API error; methodology slug boundary');
