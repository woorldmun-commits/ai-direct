import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout, PhoneAuth } from "@/components/auth";

export const metadata: Metadata = {
  title: "Вход",
  alternates: { canonical: "/login" },
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return (
    <AuthLayout
      title="Добро пожаловать!"
      sub="По номеру телефона: пришлём код в SMS."
      footer={
        <>
          Нет аккаунта?{" "}
          <Link href="/signup" className="font-semibold text-brand">
            Создать бесплатно
          </Link>
        </>
      }
    >
      <PhoneAuth />
    </AuthLayout>
  );
}
