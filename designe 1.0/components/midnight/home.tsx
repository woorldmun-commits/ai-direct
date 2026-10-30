'use client';

import Link from 'next/link';
import Image from 'next/image';
import {useRef, useState} from 'react';
import {ArrowDown, ArrowRight, BarChart3, Check, CircleHelp, Database, Fingerprint, Menu, Play, ScanLine, ShieldCheck, X} from 'lucide-react';
import {BrandMark} from '@/components/brand-mark';
import {ThemeControl} from '@/components/theme-control';
import {launchPlans} from '@/components/reference/landing-pricing';
import {useDialog} from '../ix/use-dialog';
import {SapphireChart} from './chart';
import {FeatureBento, TrustBento} from './feature-bento';
import {DemoMetrics} from '../ix/demo-metrics';
import {PricingPlans} from './pricing-plans';
import {OrbitFeatures} from './orbit-features';
import {ProductTour} from '../ix/product-tour';
import {FooterMeta} from '../ix/public/footer-meta';
import './home.css';
import {DEFAULT_PUBLIC_START, type PublicStart} from '@/lib/public-start';

const plan = launchPlans[0];
const PRICE = new Intl.NumberFormat('ru-RU').format(plan.price);
const PRODUCT_VIEWS = ['Расходы', 'Рекомендации', 'Источники', 'Бюджет и заявки'];
const NAV = [['Возможности', '#benefits'], ['Как работает', '#workflow'], ['Тарифы', '#plans']] as const;
const FAQ = [
  ['Зачем INROU, если у меня уже есть Директ?', 'Директ остаётся вашим рекламным кабинетом. INROU помогает собрать расходы, рекомендации и качество источников в одну картину. Здесь удобно понять, что проверить, открыть основания и сохранить принятое решение.'],
  ['Можно посмотреть сервис без подключения рекламы?', 'Да. Прямо на этой странице открыт интерактивный пример: расходы, рекомендация и источники с синтетическими данными. Доступ к вашему рекламному аккаунту не требуется.'],
  ['Сервис сам меняет ставки и бюджеты?', 'Нет. Решения принимаете вы или ваш специалист. Подключение источников используется для чтения данных; изменения в рекламе выполняются вручную.'],
  ['Что входит в подписку?', `План «Контроль» рассчитан на один рекламный аккаунт: контроль расходов и плана, проверка свежести источников, рекомендации с основаниями. Стоимость — ${PRICE} ₽ за 30 дней. Оплата пока не подключена; окончательные условия публикуются в тарифах и оферте.`],
  ['Подходит для агентства или нескольких клиентов?', 'Для нескольких проектов предусмотрены отдельные рабочие пространства и планы с разным количеством аккаунтов. Их состав и статус цен смотрите на странице тарифов.'],
] as const;

function Brand() {
  return <Link className="home-brand" href="/" aria-label="INROU — главная"><BrandMark size={36}/><span>INROU</span></Link>;
}

function MobileMenu({close}: {close: () => void}) {
  const panel = useRef<HTMLDivElement>(null);
  useDialog(true, panel, close);
  return <div className="home-menu-backdrop" onClick={close}><div ref={panel} className="home-menu" role="dialog" aria-modal="true" aria-label="Навигация" onClick={e => e.stopPropagation()}><div><Brand/><button className="home-icon-button" onClick={close} aria-label="Закрыть меню"><X size={22}/></button></div><nav>{NAV.map(([label, href]) => <Link key={href} href={href} onClick={close}>{label}<ArrowRight size={18}/></Link>)}<Link href="/login">Войти<ArrowRight size={18}/></Link><Link href="#product-preview" onClick={close}>Посмотреть демо<Play size={18}/></Link><ThemeControl/></nav></div></div>;
}

function ProductPreview({tab, setTab}: {tab: string; setTab: (tab: string) => void}) {
  return <div className="home-product-stage" id="product-preview">
    <div className="home-product-caption"><span className="home-status-dot"/> ВАШ СЛЕДУЮЩИЙ РАБОЧИЙ ИНСТРУМЕНТ <span>{String(PRODUCT_VIEWS.indexOf(tab) + 1).padStart(2, '0')} / 04</span></div>
    <div className="home-product-window">
      <div className="home-product-top"><span><BrandMark size={23}/> Рабочий обзор</span><span className="home-demo-label">Демо · пример данных</span></div>
      <div className="home-preview-tabs" role="group" aria-label="Пример возможностей INROU">{PRODUCT_VIEWS.map(t => <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>)}</div>
      <div className="home-preview-content">
        {tab === 'Бюджет и заявки' && <div className="ix home-metrics-preview"><DemoMetrics/></div>}
        {tab === 'Расходы' && <div className="home-preview-cost"><div className="home-preview-heading"><div><span>РАСХОДЫ НА РЕКЛАМУ</span><strong>248 640 <small>₽</small></strong></div><span>1–14 октября 2026<br/>Синтетический пример</span></div><SapphireChart small/><div className="home-preview-legend"><span><i/>Поиск · бренд</span><span><i/>РСЯ · каталог</span><span><i/>Поиск · категории</span><span><i/>Ретаргетинг</span></div></div>}
        {tab === 'Рекомендации' && <div className="home-preview-recommendation"><span className="home-preview-badge"><ScanLine size={14}/> Пример рекомендации</span><h3>Проверить CPA<br/>в поисковой кампании</h3><p>Перед решением — сравнить периоды, проверить конверсии и качество трафика.</p><dl><div><dt>Источник</dt><dd>Синтетический пример Директа</dd></div><div><dt>Период</dt><dd>1–14 октября 2026</dd></div><div><dt>Достаточность</dt><dd>Требует проверки</dd></div></dl><Link href="/features">Подробнее о возможностях <ArrowRight size={16}/></Link></div>}
        {tab === 'Источники' && <div className="home-preview-sources"><span className="home-preview-badge"><Database size={14}/> Контекст каждой цифры</span><h3>Доверие начинается<br/>с источника.</h3>{[['Яндекс Директ', 'Расходы и рекламные показатели'], ['Яндекс Метрика', 'Цели и контекст конверсий']].map(([name, text]) => <div key={name}><Database size={22}/><span><strong>{name}</strong><small>{text}</small></span><span className="home-source-demo">Пример</span></div>)}<p>Демонстрация интерфейса. Ваши аккаунты не подключены.</p><Link href="/integrations">Как устроено подключение <ArrowRight size={16}/></Link></div>}
      </div>
      <div className="home-product-bottom"><ShieldCheck size={15}/><span>Данные → основание → ваше решение</span><Link href="/features" aria-label="Подробнее о возможностях INROU"><ArrowRight size={18}/></Link></div>
    </div>
    <div className="home-product-note"><span><Fingerprint size={25}/></span><p><strong>Последнее слово — за вами.</strong>INROU показывает основания. Рекламу меняете вы.</p></div>
  </div>;
}

export function HomeLanding({start = DEFAULT_PUBLIC_START}: {start?: PublicStart}) {
  const [menu, setMenu] = useState(false);
  const [view, setView] = useState('Расходы');
  return <div className="home-redesign">
    <header className="home-header"><Brand/><nav aria-label="Основная навигация">{NAV.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}<ThemeControl/></nav><div className="home-header-actions"><Link className="home-login" href="/login">Войти</Link><Link className="home-button home-button-primary" href="#plans">Выбрать подписку <ArrowRight size={16}/></Link><button className="home-icon-button home-burger" onClick={() => setMenu(true)} aria-label="Открыть меню" aria-expanded={menu}><Menu size={23}/></button></div></header>
    {menu && <MobileMenu close={() => setMenu(false)}/>}
    <main id="ms-main" className="home-main" tabIndex={-1}>
      <section className="home-hero" aria-labelledby="home-title"><div className="home-hero-copy"><div className="home-announcement"><ProductTour label="Как начать · 4 шага" start={start}/></div><span className="home-eyebrow"><span className="home-status-dot"/> ДЛЯ СПЕЦИАЛИСТОВ И НЕБОЛЬШИХ АГЕНТСТВ</span><h1 id="home-title">Знайте, куда<br/>уходит рекламный<br/><em>бюджет.</em></h1><p className="home-lead">Расходы, изменения и рекомендации по Яндекс Директу — в одной понятной картине. Чтобы видеть, <strong>что проверить в первую очередь.</strong></p><div className="home-hero-actions"><Link className="home-button home-button-primary" href="#product-preview">Посмотреть демо <ArrowRight size={18}/></Link><Link className="home-button home-button-secondary" href="#plans">Что входит в подписку <ArrowDown size={16}/></Link></div><p className="home-hero-footnote">Демо прямо на странице, без подключения аккаунта.<br/>Подписка — от {PRICE} ₽ / 30 дней.</p></div><figure className="home-hero-visual"><Image src="/reference/inrou-advertising-clarity-v1.webp" width={1536} height={1024} sizes="(max-width: 959px) 100vw, 50vw" preload alt="Рекламные данные из нескольких кампаний сходятся в единую аналитическую картину и точку решения"/><div className="home-hero-glass"><span><ShieldCheck size={15}/> КОНТЕКСТ КАЖДОЙ ЦИФРЫ</span><strong>Сначала основания.<br/>Затем решение.</strong><ul><li><Check size={13}/>Источник</li><li><Check size={13}/>Период</li><li><Check size={13}/>Ограничения</li><li><Check size={13}/>Ручное действие</li></ul></div><figcaption>От разрозненных данных — к ясному решению.</figcaption></figure></section>
      <section className="home-context-strip" aria-label="Для кого и с чем работает INROU"><span>Ясность в рекламе.<br/><strong>Для бизнеса и агентств.</strong></span><div><span className="home-yandex-mark" aria-hidden="true">Я</span><span>Яндекс Директ<small>Расходы и кампании</small></span></div><div><BarChart3 size={27}/><span>Яндекс Метрика<small>Цели и конверсии</small></span></div><Link href="/integrations">О подключении <ArrowRight size={17}/></Link></section>

      <section className={`home-section home-product-showcase${view === 'Бюджет и заявки' ? ' home-product-showcase--expanded' : ''}`}><div><span className="home-eyebrow">ПОСМОТРИТЕ, КАК УСТРОЕН INROU</span><h2>Одна картина.<br/><em>Четыре способа разобраться.</em></h2><p>Посмотрите расходы, сравните план и факт, откройте пример рекомендации и изучите источники. Переключайте представления — без регистрации и подключения рекламы.</p></div><ProductPreview tab={view} setTab={setView}/></section>

      <FeatureBento onPreview={setView}/>

      <section className="home-section home-orbit-section" id="data-workflow"><div className="home-section-heading"><div><span className="home-eyebrow">ОТ ПОКАЗАТЕЛЯ К РЕШЕНИЮ</span><h2>Разрозненные данные.<br/><em>Связанные основания.</em></h2></div><p>Выберите источник и исследуйте учебный исторический ряд. Понятно, откуда берётся показатель и что проверить перед действием.</p></div><OrbitFeatures/></section>

      <TrustBento/>

      <section className="home-section home-workflow" id="workflow"><div className="home-section-heading"><div><span className="home-eyebrow">ПОНЯТНЫЙ ПУТЬ К РАБОТЕ</span><h2>От подключения<br/><em>к осмысленным действиям.</em></h2></div><Link className="home-text-link" href="/how-it-works">Подробнее о процессе <ArrowRight size={17}/></Link></div><ol>{[['Подключите источники', 'Создайте аккаунт, подключите Директ и Метрику и выберите цель конверсии.'], ['Проверьте картину', 'Дождитесь загрузки. Посмотрите свежесть данных, расходы и основания рекомендаций.'], ['Примите решение', 'Выберите, что проверить или изменить вручную. Зафиксируйте действие и проверьте результат.']].map(([title, text], i) => <li key={title}><span>0{i + 1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol></section>

      <section className="home-section home-pricing-section" id="plans"><div className="home-section-heading"><div><span className="home-eyebrow">ПОДПИСКА НА ЯСНОСТЬ</span><h2>Выберите масштаб.<br/><em>Сохраните контроль.</em></h2></div><p>«Контроль» и «Бизнес» — одно пространство. «Агентство» — до пяти пространств и до 15 аккаунтов суммарно. Сравните состав; тариф выбирается в кабинете.</p></div><PricingPlans start={start}/>{!start.registrationReady&&<p role="status">Самостоятельная регистрация готовится к запуску. Сейчас доступно демо{start.contactEmail?' и обсуждение подключения по почте.':'.'}</p>}</section>

      <section className="home-section home-faq"><div><span className="home-eyebrow">ПЕРЕД ПЕРВЫМ ШАГОМ</span><h2>Хорошие вопросы.<br/><em>Прямые ответы.</em></h2><p><CircleHelp size={18}/> Осталось что-то уточнить?<br/><Link href="/contact">Связаться с нами <ArrowRight size={16}/></Link></p></div><div>{FAQ.map(([q, a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}</div></section>
    </main>
    <footer className="home-footer"><div><Brand/><p>Данные. Основания. Ваше решение.</p><small>INROU — независимый сервис,<br/>не аффилирован с Яндексом.</small></div><nav aria-label="Продукт"><strong>Продукт</strong><Link href="/features">Возможности</Link><Link href="/how-it-works">Как работает</Link><Link href="/pricing">Тарифы</Link><Link href="#product-preview">Демо</Link></nav><nav aria-label="Для вашей команды"><strong>Для вашей команды</strong><Link href="/business">Бизнесу</Link><Link href="/agencies">Агентствам</Link><Link href="/integrations">Источники данных</Link><Link href="/contact">Контакты</Link></nav><nav aria-label="Документы"><strong>Документы</strong><Link href="/legal/privacy">Конфиденциальность</Link><Link href="/legal/offer">Оферта</Link><Link href="/legal/requisites">Реквизиты</Link></nav><FooterMeta/></footer>
  </div>;
}
