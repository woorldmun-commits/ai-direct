import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/ui";

// Self-service sign-in is not built yet (no auth API): /login, /signup and /onboarding show the closed-pilot notice
// instead of a fake form. Contact is taken from the environment so no address is invented in the repo.
const CONTACT_EMAIL = process.env.NEXT_PUBLIC_CONTACT_EMAIL;

export function AuthLayout({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <div className="w-full max-w-[460px]">
        <Link href="/" aria-label="На главную">
          <Logo />
        </Link>
        <div className="card mt-6 p-6 md:p-8">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
          {children}
        </div>
      </div>
    </main>
  );
}

export function ClosedAccess() {
  return (
    <AuthLayout
      title="Закрытый пилот"
      sub="Личные кабинеты пока не открыты: доступ выдаётся по приглашению и договору. Самостоятельной регистрации и входа сейчас нет."
    >
      <p className="mt-4 text-sm">
        {CONTACT_EMAIL ? (
          <>
            Чтобы участвовать в пилоте, напишите нам:{" "}
            <a href={`mailto:${CONTACT_EMAIL}`} className="font-semibold text-brand">
              {CONTACT_EMAIL}
            </a>
            .
          </>
        ) : (
          "Чтобы участвовать в пилоте, свяжитесь с нами: контакты для заявок скоро появятся здесь."
        )}
      </p>
      <Link href="/demo" className="btn btn-secondary mt-6">
        Посмотреть демо на тестовых данных
      </Link>
    </AuthLayout>
  );
}
