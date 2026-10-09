import type { MetadataRoute } from "next";
import { LEGAL_DOCS, SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date("2026-10-01");
  return [
    { url: SITE_URL, lastModified, changeFrequency: "monthly", priority: 1 },
    ...LEGAL_DOCS.map((d) => ({ url: `${SITE_URL}/legal/${d.slug}`, lastModified, changeFrequency: "yearly" as const, priority: 0.3 })),
  ];
}
