import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import net from 'node:net';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'../..');
const web=path.join(root,'designe 1.0');
const {chromium}=createRequire(import.meta.url)('C:/Users/woorl/.local/share/agent-tools/gstack/node_modules/playwright');
const screenshots=path.join(import.meta.dirname,'screenshots');
mkdirSync(screenshots,{recursive:true});
const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});});
const base=`http://127.0.0.1:${port}`;
const child=spawn(process.execPath,[path.join(web,'node_modules/next/dist/bin/next'),'start','-H','127.0.0.1','-p',String(port)],{cwd:web,stdio:'ignore',env:{...process.env,INROU_STAGING:'1',INROU_DEMO:'1',INROU_API_URL:'http://127.0.0.1:1'}});
const report={base,localSyntheticDemo:true,pages:[],guards:[],interactions:[],failures:[]};
let browser;
try {
  let ready=false;
  for(let i=0;i<100;i++){try{ready=(await fetch(base)).ok;}catch{} if(ready)break;await new Promise(r=>setTimeout(r,300));}
  assert(ready,'production server failed to start');
  browser=await chromium.launch({headless:true});
  const routes=['/','/pricing','/features','/agencies','/contact','/signup','/login','/legal','/demo/analysis','/demo/recommendations','/demo/settings'];
  for(const theme of ['light','dark'])for(const width of [1440,390]){
    const context=await browser.newContext({viewport:{width,height:900},colorScheme:theme,reducedMotion:'reduce',locale:'ru-RU'});
    await context.addInitScript(value=>localStorage.setItem('inrou-theme',value),theme);
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    for(const route of routes){
      errors.length=0;
      const response=await page.goto(base+route,{waitUntil:'networkidle'});
      const info=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,main:document.querySelectorAll('main').length,h1:document.querySelectorAll('h1').length,theme:document.documentElement.dataset.theme,smallText:[...document.querySelectorAll('main p,main small,main button,main a')].filter(e=>e.getBoundingClientRect().width&&parseFloat(getComputedStyle(e).fontSize)<12).length}));
      const row={route,width,requestedTheme:theme,status:response.status(),...info,errors:[...errors]};
      report.pages.push(row);
      if(row.status!==200||row.overflow||!row.main||row.errors.length)report.failures.push(row);
      if(['/','/pricing','/signup','/demo/analysis','/demo/recommendations'].includes(route)){
        const name=(route==='/'?'home':route.slice(1).replaceAll('/','-'))+`-${width}-${theme}.png`;
        await page.screenshot({path:path.join(screenshots,name),fullPage:true});
        await page.screenshot({path:path.join(screenshots,name.replace('.png','-viewport.png')),fullPage:false});
      }
      if(route==='/'&&theme==='light'){
        const tabs=page.locator('.home-preview-tabs button');
        for(let i=0;i<await tabs.count();i++){await tabs.nth(i).click();assert.equal(await tabs.nth(i).getAttribute('aria-pressed'),'true');}
        report.interactions.push({width,check:'preview tabs',passed:true});
        const faq=page.locator('.home-faq summary').first();
        await faq.focus();await page.keyboard.press('Enter');assert(await page.locator('.home-faq details').first().getAttribute('open')!==null);
        report.interactions.push({width,check:'FAQ keyboard',passed:true});
        if(width===390){
          await page.getByRole('button',{name:'Открыть меню',exact:true}).click();
          assert(await page.getByRole('dialog',{name:'Навигация'}).isVisible());
          await page.keyboard.press('Escape');await page.getByRole('dialog',{name:'Навигация'}).waitFor({state:'hidden'});
          assert.equal(await page.getByRole('dialog',{name:'Навигация'}).count(),0);
          report.interactions.push({width,check:'mobile menu Escape',passed:true});
        }
      }
    }
    for(const route of ['/workspace','/workspace/recommendations','/onboarding']){
      await page.goto(base+route,{waitUntil:'networkidle'});
      const guarded=new URL(page.url()).pathname==='/login';
      report.guards.push({route,width,theme,guarded});
      if(!guarded)report.failures.push({route,width,theme,guarded});
    }
    await context.close();
  }
}finally{
  await browser?.close();child.kill();
  writeFileSync(path.join(import.meta.dirname,'browser.json'),JSON.stringify(report,null,2));
}
console.log(JSON.stringify({pages:report.pages.length,guards:report.guards.length,interactions:report.interactions.length,failures:report.failures}));
assert.equal(report.failures.length,0);
