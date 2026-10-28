import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const root=path.resolve(import.meta.dirname,'..'),out=path.resolve(root,'../docs/free-staging-2026-10-25');
const base='https://inrou-pilot.onrender.com';
const runtime=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {chromium}=createRequire(import.meta.url)(runtime);
const index=Object.values(JSON.parse(await fs.readFile(path.resolve(root,'../design-inrou/docs/SCREEN_INDEX.json'),'utf8'))).flat();
const privateRoute=route=>/^\/(app|workspace|onboarding)(\/|$)/.test(route);
const demos=['analysis','recommendations','campaigns','connections','impact','reports','alerts','ai','history','team','plans','settings','overview','business-profile'];
const legal=['terms','consents','offer','privacy','pd-consent','marketing-consent','cookies','requisites'];
const routes=[...new Set([...index.map(([,route])=>route).filter(route=>!privateRoute(route)),...demos.map(slug=>'/demo/'+slug),...legal.map(slug=>'/legal/'+slug)])];
const major=new Set(['/','/register','/login','/faq','/features','/pricing','/demo/analysis','/demo/recommendations','/demo/plans']);
const sizes=[[1440,900,'light'],[768,1024,'light'],[390,844,'light'],[320,568,'light'],[1440,900,'dark']];
await fs.mkdir(path.join(out,'screenshots'),{recursive:true});
const report={started:new Date().toISOString(),base,sourceCommit:'0dd5062327818f04a7f50af1ac4af2e761cd412c',scope:'Public and explicitly synthetic demo pages; anonymous private-route guards. Authenticated client workflow requires mail and approved legal configuration.',pages:[],protected:[],checks:[],failures:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  report.browser=browser.version();
  const ctx=await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
  await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
  await ctx.addInitScript(()=>localStorage.setItem('inrou-theme','system'));
  await ctx.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
  const health=await ctx.request.get(base+'/api/health');
  assert.equal(health.status(),200);assert.equal((await health.json()).status,'ok');
  const robots=await ctx.request.get(base+'/robots.txt');
  assert.match(await robots.text(),/Disallow: \//);assert.match(robots.headers()['x-robots-tag'],/noindex/);
  report.checks.push({name:'Live health and staging noindex',pass:true});
  const config=await ctx.request.get(base+'/api/auth/config');assert.equal(config.status(),200);
  const email=(await config.json()).email_enabled;
  report.registration={status:'not_completed',emailConfigured:email,reason:'Real verification email and approved legal texts are required; no confirmation bypass'};
  if(!email){
    const blocked=await ctx.request.post(base+'/api/auth/email/register',{headers:{Origin:base},data:{email:'staging-qa@example.invalid',password:'Synthetic staging password 604!',accepted:{offer:'2026-10-01',pd_consent:'2026-10-01'}}});
    assert([403,409,503].includes(blocked.status()));
    report.registration={...report.registration,status:'blocked_by_configuration',httpStatus:blocked.status(),code:(await blocked.json()).error?.code};
  }
  for(const [,route] of index.filter(([,route])=>privateRoute(route))){
    const response=await ctx.request.get(base+route,{maxRedirects:0});
    const location=response.headers().location;
    assert([302,303,307,308].includes(response.status()),route);
    assert.equal(new URL(location,base).pathname,'/login');
    assert.match(response.headers()['cache-control'],/no-store/);
    report.protected.push({route,status:response.status(),loginRedirect:true});
  }
  const privateApi=await ctx.request.get(base+'/api/workspaces/ws_1/subscription');assert.equal(privateApi.status(),401);
  report.checks.push({name:'Anonymous pages redirect to login; private API denies access',pass:true});
  const page=await ctx.newPage();
  for(const [i,route] of routes.entries()){
    const item={route,kind:route.startsWith('/demo')?'synthetic_demo':'public',sizes:[],screenshots:[],errors:[]};
    const onError=error=>item.errors.push(error.message);page.on('pageerror',onError);
    for(const [width,height,theme] of sizes){
      await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:theme});
      const response=await page.goto(base+route,{waitUntil:'networkidle',timeout:90000});
      await page.evaluate(()=>document.fonts.ready);
      const layout=await page.evaluate(()=>({h1:document.querySelector('h1')?.textContent,overflow:document.documentElement.scrollWidth>innerWidth+1,theme:document.documentElement.dataset.theme}));
      item.sizes.push({width,height,theme,status:response.status(),...layout});
      if(response.status()!==200||layout.overflow||!layout.h1||layout.theme!==theme||!response.headers()['x-robots-tag']?.includes('noindex'))report.failures.push({route,width,theme,status:response.status(),...layout});
      if(item.kind==='synthetic_demo')assert.match(await page.locator('body').innerText(),/демо|синтетич/i);
      if(width===1440||major.has(route)){
        const filename=`${String(i+1).padStart(2,'0')}-${width}-${theme}.png`;
        await page.screenshot({path:path.join(out,'screenshots',filename),animations:'disabled'});item.screenshots.push(filename);
      }
    }
    page.off('pageerror',onError);if(item.errors.length)report.failures.push({route,errors:item.errors});
    report.pages.push(item);console.log(`${i+1}/${routes.length} ${route}`);
  }
  report.screenshots=[];
  for(const filename of await fs.readdir(path.join(out,'screenshots')))report.screenshots.push({filename,sha256:createHash('sha256').update(await fs.readFile(path.join(out,'screenshots',filename))).digest('hex')});
}catch(error){report.failures.push({fatal:error.message});}
finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify(report,null,2));await browser.close();}
const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
await fs.writeFile(path.join(out,'gallery.html'),`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>INROU · cloud staging QA</title><style>body{font:14px system-ui;background:#f3eee7;color:#10283e;margin:24px}.shots{display:flex;gap:12px;overflow:auto}.shots img{width:440px;max-width:90vw}article{padding:24px 0;border-top:1px solid #ccc}</style><h1>INROU · снимки публичного тестового сервера</h1><p>Настоящий Render. Демо использует синтетические данные. Полная регистрация и приватный клиентский сценарий не подтверждены.</p>${report.pages.map(item=>`<article><h2>${escape(item.route)} · ${item.kind==='synthetic_demo'?'ДЕМО':'публичная страница'}</h2><div class="shots">${item.screenshots.map(file=>`<a href="screenshots/${file}"><img loading="lazy" src="screenshots/${file}" alt="${escape(item.route)}"></a>`).join('')}</div></article>`).join('')}</html>`);
console.log(`Cloud QA: ${report.pages.length} public/demo pages; ${report.protected.length} private guards; ${report.failures.length} failures`);
assert.equal(report.failures.length,0,JSON.stringify(report.failures));
