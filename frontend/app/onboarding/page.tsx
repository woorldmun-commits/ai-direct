import type { Metadata } from "next";
import { ClosedAccess } from "@/components/auth";

export const metadata: Metadata = {
  title: "Подключение рекламы",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <ClosedAccess />;
}
