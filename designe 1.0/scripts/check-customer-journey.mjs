import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

function load(file) {
  const exports={};
  const code=ts.transpileModule(readFileSync(new URL(file,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  new Function('exports',code)(exports);
  return exports;
}
const {publicStart}=load('../lib/public-start.ts');
assert.equal(publicStart(false).href,'/#product-preview');
assert.equal(publicStart(true).href,'/signup');
assert.equal(publicStart(false,'support@example.test').href,'mailto:support%40example.test');
for(const bad of ['x@example.test\r\nBcc:other@example.test','https://example.test','x@bad..test','a@-bad.test','a'.repeat(255)+'@example.test'])assert.equal(publicStart(false,bad).contactEmail,null);
const injected=publicStart(false,'a?subject=changed@example.test');
assert(!injected.href.includes('?'),'mailto contact cannot inject query headers');
const {isEvaluationPolicy}=load('../lib/intelligence-contract.ts');
const policy={counter_id:1,goal_ids:[2,3],attribution:'last',conversion_stage:'visit',conversion_lag_days:2,minimum_conversions:5};
assert(isEvaluationPolicy(policy));
for(const patch of [{goal_ids:[2,2]},{goal_ids:[3,2]},{conversion_lag_days:true},{conversion_lag_days:3651},{minimum_conversions:0},{counter_id:0},{conversion_stage:'profit'},{attribution:'invented'}])assert(!isEvaluationPolicy({...policy,...patch}));
console.log('PASS customer entry readiness/contact injection and confirmed goal policy boundary');
