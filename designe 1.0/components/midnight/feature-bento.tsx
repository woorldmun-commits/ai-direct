import Link from 'next/link';
import {ArrowRight, BarChart3, Check, Database, Fingerprint, History, ShieldCheck, Smartphone, Target} from 'lucide-react';

export function FeatureBento({onPreview}: {onPreview: (view: string) => void}) {
  return <section className="home-section home-capabilities" id="benefits" aria-labelledby="capabilities-title">
    <div className="home-section-heading"><div><span className="home-eyebrow">ОТ ОБЩЕЙ КАРТИНЫ К ДЕТАЛЯМ</span><h2 id="capabilities-title">Каждой цифре — контекст.<br/><em>Каждому решению — основание.</em></h2></div><p>Расходы, качество данных и история решений связаны между собой. Выберите, с чего начать разбор.</p></div>
    <div className="home-feature-bento">
      <article className="home-feature-card home-feature-budget"><div className="home-feature-icon"><Target size={22}/><span>01 / БЮДЖЕТ</span></div><h3>Держите расходы<br/>в поле зрения.</h3><p>Факт, ваш план и отклонение за один период. Без обещаний экономии.</p><div className="home-mini-budget" aria-label="Учебный пример: расход 248 640 рублей, план 300 000 рублей"><span>СИНТЕТИЧЕСКИЙ ПРИМЕР</span><strong>248 640 <small>₽</small></strong><div><i/><i/></div><dl><div><dt>План</dt><dd>300 000 ₽</dd></div><div><dt>Факт минус план</dt><dd>−51 360 ₽</dd></div></dl></div><a href="#product-preview" onClick={() => onPreview('Бюджет и заявки')}>Посмотреть план / факт <ArrowRight size={17}/></a></article>
      <article className="home-feature-card home-feature-data"><div className="home-feature-icon"><Database size={21}/><span>02 / ИСТОЧНИКИ</span></div><h3>Проверяйте данные.</h3><p>Источник, период и свежесть доступны до принятия решения.</p><div className="home-mini-sources"><span><i/>Яндекс Директ</span><span><i/>Яндекс Метрика</span><small>Поддерживаемые источники</small></div><a href="#product-preview" onClick={() => onPreview('Источники')}>Разобрать источники <ArrowRight size={16}/></a></article>
      <article className="home-feature-card home-feature-reason"><div className="home-feature-icon"><BarChart3 size={21}/><span>03 / ОСНОВАНИЯ</span></div><h3>Понимайте рекомендацию.</h3><p>Изучите расчёт, ограничения и риск перед ручным действием.</p><div className="home-mini-evidence"><span><Check size={14}/>Источник и период</span><span><Check size={14}/>Расчёт и ограничения</span><span><Check size={14}/>Риски и следующий шаг</span></div><a href="#product-preview" onClick={() => onPreview('Рекомендации')}>Открыть пример <ArrowRight size={16}/></a></article>
      <article className="home-feature-card home-feature-history"><div className="home-feature-icon"><History size={21}/><span>04 / ИСТОРИЯ</span></div><h3>Сохраняйте ход решения.</h3><p>Одобрение, ручное выполнение и проверка результата — отдельные шаги.</p><div className="home-mini-timeline" aria-hidden="true"><span>Решение</span><i/><span>Выполнение</span><i/><span>Проверка</span></div><Link href="/how-it-works">Как устроен процесс <ArrowRight size={16}/></Link></article>
      <article className="home-feature-card home-feature-mobile"><div className="home-feature-icon"><Smartphone size={21}/><span>05 / ДОСТУП</span></div><h3>Возвращайтесь с телефона.</h3><p>Карточки, источники и рекомендации адаптируются к небольшому экрану.</p><div className="home-mini-phone" aria-hidden="true"><div/><span/><span/><span/></div><a href="#product-preview" onClick={() => onPreview('Расходы')}>Посмотреть интерфейс <ArrowRight size={16}/></a></article>
    </div>
  </section>;
}

export function TrustBento() {
  return <section className="home-section home-trust" aria-labelledby="trust-title"><div className="home-section-heading"><div><span className="home-eyebrow">КОНТРОЛЬ ОСТАЁТСЯ У ВАС</span><h2 id="trust-title">Прозрачно на каждом шаге.</h2></div><p>Важны не только показатели, но и то, как они получены и что вы решаете с ними делать.</p></div><div className="home-stats-bento">
    <article className="home-trust-main"><Fingerprint size={27}/><span>ВАШИ КАМПАНИИ</span><h3>Ваше<br/>решение.</h3><p>INROU анализирует доступные данные. Изменения ставок, объявлений и бюджетов выполняет ваш специалист вручную.</p><Link href="/security">О контроле и доступе <ArrowRight size={17}/></Link></article>
    <article className="home-trust-sources"><Database size={22}/><strong>2 источника</strong><p>Яндекс Директ и Метрика.<br/>Подключение и доступ проверяются отдельно.</p><Link href="/integrations">Как подключаются источники <ArrowRight size={16}/></Link></article>
    <article><ShieldCheck size={22}/><h3>Честные состояния</h3><p>Если данных недостаточно, вместо показателя вы увидите причину.</p></article>
    <article><History size={22}/><h3>История решений</h3><p>Ручная отметка выполнения не подменяет проверку результата.</p></article>
  </div></section>;
}
