import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire('C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {chromium}=require('playwright');
const base=process.env.BASE_URL||'http://127.0.0.1:3117',out=process.env.OUTPUT_DIR||'artifacts/inrou/premium';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true}),passed=[],errors=[];
try {
 const ctx=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
 await ctx.addCookies([{name:'inrou-consent',value:'v1:necessary',url:base}]);
 const page=await ctx.newPage();
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base,{waitUntil:'networkidle'});
 const login=page.getByRole('link',{name:'Войти',exact:true});
 await login.focus();await page.keyboard.press('Escape');
 assert(await login.evaluate(e=>e===document.activeElement),'Escape must not steal focus when menu is closed');
 await page.locator('.ap-skip-link').focus();await page.keyboard.press('Enter');
 assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
 passed.push('Landing Escape preserves unrelated focus; skip link reaches main');
 const trigger=page.getByRole('button',{name:'Открыть меню',exact:true});
 await trigger.click();await page.getByRole('navigation',{name:'Главная навигация'}).getByRole('link',{name:'Возможности'}).focus();
 await page.keyboard.press('Escape');assert.equal(await trigger.getAttribute('aria-expanded'),'false');
 assert(await trigger.evaluate(e=>e===document.activeElement));
 await trigger.click();await page.locator('.ap-hero-copy>p').click();assert.equal(await trigger.getAttribute('aria-expanded'),'false');
 await trigger.click();await page.setViewportSize({width:1280,height:1024});
 await page.waitForFunction(()=>document.querySelector('.ap-landing-menu').getAttribute('aria-expanded')==='false');
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.locator('#landing-nav').isVisible(),false);
 passed.push('Landing disclosure: Escape, outside pointer, resize and closed mobile navigation');
 await page.getByRole('button',{name:'AI-аналитика 24/7'}).click();
 const dialog=page.getByRole('dialog');await dialog.waitFor();
 assert.equal(await dialog.evaluate(e=>getComputedStyle(e).animationName),'none');
 await page.keyboard.press('Escape');assert.equal(await dialog.count(),0);
 passed.push('Reduced motion disables dialog entrance; Escape closes dialog');
 await page.setViewportSize({width:320,height:844});
 await page.goto(base+'/demo',{waitUntil:'networkidle'});
 const geometry=await page.locator('.ap-dynamics .ap-chart').evaluate(e=>({
  font:Math.min(...[...e.querySelectorAll('text')].map(t=>parseFloat(getComputedStyle(t).fontSize)*t.getScreenCTM().a)),
  overflow:document.documentElement.scrollWidth>innerWidth+1,
  captions:[...document.querySelectorAll('.ap-metric')].map(card=>({bottom:card.querySelector('small').getBoundingClientRect().bottom,spark:card.querySelector('.ap-spark').getBoundingClientRect().top}))
 }));
 assert(geometry.font>=10,'Mobile SVG axes must render at least 10px');
 assert(!geometry.overflow);
 assert(geometry.captions.every(c=>c.bottom<=c.spark),'KPI caption must not overlap sparkline');
 passed.push('320px: readable chart axes and KPI captions clear of sparklines');
 await page.goto(base+'/demo/campaigns',{waitUntil:'networkidle'});
 assert.equal(await page.locator('.ap-name-cell strong').first().innerText(),'Поиск | Бренд');
 await page.getByLabel('Поиск кампаний',{exact:true}).fill('Бренд');
 await page.getByLabel('Поиск кампаний',{exact:true}).blur();
 assert.equal(await page.locator('.ap-table tbody tr').count(),1);
 assert.equal(await page.getByLabel('Поиск кампаний',{exact:true}).inputValue(),'Бренд');
 await page.goto(base+'/demo',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Квартал',exact:true}).click();
 assert.match(await page.getByRole('status').last().innerText(),/дополнительные данные/);
 assert.equal(await page.getByRole('button',{name:'Месяц',exact:true}).getAttribute('aria-pressed'),'true');
 passed.push('Reference controls: initial campaign order, persistent search and quarter data boundary');
 assert.deepEqual(errors,[]);
 console.log('PASS',passed);
 await writeFile(out+'/polish-checks.json',JSON.stringify({passed,errors},null,2));
} finally {await browser.close();}
