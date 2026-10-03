import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { Amount, Logo, Stamp } from "@/components/ui";
import { KPI, PERIOD, PROBLEMS, SAVEABLE, SAVED, SNAPSHOT } from "@/lib/demo";

const NAV = [
  { href: "#check", label: "Что проверяем" },
  { href: "#how", label: "Как это работает" },
  { href: "#pricing", label: "Тарифы" },
  { href: "#faq", label: "Вопросы" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-rule bg-bg">
      <div className="mx-auto flex h-16 max-w-[1280px] items-center gap-8 px-4 md:px-8">
        <Link href="/" aria-label="AdPilot — на главную">
          <Logo />
        </Link>
        <nav className="hidden flex-1 items-center gap-7 text-sm font-semibold text-muted lg:flex" aria-label="Основное меню">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="hover:text-text">
              {n.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link href="/login" className="hidden px-3 text-sm font-semibold text-muted hover:text-text sm:inline">
            Войти
          </Link>
          <Link href="/demo" className="btn btn-sm btn-secondary hidden sm:inline-flex">
            Демо-кабинет
          </Link>
          <Link href="/signup" className="btn btn-sm btn-ink">
            Запустить аудит
          </Link>
        </div>
      </div>
    </header>
  );
}

const LINES: [string, number, "fact" | "loss" | "saveable" | "saved"][] = [
  ["Потрачено", KPI.spend, "fact"],
  ["Потери ≈", KPI.losses, "loss"],
  ["Можно сэкономить ≈", SAVEABLE, "saveable"],
  ["Сэкономлено ≈", SAVED, "saved"],
];

/** The product's own artifact at life size: the reconciliation statement. Demo data, stamped as a sample. */
function Statement() {
  return (
    <figure className="relative min-w-0" aria-label="Пример акта сверки AdPilot на демонстрационных данных">
      <div aria-hidden className="absolute inset-0 translate-x-3 translate-y-3 border border-rule bg-surface" />
      <div className="relative border border-rule bg-surface p-5 shadow-[var(--shadow-md)] md:p-7">
        <div className="flex items-start justify-between gap-4 border-b-2 border-text pb-3">
          <div>
            <p className="text-[19px] leading-tight font-bold">Акт сверки рекламных расходов</p>
            <p className="caption mt-1">ООО «Пример» ↔ Яндекс Директ · {PERIOD}</p>
          </div>
          <p className="reqs text-right">
            снимок
            <br />#{SNAPSHOT.id}
          </p>
        </div>
        <dl className="divide-y divide-line">
          {LINES.map(([k, v, kind]) => (
            <div key={k} className="flex items-baseline py-2.5">
              <dt className="font-medium">{k}</dt>
              <span className="leader" aria-hidden />
              <dd className="text-[19px] md:text-[22px]">
                <Amount value={v} kind={kind} bare />
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-sm font-bold">Требуют решения: {PROBLEMS.length}</p>
        <ol className="mt-1 text-sm">
          {PROBLEMS.map((p, i) => (
            <li key={p.id} className="flex items-baseline gap-2 border-b border-line py-1.5">
              <span className="reqs w-4">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate">{p.recommendation}</span>
              <Amount value={p.loss} kind="loss" />
            </li>
          ))}
        </ol>
        <div className="mt-5 grid grid-cols-2 gap-6 text-[12px]">
          <p>
            <span className="caption block">Сверку провёл</span>
            <b>AdPilot</b>
          </p>
          <p>
            <span className="caption block">Решение принимает</span>
            <span className="mt-3 block h-px bg-rule" aria-hidden />
          </p>
        </div>
        <div className="absolute right-6 bottom-12 md:right-10">
          <Stamp text="Образец" sub="демо-данные" tone="muted" />
        </div>
      </div>
    </figure>
  );
}

export function Hero() {
  return (
    <section className="border-b border-rule">
      <div className="mx-auto grid max-w-[1280px] items-center gap-12 px-4 pt-12 pb-16 md:px-8 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pt-20 lg:pb-24">
        <div className="min-w-0">
          <h1 className="text-[40px] leading-[1.02] font-bold tracking-[-0.035em] text-balance md:text-[56px] xl:text-[64px]">
            Сверим вашу рекламу с&nbsp;результатом — до&nbsp;рубля
          </h1>
          <p className="mt-6 max-w-[54ch] text-[18px] text-muted">
            Подключите Яндекс Директ за 2 минуты и узнайте, где теряются деньги в рекламе: сколько, почему и что сделать. Каждая сумма — с источником, периодом и
            формулой.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/signup" className="btn btn-primary h-12 px-6 text-[15px]">
              Запустить бесплатный аудит <ArrowRight size={18} />
            </Link>
            <Link href="/demo" className="btn btn-secondary h-12 px-6 text-[15px]">
              Открыть демо-кабинет
            </Link>
          </div>
          <ul className="mt-8 grid max-w-[560px] gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
            {["Без карты", "Изменения — только с вашего одобрения", "Цифры считает код, AI объясняет"].map((t) => (
              <li key={t} className="border-t border-rule pt-2 text-muted">
                {t}
              </li>
            ))}
          </ul>
        </div>
        <Statement />
      </div>
    </section>
  );
}
