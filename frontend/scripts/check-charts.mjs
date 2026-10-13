import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Module from 'node:module';
import ts from 'typescript';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const chartPath = fileURLToPath(new URL('../components/charts.tsx', import.meta.url));
const chartModule = new Module(chartPath);
chartModule.paths = Module._nodeModulePaths(path.dirname(chartPath));
chartModule._compile(ts.transpileModule(readFileSync(chartPath, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText, chartPath);
const { Sparkline, LineChart, Bars, Donut } = chartModule.exports;
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const series = values => [{ name: 'Расход', color: '#123456', values }];
for (const html of [render(Sparkline, {values:[7]}), render(LineChart, {series:series([7]),labels:['Один день'],bars:true}), render(LineChart, {series:series([0,0]),labels:['1','2']}), render(Bars, {a:[0,0],b:[0,0],labels:['1','2']}), render(Donut, {parts:[{label:'Нет расхода',value:0,color:'#123456'}]})]) {
  assert.doesNotMatch(html, /NaN|Infinity/);
}
assert.equal(render(Sparkline,{values:[]}), '');
assert.equal(render(Sparkline,{values:[NaN]}), '');
assert.match(render(LineChart,{series:[],labels:[]}), /role="status"/);
assert.match(render(LineChart,{series:series([7]),labels:['1','2']}), /Недостаточно данных/);
assert.match(render(Bars,{a:[5],b:[],labels:['1']}), /Недостаточно данных/);
assert.match(render(Donut,{parts:[]}), /недостаточно данных/);
assert.match(render(LineChart,{series:series([2,7]),labels:['1','2'],bars:true}), /chart-bar/);
assert.doesNotMatch(render(LineChart,{series:series([2,7]),labels:['1','2']}), /chart-bar/);
console.log('OK charts: empty, single point, zero, invalid/mismatched data and optional bars');

