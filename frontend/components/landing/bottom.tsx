import { ArrowUpRight, Check, Plus } from "lucide-react";
import Link from "next/link";
import { CookieSettingsButton } from "@/components/cookie-banner";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";

const PLANS=[
  {name:"Первый аудит",price:"0 ₽",note:"Один раз на рекламный аккаунт",features:["Проверка Директа и Метрики","Находки с формулами и источниками","Понятные рекомендации"],highlight:true},
  {name:"Мониторинг",price:"Скоро",note:"Стоимость ещё не утверждена",features:["Регулярная проверка рекламы","История решений и сверка изменений","Сравнение до и после"],highlight:false},
  {name:"Ваш бизнес",price:"Скоро",note:"Для нескольких рекламных аккаунтов",features:["Ваши кабинеты в одном пространстве","Общий обзор и приоритеты","Доказательства у каждого решения"],highlight:false},
];
export function Pricing() {
  return <section id="pricing" className="studio-section" aria-labelledby="pricing-title"><div className="studio-section-heading"><h2 id="pricing-title">Начните с ясности.<br /><span>Первый аудит — бесплатно.</span></h2></div><div className="studio-pricing-grid">{PLANS.map(p=><article className={`studio-plan ${p.highlight?"highlight":""}`} key={p.name}><h3>{p.name}</h3><p className="studio-plan-price">{p.price}</p><small>{p.note}</small><ul>{p.features.map(f=><li key={f}><Check size={15}/>{f}</li>)}</ul><Link href="/signup" className="btn btn-secondary h-11">Начать бесплатно <ArrowUpRight size={15}/></Link></article>)}</div><p className="studio-pricing-note">Цены платных тарифов будут опубликованы после утверждения. Автоматические списания здесь не подключены.</p></section>;
}
export const FAQ=[
  {q:"Что AdPilot проверяет в рекламе?",a:"Кампании без конверсий, превышение целевого CPA и площадки РСЯ с расходом без конверсий. Находка появляется при достаточности данных; сумма имеет формулу, период и источник."},
  {q:"Будет ли сервис сам менять рекламу?",a:"Нет. Вы принимаете решение и вносите изменения вручную в Яндекс Директе. AdPilot фиксирует решение, сверяет изменение и сравнивает результат до и после."},
  {q:"Какие данные нужно подключить?",a:"Яндекс Директ — для расходов и параметров рекламы, Яндекс Метрику — для целей и конверсий. Полезно указать допустимую стоимость обращения. При недостатке данных сервис покажет причину."},
  {q:"Что получает AI-аналитик?",a:"Только обезличенные агрегаты. Названия кампаний, тексты запросов, персональные данные и токены ему не передаются. Числа рассчитывает код; AI только объясняет."},
  {q:"Можно ли сначала посмотреть без регистрации?",a:"Да. Демо-кабинет показывает весь интерфейс на явно обозначенных демонстрационных данных. В нём можно исследовать рекомендации, формулы, историю и состояния без подключения вашей рекламы."},
  {q:"Вы гарантируете экономию бюджета?",a:"Нет. Мы показываем признаки неэффективности на данных и помогаем проверить эффект решений. Сравнение до и после является оценкой, без контрольной группы; результат зависит от рынка и ваших действий."},
];
export function Faq() {
  return <section id="faq" className="studio-section studio-faq" aria-labelledby="faq-title"><div className="studio-section-heading"><h2 id="faq-title">Хорошие<br /><span>вопросы.</span></h2><p className="mt-6 text-sm text-muted">Честные ответы.<br />До первого подключения.</p></div><div>{FAQ.map(f=><details key={f.q}><summary>{f.q}<Plus size={19}/></summary><p>{f.a}</p></details>)}</div></section>;
}
export function FinalCta() {
  return <section className="studio-section studio-final" aria-labelledby="final-title"><div><h2 id="final-title">Верните рекламе<br /><span>ясный курс.</span></h2><p>Ваши данные. Проверяемые выводы. Ваше решение.</p></div><Link href="/signup" className="btn btn-primary h-14 px-8">Начать бесплатно <ArrowUpRight size={19}/></Link></section>;
}
export function Footer() {
  return <footer className="studio-footer"><div className="studio-footer-top"><div><Link href="/" aria-label="AdPilot — на главную"><Logo size={34}/></Link><p className="mt-4 text-xs text-muted">Доказательный контроль рекламного бюджета.</p></div><nav aria-label="Документы">{LEGAL_DOCS.map(d=><Link key={d.slug} href={`/legal/${d.slug}`}>{d.title}</Link>)}<CookieSettingsButton className="text-left"/></nav></div><div className="studio-footer-bottom"><span>© 2026 AdPilot</span><p>Независимый сервис. Не является продуктом Яндекса и не аффилирован с ним. «Яндекс Директ» и «Яндекс Метрика» — товарные знаки их правообладателя.</p></div></footer>;
}
