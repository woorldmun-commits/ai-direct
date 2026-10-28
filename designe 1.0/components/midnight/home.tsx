'use client';

import Link from 'next/link';
import Image from 'next/image';
import {useRef, useState} from 'react';
import {ArrowDown, ArrowRight, BarChart3, Check, ChevronRight, CircleHelp, Database, Fingerprint, Layers, Menu, Play, ScanLine, ShieldCheck, Target, X} from 'lucide-react';
import {BrandMark} from '@/components/brand-mark';
import {ThemeControl} from '@/components/theme-control';
import {launchPlans} from '@/components/reference/landing-pricing';
import {useDialog} from '../ix/use-dialog';
import {SapphireChart} from './chart';
import './home.css';

const plan = launchPlans[0];
const PRICE = new Intl.NumberFormat('ru-RU').format(plan.price);
const PRODUCT_VIEWS = ['Расходы', 'Рекомендации', 'Источники'];
const NAV = [['Возможности', '#benefits'], ['Как работает', '#workflow'], ['Тарифы', '#plans']] as const;
const FAQ = [
  ['Зачем INROU, если у меня уже есть Директ?', 'Директ остаётся вашим рекламным кабинетом. INROU помогает собрать расходы, рекомендации и качество источников в одну картину. Здесь удобно понять, что проверить, открыть основания и сохранить принятое решение.'],
  ['Можно посмотреть сервис без подключения рекламы?', 'Да. Прямо на этой странице открыт интерактивный пример: расходы, рекомендация и источники с синтетическими данными. Доступ к вашему рекламному аккаунту не требуется.'],
  ['Сервис сам меняет ставки и бюджеты?', 'Нет. Решения принимаете вы или ваш специалист. Подключение источников используется для чтения данных; изменения в рекламе выполняются вручную.'],
  ['Что входит в подписку?', `План «Контроль» рассчитан на один рекламный аккаунт: контроль расходов и плана, проверка свежести источников, рекомендации с основаниями. Планируемая стоимость — ${PRICE} ₽ в месяц. Оплата пока не подключена; окончательные условия публикуются в тарифах и оферте.`],
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
    <div className="home-product-caption"><span className="home-status-dot"/> ВАШ СЛЕДУЮЩИЙ РАБОЧИЙ ИНСТРУМЕНТ <span>{String(PRODUCT_VIEWS.indexOf(tab) + 1).padStart(2, '0')} / 03</span></div>
    <div className="home-product-window">
      <div className="home-product-top"><span><BrandMark size={23}/> Рабочий обзор</span><span className="home-demo-label">Демо · пример данных</span></div>
      <div className="home-preview-tabs" role="group" aria-label="Пример возможностей INROU">{PRODUCT_VIEWS.map(t => <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>)}</div>
      <div className="home-preview-content">
        {tab === 'Расходы' && <div className="home-preview-cost"><div className="home-preview-heading"><div><span>РАСХОДЫ НА РЕКЛАМУ</span><strong>248 640 <small>₽</small></strong></div><span>1–14 октября 2026<br/>Синтетический пример</span></div><SapphireChart small/><div className="home-preview-legend"><span><i/>Поиск · бренд</span><span><i/>РСЯ · каталог</span><span><i/>Поиск · категории</span><span><i/>Ретаргетинг</span></div></div>}
        {tab === 'Рекомендации' && <div className="home-preview-recommendation"><span className="home-preview-badge"><ScanLine size={14}/> Пример рекомендации</span><h3>Проверить CPA<br/>в поисковой кампании</h3><p>Перед решением — сравнить периоды, проверить конверсии и качество трафика.</p><dl><div><dt>Источник</dt><dd>Синтетический пример Директа</dd></div><div><dt>Период</dt><dd>1–14 октября 2026</dd></div><div><dt>Достаточность</dt><dd>Требует проверки</dd></div></dl><Link href="/features">Подробнее о возможностях <ArrowRight size={16}/></Link></div>}
        {tab === 'Источники' && <div className="home-preview-sources"><span className="home-preview-badge"><Database size={14}/> Контекст каждой цифры</span><h3>Доверие начинается<br/>с источника.</h3>{[['Яндекс Директ', 'Расходы и рекламные показатели'], ['Яндекс Метрика', 'Цели и контекст конверсий']].map(([name, text]) => <div key={name}><Database size={22}/><span><strong>{name}</strong><small>{text}</small></span><span className="home-source-demo">Пример</span></div>)}<p>Демонстрация интерфейса. Ваши аккаунты не подключены.</p><Link href="/integrations">Как устроено подключение <ArrowRight size={16}/></Link></div>}
      </div>
      <div className="home-product-bottom"><ShieldCheck size={15}/><span>Данные → основание → ваше решение</span><Link href="/features" aria-label="Подробнее о возможностях INROU"><ArrowRight size={18}/></Link></div>
    </div>
    <div className="home-product-note"><span><Fingerprint size={25}/></span><p><strong>Последнее слово — за вами.</strong>INROU показывает основания. Рекламу меняете вы.</p></div>
  </div>;
}

export function HomeLanding() {
  const [menu, setMenu] = useState(false);
  const [view, setView] = useState('Расходы');
  return <div className="home-redesign">
    <header className="home-header"><Brand/><nav aria-label="Основная навигация">{NAV.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}<ThemeControl/></nav><div className="home-header-actions"><Link className="home-login" href="/login">Войти</Link><Link className="home-button home-button-primary" href="#plans">Выбрать подписку <ArrowRight size={16}/></Link><button className="home-icon-button home-burger" onClick={() => setMenu(true)} aria-label="Открыть меню" aria-expanded={menu}><Menu size={23}/></button></div></header>
    {menu && <MobileMenu close={() => setMenu(false)}/>}
    <main id="ms-main" className="home-main" tabIndex={-1}>
      <section className="home-hero" aria-labelledby="home-title"><div className="home-hero-copy"><span className="home-eyebrow"><span className="home-status-dot"/> ДЛЯ СПЕЦИАЛИСТОВ И НЕБОЛЬШИХ АГЕНТСТВ</span><h1 id="home-title">Знайте, куда<br/>уходит рекламный<br/><em>бюджет.</em></h1><p className="home-lead">Расходы, изменения и рекомендации по Яндекс Директу — в одной понятной картине. Чтобы видеть, <strong>что проверить в первую очередь.</strong></p><div className="home-hero-actions"><Link className="home-button home-button-primary" href="#product-preview">Посмотреть демо <ArrowRight size={18}/></Link><Link className="home-button home-button-secondary" href="#plans">Что входит в подписку <ArrowDown size={16}/></Link></div><p className="home-hero-footnote">Демо прямо на странице, без подключения аккаунта.<br/>Планируемая подписка — от {PRICE} ₽ / месяц.</p></div><figure className="home-hero-visual"><Image src="/reference/inrou-advertising-clarity-v1.webp" width={1536} height={1024} sizes="(max-width: 959px) 100vw, 50vw" preload alt="Рекламные данные из нескольких кампаний сходятся в единую аналитическую картину и точку решения"/><figcaption>От разрозненных данных — к ясному решению.</figcaption></figure></section>
      <section className="home-context-strip" aria-label="Для кого и с чем работает INROU"><span>Ясность в рекламе.<br/><strong>Для бизнеса и агентств.</strong></span><div><span className="home-yandex-mark" aria-hidden="true">Я</span><span>Яндекс Директ<small>Расходы и кампании</small></span></div><div><BarChart3 size={27}/><span>Яндекс Метрика<small>Цели и конверсии</small></span></div><Link href="/integrations">О подключении <ArrowRight size={17}/></Link></section>

      <section className="home-section home-product-showcase"><div><span className="home-eyebrow">ПОСМОТРИТЕ, КАК УСТРОЕН INROU</span><h2>Одна картина.<br/><em>Три способа разобраться.</em></h2><p>Посмотрите расходы, откройте пример рекомендации и изучите источники. Переключайте представления — без регистрации и подключения рекламы.</p></div><ProductPreview tab={view} setTab={setView}/></section>

      <section className="home-section home-benefits" id="benefits"><div className="home-section-heading"><div><span className="home-eyebrow">МЕНЬШЕ ПОИСКА. БОЛЬШЕ ЯСНОСТИ.</span><h2>Не просто ещё один отчёт.<br/><em>Понятная точка старта.</em></h2></div><p>Когда цифр много, сложнее понять главное. INROU связывает показатели с вопросами, которые стоит проверить.</p></div><div className="home-benefit-grid">{[[BarChart3, '01', 'Видите картину расходов', 'Фактический расход, динамика и ваш план за выбранный период. Понятно, какой бюджет требует внимания.'], [Target, '02', 'Знаете, с чего начать', 'Рекомендации с приоритетом и основаниями. Откройте расчёт и ограничения, прежде чем выбирать действие.'], [Layers, '03', 'Сохраняете контекст', 'Отдельные пространства для клиентов, источники показателей и история решений. Меньше разрозненных вкладок.']].map(([Icon, n, title, text]) => {const I = Icon as typeof BarChart3; return <article key={String(n)}><div><I size={24}/><span>{String(n)}</span></div><h3>{String(title)}</h3><p>{String(text)}</p></article>;})}</div></section>

      <section className="home-section home-decision"><div className="home-decision-copy"><span className="home-eyebrow">ОТ ПОКАЗАТЕЛЯ К РЕШЕНИЮ</span><h2>Цифры привлекают внимание.<br/><em>Основания помогают решать.</em></h2><p>За рекомендацией видны источник, период, расчёт и ограничения. Вы можете разобраться в выводе, а не принимать его на веру.</p><ul><li><Check size={17}/> Понятно, что именно требует проверки</li><li><Check size={17}/> Данные отделены от оценок и гипотез</li><li><Check size={17}/> Риски доступны до принятия решения</li></ul><Link className="home-text-link" href="#product-preview" onClick={() => setView('Рекомендации')}>Разобрать пример рекомендации <ArrowRight size={18}/></Link></div><div className="home-evidence-card"><div className="home-evidence-top"><span><ScanLine size={18}/> ПАСПОРТ РЕШЕНИЯ</span><span>ПРИМЕР</span></div><h3>Что стоит проверить<br/>перед изменением рекламы?</h3><div className="home-evidence-row"><span>01</span><div><strong>Данные и период</strong><p>Сопоставимы ли интервалы? Все ли конверсии уже поступили?</p></div><Database size={19}/></div><div className="home-evidence-row"><span>02</span><div><strong>Расчёт и ограничения</strong><p>Как получен показатель? Достаточно ли данных для вывода?</p></div><BarChart3 size={19}/></div><div className="home-evidence-row"><span>03</span><div><strong>Риски и следующий шаг</strong><p>Что проверить вручную, прежде чем менять кампанию?</p></div><ShieldCheck size={19}/></div><div className="home-evidence-footer"><Fingerprint size={20}/> Решение принимаете вы.</div></div></section>

      <section className="home-control-band"><div><span className="home-eyebrow">АНАЛИТИКА БЕЗ ПОТЕРИ КОНТРОЛЯ</span><h2>Ваши кампании.<br/><em>Ваши решения.</em></h2><p>INROU анализирует доступные данные. Ставки, объявления и рекламные бюджеты остаются под вашим управлением.</p></div><ul><li><ShieldCheck size={23}/><span><strong>Без автоматических правок</strong>Изменения выполняет ваш специалист вручную.</span></li><li><Database size={23}/><span><strong>Без выдуманных показателей</strong>Недостаточные данные обозначаются явно.</span></li><li><Fingerprint size={23}/><span><strong>С историей решений</strong>Одобрение, ручное выполнение и проверка — отдельные шаги.</span></li></ul></section>

      <section className="home-section home-workflow" id="workflow"><div className="home-section-heading"><div><span className="home-eyebrow">ПОНЯТНЫЙ ПУТЬ К РАБОТЕ</span><h2>От подключения<br/><em>к осмысленным действиям.</em></h2></div><Link className="home-text-link" href="/how-it-works">Подробнее о процессе <ArrowRight size={17}/></Link></div><ol>{[['Подключите источники', 'Создайте аккаунт, подключите Директ и Метрику и выберите цель конверсии.'], ['Проверьте картину', 'Дождитесь загрузки. Посмотрите свежесть данных, расходы и основания рекомендаций.'], ['Примите решение', 'Выберите, что проверить или изменить вручную. Зафиксируйте действие и проверьте результат.']].map(([title, text], i) => <li key={title}><span>0{i + 1}</span><h3>{title}</h3><p>{text}</p></li>)}</ol></section>

      <section className="home-section home-plans" id="plans"><div className="home-plans-copy"><span className="home-eyebrow">ПОДПИСКА НА ЯСНОСТЬ</span><h2>Один аккаунт.<br/>Вся картина.<br/><em>Регулярный контроль.</em></h2><p>Для специалиста, которому нужны расходы, основания рекомендаций и история решений по проекту.</p><Link className="home-text-link" href="/pricing">Несколько проектов? Посмотрите все планы <ArrowRight size={17}/></Link></div><article className="home-plan-card"><div className="home-plan-top"><span>INROU / {plan.name}</span><span>1 рекламный аккаунт</span></div><span className="home-plan-label">Планируемая стоимость</span><div className="home-plan-price">{PRICE} <span>₽ / месяц</span></div><p>Контроль рекламы, к которому удобно возвращаться.</p><ul>{plan.features.map(f => <li key={f}><Check size={17}/>{f}</li>)}</ul><Link className="home-button home-button-primary" href="/contact">Условия закрытого пилота <ArrowRight size={18}/></Link><Link className="home-plan-demo" href="#product-preview">Сначала посмотреть демо <ChevronRight size={15}/></Link><small>Оплата пока не подключена. Цена и состав плана предварительные. Рекламный бюджет оплачивается отдельно. Экономия и рост заявок не гарантируются. <Link href="/legal/offer">Условия подписки</Link>.</small></article></section>

      <section className="home-section home-faq"><div><span className="home-eyebrow">ПЕРЕД ПЕРВЫМ ШАГОМ</span><h2>Хорошие вопросы.<br/><em>Прямые ответы.</em></h2><p><CircleHelp size={18}/> Осталось что-то уточнить?<br/><Link href="/contact">Связаться с нами <ArrowRight size={16}/></Link></p></div><div>{FAQ.map(([q, a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}</div></section>
    </main>
    <footer className="home-footer"><div><Brand/><p>Данные. Основания. Ваше решение.</p><small>INROU — независимый сервис,<br/>не аффилирован с Яндексом.</small></div><nav aria-label="Продукт"><strong>Продукт</strong><Link href="/features">Возможности</Link><Link href="/how-it-works">Как работает</Link><Link href="/pricing">Тарифы</Link><Link href="#product-preview">Демо</Link></nav><nav aria-label="Для вашей команды"><strong>Для вашей команды</strong><Link href="/business">Бизнесу</Link><Link href="/agencies">Агентствам</Link><Link href="/integrations">Источники данных</Link><Link href="/contact">Контакты</Link></nav><nav aria-label="Документы"><strong>Документы</strong><Link href="/legal/privacy">Конфиденциальность</Link><Link href="/legal/offer">Оферта</Link><Link href="/legal/requisites">Реквизиты</Link></nav></footer>
  </div>;
}
