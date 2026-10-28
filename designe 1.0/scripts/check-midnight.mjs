import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, '../artifacts/screenshots/midnight-r2');
const base = 'http://127.0.0.1:3144';
const runtime = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const require = createRequire(path.join(runtime, 'package.json'));
const {chromium} = require(runtime);
await fs.mkdir(out, {recursive:true});
const report = {time:new Date().toISOString(), scope:'M2 R2 corrected reference preview only', ownerApproval:false, synthetic:true, viewports:[], interactions:[], failures:[], screenshots:[], consoleErrors:[], pageErrors:[]};
report.buildId = (await fs.readFile(path.join(root,'.next/BUILD_ID'),'utf8')).trim();
report.sourceHashes = {};
for(const file of ['components/midnight/preview.tsx','components/midnight/chart.tsx','components/midnight/midnight.css','components/midnight/reference.css','public/reference/midnight-sapphire-scene-r2.png','components/ix/demo-data.ts','app/demo/midnight/[screen]/page.tsx','app/demo/layout.tsx','components/ix/detail-tabs.tsx','components/ix/use-dialog.ts','components/ix/geometry.ts','lib/theme.ts','public/fonts/Prata-Regular.ttf','scripts/check-midnight.mjs'])report.sourceHashes[file]=createHash('sha256').update(await fs.readFile(path.join(root,file))).digest('hex');
const browser = await chromium.launch({channel:'msedge',headless:true});
report.browser = browser.version();
const context = await browser.newContext({locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce',deviceScaleFactor:1});
await context.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
await context.route('**/*', route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
const page = await context.newPage();
await page.goto(base+'/demo/midnight/landing',{waitUntil:'networkidle'});
page.on('pageerror', e=>report.pageErrors.push(e.message));
page.on('console', m=>{if(m.type()==='error')report.consoleErrors.push(m.text());});
async function capture(name, fullPage=false, target=page, selector=null) {
  const bytes=selector?await target.locator(selector).screenshot({path:path.join(out,name+'.png'),animations:'disabled'}):await target.screenshot({path:path.join(out,name+'.png'),fullPage,animations:'disabled'});
  report.screenshots.push({name:name+'.png',sha256:createHash('sha256').update(bytes).digest('hex'),fullPage});
}
async function check(name,fn){try{await fn();report.interactions.push({name,pass:true});}catch(e){report.failures.push({name,error:e.message});}}
try {
  for (const width of [1440,1536,768,390,320]) for (const theme of ['light','dark']) for (const screen of ['landing','overview','recommendation']) {
    const height=width===390?844:width===320?568:width===768?1024:width===1536?960:900;
    await page.setViewportSize({width,height});
    await page.evaluate(theme=>localStorage.setItem('inrou-theme',theme),theme);
    const response=await page.goto(base+'/demo/midnight/'+screen,{waitUntil:'networkidle'});
    assert.equal(response.status(),200);
    await page.evaluate(()=>document.fonts.ready);
    await page.locator('.ms-root').waitFor();
    const geometry=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,theme:document.documentElement.dataset.theme,font:getComputedStyle(document.querySelector('h1')).fontFamily,h1:document.querySelector('h1')?.getBoundingClientRect().toJSON(),sidebar:document.querySelector('.ms-sidebar')?.getBoundingClientRect().toJSON(),chart:document.querySelector('.ms-plot')?.getBoundingClientRect().toJSON(),canvas:getComputedStyle(document.querySelector('.ms-root')).backgroundColor}));
    assert.equal(geometry.theme,theme,'Theme must match the screenshot filename');
    report.viewports.push({screen,width,height,requestedTheme:theme,...geometry});
    if(geometry.scrollWidth>width)report.failures.push({name:`overflow ${screen} ${width} ${theme}`,error:String(geometry.scrollWidth)});
    const slug=`${screen}-${width}x${height}-${theme}`;
    await capture(slug);
    if([1440,390].includes(width))await capture(slug+'-full',true);
    if(width===1440&&screen==='landing')await capture(`landing-master-${theme}`,false,page,'.ms-landing-master');
    if(width===1440&&screen==='recommendation')await capture(`recommendation-document-${theme}`,false,page,'.ms-app-content');
    if(width<768&&screen==='overview')assert.equal(await page.locator('.ms-chart-tooltip').count(),0,'Mobile chart starts unobscured');
    if(width<768&&screen==='landing'){
      const cta=await page.locator('.ms-hero-copy>.ms-cta-row').boundingBox();
      const truth=await page.locator('.ms-truth').boundingBox();
      assert(truth.y>=cta.y+cta.height,'Disclaimer must follow both mobile buttons');
    }
  }
  for(const width of [1440,390])for(const theme of ['light','dark']){
    await page.setViewportSize({width,height:width===390?844:900});
    await page.evaluate(theme=>localStorage.setItem('inrou-theme',theme),theme);
    await page.goto(base+'/demo/midnight/overview',{waitUntil:'networkidle'});
    await page.getByRole('button',{name:'7 октября, показать расходы'}).click();
    await capture(`overview-${width}-${theme}-tooltip`);
    await page.goto(base+'/demo/midnight/recommendation',{waitUntil:'networkidle'});
    await page.getByRole('tab',{name:'Доказательства',exact:true}).click();
    await capture(`recommendation-${width}-${theme}-evidence`,true);
    await page.getByRole('button',{name:'Одобрить',exact:true}).click();
    await capture(`recommendation-${width}-${theme}-confirm`);
  }
  await page.setViewportSize({width:1440,height:900});
  await page.evaluate(()=>localStorage.setItem('inrou-theme','light'));
  for(const [screen,route]of [['landing','/'],['overview','/demo/overview'],['recommendation-list','/demo/recommendations']]){
    await page.goto(base+route,{waitUntil:'networkidle'});await page.evaluate(()=>document.fonts.ready);await capture(`existing-${screen}-1440-light`,true);
  }
  await page.goto(base+'/demo/midnight/overview',{waitUntil:'networkidle'});
  await check('Four same-unit series, legend and keyboard tooltip',async()=>{
    const point=page.getByRole('button',{name:'7 октября, показать расходы'});
    await point.focus();
    await page.getByRole('status').filter({hasText:'7 октября 2026'}).waitFor();
    await capture('overview-desktop-tooltip');
    await page.keyboard.press('ArrowRight');
    await page.getByRole('status').filter({hasText:'8 октября 2026'}).waitFor();
    await page.getByRole('button',{name:'Поиск · бренд',exact:true}).click();
    assert.equal(await page.getByRole('button',{name:'Поиск · бренд',exact:true}).getAttribute('aria-pressed'),'false');
    await page.getByRole('button',{name:'8 октября, показать расходы'}).focus();
    assert.equal(await page.locator('.ms-chart-tooltip').getByText('Поиск · бренд',{exact:true}).count(),0);
  });
  await check('Grouping preserves synthetic totals',async()=>{
    await page.getByRole('button',{name:'Таблица данных'}).click();
    const total=()=>page.locator('tbody tr').evaluateAll(rows=>rows.reduce((sum,row)=>sum+Number(row.cells[1].textContent),0));
    const before=await total();
    await page.getByRole('button',{name:'Недели',exact:true}).click();
    assert.equal(await total(),before);
    assert.equal(await page.locator('tbody tr').count(),2);
    await page.getByRole('button',{name:'Месяцы',exact:true}).click();
    assert.equal(await total(),before);
    assert.equal(await page.locator('tbody tr').count(),1);
  });
  await page.goto(base+'/demo/midnight/recommendation',{waitUntil:'networkidle'});
  await check('Six accessible recommendation tabs',async()=>{
    for(const title of ['Обзор','Доказательства','Расчёты','Риски','План действий','История']) {
      await page.getByRole('tab',{name:title,exact:true}).click();
      assert.equal(await page.getByRole('tabpanel').count(),1);
      assert.equal(await page.getByRole('tab',{name:title,exact:true}).getAttribute('aria-selected'),'true');
    }
    await page.getByRole('tab',{name:'Обзор',exact:true}).focus();await page.keyboard.press('ArrowRight');
    assert.equal(await page.getByRole('tab',{name:'Доказательства',exact:true}).getAttribute('aria-selected'),'true');
    await capture('recommendation-desktop-evidence');
  });
  await check('Confirmation focus trap, Escape and truthful preview feedback',async()=>{
    const trigger=page.getByRole('button',{name:'Одобрить',exact:true});
    await trigger.click();
    const dialog=page.getByRole('dialog');await dialog.waitFor();
    assert(await dialog.getByText('Это не изменит рекламную кампанию автоматически.',{exact:true}).count());
    await capture('recommendation-desktop-confirm');
    await page.keyboard.press('Shift+Tab');
    assert(await dialog.evaluate(d=>d.contains(document.activeElement)));
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('dialog').count(),0);
    assert(await trigger.evaluate(b=>b===document.activeElement));
    await trigger.click();await page.getByRole('button',{name:'Завершить просмотр'}).click();
    await page.getByRole('status').filter({hasText:'Решение не сохранено'}).waitFor();
  });
  await check('Theme persists across reload and supports system',async()=>{
    await page.getByRole('combobox',{name:'Тема',exact:true}).selectOption('dark');
    await page.reload({waitUntil:'networkidle'});
    assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    await page.emulateMedia({colorScheme:'light'});
    await page.getByRole('combobox',{name:'Тема',exact:true}).selectOption('system');
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    await page.emulateMedia({colorScheme:'dark'});
    await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
    assert.equal(await page.getByRole('combobox',{name:'Тема',exact:true}).inputValue(),'system');
  });
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'/demo/midnight/landing',{waitUntil:'networkidle'});
  await check('Mobile public menu and focus restore',async()=>{
    await page.getByRole('button',{name:'Открыть меню'}).click();await page.getByRole('dialog').waitFor();
    await capture('landing-mobile-menu');await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
  });
  await page.goto(base+'/demo/midnight/overview',{waitUntil:'networkidle'});
  await check('Mobile pointer tooltip and navigation sheet',async()=>{
    await page.getByRole('button',{name:'7 октября, показать расходы'}).click();
    await page.locator('.ms-chart-tooltip').waitFor();await capture('overview-mobile-tooltip');
    const box=await page.locator('.ms-chart-tooltip').boundingBox();assert(box.x>=0&&box.x+box.width<=390);
    await page.getByRole('button',{name:'Ещё',exact:true}).click();await page.getByRole('dialog').waitFor();await capture('overview-mobile-more');await page.keyboard.press('Escape');
  });
  await page.goto(base+'/demo/midnight/recommendation',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Одобрить',exact:true}).click();await capture('recommendation-mobile-confirm');await page.keyboard.press('Escape');
  await check('Mobile detail findings can scroll clear of fixed navigation',async()=>{
    await page.locator('.ms-detail-disclaimer').scrollIntoViewIfNeeded();
    await page.evaluate(()=>scrollBy(0,180));
    const finding=await page.locator('.ms-check-list:visible').boundingBox();
    const nav=await page.locator('.ms-bottom-nav').boundingBox();
    const action=await page.locator('.ms-actionbar').boundingBox();
    assert(finding.y+finding.height<=Math.min(nav.y,action.y),'All findings above the action/navigation panels');
    await capture('recommendation-mobile-scrolled-findings');
  });
  await check('Reduced motion disables preview animation',async()=>{
    const active=await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length);
    assert.equal(active,0);
  });
  await page.setViewportSize({width:1440,height:900});
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto(base+'/demo/midnight/landing',{waitUntil:'domcontentloaded'});
  await check('Reference hero uses physical artwork and editable projected interface',async()=>{
    assert.match(await page.locator('.ms-landing-master').evaluate(el=>getComputedStyle(el).backgroundImage),/midnight-sapphire-scene-r2/);
    assert.equal(await page.locator('.ms-device-ui .ms-series').count(),4);
    const repeating=await page.evaluate(()=>document.getAnimations().filter(a=>a.effect?.getTiming().iterations===Infinity).length);
    assert.equal(repeating,0);
  });
  await page.goto(base+'/demo/midnight/recommendation',{waitUntil:'networkidle'});
  await check('CPA chart exposes the same illustrative values in table and tooltip',async()=>{
    await page.getByRole('button',{name:'Таблица данных'}).click();
    assert.equal(await page.locator('tbody tr').count(),14);
    assert.equal(await page.locator('tbody tr').first().locator('td').first().textContent(),'900');
    assert.equal(await page.locator('tbody tr').last().locator('td').first().textContent(),'6000');
    await page.getByRole('button',{name:'14 октября, показать CPA'}).focus();
    await page.locator('.ms-chart-tooltip').waitFor();
    assert.match(await page.locator('.ms-chart-tooltip').textContent(),/6\s*000/);
    assert.match(await page.locator('.ms-chart-tooltip').textContent(),/Синтетические данные/);
  });
  await check('True touch context can tap a chart point',async()=>{
    const touch=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,isMobile:true,locale:'ru-RU',timezoneId:'Europe/Moscow',reducedMotion:'reduce'});
    try{
      await touch.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
      const tp=await touch.newPage();await tp.goto(base+'/demo/midnight/overview',{waitUntil:'networkidle'});
      await tp.getByRole('button',{name:'7 октября, показать расходы'}).tap();
      await tp.locator('.ms-chart-tooltip').waitFor();
      const box=await tp.locator('.ms-chart-tooltip').boundingBox();assert(box.x>=0&&box.x+box.width<=390);
      await capture('overview-390-touch-tooltip',false,tp);
    }finally{await touch.close();}
  });
  await check('Preview returns 404 when INROU_DEMO is disabled',async()=>{
    const gated=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3142'],{cwd:root,env:{...process.env,INROU_DEMO:'0'},stdio:'ignore',windowsHide:true});
    try{
      let status=0;
      for(let i=0;i<60;i++){
        assert.equal(gated.exitCode,null,'Isolated gate server must be running');
        try{status=(await fetch('http://127.0.0.1:3142/demo/midnight/overview')).status;}catch{}
        if(status)break;await new Promise(r=>setTimeout(r,250));
      }
      assert.equal(status,404);
    }finally{gated.kill();}
  });
  assert.equal(report.consoleErrors.length,0,'Browser page errors');
  assert.equal(report.pageErrors.length,0,'Uncaught page errors');
}catch(e){report.failures.push({name:'capture runtime',error:e.stack});}
finally{await browser.close();await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({screenshots:report.screenshots.length,viewports:report.viewports.length,interactions:report.interactions.length,failures:report.failures,consoleErrors:report.consoleErrors},null,2));
if(report.failures.length)process.exitCode=1;
