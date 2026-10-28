import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const base=process.env.INROU_QA_BASE||'http://127.0.0.1:3154';
const out=path.resolve(import.meta.dirname,'../../docs/signup-illustration-2026-10-25');
const baseline=JSON.parse(await fs.readFile(path.join(out,'form-baseline.json'),'utf8'));
const report={cases:[],checks:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const ctx=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
 await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
 await ctx.addInitScript(()=>localStorage.setItem('inrou-theme','system'));
 const page=await ctx.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 for(const width of [320,390,768,1024,1440,1920])for(const theme of ['light','dark']){
  await page.setViewportSize({width,height:900});await page.emulateMedia({colorScheme:theme});
  const response=await page.goto(base+'/signup',{waitUntil:'networkidle'});
  const image=page.locator('.ix-auth-art--signup img');
  const visible=await image.isVisible();
  if(visible)await page.waitForFunction(()=>{const i=document.querySelector('.ix-auth-art--signup img');return i.complete&&i.naturalWidth>0;});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  assert.equal(response.status(),200);assert.equal(overflow,false);assert.equal(visible,width>=768);assert.equal(await image.getAttribute('alt'),'');
  assert.equal(await page.locator('.ix-auth-art--signup').getAttribute('aria-hidden'),'true');
  if(visible){const form=await page.locator('.ix-auth-form').boundingBox(),art=await image.boundingBox();assert.ok(art.x>=form.x+form.width,'Art stays to the right of form');}
  report.cases.push({route:'/signup',width,theme,status:response.status(),overflow,imageVisible:visible});
  if([390,1440].includes(width))await page.screenshot({path:path.join(out,`signup-${width}-${theme}.png`),animations:'disabled'});
 }
 for(const route of ['/signup','/login']){
  await page.goto(base+route,{waitUntil:'networkidle'});
  const form=await page.locator('.ref-email-form').evaluate(e=>({inputs:[...e.querySelectorAll('input')].map(n=>({type:n.type,name:n.name,required:n.required,disabled:n.disabled})),submit:[...e.querySelectorAll('button[type=submit]')].map(n=>({text:n.textContent,disabled:n.disabled})),text:e.textContent}));
  assert.deepEqual(form,baseline[route],route+' form controls/state unchanged');
  report.checks.push({route,formUnchanged:true});
 }
 for(const route of ['/login','/verify-email','/forgot-password','/reset-password']){
  await page.goto(base+route,{waitUntil:'networkidle'});assert.equal(await page.locator('.ix-auth-art--signup').count(),0);report.checks.push({route,signupImageAbsent:true});
 }
 await page.goto(base+'/register',{waitUntil:'networkidle'});assert.equal(new URL(page.url()).pathname,'/signup');report.checks.push({registerAlias:true});
 await ctx.close();
}catch(e){report.errors.push(e.stack);}finally{await browser.close();report.pass=report.cases.length===12&&!report.errors.length;await fs.writeFile(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify(report,null,2));if(!report.pass)process.exitCode=1;
