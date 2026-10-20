import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  Check,
  MousePointerClick,
  Target,
  Network,
  Link2,
  ListChecks,
  Hand,
  Ruler,
} from "lucide-react";
import Link from "next/link";
const CHECKS = [
  {
    title: "Расход есть. Конверсий нет.",
    text: "Rekvero выделяет кампании с расходом и нулём конверсий. Если кликов и дней недостаточно для вывода, вы увидите это сразу.",
    icon: MousePointerClick,
  },
  {
    title: "Заявка дороже вашей цели.",
    text: "Увидьте, где CPA выше целевого или базового значения. Получите отклонение, оценку неэффективного расхода в рублях и рекомендацию.",
    icon: Target,
  },
  {
    title: "Площадки забирают бюджет.",
    text: "Получите список площадок РСЯ с расходом и нулём конверсий. Проверьте данные и решите, какие площадки стоит исключить.",
    icon: Network,
  },
];
export function Pains() {
  return (
    <section
      id="features"
      aria-labelledby="pains-title"
      className="premium-section feature-section"
    >
      <div className="section-intro">
        <h2 id="pains-title">
          Три проверки.
          <br />
          <span>Меньше слепых зон.</span>
        </h2>
        <div>
          <p>
            Rekvero помогает директологам и агентствам найти расход с признаками
            неэффективности в Яндекс Директе. Сначала — важное в рублях, затем —
            данные и конкретное действие.
          </p>
          <Link href="/demo" className="text-link">
            Посмотреть рекомендации <ArrowUpRight size={17} />
          </Link>
        </div>
      </div>
      <div className="feature-rows">
        {CHECKS.map((c) => (
          <article key={c.title}>
            <c.icon size={22} className="feature-number" aria-hidden />
            <h3>{c.title}</h3>
            <p>{c.text}</p>
            <Check size={20} aria-hidden />
          </article>
        ))}
      </div>
      <p className="feature-footnote">
        В общем обзоре клиентских кабинетов видно, чему уделить внимание первым.
        Каждая оценка сопровождается источником и формулой.
      </p>
    </section>
  );
}
const STEPS = [
  {
    icon: Link2,
    title: "Подключите данные",
    text: "Директ и Метрика через официальный OAuth Яндекса. Без передачи паролей.",
  },
  {
    icon: ListChecks,
    title: "Разберите важное",
    text: "Три правила проверяют кампании. Вы получаете причину, сумму и источник вывода.",
  },
  {
    icon: Hand,
    title: "Примите решение",
    text: "Проверьте рекомендацию и внесите изменение в Директе вручную.",
  },
  {
    icon: Ruler,
    title: "Посмотрите эффект",
    text: "Rekvero сверит изменение и через 7 дней сравнит данные до и после.",
  },
];
export function HowItWorks() {
  return (
    <section
      id="how"
      aria-labelledby="how-title"
      className="premium-section workflow-section"
    >
      <div className="section-intro">
        <h2 id="how-title">
          От данных
          <br />к решению.
        </h2>
        <p>
          Один рабочий процесс вместо разрозненных отчётов.
          <br />
          Вы сохраняете контроль.
        </p>
      </div>
      <ol className="workflow-steps">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <div className="workflow-step-top">
              <s.icon size={24} />
              <span>0{i + 1}</span>
            </div>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
export function Transparency() {
  return (
    <section
      aria-labelledby="trust-title"
      className="premium-section transparency-section"
    >
      <div className="transparency-copy">
        <h2 id="trust-title">
          Не просто совет.
          <br />
          Доказательство.
        </h2>
        <p>
          У каждой цифры — формула. У каждого вывода — источник и период.
          Расчёты выполняет код, а AI помогает объяснить их человеческим языком.
        </p>
        <p>
          Ассистент получает обезличенные агрегаты. Названия кампаний, поисковые
          запросы и персональные данные в AI не передаются.
        </p>
        <div className="transparency-principle">
          <BadgeCheck size={19} />
          Ставки и кампании меняете только вы.
        </div>
      </div>
      <div className="calculation-sheet">
        <div className="calculation-heading">
          <span>Пример расчёта</span>
          <span className="preview-demo-label">Демо</span>
        </div>
        <h3>CPA выше целевого</h3>
        <dl>
          <div>
            <dt>Стоимость конверсии</dt>
            <dd>5 250 ₽</dd>
          </div>
          <div>
            <dt>Целевой CPA</dt>
            <dd>3 000 ₽</dd>
          </div>
          <div className="calculation-result">
            <dt>Отклонение от цели</dt>
            <dd>+75%</dd>
          </div>
        </dl>
        <div className="calculation-formula">
          <span>Открытая формула</span>
          <code>floor(75 / 20) × 5% = 15%</code>
          <p>Рекомендация: снизить ставку на 15%</p>
        </div>
        <p className="calculation-source">
          <BadgeCheck size={15} />
          Источник: Директ + Метрика
        </p>
      </div>
    </section>
  );
}
export function DemoCta() {
  return (
    <section
      id="audit"
      aria-labelledby="audit-title"
      className="premium-section audit-section"
    >
      <div>
        <h2 id="audit-title">Что стоит проверить в вашем кабинете?</h2>
        <p>
          Подключите Директ и Метрику — получите первый аудит бесплатно.
          <br />
          Найденные проблемы, причины и рекомендации — в одном обзоре.
        </p>
      </div>
      <div className="audit-actions">
        <Link href="/signup" className="btn site-cta">
          Проверить мой Директ <ArrowRight size={17} />
        </Link>
        <Link href="/demo" className="text-link">
          Сначала посмотреть демо <ArrowUpRight size={17} />
        </Link>
        <small>Один бесплатный аудит на аккаунт · без карты</small>
      </div>
    </section>
  );
}
