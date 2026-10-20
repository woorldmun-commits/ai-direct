import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  ChartNoAxesColumnIncreasing,
  LayoutGrid,
  ListChecks,
  Settings2,
  Hand,
} from "lucide-react";
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
  { href: "#pricing", label: "Ранний доступ" },
];
export function Header() {
  return (
    <header className="site-header">
      <div className="site-nav">
        <Link href="/" aria-label="Rekvero — на главную">
          <Logo />
        </Link>
        <nav aria-label="Основное меню">
          {NAV.map((n) => (
            <a key={n.href} href={n.href}>
              {n.label}
            </a>
          ))}
        </nav>
        <div className="site-nav-actions">
          <Link href="/login" className="site-login">
            Войти
          </Link>
          <Link href="/signup" className="btn btn-primary">
            Начать бесплатно <ArrowUpRight size={15} />
          </Link>
        </div>
      </div>
    </header>
  );
}
export function Hero() {
  return (
    <section className="site-hero" aria-labelledby="hero-title">
      <div className="hero-copy">
        <h1 id="hero-title" className="site-title">
          Реклама под контролем.
          <br />
          <span>Решения — за вами.</span>
        </h1>
        <p className="site-lede">
          Спокойное рабочее пространство для специалиста.
          <br className="hero-desktop-break" /> Rekvero проверяет Директ и
          Метрику, находит важное
          <br className="hero-desktop-break" /> и показывает, с чего начать.
        </p>
        <div className="hero-actions">
          <Link href="/signup" className="btn site-cta">
            Проверить свой аккаунт <ArrowRight size={17} />
          </Link>
          <Link href="/demo" className="btn site-cta-secondary">
            Посмотреть демо <ArrowUpRight size={17} />
          </Link>
        </div>
        <p className="hero-note">Первый аудит бесплатно · Без привязки карты</p>
      </div>
      <ProductPreview />
      <div className="hero-integrations">
        <span>Данные из ваших привычных инструментов</span>
        <b>
          <i aria-hidden>Я</i> Яндекс Директ
        </b>
        <b>
          <ChartNoAxesColumnIncreasing
            aria-hidden
            size={23}
            className="metrika-mark"
          />{" "}
          Яндекс Метрика
        </b>
      </div>
    </section>
  );
}
function MiniMetric({
  label,
  v,
  tone,
}: {
  label: string;
  v: Value;
  tone: string;
}) {
  return (
    <div className="preview-metric">
      <p>{label}</p>
      <ValueView v={v} hint={false} className={tone} />
    </div>
  );
}
function ProductPreview() {
  const main = RECOMMENDATIONS[0];
  const today = buildToday([...RECOMMENDATIONS, ...PAST_RECOMMENDATIONS]);
  const menu = [
    { icon: LayoutGrid, label: "Обзор" },
    { icon: ListChecks, label: "Рекомендации" },
    { icon: BadgeCheck, label: "Что изменилось" },
    { icon: Settings2, label: "Интеграции" },
  ];
  return (
    <figure
      className="hero-product"
      aria-label="Интерфейс Rekvero с демонстрационными данными"
    >
      <div className="product-halo" aria-hidden />
      <div className="site-preview">
        <div className="preview-app">
          <aside className="preview-sidebar" aria-hidden>
            <Logo size={26} />
            <span className="preview-workspace">Рабочее пространство</span>
            <ul>
              {menu.map((item, i) => (
                <li key={item.label} className={i === 0 ? "active" : ""}>
                  <item.icon size={16} />
                  {item.label}
                </li>
              ))}
            </ul>
            <div className="preview-user">
              <span>А</span>
              <div>
                Алексей<small>Демо-аккаунт</small>
              </div>
            </div>
          </aside>
          <div className="preview-main">
            <div className="preview-topline">
              <span>Обзор аккаунта</span>
              <span className="preview-demo-label">Демо-данные</span>
            </div>
            <div className="preview-greeting">
              <div>
                <h2>Всё важное — перед вами</h2>
                <p>Расход, рекомендации и результат ваших решений.</p>
              </div>
              <span className="preview-period">Последние 7 дней</span>
            </div>
            <div className="preview-metrics">
              <MiniMetric
                label={EXPOSURE_SHORT}
                v={today.exposure.total}
                tone="text-danger"
              />
              <MiniMetric
                label="Можно сэкономить"
                v={today.can_save.total}
                tone="text-warning"
              />
              <MiniMetric
                label="Сэкономлено"
                v={today.saved}
                tone="text-success"
              />
            </div>
            <div className="preview-details">
              <div className="preview-recommendation">
                <span className="preview-priority">
                  Сегодня важнее всего <ArrowUpRight size={14} />
                </span>
                <h3>{main.title}</h3>
                <ValueView
                  v={main.exposure}
                  hint={false}
                  className="preview-exposure text-danger"
                />
                <p>
                  <ActionText r={main} />
                </p>
                <Link href="/demo" className="preview-action">
                  Разобрать рекомендацию <ArrowRight size={14} />
                </Link>
              </div>
              <div className="preview-chart">
                <div>
                  <p>Расход за неделю</p>
                  <ArrowUpRight size={16} />
                </div>
                <ValueView
                  v={WEEK_VALUES.spend}
                  hint={false}
                  className="preview-chart-value"
                />
                <Sparkline values={WEEK.spend} height={90} />
                <span>Демонстрационный период: 7 дней</span>
              </div>
            </div>
            <div className="preview-source">
              <Hand size={15} />
              <span>
                Изменения в Директе вносите вы. Rekvero помогает решить.
              </span>
            </div>
          </div>
        </div>
      </div>
      <figcaption>
        Интерфейс с демонстрационными данными.{" "}
        <Link href="/demo">
          Открыть демо <ArrowUpRight size={13} />
        </Link>
      </figcaption>
    </figure>
  );
}
