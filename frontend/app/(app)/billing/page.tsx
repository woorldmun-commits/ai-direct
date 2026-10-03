import type { Metadata } from "next";
import { Billing } from "@/components/dashboard/billing";

export const metadata: Metadata = { title: "Тариф и оплата" };

export default function BillingPage() {
  return <Billing />;
}
