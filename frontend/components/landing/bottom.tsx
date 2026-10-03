import { ArrowRight, Check, ChevronDown } from "lucide-react";
import Link from "next/link";
import { CookieSettingsButton } from "@/components/cookie-banner";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";

const PLANS = [
  {
    name: "Аудит",
    price: "0 ₽",
    note: "один раз на рекламный кабинет",
    cta: "Запустить аудит",
    features: ["Разовая сверка Директа и Метрики", "Потери ≈ в ₽ с формулой и источником", "Результат только для чтения"],
    main: false,
  },
  {
    name: "Мониторинг",
    price: "[ЦЕНА] ₽/мес",
    note: "один рекламный кабинет",
    cta: "Продолжить мониторинг",
    features: ["Ежедневная сверка", "Рекомендации и история решений", "Замер «Сэкономлено ≈» через 7 дней", "Telegram: утренний дайджест и недельный отчёт"],
    main: true,
  },
  {
    name: "Агентство",
    price: "[ЦЕНА] ₽/мес",
    note: "несколько кабинетов и клиентов",
    cta: "Обсудить условия",
    features: ["Всё из «Мониторинга»", "Клиентские пространства и роли", "Одобрение и применение — раздельно"],
    main: false,
  },
];

export function Pricing() {
  return (
    <section id="pricing" aria-labelledby="pricing-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-24 md:px-8">
      <h2 id="pricing-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[40px]">
        Тарифы
      </h2>
      <div className="mt-8 grid border-t-2 border-text lg:grid-cols-3">
        {PLANS.map((p) => (
          <article key={p.name} className={`flex flex-col border-b border-rule py-6 lg:border-b-0 lg:px-6 lg:first:pl-0 lg:last:pr-0 ${p.main ? "lg:border-x" : ""}`}>
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-[19px] font-bold">{p.name}</h3>
              {p.main && <span className="badge text-brand">Основной</span>}
            </div>
            <p className="money mt-4 text-[32px]">{p.price}</p>
            <p className="caption">{p.note}</p>
            <ul className="mt-5 flex-1 space-y-2 text-sm">
              {p.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <Check size={16} className="mt-0.5 shrink-0 text-success" /> {f}
                </li>
              ))}
            </ul>
            <Link href="/signup" className={`btn mt-6 ${p.main ? "btn-primary" : "btn-secondary"}`}>
              {p.cta}
            </Link>
          </article>
        ))}
      </div>
      <p className="caption mt-4 max-w-[90ch]">
        Цены указаны в рублях, [НДС не облагается (УСН / НПД) | включая НДС 20%]. Подписка продлевается автоматически только с вашего явного согласия; о списании
        предупредим за 3 дня, отменить можно в кабинете в любой момент. Условия — в{" "}
        <Link href="/legal/offer" className="underline">
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
    a: "Вы входите в AdPilot по email и паролю, а Яндекс Директ и Метрику подключаете уже в кабинете через официальный OAuth Яндекса: пароль от Яндекса мы не видим. Токены доступа хранятся в зашифрованном виде, отключить источник можно в любой момент.",
  },
  {
    q: "AdPilot сам меняет ставки и кампании?",
    a: "Нет. Без вашего одобрения в рекламном кабинете ничего не меняется. Вы видите изменение «было → станет» и решаете сами.",
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
    <section id="faq" aria-labelledby="faq-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-24 md:px-8">
      <div className="grid gap-10 lg:grid-cols-[1fr_2fr]">
        <div>
          <h2 id="faq-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[40px]">
            Частые вопросы
          </h2>
          <p className="mt-4 max-w-[40ch] text-sm text-muted">
            Используем официальные API Яндекс Директа и Метрики. Доступы хранятся зашифрованными, данные обрабатываются по 152-ФЗ и не продаются третьим лицам.
          </p>
          <Link href="/legal/privacy" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
            Политика обработки данных <ArrowRight size={14} />
          </Link>
        </div>
        <div className="border-t-2 border-text">
          {FAQ.map((f) => (
            <details key={f.q} className="group border-b border-rule">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 text-[17px] font-semibold">
                {f.q}
                <ChevronDown size={18} className="shrink-0 text-muted group-open:rotate-180" />
              </summary>
              <p className="max-w-[70ch] pb-5 text-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section aria-labelledby="final-title" className="mx-auto max-w-[1280px] px-4 py-24 md:px-8">
      <div className="flex flex-col items-start gap-6 border-y-2 border-text py-10 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 id="final-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[40px]">
            Проведите первую сверку
          </h2>
          <p className="mt-1 text-muted">Без карты. Регистрация по email. Изменения в рекламе — только с вашего одобрения.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/signup" className="btn btn-primary h-12 px-6">
            Создать аккаунт бесплатно <ArrowRight size={18} />
          </Link>
          <Link href="/demo" className="btn btn-secondary h-12 px-6">
            Демо-кабинет
          </Link>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-rule bg-surface">
      <div className="mx-auto grid max-w-[1280px] gap-8 px-4 py-12 md:grid-cols-[1fr_2fr] md:px-8">
        <div>
          <Logo />
          <p className="mt-2 text-sm text-muted">Контроль рекламных расходов в Яндекс Директе.</p>
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
      <div className="caption mx-auto max-w-[1280px] space-y-2 border-t border-line px-4 py-6 md:px-8">
        <p>[ИП Фамилия И. О. / ООО «Название»] · ИНН [__________] · ОГРН/ОГРНИП [_____________] · Адрес: [____] · E-mail: [support@…] · © 2026 AdPilot</p>
        <p>
          AdPilot — независимый сервис, не является продуктом ООО «ЯНДЕКС» и не аффилирован с ним. «Яндекс», «Яндекс Директ», «Яндекс Метрика» — товарные знаки ООО
          «ЯНДЕКС».
        </p>
      </div>
    </footer>
  );
}
