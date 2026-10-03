import type { Metadata } from "next";
import { History } from "@/components/recommendations/history";

export const metadata: Metadata = { title: "История решений" };

export default function HistoryPage() {
  return <History />;
}
