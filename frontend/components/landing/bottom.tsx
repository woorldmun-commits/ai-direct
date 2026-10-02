import { ArrowRight, Check, ChevronDown, Lock } from "lucide-react";
import Link from "next/link";
import { CookieSettingsButton } from "@/components/cookie-banner";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";

const PLANS = [
  {
    name: "Аудит",
    price: "0 ₽",
    note: "один раз на рекламный аккаунт",
    cta: "Запустить аудит",
    features: ["Разовая проверка Директа и Метрики", "Потери в ₽ с формулой и источником", "Результат только для чтения"],
    highlight: false,
  },
  {
    name: "Мониторинг",
    price: "[ЦЕНА] ₽/мес",
    note: "один рекламный аккаунт",
    cta: "Продолжить мониторинг",
    features: ["Ежедневная проверка", "Рекомендации и история решений", "Замер эффекта через 7 дней", "Уведомления в Telegram и на почту"],
    highlight: true,
  },
  {
    name: "Агентство",
    price: "[ЦЕНА] ₽/мес",
    note: "несколько аккаунтов",
    cta: "Обсудить условия",
    features: ["Всё из «Мониторинга»", "Несколько рекламных аккаунтов", "Общий обзор по клиентам"],
    highlight: false,
  },
];

export function Pricing() {
  return (
    <section id="pricing" aria-labelledby="pricing-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <h2 id="pricing-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
        Тарифы
      </h2>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {PLANS.map((p) => (
          <article key={p.name} className={`card flex flex-col p-6 ${p.highlight ? "border-brand ring-1 ring-brand" : ""}`}>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">{p.name}</h3>
              {p.highlight && <span className="badge bg-brand-soft text-brand">Основной</span>}
            </div>
            <p className="money mt-4 text-[32px]">{p.price}</p>
            <p className="text-sm text-muted">{p.note}</p>
            <ul className="mt-5 flex-1 space-y-2 text-sm">
              {p.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <Check size={16} className="mt-0.5 shrink-0 text-success" /> {f}
                </li>
              ))}
            </ul>
            <Link href="/signup" className={`btn mt-6 ${p.highlight ? "btn-primary" : "btn-secondary"}`}>
              {p.cta}
            </Link>
          </article>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted">
        Цены указаны в рублях, [НДС не облагается (УСН / НПД) | включая НДС 20%]. Подписка продлевается автоматически только с
        вашего явного согласия; о списании предупредим за 3 дня, отменить можно в кабинете в любой момент. Условия — в{" "}
        <Link href="/legal/offer" className="underline underline-offset-2">
          Договоре-оферте
        </Link>
        .
      </p>
    </section>
  );
}

export const FAQ = [
  {
    q: "Безопасно ли передавать доступ к Яндекс Директу?",
    a: "Вы входите в AdPilot по номеру телефона и одноразовому коду из SMS, а Яндекс Директ и Метрику подключаете уже в кабинете через официальный OAuth Яндекса: пароль от Яндекса мы не видим. Токены доступа хранятся в зашифрованном виде, отключить источник можно в любой момент.",
  },
  {
    q: "AdPilot сам меняет ставки и кампании?",
    a: "Нет. AdPilot только читает статистику и показывает рекомендации. Изменения в Яндекс Директе вносите вы.",
  },
  {
    q: "Какие данные нужны для работы?",
    a: "Доступ к Яндекс Директу. Яндекс Метрика нужна для целей и конверсий, а целевой CPA — для рекомендаций по ставкам.",
  },
  {
    q: "Сколько времени занимает аудит?",
    a: "Для небольшого аккаунта — обычно несколько минут. Большие аккаунты с долгой историей проверяются дольше.",
  },
  {
    q: "Что передаётся в AI?",
    a: "Только обезличенные агрегаты: без названий кампаний, текстов поисковых запросов и персональных данных. Цифры считает код, AI их только объясняет.",
  },
  {
    q: "Можно ли отменить подписку?",
    a: "Да, в кабинете в любой момент. Условия описаны в Договоре-оферте.",
  },
];

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <h2 id="faq-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
        Частые вопросы
      </h2>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="card divide-y divide-line">
          {FAQ.map((f) => (
            <details key={f.q} className="group px-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 font-semibold">
                {f.q}
                <ChevronDown size={18} className="shrink-0 text-muted transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <p className="pb-4 text-sm text-muted">{f.a}</p>
            </details>
          ))}
        </div>
        <aside className="card self-start p-6">
          <span className="grid size-11 place-items-center rounded-full bg-brand-soft text-brand">
            <Lock size={20} />
          </span>
          <h3 className="mt-4 font-bold">Ваши данные в безопасности</h3>
          <p className="mt-2 text-sm text-muted">
            Мы используем официальные API Яндекс Директа и Яндекс Метрики. Доступы хранятся зашифрованными, данные обрабатываются
            по 152-ФЗ и не продаются третьим лицам.
          </p>
          <Link href="/legal/privacy" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand">
            Политика обработки данных <ArrowRight size={14} />
          </Link>
        </aside>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section aria-labelledby="final-title" className="mx-auto max-w-[1360px] px-4 py-20 md:px-8">
      <div className="card flex flex-col items-start gap-6 p-8 md:flex-row md:items-center md:justify-between md:p-10">
        <div>
          <h2 id="final-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
            Запустите бесплатный аудит
          </h2>
          <p className="mt-1 text-muted">Без карты. Вход по номеру телефона. Изменения в рекламе вносите только вы.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/signup" className="btn btn-primary h-12 px-6">
            Создать аккаунт бесплатно <ArrowRight size={18} />
          </Link>
          <Link href="/demo" className="btn btn-secondary h-12 px-6">
            Попробовать демо
          </Link>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid max-w-[1360px] gap-8 px-4 py-12 md:grid-cols-[1fr_2fr] md:px-8">
        <div>
          <Logo />
          <p className="mt-2 text-sm text-muted">Контроль. Реклама. Прибыль.</p>
        </div>
        <nav aria-label="Документы" className="grid gap-2 text-sm sm:grid-cols-2">
          {LEGAL_DOCS.map((d) => (
            <Link key={d.slug} href={`/legal/${d.slug}`} className="text-muted hover:text-text">
              {d.title}
            </Link>
          ))}
          <CookieSettingsButton className="text-left text-muted hover:text-text" />
        </nav>
      </div>
      <div className="mx-auto max-w-[1360px] space-y-2 border-t border-line px-4 py-6 text-xs text-muted md:px-8">
        <p>
          [ИП Фамилия И. О. / ООО «Название»] · ИНН [__________] · ОГРН/ОГРНИП [_____________] · Адрес: [____] · E-mail: [support@…] ·
          © 2026 AdPilot
        </p>
        <p>
          AdPilot — независимый сервис, не является продуктом ООО «ЯНДЕКС» и не аффилирован с ним. «Яндекс», «Яндекс Директ»,
          «Яндекс Метрика» — товарные знаки ООО «ЯНДЕКС».
        </p>
      </div>
    </footer>
  );
}
