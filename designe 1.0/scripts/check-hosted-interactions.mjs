import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
const root=path.resolve(import.meta.dirname,'..'),out=path.resolve(root,'../docs/free-staging-2026-10-25');
const base='https://inrou-pilot.onrender.com';
const {chromium}=createRequire(import.meta.url)(path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'));
const report={started:new Date().toISOString(),checks:[],failures:[]};
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  const ctx=await browser.newContext({locale:'ru-RU',colorScheme:'light',reducedMotion:'reduce',viewport:{width:1440,height:900}});
  await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
  await ctx.addInitScript(()=>localStorage.setItem('inrou-theme','system'));
  await ctx.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  const page=await ctx.newPage();page.on('pageerror',e=>report.failures.push({error:e.message}));
  const check=async(name,fn)=>{try{await fn();report.checks.push({name,pass:true});}catch(e){report.failures.push({name,error:e.message});}};
  await check('Registration submit disabled while email is unconfigured',async()=>{
    await page.goto(base+'/register',{waitUntil:'networkidle'});
    assert.equal((await (await ctx.request.get(base+'/api/auth/config')).json()).email_enabled,false);
    assert(await page.locator('.ref-email-form .ref-auth-submit').isDisabled());
  });
  await check('FAQ search, keyboard accordion and empty result',async()=>{
    await page.goto(base+'/faq',{waitUntil:'networkidle'});
    await page.getByRole('searchbox').fill('площадки');assert.equal(await page.locator('details').count(),1);
    await page.locator('summary').focus();await page.keyboard.press('Enter');assert.equal(await page.locator('details[open]').count(),1);
    await page.getByRole('searchbox').fill('нет такого вопроса 178');assert.equal(await page.locator('details').count(),0);
  });
  await check('Demo passport five tabs and Escape',async()=>{
    await page.goto(base+'/demo/recommendations',{waitUntil:'networkidle'});
    await page.getByRole('button',{name:'Подробнее →',exact:true}).first().click();
    const dialog=page.getByRole('dialog');await dialog.waitFor();
    assert.deepEqual(await dialog.getByRole('tab').allTextContents(),['Обзор','Данные','Расчёты','Риски','История']);
    await dialog.getByRole('tab',{name:'История',exact:true}).click();
    assert.equal(await dialog.getByRole('tab',{name:'История',exact:true}).getAttribute('aria-selected'),'true');
    await page.screenshot({path:path.join(out,'passport-cloud.png')});
    await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
  });
  await check('Demo chart keyboard tooltip and theme switch',async()=>{
    await page.goto(base+'/demo/analysis',{waitUntil:'networkidle'});
    await page.locator('.ix-hit').first().focus();await page.locator('.ix-tooltip').first().waitFor();
    await page.keyboard.press('ArrowRight');assert(await page.locator('.ix-tooltip').first().isVisible());
    await page.keyboard.press('Escape');assert.equal(await page.locator('.ix-tooltip').count(),0);
    for(const theme of ['light','dark','system']){
      await page.locator('.ix-top button').filter({hasText:'Тема'}).click();
      await page.waitForFunction(theme=>localStorage.getItem('inrou-theme')===theme&&document.documentElement.dataset.theme===(theme==='system'?'light':theme),theme);
    }
  });
  await check('Mobile demo notice, focus trap and restored focus',async()=>{
    await page.setViewportSize({width:320,height:568});await page.goto(base+'/demo/analysis',{waitUntil:'networkidle'});
    assert(await page.getByText('Демо-кабинет · синтетические данные. Это пример интерфейса, не данные вашего Директа.',{exact:true}).isVisible());
    const opener=page.locator('.ix-top button[aria-label="Открыть меню"]');await opener.click();
    assert(await page.locator('main').evaluate(e=>e.inert));
    for(let i=0;i<20;i++)await page.keyboard.press('Tab');
    assert(await page.locator('#ix-sidebar').evaluate(e=>e.contains(document.activeElement)));
    await page.keyboard.press('Escape');assert(await opener.evaluate(e=>e===document.activeElement));
    await page.screenshot({path:path.join(out,'demo-mobile-cloud.png')});
  });
}finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'interaction-results.json'),JSON.stringify(report,null,2));await browser.close();}
console.log(`Cloud interactions: ${report.checks.length} PASS; ${report.failures.length} failures`);
assert.equal(report.failures.length,0,JSON.stringify(report.failures));
