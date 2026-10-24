import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const out=path.join(root,'../artifacts/screenshots/midnight-r2');
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const ctx=await browser.newContext({viewport:{width:1440,height:900},locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:'http://127.0.0.1:3144'}]);
await ctx.addInitScript(()=>localStorage.setItem('inrou-theme','light'));
const page=await ctx.newPage();const geometry=[];
try{
  for(const screen of ['landing','overview','recommendation']){
    const res=await page.goto('http://127.0.0.1:3144/demo/midnight/'+screen,{waitUntil:'networkidle'});assert.equal(res.status(),200);
    await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'nextjs-portal{display:none!important}'});
    await page.screenshot({path:path.join(out,screen+'-review-desktop.png'),animations:'disabled'});
    await page.screenshot({path:path.join(out,screen+'-review-full.png'),fullPage:true,animations:'disabled'});
    if(screen==='landing')await page.locator('.ms-landing-master').screenshot({path:path.join(out,'landing-master-review.png')});
    geometry.push(await page.evaluate(screen=>({screen,scrollWidth:document.documentElement.scrollWidth,width:innerWidth,rects:Object.fromEntries(['h1','.ms-landing-master','.ms-hero-copy>p','.ms-hero-copy>.ms-cta-row','.ms-benefits','.ms-sidebar','.ms-chart-card','.ms-status-grid','.ms-overview-lower','.ms-cpa-card','.ms-check-list','.ms-actionbar'].map(s=>[s,document.querySelector(s)?.getBoundingClientRect().toJSON()]))}),screen));
  }
  await page.setViewportSize({width:390,height:844});
  for(const screen of ['landing','overview','recommendation']){
    await page.goto('http://127.0.0.1:3144/demo/midnight/'+screen,{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);await page.addStyleTag({content:'nextjs-portal{display:none!important}'});
    await page.screenshot({path:path.join(out,screen+'-review-mobile.png'),animations:'disabled'});
    await page.screenshot({path:path.join(out,screen+'-review-mobile-full.png'),fullPage:true,animations:'disabled'});
  }
  await fs.writeFile(path.join(out,'review-geometry.json'),JSON.stringify(geometry,null,2));
  console.log(JSON.stringify(geometry,null,2));
}finally{await browser.close();}
