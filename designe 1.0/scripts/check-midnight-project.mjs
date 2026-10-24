import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

// Local visual smoke check; full authenticated regression is check-ix-acceptance.mjs.
const root=path.resolve(import.meta.dirname,'..');
const base=process.env.MIDNIGHT_QA_BASE||'http://127.0.0.1:3160';
assert.equal(new URL(base).hostname,'127.0.0.1');
const out=path.join(root,'../artifacts/screenshots/midnight-m3/smoke');
await fs.mkdir(out,{recursive:true});
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(path.join(runtime,'package.json'))(runtime);
const browser=await chromium.launch({channel:'msedge',headless:true});
const ctx=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
const page=await ctx.newPage();
page.setDefaultNavigationTimeout(90000);
const report={cases:[],errors:[],failures:[]};
page.on('pageerror',e=>report.errors.push(e.message));
try{
  for(const theme of ['light','dark']){
    await page.goto(base+'/login',{waitUntil:'networkidle'});
    await page.evaluate(t=>localStorage.setItem('inrou-theme',t),theme);
    for(const route of ['/','/features','/pricing','/login','/demo/overview','/demo/analysis','/demo/recommendations','/demo/settings','/demo/states','/legal','/nonexistent-midnight']){
      const res=await page.goto(base+route,{waitUntil:'networkidle'});
      assert.equal(res.status(),route.includes('nonexistent')?404:200);
      await page.evaluate(()=>document.fonts.ready);
      await page.addStyleTag({content:'nextjs-portal{display:none!important}'});
      for(const width of [390,768,1440,2560]){
        await page.setViewportSize({width,height:width===390?844:width===768?1024:1080});
        const geometry=await page.evaluate(()=>{
          const rect=s=>document.querySelector(s)?.getBoundingClientRect().toJSON();
          const r=document.querySelector('.ix,.ms-root');
          return {viewport:innerWidth,available:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,theme:document.documentElement.dataset.theme,canvas:rect('.ix-shell,.ms-public-main,.ix-pub,.ix-auth-shell,.mc-error-page'),sidebar:rect('.ix-sidebar,.ms-sidebar'),h1:rect('h1'),bg:r?getComputedStyle(r).getPropertyValue('--bg').trim():null};
        });
        const name=(route==='/'?'home':route.slice(1).replaceAll('/','-'))+'-'+width+'-'+theme;
        report.cases.push({route,width,theme,...geometry});
        if(geometry.scrollWidth>width)report.failures.push({name,error:'overflow',scrollWidth:geometry.scrollWidth});
        if(geometry.theme!==theme)report.failures.push({name,error:'theme mismatch'});
        if([390,1440,2560].includes(width))await page.screenshot({path:path.join(out,name+'.png'),fullPage:width===390,animations:'disabled'});
      }
    }
  }
}finally{await browser.close();await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({cases:report.cases.length,failures:report.failures,errors:report.errors},null,2));
if(report.failures.length||report.errors.length)process.exitCode=1;
