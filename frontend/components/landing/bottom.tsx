import { ArrowRight, Check, ChevronDown, Lock } from "lucide-react";
import Link from "next/link";
import { CookieSettingsButton } from "@/components/cookie-banner";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";

const PILOT = {
  name: "Закрытый пилот",
  note: "для агентств и директологов, по договору",
  features: [
    "Разовая проверка кабинета Директа и Метрики (только чтение)",
    "Расход с признаками неэффективности в ₽ (оценка) с формулой и источником",
    "Каждая рекомендация проверяется специалистом AdPilot до передачи вам",
    "Отчёт с доказательствами; решение и изменение в кабинете остаются за вами",
  ],
};

export function Pricing() {
  return (
    <section id="pricing" aria-labelledby="pricing-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <h2 id="pricing-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
        Участие в пилоте
      </h2>
      <article className="card mt-6 flex max-w-[640px] flex-col p-6">
        <h3 className="text-lg font-bold">{PILOT.name}</h3>
        <p className="text-sm text-muted">{PILOT.note}</p>
        <ul className="mt-5 flex-1 space-y-2 text-sm">
          {PILOT.features.map((f) => (
            <li key={f} className="flex gap-2">
              <Check size={16} className="mt-0.5 shrink-0 text-success" /> {f}
            </li>
          ))}
        </ul>
        <Link href="/signup" className="btn btn-primary mt-6">
          Подать заявку на пилот
        </Link>
      </article>
      <p className="mt-4 text-xs text-muted">
        Условия участия, порядок передачи доступа к данным, их хранения и удаления фиксируются в договоре пилота. Тарифы появятся
        после пилота; автоматической синхронизации, уведомлений и управления рекламой в пилоте нет.
      </p>
    </section>
  );
}

export const FAQ = [
  {
    q: "Безопасно ли передавать доступ к Яндекс Директу?",
    a: "Доступ к Директу и Метрике оформляется через официальный OAuth Яндекса: пароль от Яндекса мы не видим и не запрашиваем. Токены доступа хранятся в зашифрованном виде. Порядок передачи, хранения и удаления данных, а также отзыв доступа фиксируются в договоре пилота.",
  },
  {
    q: "AdPilot сам меняет ставки и кампании?",
    a: "Нет. AdPilot показывает проблему с доказательством: цифры, формулу, источник и уровень уверенности. Решение принимаете вы и вносите изменение в Яндекс Директе вручную. AdPilot сверяет его по данным Директа и через 7 дней измеряет эффект. Применение изменений через API после вашего одобрения — в планах, но не в текущей версии.",
  },
  {
    q: "Какие данные нужны для работы?",
    a: "Доступ к Яндекс Директу. Яндекс Метрика нужна для целей и конверсий. Целевой CPA желателен: без него сравниваем с базовым CPA кампании. Если данных мало, так и пишем — «Недостаточно данных» — и подсказываем, что подключить.",
  },
  {
    q: "Подходит ли AdPilot агентству или директологу с несколькими клиентами?",
    a: "Да, это основной сценарий пилота: проверка кабинетов ваших клиентов и отчёт, где каждый вывод подкреплён цифрами и источником.",
  },
  {
    q: "AdPilot гарантирует снижение CPA или рост заявок?",
    a: "Нет. Мы не обещаем автоматического роста. AdPilot находит, где расход имеет признаки неэффективности, доказывает это на данных и измеряет эффект ваших решений. Результат зависит от решений специалиста, рынка и сезона, поэтому эффект показываем как оценку: сравнение до и после без контрольной группы.",
  },
  {
    q: "Сколько времени занимает аудит?",
    a: "Сроки согласуем при подключении: в пилоте результат готовим с ручной проверкой каждой рекомендации, поэтому быстро и без неё не обещаем.",
  },
  {
    q: "Что передаётся в AI?",
    a: "Только обезличенные агрегаты: без названий кампаний, текстов поисковых запросов и персональных данных. Цифры считает код, AI их только объясняет.",
  },
  {
    q: "Как отозвать доступ и удалить данные?",
    a: "Доступ можно отозвать в любой момент, удаление данных по запросу. Точный порядок и сроки согласуются в договоре пилота.",
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
            Участвуйте в закрытом пилоте
          </h2>
          <p className="mt-1 text-muted">Доступ по договору. Изменения в кабинетах вносите только вы — AdPilot ничего не меняет сам.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link href="/signup" className="btn btn-primary h-12 px-6">
            Подать заявку <ArrowRight size={18} />
          </Link>
          <Link href="/demo" className="btn btn-secondary h-12 px-6">
            Демо на тестовых данных
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
          <p className="mt-2 text-sm text-muted">Доказательный контроль рекламных кабинетов.</p>
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
          © 2026 AdPilot. Реквизиты оператора публикуются до начала приёма пользователей.
        </p>
        <p>
          AdPilot — независимый сервис, не является продуктом ООО «ЯНДЕКС» и не аффилирован с ним. «Яндекс», «Яндекс Директ»,
          «Яндекс Метрика» — товарные знаки ООО «ЯНДЕКС».
        </p>
      </div>
    </footer>
  );
}
