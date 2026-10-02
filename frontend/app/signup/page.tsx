import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout, PhoneAuth } from "@/components/auth";

export const metadata: Metadata = {
  title: "Создать аккаунт",
  description: "Создайте аккаунт AdPilot по номеру телефона и запустите бесплатный аудит Яндекс Директ. Без карты.",
  alternates: { canonical: "/signup" },
};

export default function SignupPage() {
  return (
    <AuthLayout
      title="Создайте аккаунт"
      sub="По номеру телефона и коду из SMS. Без карты: первый аудит бесплатно, один на рекламный аккаунт."
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-semibold text-brand">
            Войти
          </Link>
        </>
      }
    >
      <PhoneAuth />
    </AuthLayout>
  );
}
