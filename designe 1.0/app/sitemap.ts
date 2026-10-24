import type { MetadataRoute } from "next";
import { SITE_URL, PUBLIC_SITE_CONFIGURED } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  if (!PUBLIC_SITE_CONFIGURED) return [];
  const lastModified = new Date("2026-10-19");
  return [
    { url: SITE_URL, lastModified, changeFrequency: "monthly", priority: 1 },
    ...["features","how-it-works","agencies","business","integrations","pricing","security","faq","contact","about"].map(slug=>({url:SITE_URL+"/"+slug,lastModified,changeFrequency:"monthly" as const,priority:0.7})),
  ];
}
