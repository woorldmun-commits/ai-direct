import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('C:/Users/woorl/.local/share/agent-tools/gstack/node_modules/playwright');
const out=import.meta.dirname, base=process.env.BASE_URL||'https://inrou-pilot.onrender.com';
const report={base,started:new Date().toISOString(),pages:[],guards:[],checks:[],failures:[]};
const routes=['/','/features','/how-it-works','/agencies','/business','/pricing','/integrations','/security','/faq','/contact','/about','/methodology','/methodology/zero-conversions','/methodology/high-cpa','/methodology/placements','/signup','/login','/forgot-password','/legal','/legal/privacy','/legal/offer','/demo/overview','/demo/analysis','/demo/recommendations','/demo/connections','/demo/plans','/demo/team','/demo/settings'];
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  report.browser=browser.version();
  const ctx=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
  await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
  const page=await ctx.newPage();
  for(const width of [1440,804,390]){
    await page.setViewportSize({width,height:900});
    for(const route of routes){
      const errors=[];const onError=e=>errors.push(e.message);page.on('pageerror',onError);
      try{
        const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:90000});
        const details=await page.evaluate(()=>({title:document.title,h1:[...document.querySelectorAll('h1')].map(e=>e.textContent),overflow:document.documentElement.scrollWidth>innerWidth+1,canonical:document.querySelector('link[rel="canonical"]')?.href,robots:document.querySelector('meta[name="robots"]')?.content,body:document.body.innerText.slice(0,1800)}));
        const row={route,width,status:response.status(),url:page.url(),...details,errors};report.pages.push(row);
        if(row.status!==200||row.overflow||row.h1.length!==1||errors.length)report.failures.push(row);
        if(width!==804&&['/','/signup','/demo/analysis','/demo/recommendations'].includes(route))await page.screenshot({path:`${out}/hosted-${width}-${route.replaceAll('/','-')||'home'}.png`,fullPage:true});
      }catch(error){report.failures.push({route,width,error:error.message});}
      finally{page.off('pageerror',onError);}
    }
    console.log(`Completed ${width}px`,report.pages.length,flush=>flush);
  }
  for(const route of ['/workspace','/workspace/recommendations','/onboarding']){
    const res=await ctx.request.get(base+route,{maxRedirects:0});
    const row={route,status:res.status(),location:res.headers().location,cache:res.headers()['cache-control']};report.guards.push(row);
    if(![302,303,307,308].includes(row.status)||new URL(row.location,base).pathname!=='/login')report.failures.push(row);
  }
  for(const route of ['/api/health','/api/auth/config','/api/workspaces/ws_1/subscription','/robots.txt']){
    const res=await ctx.request.get(base+route);report.checks.push({route,status:res.status(),body:(await res.text()).slice(0,5000),cache:res.headers()['cache-control'],robots:res.headers()['x-robots-tag']});
  }
  await page.goto(base+'/signup',{waitUntil:'networkidle'});
  report.registration=await page.locator('main').evaluate(e=>({text:e.innerText,inputs:[...e.querySelectorAll('input')].map(i=>({type:i.type,disabled:i.disabled})),buttons:[...e.querySelectorAll('button')].map(i=>({text:i.textContent,disabled:i.disabled}))}));
  await page.goto(base+'/features',{waitUntil:'networkidle'});
  await page.setViewportSize({width:804,height:900});
  const menu=page.getByRole('button',{name:'Открыть меню',exact:true});
  await menu.click();assert(await page.getByRole('navigation',{name:'Главная навигация'}).isVisible());
  await page.keyboard.press('Escape');assert(await menu.evaluate(e=>e===document.activeElement));
  report.checks.push({name:'804px menu opens, Escape restores focus',pass:true});
  await page.goto(base+'/faq',{waitUntil:'networkidle'});
  await page.getByRole('searchbox').fill('нет такого вопроса 178');assert.equal(await page.locator('details').count(),0);
  report.checks.push({name:'FAQ search empty state',pass:true});
  await page.goto(base+'/demo/recommendations',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Подробнее →',exact:true}).first().click();
  const dialog=page.getByRole('dialog');await dialog.waitFor();
  report.passportTabs=await dialog.getByRole('tab').allTextContents();
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
  report.checks.push({name:'Synthetic recommendation passport opens and closes',pass:true});
}catch(error){report.failures.push({fatal:error.message});}
finally{
  report.finished=new Date().toISOString();await fs.writeFile(`${out}/browser-results.json`,JSON.stringify(report,null,2));await browser.close();
}
console.log(JSON.stringify({pages:report.pages.length,guards:report.guards.length,failures:report.failures}));
assert.equal(report.failures.length,0);
