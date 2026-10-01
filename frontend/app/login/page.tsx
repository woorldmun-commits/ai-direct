import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout, LoginForm } from "@/components/auth";

export const metadata: Metadata = {
  title: "Вход",
  alternates: { canonical: "/login" },
};

export default function LoginPage() {
  return (
    <AuthLayout
      title="Вход в AdPilot"
      footer={
        <>
          Нет аккаунта?{" "}
          <Link href="/signup" className="font-semibold text-brand">
            Создать бесплатно
          </Link>
        </>
      }
    >
      <LoginForm />
    </AuthLayout>
  );
}
