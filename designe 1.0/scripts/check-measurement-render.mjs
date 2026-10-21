import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),{jsx}=require('react/jsx-runtime'),{renderToStaticMarkup}=require('react-dom/server');
const source=readFileSync(new URL('../components/workspace/measurement.tsx',import.meta.url),'utf8');
const code=ts.transpileModule(source,{fileName:'measurement.tsx',compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const exports={};
const dependencies={'react/jsx-runtime':require('react/jsx-runtime'),'next/link':{default:()=>null},'@/components/value-view':{ValueView:()=>null},'@/lib/value':{formatPeriod:()=> 'Synthetic period'}};
new Function('exports','require',code)(exports,name=>{assert(name in dependencies);return dependencies[name];});
for(const reason of ['spend_lower_conversions_at_reference_cpa','placements_spend_left_campaign','cpa_lower_at_same_volume']){
 const measurement={id:'measurement_1',status:'complete',reason,next_check_on:null,policy:'synthetic',before_period:{},after_period:{},result:{verdict:'effect',before:{},after:{}}};
 const html=renderToStaticMarkup(jsx(exports.MeasurementView,{measurement}));
 assert(html.includes('Наблюдаемое улучшение'));assert(!html.includes('Данных недостаточно'));
 assert(html.includes('Причинная связь и подтверждённая экономия не установлены'));
}
console.log('PASS measured outcomes render success explanations without contradictory insufficient-data message');
