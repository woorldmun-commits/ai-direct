import type { NextConfig } from "next";

// The demo moved from /demo/* to the app routes; registration moved to /register.
const MOVED: [string, string][] = [
  ["/demo", "/today"],
  ["/demo/recommendations", "/recommendations"],
  ["/demo/analytics", "/analytics"],
  ["/demo/settings", "/settings"],
  ["/demo/history", "/history"],
  ["/demo/integrations", "/integrations"],
  ["/demo/ai", "/assistant"],
  ["/demo/:path*", "/today"],
  ["/signup", "/register"],
];

const nextConfig: NextConfig = {
  async redirects() {
    return MOVED.map(([source, destination]) => ({ source, destination, permanent: true }));
  },
};

export default nextConfig;
