import type { Metadata } from "next";
import { Analytics } from "@/components/dashboard/analytics";

export const metadata: Metadata = { title: "Аналитика" };

export default function AnalyticsPage() {
  return <Analytics />;
}
