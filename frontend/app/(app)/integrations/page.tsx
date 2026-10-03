import type { Metadata } from "next";
import { Integrations } from "@/components/dashboard/integrations";

export const metadata: Metadata = { title: "Интеграции" };

export default function IntegrationsPage() {
  return <Integrations />;
}
