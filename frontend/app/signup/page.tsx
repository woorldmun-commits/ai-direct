import type { Metadata } from "next";
import { ClosedAccess } from "@/components/auth";

export const metadata: Metadata = {
  title: "Регистрация",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <ClosedAccess />;
}
