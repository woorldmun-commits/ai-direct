import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// /demo is not disallowed on purpose: crawlers must see its meta noindex.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/api/"] },
    ...(SITE_URL && { sitemap: `${SITE_URL}/sitemap.xml` }),
  };
}
