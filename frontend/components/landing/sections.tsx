import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { PROBLEMS, SNAPSHOT } from "@/lib/demo";

const CHECKS: { line: string; text: string; check: string; rule: string }[] = [
  {
    line: "CPA выше цели",
    text: "Конверсия обходится дороже, чем вы готовы платить.",
    check: "Сравниваем CPA кампании с вашей целью и считаем переплату в ₽.",
    rule: "bid_cpa",
  },
  {
    line: "Расход без конверсий",
    text: "Клики есть, заявок нет: бюджет уходит на площадки и группы без результата.",
    check: "Находим площадки и группы с расходом и нулём конверсий.",
    rule: "zero_conv_placements",
  },
  {
    line: "Нерелевантные запросы",
    text: "Объявления показываются по запросам, которые не приводят клиентов.",
    check: "Ищем запросы с расходом без конверсий и предлагаем минус-слова.",
    rule: "irrelevant_queries",
  },
  {
    line: "Незамеченные изменения",
    text: "CPA вырос за неделю, а в отчёте это видно только через месяц.",
    check: "Каждый день сравниваем неделю с прошлой и сообщаем о скачках.",
    rule: "week_over_week",
  },
];

export function Pains() {
  return (
    <section id="check" aria-labelledby="check-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-24 md:px-8">
      <h2 id="check-title" className="max-w-[22ch] text-[30px] leading-tight font-bold tracking-[-0.025em] text-balance md:text-[40px]">
        Где реклама чаще всего расходится с результатом
      </h2>
      <div className="mt-8 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left">
          <thead>
            <tr className="caption border-b-2 border-text">
              <th className="w-[24%] py-2 font-normal">Строка расхождения</th>
              <th className="w-[34%] py-2 font-normal">Что происходит</th>
              <th className="py-2 font-normal">Как проверяет AdPilot</th>
              <th className="py-2 text-right font-normal">Правило</th>
            </tr>
          </thead>
          <tbody>
            {CHECKS.map((c) => (
              <tr key={c.line} className="border-b border-rule align-top">
                <td className="py-5 pr-4 text-[18px] font-bold">{c.line}</td>
                <td className="py-5 pr-4 text-muted">{c.text}</td>
                <td className="py-5 pr-4">{c.check}</td>
                <td className="reqs py-5 text-right">{c.rule}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const STEPS: { title: string; text: string }[] = [
  { title: "Подключаете Директ", text: "Регистрация по email, затем Директ и Метрика через официальный вход Яндекса." },
  { title: "Код сверяет данные", text: "Правила с открытыми формулами проходят по кампаниям каждый день." },
  { title: "Видите расхождение", text: "Сумма в ₽, причина, источник, период и уровень уверенности." },
  { title: "Одобряете решение", text: "Видите «было → станет». Без вашего одобрения ничего не меняется." },
  { title: "Получаете замер", text: "Через 7 дней сравниваем расход до и после и показываем «Сэкономлено ≈»." },
];

export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-24 md:px-8">
      <h2 id="how-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[40px]">
        Порядок сверки
      </h2>
      <ol className="mt-8 grid border-t-2 border-text sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((s, i) => (
          <li key={s.title} className="border-b border-rule py-5 pr-6 lg:border-r lg:border-b-0 lg:pl-5 lg:first:pl-0 lg:last:border-r-0">
            <span className="reqs">
              шаг {i + 1} из {STEPS.length}
            </span>
            <h3 className="mt-2 text-[17px] font-bold">{s.title}</h3>
            <p className="mt-1 text-sm text-muted">{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Transparency() {
  const p = PROBLEMS[0];
  const rows: [string, string, boolean][] = [
    ["Рекомендация", p.recommendation, false],
    ["Основание", p.reason, false],
    ["Расчёт", p.calc, true],
    ["Источник", "Яндекс Директ + Яндекс Метрика", false],
    ["Снимок и правило", `#${SNAPSHOT.id} · ${p.rule}`, true],
    ["Уверенность", p.quality, false],
  ];
  return (
    <section aria-labelledby="trust-title" className="mx-auto max-w-[1280px] px-4 pt-24 md:px-8">
      <div className="grid gap-10 border-y-2 border-text py-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
        <div>
          <h2 id="trust-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] text-balance md:text-[40px]">
            Цифры считает код. AI только объясняет.
          </h2>
          <p className="mt-4 max-w-[60ch] text-muted">
            Потери и рекомендации рассчитываются детерминированными правилами с открытой формулой и источником. AI формулирует пояснение на основе этих расчётов и не
            вводит своих чисел. В AI уходят только обезличенные агрегаты — без названий кампаний, поисковых запросов и персональных данных.
          </p>
        </div>
        <div className="text-sm">
          <p className="reqs mb-2">Паспорт рекомендации · пример на демо-данных</p>
          <dl>
            {rows.map(([k, v, mono]) => (
              <div key={k} className="grid grid-cols-[9rem_1fr] gap-3 border-b border-line py-2.5">
                <dt className="text-muted">{k}</dt>
                <dd className={mono ? "font-mono" : "font-semibold"}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

export function DemoCta() {
  return (
    <section id="audit" aria-labelledby="audit-title" className="mx-auto max-w-[1280px] scroll-mt-20 px-4 pt-24 md:px-8">
      <div className="grid items-end gap-8 bg-text p-8 text-bg md:p-12 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 id="audit-title" className="text-[30px] leading-tight font-bold tracking-[-0.025em] md:text-[40px]">
            Первый аудит — бесплатно
          </h2>
          <p className="mt-3 max-w-[56ch] opacity-80">
            Один раз на рекламный кабинет, без привязки карты. Хотите сначала посмотреть? Демо-кабинет открывается без регистрации — на тестовых данных.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 lg:justify-end">
          <Link href="/signup" className="btn h-12 bg-bg px-6 text-text hover:bg-brand-soft">
            Запустить аудит <ArrowRight size={18} />
          </Link>
          <Link href="/demo" className="btn h-12 border border-current px-6">
            Демо-кабинет
          </Link>
        </div>
      </div>
    </section>
  );
}
