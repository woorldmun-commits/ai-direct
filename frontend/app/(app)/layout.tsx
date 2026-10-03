import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { AppStateProvider } from "@/components/layout/app-state";

export const metadata: Metadata = {
  title: { default: "Кабинет", template: "%s — AdPilot" },
  // The app shows demo data in development; keep it out of the index.
  robots: { index: false, follow: false },
};

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AppStateProvider>
      <AppShell>{children}</AppShell>
    </AppStateProvider>
  );
}
