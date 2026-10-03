import type { Metadata } from "next";
import { Audit } from "@/components/dashboard/audit";

export const metadata: Metadata = { title: "Бесплатный аудит" };

export default function AuditPage() {
  return <Audit />;
}
