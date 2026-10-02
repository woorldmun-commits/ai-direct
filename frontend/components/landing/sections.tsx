import {
  ArrowRight,
  BadgeCheck,
  Calculator,
  ChartNoAxesCombined,
  Code2,
  Link2,
  ListChecks,
  MessageSquareText,
  MousePointerClick,
  Play,
  Ruler,
  SearchX,
  ShieldCheck,
  Target,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

const PAINS: { icon: LucideIcon; tone: string; title: string; text: string; check: string }[] = [
  {
    icon: Target,
    tone: "bg-danger-bg text-danger",
    title: "CPA выше цели",
    text: "Конверсия обходится дороже, чем вы готовы платить.",
    check: "Сравниваем CPA кампании с вашей целью и оцениваем переплату в ₽ (≈).",
  },
  {
    icon: MousePointerClick,
    tone: "bg-warning-bg text-warning",
    title: "Расход без конверсий",
    text: "Клики есть, заявок нет: бюджет уходит на площадки и группы без результата.",
    check: "Находим площадки и группы с расходом и нулём конверсий.",
  },
  {
    icon: SearchX,
    tone: "bg-info-bg text-info",
    title: "Нерелевантные запросы",
    text: "Объявления показываются по запросам, которые не приводят клиентов.",
    check: "Ищем запросы с расходом без конверсий и предлагаем минус-слова.",
  },
  {
    icon: ChartNoAxesCombined,
    tone: "bg-brand-soft text-brand",
    title: "Незамеченные изменения",
    text: "CPA вырос за неделю, а в отчёте это видно только через месяц.",
    check: "Каждый день сравниваем неделю с прошлой и сообщаем о скачках.",
  },
];

export function Pains() {
  return (
    <section id="features" aria-labelledby="pains-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <h2 id="pains-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
        Где бюджет чаще всего расходуется неэффективно
      </h2>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {PAINS.map((p) => (
          <article key={p.title} className="card flex flex-col p-5 transition-shadow hover:shadow-[var(--shadow-md)]">
            <span className={`grid size-11 place-items-center rounded-full ${p.tone}`}>
              <p.icon size={20} />
            </span>
            <h3 className="mt-4 font-bold">{p.title}</h3>
            <p className="mt-1 text-sm text-muted">{p.text}</p>
            <p className="mt-3 border-t border-line pt-3 text-sm">{p.check}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

const STEPS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: Link2, title: "Подключаете рекламу", text: "Входите по номеру телефона и подключаете Директ и Метрику в кабинете." },
  { icon: Code2, title: "Код проверяет данные", text: "Правила с открытыми формулами проходят по кампаниям каждый день." },
  { icon: ListChecks, title: "Показываем проблемы", text: "Сумма в ₽, причина, источник и уровень уверенности." },
  { icon: MessageSquareText, title: "Даём рекомендацию", text: "Конкретное действие. Решение и изменение в Директе — за вами." },
  { icon: Ruler, title: "Измеряем результат", text: "Через 7 дней сравниваем до и после и показываем эффект." },
];

export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <h2 id="how-title" className="text-[26px] font-bold tracking-tight md:text-[28px]">
        Как это работает
      </h2>
      <ol className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-full bg-brand text-sm font-bold text-on-brand">{i + 1}</span>
              <s.icon size={20} className="text-brand" />
              {i < STEPS.length - 1 && <span aria-hidden className="hidden h-px flex-1 bg-line lg:block" />}
            </div>
            <h3 className="mt-4 font-bold">{s.title}</h3>
            <p className="mt-1 text-sm text-muted">{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Transparency() {
  return (
    <section aria-labelledby="trust-title" className="mx-auto max-w-[1360px] px-4 pt-20 md:px-8">
      <div className="card grid gap-8 p-6 md:p-10 lg:grid-cols-[1fr_1.1fr]">
        <div>
          <span className="badge bg-brand-soft text-brand">Прозрачность</span>
          <h2 id="trust-title" className="mt-3 text-[26px] font-bold tracking-tight md:text-[28px]">
            Цифры считает код. AI только объясняет.
          </h2>
          <p className="mt-3 text-muted">
            Потери, CPA и рекомендации рассчитываются детерминированными правилами с открытой формулой и источником данных.
            AI-ассистент формулирует пояснения на основе этих расчётов и не меняет цифры. В AI передаются только обезличенные
            агрегаты — без названий кампаний, поисковых запросов и персональных данных. AdPilot не вносит изменения в рекламу
            автоматически: решение всегда за вами.
          </p>
        </div>
        <div className="rounded-2xl bg-surface-2 p-5">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Calculator size={16} className="text-brand" /> Пример расчёта (демо)
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
            {[
              ["CPA", "5 250 ₽"],
              ["Цель", "3 000 ₽"],
              ["Отклонение", "+75%"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-xl bg-surface p-3">
                <dt className="label">{k}</dt>
                <dd className="money mt-1 text-lg">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 rounded-xl bg-surface p-3 font-mono text-sm">floor(75 / 20) × 5% = 15% → снизить ставку на 15%</p>
          <ul className="mt-4 space-y-1.5 text-sm text-muted">
            <li className="flex items-center gap-2">
              <BadgeCheck size={15} className="text-success" /> Источник: Яндекс Директ, Яндекс Метрика
            </li>
            <li className="flex items-center gap-2">
              <BadgeCheck size={15} className="text-success" /> Период и достаточность данных указаны у каждого вывода
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

export function DemoCta() {
  return (
    <section id="audit" aria-labelledby="audit-title" className="mx-auto max-w-[1360px] scroll-mt-24 px-4 pt-20 md:px-8">
      <div className="relative overflow-hidden rounded-[24px] bg-premium p-8 text-white md:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(50% 80% at 85% 50%, rgba(57,191,160,.25), transparent 70%)" }}
        />
        <div className="relative grid items-center gap-8 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <h2 id="audit-title" className="text-[26px] font-bold tracking-tight md:text-[32px]">
              Бесплатный аудит Яндекс Директ
            </h2>
            <p className="mt-3 max-w-[560px] text-white/70">
              Первый аудит бесплатно — один на рекламный аккаунт, без привязки карты. Хотите сначала посмотреть? Откройте демо-кабинет
              с тестовыми данными без регистрации.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/signup" className="btn h-12 bg-[#39BFA0] px-6 text-[#04130f] hover:bg-[#52cfb2]">
                Запустить аудит <ArrowRight size={18} />
              </Link>
              <Link href="/demo" className="btn h-12 border border-white/25 px-6 text-white hover:border-white/60">
                <Play size={16} /> Попробовать демо
              </Link>
            </div>
          </div>
          <ul className="space-y-3 text-sm text-white/80">
            {["Полный интерфейс продукта", "Сценарии на демо-данных", "Без регистрации"].map((t) => (
              <li key={t} className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                <ShieldCheck size={16} className="text-[#39BFA0]" /> {t}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
