import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'../..'),web=path.join(root,'designe 1.0'),out=import.meta.dirname;
const {chromium}=createRequire(import.meta.url)('C:/Users/woorl/.local/share/agent-tools/gstack/node_modules/playwright');
const fixture=JSON.parse(await fs.readFile(path.join(web,'artifacts/.runtime/fixture.json'),'utf8'));
const base='http://127.0.0.1:3130';
const child=spawn(process.execPath,[path.join(web,'node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p','3130'],{cwd:web,stdio:'ignore',env:{...process.env,INROU_API_URL:'http://127.0.0.1:3121',INROU_APP_ORIGIN:base,INROU_STAGING:'1',INROU_DEMO:'1'}});
const report={base,scope:'Local production Next build and real FastAPI/RLS; disposable synthetic fixture only',pages:[],checks:[],failures:[]};
let browser;
try{
 let ready=false;for(let i=0;i<100;i++){try{ready=(await fetch(base)).ok;}catch{}if(ready)break;await new Promise(r=>setTimeout(r,300));}assert(ready);
 browser=await chromium.launch({channel:'msedge',headless:true});
 for(const width of [1440,804,390])for(const theme of ['light','dark']){
  const ctx=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:'reduce',locale:'ru-RU'});
  await ctx.addCookies([{name:'session',value:fixture.tokens.owner,url:base,httpOnly:true,sameSite:'Lax'},{name:'inrou-consent',value:'v1:necessary',url:base}]);
  await ctx.addInitScript(theme=>localStorage.setItem('inrou-theme',theme),theme);
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const [section,ws] of [['overview',fixture.workspaces.a1],['ai',fixture.workspaces.a1],['plans',fixture.workspaces.a2]]){
   errors.length=0;const response=await page.goto(`${base}/workspace/${section}?workspace=${ws}&days=7`,{waitUntil:'networkidle'});
   const row={section,width,theme,status:response.status(),h1:await page.locator('h1').count(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),errors:[...errors]};
   report.pages.push(row);assert.equal(row.status,200);assert.equal(row.h1,1);assert(!row.overflow);assert.deepEqual(errors,[]);
   if(section==='overview')assert(await page.locator('svg[role="img"]').count()>0,'overview must render actual series');
   if(section==='ai'){
    await page.getByRole('heading',{name:'Подключённые данные и основания',exact:true}).waitFor();
    const text=await page.locator('main').innerText();assert(text.includes('Снимки и ограничения расчёта'));assert(text.includes('Внешняя языковая модель не подключена'));
   }
   if(section==='plans'){const text=await page.locator('main').innerText();assert(text.includes('7 дней бесплатно'));assert(text.includes('Без карты и автосписаний'));}
   assert(!(await page.content()).includes(fixture.tokens.owner));
   if(width!==804)await page.screenshot({path:path.join(out,`${section}-${width}-${theme}.png`),fullPage:true});
  }
  await ctx.close();
 }
 for(const [who,workspace] of [['viewer',fixture.workspaces.b1],['owner_b',fixture.workspaces.a1]]){
  const ctx=await browser.newContext();await ctx.addCookies([{name:'session',value:fixture.tokens[who],url:base,httpOnly:true,sameSite:'Lax'}]);
  const response=await ctx.request.get(`${base}/api/workspaces/${workspace}/intelligence/snapshot-analysis?days=7`);
  assert.equal(response.status(),404);report.checks.push({name:'Foreign workspace snapshot analysis denied',pass:true});await ctx.close();
 }
}catch(error){report.failures.push({error:error.message});}
finally{await browser?.close();child.kill();await fs.writeFile(path.join(out,'browser.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({cases:report.pages.length,checks:report.checks.length,failures:report.failures}));
assert.equal(report.failures.length,0);
