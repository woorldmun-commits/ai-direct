import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
function load(file, dependencies = {}) {
  const exports = {};
  const code = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  new Function('exports', 'require', code)(exports, name => {assert(name in dependencies); return dependencies[name];});
  return exports;
}
const base = load('../lib/pilot-contract.ts');
const { isInsights, isPassport, isActivity, isMeasurement, isWeeklyReport } = load('../lib/insights-contract.ts', {'./pilot-contract':base});
const period = {from:'2026-09-01',to:'2026-09-07'};
const value = {amount:null,unit:'rub',source:'yandex_direct',period,calculation_type:'unavailable',data_status:'complete',data_sufficiency:'insufficient',unavailable_reason:'no_data',rule_version:null,formula:null};
const data = {period,ad_accounts:[{id:'acc_1'}],health:{checks:[]},budget:{plan:null,actual:value,variance:value},lead_quality:{counts:{total:0,qualified:0,unresolved:0,matched:0},coverage:{matched_pct:null,qualification_complete:false,cohort_complete:false},qcpl:value,reason:'no_imported_leads'},summary:{period,generated_at:'2026-09-08T12:00:00Z',delivery:'manual_pull',facts:[],limitations:[]}};
assert(isInsights(data));
assert(isInsights({...data,lead_quality:{...data.lead_quality,reason:null}}));
assert(!isInsights({...data,budget:{...data.budget,actual:{...value,amount:0}}}));
assert(!isInsights({...data,period:{from:'2026-02-31',to:'2026-03-03'}}));
assert(!isInsights({...data,ad_accounts:[{id:'../acc_1'}]}));
assert(!isInsights({...data,lead_quality:{...data.lead_quality,counts:{...data.lead_quality.counts,total:-1}}}));
const passport = {id:'rec_1',version_id:'rv_1',state_version:'initial',status:'new',action:null,object:{type:'campaign',id:'1',name:null},evidence_current:true,title:'Synthetic test',action_level:'review',allowed_actions:['reject'],evidence:{cost:value},exposure:value,can_save:value,computed_at:'2026-09-08T12:00:00Z',explanation:null,history:[],latest_measurement:null,verification:{status:'unavailable',reason:'verification_worker_not_implemented'}};
assert(isPassport(passport));
assert(isPassport({...passport,action:{type:'decrease_bid',execution:'manual',change_pct:'-10.00'}}));
assert(!isPassport({...passport,action:{type:'decrease_bid',execution:'manual',change_pct:'-200.00'}}));
assert(!isPassport({...passport,action:{type:'investigate',execution:'manual',checks:['unknown'],placements:null}}));
assert(!isPassport({...passport,evidence:{cost:{...value,amount:1}}}));
assert(!isPassport({...passport,explanation:{text:['unsafe'],source:'template'}}));
assert(!isPassport({...passport,allowed_actions:['automatic_write']}));
assert(!isPassport({...passport,computed_at:'invalid'}));
console.log('PASS insights and passport: unavailable money, nullable reasons, periods, scope IDs and nested evidence');

const measurement={id:'measurement_1',policy:'high_cpa_measure@2',status:'pending',reason:'window_open',next_check_on:'2026-09-09',before_period:period,after_period:period,result:null};
assert(isMeasurement(measurement));
assert(!isMeasurement({...measurement,status:'complete'}));
assert(!isMeasurement({...measurement,next_check_on:'2026-02-31'}));
assert(!isMeasurement({...measurement,result:{verdict:'effect',before:{cpa:{...value,amount:1}},after:{},computed_at:'2026-09-08T12:00:00Z',counted_in_saved_total:false}}));
assert(isActivity({items:[{id:'rec_1',title:'Synthetic',status:'applied',execution_mode:'manual',updated_at:'2026-09-08T12:00:00Z',measurement}],next_cursor:null}));
assert(!isActivity({items:[],next_cursor:'1&url=evil'}));
const {workspacePath}=load('../lib/workspace-path.ts');
for(const endpoint of ['recommendation-activity','recommendation-activity?cursor=1','weekly-report'])assert(workspacePath('/workspaces/ws_1/'+endpoint,'GET'));
assert(workspacePath('/workspaces/ws_1/lead-import/preview','POST'));
for(const path of ['/workspaces/ws_1/lead-import/preview?url=evil','/workspaces/ws_1/recommendation-activity?cursor=0','/workspaces/ws_1/weekly-report/../../me'])assert(!workspacePath(path,'GET'));
console.log('PASS measurement states, activity pagination and closed BFF routes');

assert(isWeeklyReport({insights:data,decisions:[{type:'done',count:1}]}));
assert(!isWeeklyReport({insights:data,decisions:[{type:'automatic_ad_write',count:1}]}));
assert(!isWeeklyReport({insights:data,decisions:[{type:'done',count:-1}]}));
assert(!isWeeklyReport({insights:{...data,budget:{...data.budget,actual:{...value,amount:123}}},decisions:[]}));
console.log('PASS weekly report validates event kinds, nonnegative counts and nested Value');
