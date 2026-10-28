import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
function load(file) {
  const exports = {};
  new Function('exports', 'require', ts.transpileModule(fs.readFileSync(new URL(file, import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText)(exports, name => name === 'next/image' ? {default: () => null} : name === './geometry' || name === './ui' || name === '@/components/value-view' ? {} : require(name));
  return exports;
}
const {allocateDemo, DEMO_METRIC_SERIES, DEMO_CAMPAIGNS} = load('../components/ix/demo-data.ts');
for (const row of DEMO_CAMPAIGNS.filter(row => row[2] === 'Активна')) {
  const number = s => Number(s.replace(/[^\d]/g, ''));
  assert.equal(number(row[5]), Math.round(number(row[3]) / number(row[4])));
}
for (const total of [0, 1, 1284, 248640, 3842000]) {
  const values = allocateDemo(total, [1, 2, 7]);
  assert.equal(values.reduce((a, b) => a + b, 0), total);
  assert(values.every(Number.isInteger)); assert(values.every(v => v >= 0));
}
assert.equal(DEMO_METRIC_SERIES.length, 4);
assert.equal(new Set(DEMO_METRIC_SERIES.map(s => s.color)).size, 4);
for (const s of DEMO_METRIC_SERIES) {
  assert.equal(s.values.length, 14); assert.equal(s.display.length, 14);
  assert(s.values.every(Number.isFinite)); assert(s.previous.every(Number.isFinite));
}
for (let i = 0; i < 14; i++) {
  assert.equal(DEMO_METRIC_SERIES[2].values[i], DEMO_METRIC_SERIES[0].values[i] / DEMO_METRIC_SERIES[1].values[i]);
  assert.equal(DEMO_METRIC_SERIES[2].previous[i], DEMO_METRIC_SERIES[0].previous[i] / DEMO_METRIC_SERIES[1].previous[i]);
}
assert(fs.existsSync(new URL('../public/fonts/INTER-OFL.txt', import.meta.url)));
const {indexValues} = load('../components/ix/chart.tsx');
const {curvePath, segments} = load('../components/ix/geometry.ts');
assert.equal(curvePath('0,10 20,30 40,0'), 'M0,10 C10,10 10,30 20,30 C30,30 30,0 40,0');
assert.equal(segments([10, 20, null, 30, 40], 1).map(curvePath).length, 2);
assert.deepEqual(indexValues([0, 0, null, 0], undefined), [0, 0, null, 0]);
assert.deepEqual(indexValues([0, null, 10, 20], 10), [0, null, 100, 200]);
assert.deepEqual(indexValues([15, 30], 10), [150, 300]);
console.log('PASS premium: exact demo allocation/CPA, four distinct series, finite comparison and chart geometry; local font license');
