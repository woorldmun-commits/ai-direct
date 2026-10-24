import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
function load(path){const exports={};new Function('exports',ts.transpileModule(readFileSync(new URL(path,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports);return exports;}
const {isIntelligence,isBusinessFields,isIntelligenceMetric,syntheticImport}=load('../lib/intelligence-contract.ts');
const {workspacePath}=load('../lib/workspace-path.ts');
const fields={name:'Синтетический бизнес',industry_code:'generic',business_model:'b2b',products:['Услуги'],geography:['Москва'],currency:'RUB',timezone:'Europe/Moscow',goal:'Проверка',conversion_definition:'lead',average_order_value:null,gross_margin_pct:null,sales_cycle_days:null,budget_limit:null,seasonality:null,advantages:[],crm_available:false};
assert(isBusinessFields(fields));assert(!isBusinessFields({...fields,products:'wrong'}));assert(!isBusinessFields({...fields,sales_cycle_days:-1}));
const data={enabled:true,mode:'synthetic',can_write:true,profile:{revision:1,fields,provenance:{name:{origin:'user_confirmed',actor_id:1,updated_at:'2026-10-21T12:00:00Z'}}},industries:[],imports:[],runs:[],limits:{external_llm:false,external_execution:false}};
assert(isIntelligence(data));assert(isIntelligence({...data,enabled:false,profile:null}));
assert(!isIntelligence({...data,limits:{external_llm:true,external_execution:false}}));
assert(!isIntelligence({...data,profile:{...data.profile,provenance:{name:{origin:'model',actor_id:1,updated_at:'2026-10-21T12:00:00Z'}}}}));
assert(!isIntelligence({...data,industries:[{code:'x',name:'x',version:'1',review_status:'reviewed',sources:[{url:'javascript:alert(1)',title:'x'}],limitations:[]}]}));
const metric={value:null,status:'insufficient',reason_code:'no_data',unit:'RUB',currency:'RUB'};
assert(isIntelligenceMetric(metric));assert(!isIntelligenceMetric({...metric,value:'0'}));assert(isIntelligenceMetric({...metric,value:'0',status:'actual',reason_code:null}));assert(!isIntelligenceMetric({...metric,value:0,status:'actual'}));
assert(isIntelligenceMetric({...metric,value:'0.3333333333333333333333333333',status:'actual',reason_code:null}));
assert(!isIntelligenceMetric({...metric,value:'1e100',status:'actual',reason_code:null}));
const run={id:'00000000-0000-4000-8000-000000000001',status:'completed',created_at:'2026-10-21T12:00:00Z',question:'metrics',result:{metrics:{cpa:metric}},profile_revision:1,recommendations:[{id:'rec-1',title:'Проверить',status:'requires_decision',revision:1,state_version:0,facts:[],hypotheses:[],risks:[],next_step:'Проверить'}]};
assert(isIntelligence({...data,runs:[run]}));assert(!isIntelligence({...data,runs:[{...run,recommendations:[{...run.recommendations[0],status:'applied'}]}]}));
for(const endpoint of ['profile','import','analyze','decisions'])assert(workspacePath('/workspaces/ws_1/intelligence/'+endpoint,'POST'));
assert(workspacePath('/workspaces/ws_1/intelligence','GET'));
for(const path of ['/workspaces/ws_1/intelligence?url=https://evil.test','/workspaces/ws_1/intelligence/apply','/workspaces/ws_1/intelligence/profile/../../auth','/workspaces/../intelligence','/workspaces/ws_0/intelligence','https://evil.test/workspaces/ws_1/intelligence']){assert(!workspacePath(path,'GET'));assert(!workspacePath(path,'POST'));}
assert(!workspacePath('/workspaces/ws_1/intelligence','POST'));assert(!workspacePath('/workspaces/ws_1/intelligence/profile','GET'));
const before=syntheticImport(),after=syntheticImport(true);assert.equal(before.data_mode,'synthetic');assert.equal(after.data_mode,'synthetic');assert.equal(before.values.cost,'10000');assert.equal(before.values.clicks,'500');assert.equal(before.values.conversions,'50');assert.equal(after.values.cost,'12000');assert.equal(after.values.clicks,'400');assert.equal(after.values.conversions,'20');assert.deepEqual(before.account_ids,[]);
console.log('PASS intelligence: bounded contracts, no zero fill, explicit synthetic fixtures, unsafe source/status rejection and closed proxy endpoints');
const component={};
new Function('exports','require',ts.transpileModule(readFileSync(new URL('../components/workspace/intelligence.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(component,name=>name==='@/lib/intelligence-contract'?load('../lib/intelligence-contract.ts'):require(name));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const render=value=>renderToStaticMarkup(React.createElement(component.IntelligencePanel,{workspace:'ws_1',data:value}));
assert.match(render({...data,enabled:false}),/Аналитический контур выключен/);
const viewer=render({...data,can_write:false,runs:[run]});assert.match(viewer,/Режим просмотра/);assert.match(viewer,/fieldset disabled/);assert.match(viewer,/Нет данных/);assert(!viewer.includes('>0 RUB<'));
const escaped=render({...data,runs:[{...run,result:{note:'<script>alert(1)</script>'}}]});assert(!escaped.includes('<script>alert(1)</script>'));assert(escaped.includes('&lt;script&gt;'));
console.log('PASS intelligence rendering: disabled/viewer states, nullable metric and escaped evidence; no external execution or model claims');

assert(workspacePath('/workspaces/ws_1/intelligence/imports/00000000-0000-4000-8000-000000000001','GET'));
assert(!workspacePath('/workspaces/ws_1/intelligence/imports/00000000-0000-4000-8000-000000000001','POST'));
assert(!workspacePath('/workspaces/ws_1/intelligence/imports/https://evil.test','GET'));
assert(workspacePath('/workspaces/ws_1/intelligence?cursor=00000000-0000-4000-8000-000000000001','GET'));
console.log('PASS intelligence source references: bounded same-origin import evidence and read-only paths');

const historyCursor='00000000-0000-4000-8000-000000000002';
assert(render({...data,next_cursor:historyCursor}).includes(`/workspace/ai?workspace=ws_1&amp;cursor=${historyCursor}`));
const legacy={};
new Function('exports','require',ts.transpileModule(readFileSync(new URL('../app/workspace/page.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(legacy,()=>({redirect:url=>{throw new Error(url);}}));
await assert.rejects(()=>legacy.default({searchParams:Promise.resolve({workspace:'ws_1',view:'analyst',analysis_cursor:historyCursor})}),error=>error.message===`/workspace/ai?workspace=ws_1&cursor=${historyCursor}`);
await assert.rejects(()=>legacy.default({searchParams:Promise.resolve({workspace:'ws_1',view:'recommendations',rec:'rec_1',cursor:'o50'})}),error=>error.message==='/workspace/recommendations?workspace=ws_1&rec=rec_1&cursor=o50');
console.log('PASS intelligence pagination: current UI link and legacy bookmark preserve cursor/context');
