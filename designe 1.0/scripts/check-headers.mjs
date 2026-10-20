#!/usr/bin/env node
// Security-header check against a real production server.
//
// Usage: npm run build && npm run test:headers
//
// 1. Starts `next start` on a free port (needs an existing `.next` build).
// 2. HTTP: checks the static security headers, the nonce-based CSP, that every executable
//    <script> carries the request's nonce, that nonces differ between requests, and the
//    retired routes → real workspace redirects, and account-route cache boundaries.
// 3. Browser (Playwright/Chromium, if installed): loads pages and fails on any CSP violation
//    or console error, and checks that nonced inline + bundled scripts actually run.
//    Set REQUIRE_BROWSER=1 to fail instead of skipping when Playwright is missing.
//    HTTP_ONLY=1 explicitly delegates browser verification to another runner; it
//    cannot be combined with REQUIRE_BROWSER=1.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LEGAL_PAGES = ["/legal", ...["privacy", "terms", "offer", "consents", "pd-consent", "marketing-consent", "cookies", "requisites"].map(slug => `/legal/${slug}`)];
const AUTH_PAGES=["/login","/signup","/verify-email","/forgot-password","/reset-password"];
const PAGES = ["/", ...AUTH_PAGES, ...LEGAL_PAGES];
const REDIRECTS = new Map([
  ["/onboarding", "/workspace"], ["/prisma-preview", "/"],
]);
const STATIC_HEADERS = {
  "strict-transport-security": "max-age=63072000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "x-frame-options": "DENY",
};
const failures = [];
const fail = (msg) => failures.push(msg);

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

async function waitForServer(base, child, timeoutMs = 60_000) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if (child.exitCode !== null) throw new Error(`next start exited with code ${child.exitCode}`);
    try {
      await fetch(base, { redirect: "manual" });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 300));
    }
  }
  throw new Error(`server did not start within ${timeoutMs} ms`);
}

function parseCsp(value) {
  const map = new Map();
  for (const part of value.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) map.set(name.toLowerCase(), sources);
  }
  return map;
}

function checkStatic(url, headers) {
  for (const [name, original] of Object.entries(STATIC_HEADERS)) {
    const expected=name==="referrer-policy"&&AUTH_PAGES.some(p=>new URL(url,"http://localhost").pathname===p)?"no-referrer":original;
    const got = headers.get(name);
    if (got !== expected) fail(`${url}: ${name} = ${JSON.stringify(got)}, expected ${JSON.stringify(expected)}`);
  }
  const pp = headers.get("permissions-policy") ?? "";
  for (const feature of ["camera=()", "microphone=()", "geolocation=()", "payment=()"]) {
    if (!pp.includes(feature)) fail(`${url}: Permissions-Policy lacks ${feature}`);
  }
  if (headers.has("x-powered-by")) fail(`${url}: X-Powered-By must not be sent`);
}

/** Returns the nonce of a page response after checking its CSP and scripts. */
function checkCsp(url, headers, html) {
  const raw = headers.get("content-security-policy");
  if (!raw) return fail(`${url}: no Content-Security-Policy`);
  const csp = parseCsp(raw);
  const media = csp.get("media-src") ?? [];
  const previewVideo = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4";
  if (media.join(" ") !== `'self' ${previewVideo}`) fail(`${url}: unexpected hero media allowlist`);
  const expect = (directive, source) => {
    if (!(csp.get(directive) ?? []).includes(source)) fail(`${url}: CSP ${directive} lacks ${source}`);
  };
  expect("default-src", "'self'");
  expect("object-src", "'none'");
  expect("base-uri", "'self'");
  expect("form-action", "'self'");
  expect("frame-ancestors", "'none'");
  expect("script-src", "'strict-dynamic'");
  const script = csp.get("script-src") ?? [];
  for (const banned of ["'unsafe-inline'", "'unsafe-eval'", "*", "data:", "http:", "https:"]) {
    if (script.includes(banned)) fail(`${url}: script-src must not contain ${banned}`);
  }
  if ((csp.get("style-src") ?? []).includes("'unsafe-inline'")) fail(`${url}: style-src must not contain 'unsafe-inline' in production`);
  const nonce = script.find((s) => s.startsWith("'nonce-"))?.slice(7, -1);
  if (!nonce || nonce.length < 16) return fail(`${url}: script-src has no usable nonce`);

  // Every executable script must carry this nonce; JSON data blocks are not executed and need none.
  const tags = html.match(/<script\b[^>]*>/gi) ?? [];
  let executable = 0;
  for (const tag of tags) {
    const type = /\btype="([^"]*)"/i.exec(tag)?.[1];
    if (type && type !== "module" && type !== "text/javascript") continue;
    executable++;
    if (!tag.includes(`nonce="${nonce}"`)) fail(`${url}: script without the request nonce: ${tag.slice(0, 120)}`);
  }
  if (executable === 0) fail(`${url}: no executable scripts found — page did not render?`);
  return nonce;
}

async function httpChecks(base) {
  const nonces = new Set();
  for (const p of PAGES) {
    const url = base + p;
    const res = await fetch(url, { redirect: "manual" });
    if (res.status !== 200) {
      fail(`${url}: status ${res.status}`);
      continue;
    }
    checkStatic(url, res.headers);
    const pageHtml = await res.text();
    const nonce = checkCsp(url, res.headers, pageHtml);
    if (LEGAL_PAGES.includes(p)) {
      const robots = pageHtml.match(/<meta\b[^>]*name="robots"[^>]*>/i)?.[0] ?? "";
      if (!robots.includes("noindex") || !robots.includes("nofollow")) fail(`${url}: legal draft must be noindex,nofollow`);
      if (!/требуют утверждения|Документ не утверждён|Утверждён · редакция/.test(pageHtml)) fail(`${url}: missing explicit document status`);
      if (pageHtml.includes("Утверждён · редакция") && !/SHA256: [a-f0-9]{64}/.test(pageHtml.replace(/<!--[\s\S]*?-->/g, ""))) fail(`${url}: published document lacks exact hash`);
      if (/\[ИП Фамилия|\[_{4,}|\[support@/.test(pageHtml)) fail(`${url}: fabricated requisites placeholder`);
    }
    if (p === "/login") {
      if (!/no-store/.test(res.headers.get("cache-control") ?? "")) fail(`${url}: account HTML must not be cached`);
      if (!pageHtml.includes('Войти через Яндекс ID')) fail(`${url}: real account entry missing`);
    }
    if (p === "/" && ["features", "how-it-works", "pricing"].some(id => !pageHtml.includes(`id="${id}"`))) fail(`${url}: reference landing sections missing`);
    if (nonce) nonces.add(nonce);
  }
  if (nonces.size !== PAGES.length) fail(`nonces must be unique per response, got ${nonces.size} for ${PAGES.length} pages`);

  const sitemap = await fetch(base + "/sitemap.xml");
  if (sitemap.status !== 200 || /<loc>[^<]*\/legal(?:\/|<)/.test(await sitemap.text())) fail("sitemap: legal drafts must be excluded");

  for (const [route, target] of REDIRECTS) {
    const redirect = await fetch(base + route, { redirect: "manual" });
    const location = redirect.headers.get("location") ?? "";
    if (![307, 308].includes(redirect.status) || new URL(location || "/invalid", base).href !== base + target) {
      fail(`${route}: expected redirect to ${target}, got ${redirect.status} ${location}`);
    }
    checkStatic(route, redirect.headers);
    if (!/no-store/.test(redirect.headers.get("cache-control") ?? "")) fail(`${route}: retired account route must not be cached`);
  }
  const anonymous = await fetch(base + "/workspace", { redirect: "manual" });
  if (anonymous.status !== 307 || new URL(anonymous.headers.get('location') || '/invalid', base).pathname !== '/login') fail('/workspace: anonymous visitor must redirect to /login before streaming');
  if (!/no-store/.test(anonymous.headers.get("cache-control") ?? "")) fail("/workspace: anonymous response must not be cached");
  const forged = await fetch(base + "/api/auth/logout", { method: "POST", headers: { Origin: "https://untrusted.example" }, redirect: "manual" });
  if (forged.status !== 403 || forged.headers.get("cache-control") !== "no-store") fail("auth: foreign-origin POST must fail closed without caching");

  for (const route of ['/demo', '/demo/recommendations', '/demo/reports', '/demo/settings', '/demo/ai']) {
    const retired = await fetch(base + route, {redirect:'manual'});
    if (retired.status !== 404) fail(`${route}: removed demo must return 404, got ${retired.status}`);
  }
  const html = await (await fetch(base + "/")).text();
  if (/href=["']\/demo(?:[\/"'?#])/.test(html) || html.includes('mc-demo-window')) fail('/: demo links or interactive demo remain');
  if (!html.includes('adpilot-laptop.png')) fail('/: retained product illustration is missing');
  const asset = /\/_next\/static\/[^"']+\.js/.exec(html)?.[0];
  if (!asset) fail("/: no /_next/static script found");
  else checkStatic(asset, (await fetch(base + asset)).headers);
}

function loadPlaywright() {
  const require = createRequire(path.join(ROOT, "package.json"));
  for (const name of ["playwright", "playwright-core"]) {
    try {
      return require(name);
    } catch {}
  }
  try {
    // Globally installed Playwright (e.g. npm i -g playwright in CI images).
    const globalRoot = path.join(path.dirname(process.execPath), "..", "lib", "node_modules");
    return createRequire(path.join(globalRoot, "noop.js"))("playwright");
  } catch {
    return null;
  }
}

async function browserChecks(base) {
  if (process.env.HTTP_ONLY === "1") {
    console.log("SKIP browser checks: HTTP_ONLY=1; browser evidence must be supplied separately.");
    return;
  }
  const pw = loadPlaywright();
  if (!pw) {
    const msg = "browser check: Playwright not found";
    if (process.env.REQUIRE_BROWSER === "1") fail(msg);
    else console.log(`SKIP ${msg} (set REQUIRE_BROWSER=1 to make this fatal)`);
    return;
  }
  const browser = await pw.chromium.launch(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {});
  try {
    for (const p of ["/", "/login"]) {
      const ctx = await browser.newContext();
      // Saved dark theme: proves the nonced inline theme script in <head> ran.
      await ctx.addInitScript(() => {
        try {
          localStorage.setItem("adpilot-theme", "dark");
        } catch {}
        window.__csp = [];
        document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
      });
      const page = await ctx.newPage();
      const errors = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(base + p, { waitUntil: "networkidle" });
      if (p === "/login") {
        // Exercise React state without contacting the identity provider.
        const boxes = page.getByRole("checkbox");
        if (await boxes.count()) {
          await boxes.first().check();
          if (!await page.getByRole("button", { name: /Войти через Яндекс ID/ }).isDisabled()) fail("/login: partial consent must disable submit");
          await boxes.first().uncheck();
        }
      }
      const violations = await page.evaluate(() => window.__csp);
      const theme = await page.evaluate(() => document.documentElement.dataset.theme);
      for (const v of violations) fail(`${p} (browser): CSP violation ${v}`);
      for (const e of errors) fail(`${p} (browser): console error ${e}`);
      if (theme !== "dark") fail(`${p} (browser): nonced theme script did not run`);
      console.log(`browser ${p}: ${violations.length} CSP violations, ${errors.length} console errors`);
      await ctx.close();
    }
    for (const width of [320, 1440]) {
      const ctx = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await ctx.newPage();
      for (const p of LEGAL_PAGES) {
        await page.goto(base + p, { waitUntil: "domcontentloaded" });
        await page.getByRole("heading", { level: 1 }).waitFor();
        if (!await page.getByRole("main").textContent().then(text => /требуют утверждения|Документ не утверждён|Утверждён · редакция/.test(text))) fail(`${p}: missing visible document status`);
        if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) fail(`${p}: overflow at ${width}px`);
        if (p !== "/legal" && !await page.getByRole("link", { name: "Правовая информация", exact: true }).count()) fail(`${p}: missing legal center navigation`);
      }
      console.log(`browser legal: ${LEGAL_PAGES.length} pages at ${width}px`);
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
}

async function main() {
  if (process.env.HTTP_ONLY === "1" && process.env.REQUIRE_BROWSER === "1") throw new Error("HTTP_ONLY=1 cannot satisfy REQUIRE_BROWSER=1");
  if (!existsSync(path.join(ROOT, ".next", "BUILD_ID"))) {
    console.error("No production build: run `npm run build` first.");
    process.exit(1);
  }
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const nextBin = path.join(ROOT, "node_modules", "next", "dist", "bin", "next");
  const child = spawn(process.execPath, [nextBin, "start", "-p", String(port), "-H", "127.0.0.1"], {
    cwd: ROOT,
    stdio: ["ignore", "ignore", "inherit"],
    env: { ...process.env, NODE_ENV: "production" },
  });
  try {
    await waitForServer(base, child);
    await httpChecks(base);
    await browserChecks(base);
  } finally {
    child.kill();
  }
  if (failures.length) {
    console.error(`FAIL test:headers (${failures.length})`);
    for (const f of failures) console.error(`  - ${f}`);
    process.exit(1);
  }
  console.log(`OK test:headers: ${PAGES.join(", ")} + ${REDIRECTS.size} retired-route redirects + anonymous workspace + auth origin + static asset`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
