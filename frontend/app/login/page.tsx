import type { Metadata } from "next";
import { ClosedAccess } from "@/components/auth";

export const metadata: Metadata = {
  title: "Вход",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <ClosedAccess />;
}
