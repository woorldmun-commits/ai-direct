import { ArrowRight, BadgeCheck, CreditCard, Layers, Plug, Sparkles } from "lucide-react";
import Link from "next/link";
import { Sparkline } from "@/components/charts";
import { Logo } from "@/components/ui";
import { ActionText } from "@/components/app/rec-parts";
import { ValueView } from "@/components/value-view";
import { RECOMMENDATIONS, WEEK, WEEK_VALUES } from "@/lib/demo";
import { buildToday } from "@/lib/demo-backend";
import { PAST_RECOMMENDATIONS } from "@/lib/demo-history";
import { EXPOSURE_SHORT } from "@/lib/site";
import type { Value } from "@/lib/value";

const NAV = [
  { href: "#features", label: "Возможности" },
  { href: "#how", label: "Как это работает" },
  { href: "#pricing", label: "Тарифы" },
  { href: "#faq", label: "FAQ" },
];

export function Header() {
  return (
    <header className="sticky top-3 z-50 mx-auto max-w-[1360px] px-4">
      <div className="flex h-16 items-center gap-6 rounded-2xl border border-white/10 bg-[#071613]/70 px-4 backdrop-blur-xl md:px-6">
        <Link href="/" aria-label="AdPilot — на главную">
          <Logo light />
        </Link>
        <nav className="hidden flex-1 items-center gap-7 text-sm text-white/70 lg:flex" aria-label="Основное меню">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="transition-colors hover:text-white">
              {n.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Link href="/login" className="hidden px-3 text-sm text-white/70 hover:text-white sm:inline">
            Войти
          </Link>
          <Link href="/demo" className="btn btn-sm hidden border border-white/25 text-white hover:border-white/60 sm:inline-flex">
            Попробовать демо
          </Link>
          <Link href="/signup" className="btn btn-sm bg-[#39BFA0] text-[#04130f] hover:bg-[#52cfb2]">
            Создать аккаунт
          </Link>
        </div>
      </div>
    </header>
  );
}

export function Hero() {
  return (
    <section className="relative -mt-[76px] overflow-hidden bg-hero pt-[76px] text-white">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 60% at 75% 40%, rgba(57,191,160,.22), transparent 70%), radial-gradient(40% 50% at 10% 90%, rgba(13,107,91,.35), transparent 70%)",
        }}
      />
      <div className="relative mx-auto grid max-w-[1360px] items-center gap-12 px-4 pt-16 pb-24 md:px-8 lg:grid-cols-[1.1fr_1fr] lg:pt-20 lg:pb-32">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80">
            <Sparkles size={14} className="text-[#39BFA0]" /> Для малых агентств и директологов · Яндекс Директ
          </span>
          <h1 className="mt-6 text-[38px] leading-[1.06] font-bold tracking-[-0.03em] md:text-[52px] xl:text-[60px]">
            Где бюджет клиентов <span className="text-[#39BFA0]">расходуется неэффективно</span> — с{" "}
            <span className="text-[#39BFA0]">доказательством</span> на данных.
          </h1>
          <p className="mt-6 max-w-[540px] text-lg text-white/70">
            AdPilot каждый день проверяет все ваши кабинеты Директа и Метрики, оценивает расход с признаками неэффективности в рублях
            и показывает формулу и источник каждой цифры. Решение и изменение в кабинете остаются за вами, а AdPilot сверяет его по
            данным Директа, измеряет эффект и собирает отчёт для клиента.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/signup" className="btn h-12 bg-[#39BFA0] px-6 text-[15px] text-[#04130f] hover:bg-[#52cfb2]">
              Запустить бесплатный аудит <ArrowRight size={18} />
            </Link>
            <Link href="/demo" className="btn h-12 border border-white/25 px-6 text-[15px] text-white hover:border-white/60">
              Попробовать демо
            </Link>
          </div>
          <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/60">
            <li className="flex items-center gap-2">
              <CreditCard size={16} /> Без карты
            </li>
            <li className="flex items-center gap-2">
              <Layers size={16} /> Несколько кабинетов в одном обзоре
            </li>
            <li className="flex items-center gap-2">
              <Plug size={16} /> Подключение в пару кликов
            </li>
          </ul>
        </div>
        <ProductPreview />
      </div>
    </section>
  );
}

// Decorative preview: the same demo contract objects as the cabinet, without «Как посчитано» buttons.
function MiniMetric({ label, v, tone }: { label: string; v: Value; tone: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <p className="text-[10px] text-muted">{label}</p>
      <p className="mt-1">
        <ValueView v={v} hint={false} className={`text-[15px] xl:text-[17px] ${tone}`} />
      </p>
    </div>
  );
}

function ProductPreview() {
  const main = RECOMMENDATIONS[0];
  const today = buildToday([...RECOMMENDATIONS, ...PAST_RECOMMENDATIONS]);
  return (
    <figure className="relative" aria-label="Интерфейс AdPilot с демонстрационными данными">
      <div className="relative rounded-[22px] border border-white/10 bg-white/5 p-2 shadow-[0_40px_120px_-30px_rgba(57,191,160,.45)] lg:[transform:perspective(1600px)_rotateY(-8deg)_rotateX(3deg)]">
        <div className="flex overflow-hidden rounded-2xl bg-bg text-text">
          <aside className="hidden w-[132px] shrink-0 border-r border-line bg-surface p-3 sm:block" aria-hidden>
            <Logo size={18} />
            <ul className="mt-4 space-y-1 text-[10px] text-muted">
              {["Обзор", "Неэфф. расход", "Рекомендации", "Что изменилось", "Финансы", "История", "Интеграции"].map((x, i) => (
                <li key={x} className={`rounded-md px-2 py-1.5 ${i === 0 ? "bg-brand-soft font-semibold text-brand" : ""}`}>
                  {x}
                </li>
              ))}
            </ul>
          </aside>
          <div className="min-w-0 flex-1 p-4">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-bold">Доброе утро, Алексей</p>
              <span className="badge bg-warning-bg text-[9px] text-warning">ДЕМО-ДАННЫЕ</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <MiniMetric label={EXPOSURE_SHORT} v={today.exposure.total} tone="text-danger" />
              <MiniMetric label="Можно сэкономить" v={today.can_save.total} tone="text-warning" />
              <MiniMetric label="Сэкономлено" v={today.saved} tone="text-success" />
            </div>
            <div className="mt-2 grid grid-cols-[1.4fr_1fr] gap-2">
              <div className="rounded-xl border border-line bg-surface p-3">
                <span className="badge bg-danger-bg text-[9px] text-danger">Сегодня важнее всего</span>
                <p className="mt-2 text-[12px] font-bold">{main.title}</p>
                <p>
                  <ValueView v={main.exposure} hint={false} className="text-[15px] text-danger" />
                </p>
                <p className="mt-1 text-[10px] text-muted">
                  <ActionText r={main} />
                </p>
              </div>
              <div className="rounded-xl border border-line bg-surface p-3">
                <p className="text-[10px] text-muted">Расход, 7 дней</p>
                <p>
                  <ValueView v={WEEK_VALUES.spend} hint={false} className="text-[13px]" />
                </p>
                <div className="mt-2">
                  <Sparkline values={WEEK.spend} height={40} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="absolute -right-2 -bottom-10 hidden w-[260px] rounded-2xl border border-white/15 bg-[#0c1916]/80 p-4 text-white shadow-[0_20px_50px_-20px_rgba(0,0,0,.7)] backdrop-blur-xl sm:block lg:-right-6">
        <p className="flex items-center gap-2 text-xs font-bold">
          <BadgeCheck size={15} className="text-[#39BFA0]" /> Почему AdPilot так считает?
        </p>
        <p className="mt-1.5 text-xs text-white/70">
          {main.explanation.text.split(". ")[0]}. Источник: Директ + Метрика.
        </p>
      </div>
      <figcaption className="mt-6 text-xs text-white/45 sm:mt-14">Интерфейс с демонстрационными данными</figcaption>
    </figure>
  );
}
