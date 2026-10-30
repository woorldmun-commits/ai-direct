import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const base='http://127.0.0.1:3130';
const out=path.join(root,'../artifacts/screenshots/midnight-m3/states');
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const report={buildId:(await fs.readFile(path.join(root,'.next/BUILD_ID'),'utf8')).trim(),checks:[],captures:[],failures:[],pageErrors:[],synthetic:true};
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const ctx=await browser.newContext({viewport:{width:1440,height:900},locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce',hasTouch:true});
await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
await ctx.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
const page=await ctx.newPage();page.on('pageerror',e=>report.pageErrors.push(e.message));
const check=async(name,fn)=>{try{await fn();report.checks.push({name,pass:true});}catch(e){report.failures.push({name,error:e.message});}};
async function capture(name,selector){
 const options={path:path.join(out,name+'.png'),animations:'disabled'};
 const bytes=selector?await page.locator(selector).screenshot(options):await page.screenshot(options);
 report.captures.push({name:name+'.png',sha256:createHash('sha256').update(bytes).digest('hex')});
}
try{
 for(const theme of ['light','dark']){
  await page.goto(base+'/login',{waitUntil:'networkidle'});await page.evaluate(t=>localStorage.setItem('inrou-theme',t),theme);
  await page.reload({waitUntil:'networkidle'});
  await check('Auth CTA keeps Sapphire gradient and white text '+theme,async()=>{
   const paint=await page.locator('.ref-primary,.ref-auth-submit').first().evaluate(e=>({background:getComputedStyle(e).backgroundImage,color:getComputedStyle(e).color}));
   assert.match(paint.background,/49, 90, 124/);assert.equal(paint.color,'rgb(255, 255, 255)');
  });
  await page.setViewportSize({width:1440,height:900});
  await page.goto(base+'/',{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);
  await capture('home-master-'+theme,'.home-hero');
  await page.goto(base+'/demo/analysis',{waitUntil:'networkidle'});
  await page.locator('.ix-hit').nth(8).focus();await page.locator('.ix-tooltip').waitFor();await capture('analysis-keyboard-tooltip-'+theme);
  await page.goto(base+'/demo/recommendations?rec=0',{waitUntil:'networkidle'});
  await page.getByRole('dialog').waitFor();await capture('recommendation-drawer-'+theme);
  for(const title of ['Данные','Расчёты']){
   const tab=page.getByRole('tab',{name:title,exact:true});await tab.click();await capture('recommendation-'+(title==='Расчёты'?'calculation':'evidence')+'-'+theme);
  }
  await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'/',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Открыть меню'}).click();await page.getByRole('dialog').waitFor();await capture('home-mobile-menu-'+theme);await page.keyboard.press('Escape');
  await check('Home mobile menu restores focus '+theme,async()=>assert(await page.getByRole('button',{name:'Открыть меню'}).evaluate(e=>e===document.activeElement)));
  await page.goto(base+'/demo/overview',{waitUntil:'networkidle'});
  await page.locator('.ix-top').getByRole('button',{name:'Открыть меню'}).click();await capture('cabinet-mobile-menu-'+theme);await page.keyboard.press('Escape');
  await page.locator('.ix-hit').nth(8).tap();await page.locator('.ix-tooltip').waitFor();await capture('overview-mobile-touch-tooltip-'+theme);
  await check('Touch tooltip stays inside mobile viewport '+theme,async()=>{const b=await page.locator('.ix-tooltip').boundingBox();assert(b.x>=0&&b.x+b.width<=390);});
  await page.goto(base+'/demo/recommendations?rec=0',{waitUntil:'networkidle'});await page.getByRole('dialog').waitFor();await capture('recommendation-mobile-drawer-'+theme);
  await check('Mobile decision buttons remain above bottom navigation '+theme,async()=>{
   const action=page.getByRole('dialog').getByRole('button',{name:'Отклонить',exact:true});await action.scrollIntoViewIfNeeded();
   assert(await action.evaluate(e=>{const b=e.getBoundingClientRect();return e.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2));}));
  });await page.keyboard.press('Escape');
  for(const route of ['/forgot-password','/verify-email','/reset-password']){await page.goto(base+route,{waitUntil:'networkidle'});await capture(route.slice(1)+'-mobile-'+theme);}
  await page.goto(base+'/missing-midnight-page',{waitUntil:'networkidle'});await page.getByRole('heading',{name:'Эта страница не найдена'}).waitFor();await capture('not-found-mobile-'+theme);
 }
 await check('Normal motion finishes without continuous decorative animation',async()=>{
  await page.setViewportSize({width:1440,height:900});await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto(base+'/demo/overview',{waitUntil:'networkidle'});await page.waitForTimeout(1000);
  assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.effect?.getTiming().iterations===Infinity).length),0);
  assert.equal(await page.locator('.ix-page').evaluate(e=>getComputedStyle(e).opacity),'1');
  await capture('overview-normal-motion-finished');
 });
 await check('Cookie controls retain a visible working dialog',async()=>{
  await page.goto(base+'/',{waitUntil:'networkidle'});await page.getByRole('button',{name:'Настройки cookie',exact:true}).click();await page.getByRole('dialog',{name:'Настройки cookie'}).waitFor();await capture('cookie-settings');
  await page.getByRole('dialog',{name:'Настройки cookie'}).getByRole('button',{name:'Сохранить выбор',exact:true}).click();await page.getByRole('dialog',{name:'Настройки cookie'}).waitFor({state:'detached'});
 });
 await check('Theme colors remain Sapphire after client-side route navigation',async()=>{
  await page.goto(base+'/pricing',{waitUntil:'networkidle'});
  const color=await page.locator('.ix-btn--primary').first().evaluate(e=>getComputedStyle(e).backgroundImage);
  assert.match(color,/49, 90, 124/);
  await page.getByRole('link',{name:'Возможности',exact:true}).first().click();await page.waitForURL('**/features');
  assert.equal(await page.locator('.ms-artwork').count(),1);
 });
}catch(e){report.failures.push({name:'fatal state capture',error:e.stack||e.message});}
finally{await browser.close();report.complete=report.failures.length===0&&report.pageErrors.length===0;await fs.writeFile(path.join(out,'results.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({checks:report.checks.length,captures:report.captures.length,failures:report.failures,pageErrors:report.pageErrors},null,2));
assert(report.complete);
