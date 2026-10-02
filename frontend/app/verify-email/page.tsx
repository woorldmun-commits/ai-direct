import { MailCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { AuthLayout } from "@/components/auth";

export const metadata: Metadata = {
  title: "Подтвердите email",
  robots: { index: false, follow: false },
};

export default function VerifyEmailPage() {
  return (
    <AuthLayout title="Подтвердите email" sub="Мы отправим письмо со ссылкой. Откройте его, чтобы активировать аккаунт.">
      <div className="mt-6 flex items-center gap-3 rounded-2xl bg-brand-soft p-4 text-sm text-brand">
        <MailCheck size={20} className="shrink-0" /> Письма нет? Проверьте «Спам» или отправьте ещё раз.
      </div>
      <div className="mt-6 flex flex-col gap-2">
        {/* ponytail: prototype step — the real flow lands on /onboarding from the email link. */}
        <Link href="/onboarding" className="btn btn-primary h-12">
          Я подтвердил email
        </Link>
        <button className="btn btn-secondary h-12">Отправить письмо ещё раз</button>
      </div>
    </AuthLayout>
  );
}
