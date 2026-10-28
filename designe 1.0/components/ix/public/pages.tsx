import Link from 'next/link';

import {launchPlans} from '@/components/reference/landing-pricing';
import {Card, Info, LinkBtn} from '../ui';
import {PublicFrame} from './chrome';
import {HeroScene} from './hero-scene';
import {ProcessArt} from './process-art';
import {MidnightHome} from '@/components/midnight/preview';
import {FaqSearch} from './faq';

export type PublicKey = 'home' | 'features' | 'how-it-works' | 'agencies' | 'business' | 'pricing' | 'faq' | 'contact' | 'about' | 'security' | 'integrations' | 'cases' | 'blog';

// Тексты — из ранее выверенных страниц репозитория; новые страницы описывают только реализованные возможности.
const FEATURES: [string, string][] = [
  ['Картина расходов', 'Смотрите фактический расход и сравнивайте его с вашим планом. Период и источник помогают понять, откуда взялась каждая сумма.'],
  ['Список того, что проверить', 'Рекомендации показывают проблему, затронутые расходы и основание. Откройте формулу и ограничения перед решением.'],
  ['Контроль над рекламой', 'Ставки, объявления и бюджеты остаются под вашим управлением. INROU анализирует данные; изменения выполняете вы.'],
  ['Проверка качества данных', 'Видите свежесть Директа и Метрики, состояние целей и пробелы в данных. Недостающие значения не превращаются в нули.'],
  ['Порядок в проектах и решениях', 'Рабочее пространство разделяет доступ клиентов. Выдача дополнительных пространств и доступов в пилоте — через оператора; решения записываются в историю.'],
  ['Подробные отчёты', 'Недельная сводка с периодом, источниками и ограничениями. Выгрузка доступна для подтверждённых данных рабочего пространства.'],
];
const STEPS: [string, string][] = [
  ['Подключите источники', 'Войдите в INROU. Директ и Метрика подключаются отдельно от входа.'],
  ['Проверьте данные', 'Убедитесь в полноте и свежести данных выбранного периода.'],
  ['Изучите рекомендации', 'Откройте показатели, методику и ограничения перед решением.'],
  ['Примите решение', 'Проверьте последствия и примите решение. Изменения рекламы выполняются вручную.'],
  ['Проверьте результат', 'Сопоставьте фактическое изменение и показатели после действия. Непроверенное не считается подтверждённым.'],
];
const FAQ: [string, string][] = [
  ['Чем INROU полезен, если у меня уже есть Директ?', 'Директ остаётся вашим рекламным кабинетом. INROU объединяет контроль расходов, рекомендации с основаниями и проверку состояния источников — для регулярной работы с одним или несколькими проектами.'],
  ['INROU сам управляет рекламой?', 'Нет. Изменения в рекламе выполняет специалист вручную. INROU показывает показатели и основания рекомендаций.'],
  ['Какие площадки поддерживаются?', 'Текущая версия работает с Яндекс Директом и Яндекс Метрикой. VK Реклама и Авито пока не подключаются.'],
  ['Как начать анализ?', 'Создайте аккаунт, подключите Яндекс Директ и Метрику, выберите цель конверсии. Анализ появится после загрузки и проверки данных.'],
  ['Почему вместо показателя стоит «Недостаточно данных»?', 'Недоступные или недостаточные данные не заменяются нулём. Проверьте источник, период и свежесть синхронизации.'],
  ['Гарантирует ли подписка экономию бюджета?', 'Нет. Рекомендация — основание для проверки, а не гарантия экономии или роста заявок. Результат зависит от данных, рекламы и принятых вами решений.'],
  ['Можно ли уже оплатить подписку?', 'Оплата пока не подключена. На странице тарифов опубликованы планируемые цены и состав подписки. Доступ и окончательные условия появятся после завершения настройки сервиса.'],
];
const SECURITY: [string, string][] = [
  ['Изменения только вручную', 'Сервис не меняет ставки, объявления и рекламные бюджеты.'],
  ['Разделение доступа', 'Сервер проверяет доступ к рабочему пространству.'],
  ['Проверяемые основания', 'У рекомендации есть источник, период и ограничения.'],
];

const Head = ({kicker, title, lead}: {kicker?: string; title: string; lead?: string}) => <div style={{marginBottom: 20}}>{kicker && <span className="ix-eyebrow ix-pub-kicker">{kicker}</span>}<h1>{title}</h1>{lead && <p className="ix-pub-lead">{lead}</p>}</div>;
const Cards = ({items, cols}: {items: [string, string][]; cols?: 2}) => <div className={cols === 2 ? 'ix-pub-cols ix-pub-cols--2' : 'ix-pub-cols'}>{items.map(([t, x]) => <Card key={t}><h2 className="ix-h3" style={{fontSize: 16}}>{t}</h2><p className="ix-muted" style={{margin: 0}}>{x}</p></Card>)}</div>;
const Steps = () => <ol className="ix-pub-steps">{STEPS.map(([t, x], i) => <li key={t}><b>0{i + 1}</b><h2 className="ix-h3">{t}</h2><p className="ix-muted" style={{margin: 0}}>{x}</p></li>)}</ol>;
const Pricing = () => <><div className="ix-pub-cols">{launchPlans.map((p, i) => <div key={p.id} className="ix-card ix-pub-price">
  {i === 1 && <span className="ix-eyebrow">Для нескольких проектов</span>}<h2 className="ix-h3" style={{fontSize: 18, margin: 0}}>{p.name}</h2><p className="ix-muted" style={{margin: 0}}>{p.caption}</p>
  <strong style={p.id === 'control' ? undefined : {fontSize: 26}}>{p.id === 'control' ? <>{new Intl.NumberFormat('ru-RU').format(p.price)} ₽<span className="ix-muted ix-mini" style={{font: '14px Inter,sans-serif', letterSpacing: 0}}> / месяц</span></> : 'Цена согласуется'}</strong>
  <p className="ix-plan-scope">Одно рабочее пространство, до {p.accounts} {p.accounts === 1 ? 'рекламного аккаунта' : 'рекламных аккаунтов'}. Для изолированных клиентов нужны отдельные пространства; в пилоте их выдаёт оператор.</p>
  <ul>{p.features.map(f => <li key={f}>{f}</li>)}</ul><LinkBtn href="/contact" variant={i === 0 ? 'primary' : undefined}>Условия закрытого пилота</LinkBtn></div>)}</div>
  <p className="ix-muted ix-mini">Единица подписки — одно рабочее пространство. Указан лимит рекламных аккаунтов внутри него; это не число изолированных клиентов. Планируемые цены. Оплата пока не подключена. Автоматических списаний нет; после открытия регистрации — 7 дней бесплатно без карты с подтверждения аккаунта, один раз для первого рабочего пространства. Рекламный бюджет оплачивается отдельно. Подписка не гарантирует экономию или рост заявок. Условия подписки — в <Link href="/legal/offer" style={{textDecoration: 'underline'}}>договоре-оферте</Link>.</p></>;
const Security = () => <Cards items={SECURITY} />;

export function PublicPage({page}: {page: PublicKey}) {
  if(page==='home')return <MidnightHome/>;
  const body = (() => {
    switch (page) {
      case 'features': return <><section className="ix-editorial-split"><div><Head kicker="Возможности" title="От расходов к обоснованному решению" lead="Контроль рекламы начинается с понятных данных." /><div className="ix-feature-rows">{FEATURES.slice(0, 3).map(([title, description], i) => <div key={title}><span aria-hidden="true">{['◎', '▤', '◇'][i]}</span><div><h2>{title}</h2><p>{description}</p></div></div>)}</div><div className="ix-actions" style={{marginTop: 24}}><LinkBtn variant="primary" href="/#product-preview">Посмотреть интерфейс</LinkBtn><LinkBtn href="/methodology">Как проверяются рекомендации</LinkBtn></div></div><HeroScene /></section><section><h2>Источники, проекты и история</h2><Cards items={FEATURES.slice(3)} /><p className="ix-muted">Узнайте <Link href="/integrations">о подключении источников</Link> и <Link href="/agencies">работе с клиентскими пространствами</Link>. Для продолжения работы <Link href="/login">войдите в кабинет</Link>.</p></section></>;
      case 'how-it-works': return <><section className="ix-editorial-split ix-process"><div><Head title="Простой и понятный процесс" lead="Пять шагов от источника до проверки результата." /><Steps /><div className="ix-actions"><LinkBtn variant="primary" href="/signup">Начать настройку</LinkBtn></div></div><ProcessArt /></section><section><p><Link href="/methodology">Методики и ограничения рекомендаций →</Link></p><Info>Одобрение решения, ручное выполнение и проверка результата — отдельные шаги с записью в историю. Автоматического применения изменений нет.</Info></section></>;
      case 'agencies': return <section className="ix-benefit-page ix-agency-page"><Head kicker="Агентствам" title="Больше клиентов. Меньше рутины." lead="Для специалистов и агентств с портфелем проектов." /><ul>{['Отдельные рабочие пространства для клиентов', 'Рекомендации и основания в одном контуре', 'Роли и серверная проверка доступа', 'Контроль свежести и качества источников', 'Прозрачная история ручных решений'].map(t => <li key={t}><span aria-hidden="true">✓</span>{t}</li>)}</ul><div className="ix-actions"><LinkBtn variant="primary" href="/pricing">Посмотреть условия</LinkBtn></div><p className="ix-mini ix-muted">В пилоте дополнительные пространства и доступы выдаёт оператор. Подписка относится к одному пространству; лимит аккаунтов не разделяет права между клиентами. Оплата пока не подключена.</p></section>;
      case 'business': return <section className="ix-benefit-page"><Head kicker="Бизнесу" title="Простые решения для роста продаж" lead="Понятно, что происходит с рекламным бюджетом." /><ul>{['Фактический расход и план за один период', 'Показатели с источниками и ограничениями', 'Персональная область рекомендаций', 'Контроль качества и свежести данных', 'Решения и изменения под вашим управлением'].map(t => <li key={t}><span aria-hidden="true">✓</span>{t}</li>)}</ul><div className="ix-actions"><LinkBtn variant="primary" href="/signup">Создать аккаунт</LinkBtn></div><p className="ix-mini ix-muted">Экономия и рост заявок не гарантируются. Изменения рекламы выполняются вручную.</p></section>;
      case 'pricing': return <><Head title="Тарифы" lead="Выберите количество рекламных аккаунтов." /><Pricing /></>;
      case 'faq': return <><Head title="Часто задаваемые вопросы" lead="Всё, что нужно знать перед подключением." /><FaqSearch items={FAQ} /></>;
      case 'cases': return <><Head title="Кейсы INROU" lead="Результаты публикуются с источниками, периодом и разрешением клиента." /><Card><h2>Подтверждённые кейсы готовятся</h2><p className="ix-muted">Клиентские показатели пока не опубликованы. С устройством продукта можно познакомиться в отдельном демонстрационном режиме.</p><LinkBtn href="/#product-preview">Посмотреть демо</LinkBtn></Card></>;
      case 'blog': return <><Head title="Журнал INROU" lead="Практика доказательной рекламной аналитики." /><Cards items={[["Как устроена проверка", "Источник, период, расчёт и ограничения — основа каждого решения."], ["Подключение источников", "Директ и Метрика подключаются отдельно от входа в INROU."]]} cols={2} /><div className="ix-actions" style={{marginTop: 20}}><LinkBtn href="/how-it-works">Как это работает</LinkBtn><LinkBtn href="/faq">Вопросы и ответы</LinkBtn></div><p className="ix-muted ix-mini">Редакционные публикации пока не выпущены. Здесь доступны руководства по работе с продуктом.</p></>;
      case 'contact': return <><Head title="Связаться с нами" lead="Закрытый пилот INROU." /><Card><h2>Контакт будет опубликован</h2><p role="status">Заглушка: приём заявок на пилот пока не открыт. Email и форма появятся после утверждения контакта владельцем.</p><p className="ix-muted">Сейчас можно изучить демонстрационный пример, условия тарифов и справку. Эта страница не отправляет заявку.</p><div className="ix-actions"><LinkBtn variant="primary" href="/#product-preview">Посмотреть продукт</LinkBtn><LinkBtn href="/pricing">Условия тарифов</LinkBtn><LinkBtn href="/faq">Открыть справку</LinkBtn><LinkBtn href="/legal/requisites">Реквизиты и контакты</LinkBtn></div></Card></>;
      case 'about': return <><Head kicker="О компании" title="Данные. Основания. Ваше решение." lead="INROU — независимый сервис контроля рекламных расходов. Не аффилирован с Яндексом." /><Cards items={[['Evidence first', 'Каждый вывод — источник, период, формула и ограничения.'], ['Честные состояния', 'Недоступное не заменяется нулём; оценка не выдаётся за факт.'], ['Человек решает', 'Никаких автоматических изменений в рекламных кабинетах.']]} /><p className="ix-muted ix-mini">Сведения о команде и реквизиты публикуются после их утверждения.</p></>;
      case 'security': return <><Head title="Безопасность" lead="Контроль доступа и прозрачность решений." /><Security /><div className="ix-actions" style={{marginTop: 18}}><LinkBtn href="/legal">Документы</LinkBtn></div></>;
      case 'integrations': return <><Head title="Источники данных" lead="Прозрачный статус каждой площадки. Директ и Метрика — источники текущей версии." /><Cards items={[['Яндекс Директ', 'Поддерживается. Подключается отдельно от входа, доступ только для чтения.'], ['Яндекс Метрика', 'Поддерживается. Используется для целей и конверсий.'], ['VK Реклама', 'В разработке. Подключение недоступно.'], ['Авито', 'В разработке. Подключение недоступно.']]} cols={2} /></>;
    }
  })();
  return <PublicFrame>{body}</PublicFrame>;
}

