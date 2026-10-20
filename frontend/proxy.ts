import { NextResponse, type NextRequest } from "next/server";
import { buildCsp } from "./lib/csp";

/** A fresh nonce is forwarded to Next.js and the root layout on every page request. */
export function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const captchaEnabled = !!process.env.NEXT_PUBLIC_SMARTCAPTCHA_SITE_KEY?.startsWith("ysc1_") &&
    ["/login", "/signup"].includes(request.nextUrl.pathname);
  const csp = buildCsp(nonce, process.env.NODE_ENV === "development", captchaEnabled);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}
export const config = {
  matcher: [{
    source: "/((?!api|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml).*)",
    missing: [{ type: "header", key: "next-router-prefetch" }, { type: "header", key: "purpose", value: "prefetch" }],
  }],
};
