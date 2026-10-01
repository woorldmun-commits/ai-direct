import type { Metadata } from "next";
import { AuthLayout, ConnectSources } from "@/components/auth";

export const metadata: Metadata = {
  title: "Подключите рекламу",
  robots: { index: false, follow: false },
};

export default function OnboardingPage() {
  return (
    <AuthLayout title="Подключите рекламу" sub="Чтобы AdPilot смог провести аудит, подключите источники данных. Изменения в рекламу AdPilot не вносит.">
      <ConnectSources />
    </AuthLayout>
  );
}
