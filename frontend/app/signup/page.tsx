import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout, SignupForm } from "@/components/auth";

export const metadata: Metadata = {
  title: "Создать аккаунт",
  description: "Создайте аккаунт AdPilot по email и запустите бесплатный аудит Яндекс Директ. Без карты.",
  alternates: { canonical: "/signup" },
};

export default function SignupPage() {
  return (
    <AuthLayout
      title="Создайте аккаунт"
      sub="И начните бесплатный аудит. Без карты: первый аудит бесплатно, один на рекламный аккаунт."
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-semibold text-brand">
            Войти
          </Link>
        </>
      }
    >
      <SignupForm />
    </AuthLayout>
  );
}
