import type { Metadata } from "next";
import { Shell } from "@/components/app/shell";
import { DemoProvider } from "@/components/app/store";

export const metadata: Metadata = {
  title: "Демо — пример дашборда Яндекс Директ",
  description: "Посмотрите, как AdPilot показывает потери бюджета и рекомендации. Демо-данные, регистрация не нужна.",
  // Demo data is thin, duplicate-ish content: keep it out of the index but crawlable.
  robots: { index: false, follow: false },
  alternates: { canonical: "/demo" },
};

export default function DemoLayout({ children }: LayoutProps<"/demo">) {
  return (
    <DemoProvider>
      <Shell>{children}</Shell>
    </DemoProvider>
  );
}
