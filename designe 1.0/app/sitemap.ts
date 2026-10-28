import type { MetadataRoute } from "next";
import { SITE_URL, PUBLIC_SITE_CONFIGURED } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  if (!PUBLIC_SITE_CONFIGURED) return [];
  return [
    { url: SITE_URL, changeFrequency: "monthly", priority: 1 },
    ...["features","how-it-works","agencies","business","integrations","pricing","security","faq","contact","about","methodology","methodology/zero-conversions","methodology/high-cpa","methodology/placements"].map(slug=>({url:SITE_URL+"/"+slug,changeFrequency:"monthly" as const,priority:0.7})),
  ];
}
