import type { Metadata } from "next";
import { Clients } from "@/components/dashboard/clients";

export const metadata: Metadata = { title: "Клиенты" };

export default function ClientsPage() {
  return <Clients />;
}
