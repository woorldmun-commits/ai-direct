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
    cta: "Получить бесплатный аудит",
    features: [
      "Разовая проверка Директа и Метрики",
      "Неэффективный расход в ₽ (оценка) с формулой и источником",
      "Результат только для чтения",
    ],
    highlight: false,
  },
  {
    name: "Рабочее пространство",
    price: "Ранний доступ",
    note: "для специалиста по рекламе",
    cta: "Посмотреть возможности",
    features: [
      "Приоритеты на одном экране",
      "Рекомендации с формулой и источником",
      "История решений и сравнение периодов",
    ],
    highlight: true,
  },
  {
    name: "Агентство",
    price: "Пилотный запуск",
    note: "для работы с несколькими клиентами",
    cta: "Начать знакомство",
    features: [
      "Знакомство с общим обзором кабинетов",
      "Проверка сценариев на демо-данных",
      "Условия пилота согласуем отдельно",
    ],
    highlight: false,
  },
];

export function Pricing() {
  return (
    <section
      id="pricing"
      aria-labelledby="pricing-title"
      className="site-pricing mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8"
    >
      <h2
        id="pricing-title"
        className="text-[26px] font-bold tracking-tight md:text-[28px]"
      >
        Сначала проверьте. Затем выберите формат.
      </h2>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {PLANS.map((p) => (
          <article
            key={p.name}
            className={`card flex flex-col p-6 ${p.highlight ? "border-brand ring-1 ring-brand" : ""}`}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">{p.name}</h3>
              {p.highlight && (
                <span className="badge bg-brand-soft text-brand">Основной</span>
              )}
            </div>
            <p className="money mt-4 text-[28px]">{p.price}</p>
            <p className="text-sm text-muted">{p.note}</p>
            <ul className="mt-5 flex-1 space-y-2 text-sm">
              {p.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <Check size={16} className="mt-0.5 shrink-0 text-success" />{" "}
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href={p.name === "Аудит" ? "/signup" : "/demo"}
              className={`btn mt-6 ${p.highlight ? "btn-primary" : "btn-secondary"}`}
            >
              {p.cta}
            </Link>
          </article>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted">
        Rekvero развивается в формате раннего доступа. Демо доступно без
        регистрации, первый аудит — без карты. Условия — в{" "}
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
    a: "Вы входите в Rekvero по номеру телефона и одноразовому коду из SMS, а Яндекс Директ и Метрику подключаете уже в кабинете через официальный OAuth Яндекса: пароль от Яндекса мы не видим. Токены доступа хранятся в зашифрованном виде, отключить источник можно в любой момент.",
  },
  {
    q: "Rekvero сам меняет ставки и кампании?",
    a: "Нет. Rekvero показывает проблему с доказательством: цифры, формулу, источник и уровень уверенности. Решение принимаете вы и вносите изменение в Яндекс Директе вручную. Rekvero сверяет его по данным Директа и через 7 дней измеряет эффект. Применение изменений через API после вашего одобрения — в планах, но не в текущей версии.",
  },
  {
    q: "Какие данные нужны для работы?",
    a: "Доступ к Яндекс Директу. Яндекс Метрика нужна для целей и конверсий. Целевой CPA желателен: без него сравниваем с базовым CPA кампании. Если данных мало, так и пишем — «Недостаточно данных» — и подсказываем, что подключить.",
  },
  {
    q: "Подходит ли Rekvero агентству или директологу с несколькими клиентами?",
    a: "Работа с несколькими клиентами — один из основных сценариев Rekvero. В демо можно посмотреть общий обзор кабинетов и приоритеты проблем по сумме. Доступность возможностей в пилоте согласуем отдельно; командные роли пока не реализованы.",
  },
  {
    q: "Rekvero гарантирует снижение CPA или рост заявок?",
    a: "Нет. Мы не обещаем автоматического роста. Rekvero находит, где расход имеет признаки неэффективности, доказывает это на данных и измеряет эффект ваших решений. Результат зависит от решений специалиста, рынка и сезона, поэтому эффект показываем как оценку: сравнение до и после без контрольной группы.",
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
    q: "Как познакомиться с Rekvero?",
    a: "Откройте демо без регистрации: там можно изучить рекомендации, источники цифр и историю решений на тестовых данных. Для подключения своих источников создайте аккаунт. Условия раннего доступа описаны в Договоре-оферте.",
  },
];

export function Faq() {
  return (
    <section
      id="faq"
      aria-labelledby="faq-title"
      className="site-faq mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8"
    >
      <h2
        id="faq-title"
        className="text-[26px] font-bold tracking-tight md:text-[28px]"
      >
        Частые вопросы
      </h2>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="card divide-y divide-line">
          {FAQ.map((f) => (
            <details key={f.q} className="group px-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 font-semibold">
                {f.q}
                <ChevronDown
                  size={18}
                  className="shrink-0 text-muted transition-transform duration-200 group-open:rotate-180"
                />
              </summary>
              <p className="pb-4 text-sm text-muted">{f.a}</p>
            </details>
          ))}
        </div>
        <aside className="card self-start p-6">
          <span className="grid size-11 place-items-center rounded-full bg-brand-soft text-brand">
            <Lock size={20} />
          </span>
          <h3 className="mt-4 font-bold">Доступ без передачи пароля</h3>
          <p className="mt-2 text-sm text-muted">
            Директ и Метрика подключаются через официальный OAuth Яндекса.
            Пароль от Яндекса не передаётся Rekvero. Перед подключением можно
            изучить политику обработки данных.
          </p>
          <Link
            href="/legal/privacy"
            className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand"
          >
            Политика обработки данных <ArrowRight size={14} />
          </Link>
        </aside>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section
      aria-labelledby="final-title"
      className="site-final mx-auto max-w-[1360px] px-4 py-20 md:px-8"
    >
      <div className="card flex flex-col items-start gap-6 p-8 md:flex-row md:items-center md:justify-between md:p-10">
        <div>
          <h2
            id="final-title"
            className="text-[26px] font-bold tracking-tight md:text-[28px]"
          >
            Следующий шаг — проверить свой Директ.
          </h2>
          <p className="mt-1 text-muted">
            Найдите, что требует внимания, прежде чем менять ставки. Первый аудит
            бесплатно, без карты. Вы решаете, что делать дальше.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/signup" className="btn btn-primary h-12 px-6">
            Получить бесплатный аудит <ArrowRight size={18} />
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
          <p className="mt-2 text-sm text-muted">
            Контроль рекламного бюджета. Данные, причины, решения.
          </p>
        </div>
        <nav
          aria-label="Документы"
          className="grid gap-2 text-sm sm:grid-cols-2"
        >
          <Link href="/legal" className="text-muted hover:text-text">Правовая информация</Link>
          {LEGAL_DOCS.map((d) => (
            <Link
              key={d.slug}
              href={`/legal/${d.slug}`}
              className="text-muted hover:text-text"
            >
              {d.title}
            </Link>
          ))}
          <CookieSettingsButton className="text-left text-muted hover:text-text" />
        </nav>
      </div>
      <div className="mx-auto max-w-[1360px] space-y-2 border-t border-line px-4 py-6 text-xs text-muted md:px-8">
        <p>© 2026 Rekvero</p>
        <p>Условия использования сервиса и информация об операторе доступны в правовых документах.</p>
        <p>
          Rekvero — независимый сервис, не является продуктом ООО «ЯНДЕКС» и не
          аффилирован с ним. «Яндекс», «Яндекс Директ», «Яндекс Метрика» —
          товарные знаки ООО «ЯНДЕКС».
        </p>
      </div>
    </footer>
  );
}
