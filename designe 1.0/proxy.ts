import { NextResponse, type NextRequest } from "next/server";
import {isPrivatePage} from "./lib/private-page";

/**
 * Per-request Content-Security-Policy with a nonce (see node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md).
 *
 * Why a nonce and not hashes: the App Router streams the RSC payload as many inline
 * `self.__next_f.push(...)` scripts whose content differs per page and per request, so a static
 * list of hashes cannot cover them, and 'unsafe-inline' would defeat the point of script-src.
 * Next.js reads the nonce from this request header and stamps it on its own scripts; the root
 * layout passes it to the theme script. JSON-LD (`application/ld+json`) is a data block, not
 * executed, so CSP does not apply to it. Cost: every page renders dynamically.
 *
 * Static headers (HSTS, nosniff, Referrer-Policy, X-Frame-Options, Permissions-Policy) live in
 * next.config.ts.
 */
function buildCsp(nonce: string, isDev: boolean, analytics: boolean): string {
  return [
    "default-src 'self'",
    // 'strict-dynamic': scripts loaded by trusted (nonced) scripts are trusted too; 'self' is ignored by CSP3 browsers.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // Dev injects <style> tags for HMR without a nonce.
    `style-src 'self' ${isDev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    // React renders style="" attributes (progress bars, chart sizes); nonces cannot cover attributes.
    // Inline style attributes cannot run script, so this is the usual accepted trade-off.
    "style-src-attr 'unsafe-inline'",
    `img-src 'self' blob: data:${analytics ? ' https://mc.yandex.ru' : ''}`,
    "font-src 'self'",
    `connect-src 'self'${analytics ? ' https://mc.yandex.ru' : ''}`,
    // Client navigation retains the document CSP when returning to the landing.
    "media-src 'self' https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260405_170732_8a9ccda6-5cff-4628-b164-059c500a2b41.mp4",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const analytics = /^[1-9]\d*$/.test(process.env.NEXT_PUBLIC_YM_ID || '') && !isPrivatePage(request.nextUrl.pathname);
  const csp = buildCsp(nonce, process.env.NODE_ENV === "development", analytics);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const cookieName = process.env.REKVERO_SESSION_COOKIE ?? process.env.ADPILOT_SESSION_COOKIE ?? 'session';
  const needsLogin = /^\/workspace(\/|$)/.test(request.nextUrl.pathname)
    && !/^[A-Za-z0-9_-]{32,128}$/.test(request.cookies.get(cookieName)?.value ?? '');
  const response = needsLogin
    ? NextResponse.redirect(new URL('/login', process.env.REKVERO_APP_ORIGIN || request.url))
    : NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  if(isPrivatePage(request.nextUrl.pathname)){response.headers.set("Referrer-Policy","no-referrer");response.headers.set("Cache-Control","no-store");}
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: static files, images and metadata files don't execute scripts.
      source: "/((?!api|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
