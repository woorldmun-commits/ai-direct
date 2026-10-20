import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

// Uses the installed desktop runtime; no dependency or browser download required.
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); }
catch { playwright = createRequire("C:/Users/woorl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json")("playwright"); }
const base = process.env.BASE_URL || "http://127.0.0.1:3110";
const output = path.resolve(process.env.SCREENSHOT_DIR || "artifacts/reference-check");
const browser = await playwright.chromium.launch({ headless: true, ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : { channel: "msedge" }) });
const context = await browser.newContext({ viewport: { width: 1536, height: 1024 }, reducedMotion: "reduce" });
const page = await context.newPage();
const errors = [];
page.on("pageerror", error => errors.push(error.message));
const routes = ["/", "/login", "/signup", "/demo", "/demo/recommendations", "/demo/changes", "/demo/integrations", "/demo/settings"];
const findings = [];
await mkdir(output, { recursive: true });

async function visit(route) {
  console.log("Checking", route);
  const response = await page.goto(base + route, { waitUntil: "networkidle" });
  assert(response && response.status() < 400, `${route} must load`);
  await page.locator("h1").first().waitFor();
  const consent = page.getByRole("button", { name: "Только необходимые", exact: true });
  if (await consent.isVisible()) await consent.click();
  const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: innerWidth }));
  assert(dimensions.scroll <= dimensions.viewport + 1, `${route} horizontal overflow: ${JSON.stringify(dimensions)}`);
  assert(!/Application error|Internal Server Error/.test(await page.locator("body").innerText()), `${route} error page`);
}

try {
  for (const route of routes) {
    await visit(route);
    const name = route === "/" ? "landing" : route.slice(1).replaceAll("/", "-");
    for (const preference of ["light", "dark"]) {
      await page.getByLabel("Тема", { exact: true }).selectOption(preference);
      await page.waitForFunction(value => document.documentElement.dataset.theme === value, preference, { polling: 100 });
      await page.screenshot({ path: path.join(output, `${name}-${preference}-1536.png`), fullPage: false });
    }
    findings.push({ route, title: await page.locator("h1").first().innerText(), desktop: "passed" });
  }
  for (const route of ["/login", "/signup"]) {
    await visit(route);
    assert.equal(await page.locator("input").count(), 0, "demo entry collects no credentials or contact details");
    await page.getByRole("link", { name: "Открыть демо", exact: true }).click();
    await page.waitForURL(base + "/demo");
  }
  await visit("/demo");
  const theme = page.getByLabel("Тема", { exact: true });
  await theme.selectOption("light");
  assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), "light", "light theme applies");
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await theme.inputValue(), "light", "theme persists on reload");
  await theme.selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark", undefined, { polling: 100 });
  await page.emulateMedia({ colorScheme: "light" });
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light", undefined, { polling: 100 });
  await theme.selectOption("dark");
  const sibling = await context.newPage();
  await sibling.goto(base + "/demo", { waitUntil: "networkidle" });
  await sibling.getByLabel("Тема", { exact: true }).selectOption("light");
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light", undefined, { polling: 100 });
  assert.equal(await theme.inputValue(), "light", "theme preference synchronizes across tabs");
  await sibling.close();
  await theme.selectOption("dark");
  await visit("/demo");
  for (const [label, route] of [["Рекомендации", "/demo/recommendations"], ["Эффект", "/demo/changes"], ["Подключения", "/demo/integrations"], ["Настройки", "/demo/settings"], ["Анализ", "/demo"]]) {
    await page.locator(`a[href="${route}"]`).first().click();
    await page.waitForURL(base + route);
    assert(await page.locator("h1").first().isVisible(), `${label} screen visible`);
  }
  await visit("/demo");
  assert.equal(await page.locator("main").evaluate(main => getComputedStyle(main).animationDuration), "0s", "reduced motion disables screen animation");
  const period = page.getByLabel("Период анализа");
  await period.selectOption("3");
  assert.equal(await period.inputValue(), "3", "analysis period switches");
  const metric = page.getByLabel("Показатель графика");
  await metric.selectOption("conversions");
  assert.equal(await metric.inputValue(), "conversions", "chart metric switches");
  await metric.selectOption("all");
  assert.match(await page.locator(".rc-chart-scale").innerText(), /Слева: расходы, ₽ · Справа: конверсии, шт\./);
  const point = page.locator('svg [role="button"]').first();
  await point.hover();
  assert(await page.getByRole("status").first().isVisible(), "chart hover shows tooltip");
  await point.focus();
  await point.press("Enter");
  assert(await page.getByRole("status").first().isVisible(), "chart supports keyboard selection");
  await point.press("ArrowRight");
  assert(await page.getByRole("status").first().isVisible(), "chart supports arrow navigation");
  await page.getByRole("button", { name: "VK", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Экспорт", exact: true }).click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), "rekvero-demo-campaigns.csv");
  const csv = await readFile(await download.path(), "utf8");
  assert(csv.includes("VK — Бренд") && !csv.includes("Поиск — Товары"), "export respects campaign filter");
  assert(csv.includes("Кампания") && csv.includes("CPA"), "export includes column names");
  await page.getByRole("button", { name: "Все", exact: true }).first().click();
  await visit("/demo/recommendations");
  await page.getByRole("button", { name: "Высокий приоритет", exact: true }).click();
  await page.getByRole("button", { name: "Все", exact: true }).click();
  assert.equal(await page.locator('.rc-disclosure[inert]').count(), 4, "closed recommendation controls are inert");
  await page.getByRole("button", { name: "Подробнее", exact: true }).first().click();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).first().click();
  assert(await page.locator("dialog").isVisible(), "recommendation confirmation opens dialog");
  await page.getByRole("button", { name: "Закрыть окно", exact: true }).focus();
  await page.keyboard.press("Tab");
  assert(await page.evaluate(() => document.querySelector("dialog")?.contains(document.activeElement)), "modal contains keyboard focus");
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await page.getByText(/Демо: Подтверждено/).waitFor();
  await page.getByRole("button", { name: "Отклонить", exact: true }).first().click();
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await page.getByText(/Демо: Отклонено/).waitFor();
  await page.getByRole("button", { name: "Отложить", exact: true }).first().click();
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await page.getByText(/Демо: Отложено/).waitFor();
  await visit("/demo/integrations");
  await page.getByRole("button", { name: "Подключить", exact: true }).first().click();
  assert(await page.locator("dialog").isVisible(), "connection opens honest demonstration dialog");
  await page.getByRole("button", { name: "Понятно", exact: true }).click();
  await page.getByRole("button", { name: "AI-ассистент", exact: true }).click();
  await page.getByLabel("Сообщение ассистенту").fill("Какие расходы за неделю?");
  await page.getByRole("button", { name: "Отправить сообщение", exact: true }).click();
  await page.getByText(/Демо-ответ/).waitFor();
  await page.keyboard.press("Escape");
  await page.locator("dialog").waitFor({ state: "hidden" });
  await visit("/demo/settings");
  const profileName = page.getByLabel("Имя", { exact: true });
  await profileName.fill("Тестовый профиль");
  await page.getByRole("button", { name: "Сохранить настройки", exact: true }).click();
  await page.getByText("Тестовый профиль", { exact: true }).first().waitFor();
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await profileName.inputValue(), "Тестовый профиль", "profile setting survives reload");
  await profileName.fill("Иван Петров");
  await page.getByRole("button", { name: "Сохранить настройки", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of routes) {
    await visit(route);
    const name = route === "/" ? "landing" : route.slice(1).replaceAll("/", "-");
    for (const preference of ["light", "dark"]) {
      await page.getByLabel("Тема", { exact: true }).selectOption(preference);
      await page.waitForFunction(value => document.documentElement.dataset.theme === value, preference, { polling: 100 });
      await page.screenshot({ path: path.join(output, `${name}-${preference}-390.png`), fullPage: false });
    }
    findings.find(item => item.route === route).mobile = "passed";
  }
  await visit("/");
  const primaryCta = page.getByRole("link", { name: /Открыть интерактивное демо/ }).first();
  await primaryCta.scrollIntoViewIfNeeded();
  assert(await primaryCta.evaluate(element => {
    const cta = element.getBoundingClientRect();
    return [...document.querySelectorAll(".ref-hero-floating")].every(card => {
      const box = card.getBoundingClientRect();
      return box.right <= cta.left || box.left >= cta.right || box.bottom <= cta.top || box.top >= cta.bottom;
    });
  }), "mobile floating cards do not overlap signup CTA");
  assert(await primaryCta.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return top === element || element.contains(top);
  }), "mobile signup CTA is unobscured and receives pointer events");
  await primaryCta.click();
  await page.waitForURL(base + "/demo");
  await visit("/");
  const demoCta = page.getByRole("link", { name: /Смотреть как это работает/ }).first();
  await demoCta.scrollIntoViewIfNeeded();
  assert(await demoCta.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return top === element || element.contains(top);
  }), "mobile demo CTA is unobscured and receives pointer events");
  await demoCta.click();
  await page.waitForURL(base + "/#features");
  for (const width of [320, 375, 768, 1024]) {
    await page.setViewportSize({ width, height: 1024 });
    await visit("/");
    for (const label of [/Открыть интерактивное демо/, /Смотреть как это работает/]) {
      const cta = page.getByRole("link", { name: label }).first();
      await cta.scrollIntoViewIfNeeded();
      assert(await cta.evaluate(element => {
        const rect = element.getBoundingClientRect();
        const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        return top === element || element.contains(top);
      }), `${width}px landing CTA is unobscured`);
    }
  }
  assert.deepEqual(errors, [], "browser runtime errors");
  const motionContext = await browser.newContext({ viewport: { width: 1536, height: 1024 }, reducedMotion: "no-preference" });
  const motionPage = await motionContext.newPage();
  await motionPage.goto(base + "/demo", { waitUntil: "networkidle" });
  const animation = await motionPage.locator("main").evaluate(main => getComputedStyle(main).animationDuration);
  assert(animation !== "0s", "screen appearance animates when motion is allowed");
  await motionPage.locator("main").evaluate(main => {
    window.referenceScreen = main;
    window.referenceAnimationCount = 0;
    main.addEventListener("animationstart", event => { if (event.target === main) window.referenceAnimationCount++; });
  });
  await motionPage.getByLabel("Период анализа").selectOption("3");
  await motionPage.getByLabel("Показатель графика").selectOption("spend");
  assert(await motionPage.locator("main").evaluate(main => main === window.referenceScreen && window.referenceAnimationCount === 0), "filters preserve screen without restarting animation");
  await motionContext.close();
  await writeFile(path.join(output, "results.json"), JSON.stringify({ base, findings, errors }, null, 2));
  console.log(`Reference checks passed: ${routes.length} routes, desktop/mobile, navigation, honest demo entry, light/dark/system themes, no runtime errors. Screenshots: ${output}`);
} catch (error) {
  await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
  await writeFile(path.join(output, "failure.txt"), await page.locator("body").innerText());
  throw error;
} finally { await browser.close(); }
