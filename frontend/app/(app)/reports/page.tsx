import type { Metadata } from "next";
import { Reports } from "@/components/dashboard/reports";

export const metadata: Metadata = { title: "Отчёты" };

export default function ReportsPage() {
  return <Reports />;
}
