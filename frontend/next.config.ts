import type { NextConfig } from "next";

// Static security headers for every response. The Content-Security-Policy needs a fresh nonce
// per request, so it is set in proxy.ts (frame-ancestors 'none' there backs up X-Frame-Options).
// Checked by `npm run test:headers` (scripts/check-headers.mjs).
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async redirects() {
    // v1.0 has no general AI chat; the old page points back to the dashboard.
    return [{ source: "/demo/ai", destination: "/demo", permanent: true }];
  },
};

export default nextConfig;
