import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout, ResetForm } from "@/components/auth";

export const metadata: Metadata = {
  title: "Восстановление пароля",
  robots: { index: false, follow: false },
};

export default function ResetPasswordPage() {
  return (
    <AuthLayout
      title="Восстановление пароля"
      sub="Укажите email аккаунта — пришлём ссылку для смены пароля."
      footer={
        <Link href="/login" className="font-semibold text-brand">
          Вернуться ко входу
        </Link>
      }
    >
      <ResetForm />
    </AuthLayout>
  );
}
