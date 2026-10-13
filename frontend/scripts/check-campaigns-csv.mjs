import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../lib/campaigns-csv.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { campaignsCsv } = await import('data:text/javascript;base64,' + Buffer.from(output).toString('base64'));
const header = '\uFEFFКампания;ID;Расход (руб.);Конверсии\r\n';
const campaign = { name: 'Поиск; "Москва"\r\nУслуги', id: '51234567', spend: 1234.5, conversions: 0 };
assert.equal(campaignsCsv([campaign]), header + '"Поиск; ""Москва""\r\nУслуги";"51234567";1234,50;0');
assert.equal(campaignsCsv([]), header);
for (const name of ['=1+1', '+SUM(A1)', '-1+2', '@SUM(A1)', '  =1+1', '\t=1+1', '\r=1+1', '\n=1+1']) {
  assert.equal(campaignsCsv([{ ...campaign, name }]), header + `"'${name}";"51234567";1234,50;0`);
}
assert.equal(campaignsCsv([{ ...campaign, name: 'Обычная кампания', spend: 0, conversions: 12 }]), header + '"Обычная кампания";"51234567";0,00;12');
assert.equal(campaignsCsv([campaign, campaign]).split('\r\n"Поиск').length, 3);
console.log('OK campaigns CSV: BOM, escaping, decimal amounts, zero conversions and formula safety');
