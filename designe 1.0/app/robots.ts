import type { MetadataRoute } from "next";
import { SITE_URL, PUBLIC_SITE_CONFIGURED } from "@/lib/site";

// Public auth routes stay crawlable so crawlers can read their noindex directives.
export default function robots(): MetadataRoute.Robots {
  if (process.env.INROU_STAGING === '1') return {rules:{userAgent:'*',disallow:'/'}};
  return {
    rules: PUBLIC_SITE_CONFIGURED ? { userAgent: "*", allow: "/", disallow: ["/api/"] } : { userAgent: "*", disallow: "/" },
    ...(PUBLIC_SITE_CONFIGURED ? { sitemap: `${SITE_URL}/sitemap.xml` } : {}),
  };
}
