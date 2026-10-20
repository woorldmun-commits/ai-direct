import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire('C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium}=require('playwright');
const output=process.env.SCREENSHOT_DIR||'artifacts/adpilot/screenshots';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1536,height:1024},reducedMotion:'reduce'});
await context.addCookies([{name:'adpilot-consent',value:'v1:necessary',domain:'127.0.0.1',path:'/'}]);
const page=await context.newPage(),errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
const routes=['/','/demo','/demo/recommendations','/demo/campaigns','/demo/analyst','/demo/changes','/demo/integrations','/demo/reports','/demo/pricing','/demo/history','/demo/signals','/demo/team','/demo/settings'];
const findings=[];
for(const width of [1536,1280,834,390,320]){
 await page.setViewportSize({width,height:1024});
 for(const route of routes){
  const response=await page.goto((process.env.BASE_URL||'http://127.0.0.1:3117')+route,{waitUntil:'networkidle',timeout:60000});
  assert(response.status()<400,route+' HTTP '+response.status());
  await page.locator('h1').first().waitFor();
  const size=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));
  findings.push({route,width,...size});
  assert(size.scroll<=width+1,route+' overflow at '+width+': '+size.scroll);
  if(width===1536||width===390){const name=route==='/'?'landing':route==='/demo'?'analysis':route.split('/').pop();await page.screenshot({path:output+'/'+name+'-'+width+'.png',fullPage:true});}
  console.log('CHECK',width,route);
 }
}
await writeFile(output+'/layout-checks.json',JSON.stringify({findings,errors},null,2));
assert.deepEqual(errors,[]);await browser.close();
console.log('ERRORS',JSON.stringify(errors));



