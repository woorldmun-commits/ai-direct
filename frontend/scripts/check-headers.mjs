#!/usr/bin/env node
// Security-header check against a real production server.
//
// Usage: npm run build && npm run test:headers
//
// 1. Starts `next start` on a free port (needs an existing `.next` build).
// 2. HTTP: checks the static security headers, the nonce-based CSP, that every executable
//    <script> carries the request's nonce, that nonces differ between requests, and the
//    /demo/ai → /demo redirect.
// 3. Browser (Playwright/Chromium, if installed): loads pages and fails on any CSP violation
//    or console error, and checks that nonced inline + bundled scripts actually run.
//    Set REQUIRE_BROWSER=1 to fail instead of skipping when Playwright is missing.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PAGES = ["/", "/demo", "/demo/recommendations", "/login"];
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
  for (const [name, expected] of Object.entries(STATIC_HEADERS)) {
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
    const nonce = checkCsp(url, res.headers, await res.text());
    if (nonce) nonces.add(nonce);
  }
  if (nonces.size !== PAGES.length) fail(`nonces must be unique per response, got ${nonces.size} for ${PAGES.length} pages`);

  const redirect = await fetch(`${base}/demo/ai`, { redirect: "manual" });
  const location = redirect.headers.get("location") ?? "";
  if (![301, 308].includes(redirect.status) || !location.endsWith("/demo")) {
    fail(`/demo/ai: expected permanent redirect to /demo, got ${redirect.status} ${location}`);
  }

  const html = await (await fetch(base + "/")).text();
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
  const pw = loadPlaywright();
  if (!pw) {
    const msg = "browser check: Playwright not found";
    if (process.env.REQUIRE_BROWSER === "1") fail(msg);
    else console.log(`SKIP ${msg} (set REQUIRE_BROWSER=1 to make this fatal)`);
    return;
  }
  const browser = await pw.chromium.launch();
  try {
    for (const p of ["/", "/demo"]) {
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
      if (p === "/demo") {
        // Proves bundled client JS hydrated: the evidence drawer only opens via React.
        await page.getByRole("button", { name: /Почему\?/ }).first().click();
        await page.getByRole("dialog", { name: "Почему AdPilot так решил" }).waitFor({ timeout: 5000 });
      }
      const violations = await page.evaluate(() => window.__csp);
      const theme = await page.evaluate(() => document.documentElement.dataset.theme);
      for (const v of violations) fail(`${p} (browser): CSP violation ${v}`);
      for (const e of errors) fail(`${p} (browser): console error ${e}`);
      if (theme !== "dark") fail(`${p} (browser): nonced theme script did not run`);
      console.log(`browser ${p}: ${violations.length} CSP violations, ${errors.length} console errors`);
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
}

async function main() {
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
  console.log(`OK test:headers: ${PAGES.join(", ")} + /demo/ai redirect + static asset`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
