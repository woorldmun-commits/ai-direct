'use client';
import {useId, useState} from 'react';
import Link from 'next/link';
import {ArrowRight, BarChart3, Check, Database, FileText, Fingerprint} from 'lucide-react';
import {BrandMark} from '@/components/brand-mark';
import {DEMO_DAYS, DEMO_METRIC_SERIES} from '@/components/ix/demo-data';
import './site-wave2.css';

const SOURCES = [{title: 'Яндекс Директ', short: 'Расходы', text: 'Расходы, клики и рекламные показатели. Права доступа и полнота проверяются при подключении.', Icon: BarChart3}, {title: 'Яндекс Метрика', short: 'Конверсии', text: 'Цели и контекст конверсий. Определение конверсии и период нужно согласовать до сравнения.', Icon: Database}];

export function OrbitFeatures() {
  const [source, setSource] = useState(0);
  const [interval, setInterval] = useState(6);
  const rangeId = useId();
  const current = SOURCES[source];
  const history = DEMO_METRIC_SERIES[0];
  const maximum = Math.max(...history.values);
  const chartPoints = history.values.map((value, i) => `${10 + i / 13 * 370},${100 - value / maximum * 85}`).join(' ');
  return <div className="orbit-features">
    <article className="orbit-workflow"><div className="orbit-card-heading"><span>01 / СВЯЗЬ ДАННЫХ</span><span>Схема работы</span></div><div className="orbit-flow"><div className="orbit-source-list" role="group" aria-label="Источник в схеме">{SOURCES.map(({title, Icon}, i) => <button type="button" key={title} aria-pressed={source === i} onClick={() => setSource(i)}><Icon size={19}/><span>{title}</span><i/></button>)}</div><div className="orbit-connector" aria-hidden="true"><i/><span/></div><div className="orbit-hub"><BrandMark size={30}/><strong>INROU</strong><span>Источник + период</span></div><div className="orbit-connector" aria-hidden="true"><i/><span/></div><div className="orbit-output"><FileText size={25}/><strong>{current.short}</strong><span>Основания для проверки</span></div></div><div className="orbit-description" aria-live="polite"><h3>{current.title}</h3><p>{current.text}</p></div><p className="orbit-footnote">Интерактивная иллюстрация. Переключение не подключает аккаунт и не запускает синхронизацию.</p></article>
    <article className="orbit-history"><div className="orbit-card-heading"><span>02 / ИСТОРИЯ ПОКАЗАТЕЛЯ</span><BarChart3 size={18}/></div><div className="orbit-history-value"><strong>{history.display[interval]}</strong><span>{DEMO_DAYS[interval]} · демо</span></div><svg viewBox="0 0 390 110" role="img" aria-label="Исторический ряд расходов, синтетический пример"><polyline points={chartPoints} fill="none" stroke="currentColor" strokeWidth="2"/><line x1={10 + interval / 13 * 370} x2={10 + interval / 13 * 370} y1="0" y2="110" stroke="currentColor" strokeDasharray="3 5" opacity=".35"/><circle cx={10 + interval / 13 * 370} cy={100 - history.values[interval] / maximum * 85} r="4" fill="currentColor"/></svg><label htmlFor={rangeId}>Выберите исторический интервал</label><input id={rangeId} type="range" min={0} max={13} step={1} value={interval} onChange={event => setInterval(Number(event.target.value))} aria-valuetext={`${DEMO_DAYS[interval]}, ${history.display[interval]}, синтетический пример`}/><p>Двигайте ползунок или используйте стрелки клавиатуры. Показаны учебные интервалы марта 2025, а не прогноз будущего расхода.</p></article>
    <article className="orbit-report"><div className="orbit-card-heading"><span>03 / ПАСПОРТ РЕШЕНИЯ</span><Fingerprint size={18}/></div><div className="orbit-report-sheet"><span>ОСНОВАНИЕ ПЕРЕД ДЕЙСТВИЕМ</span>{['Источник и период', 'Расчёт и ограничения', 'Риски и ручной шаг'].map(text => <div key={text}><Check size={15}/>{text}</div>)}</div><h3>Проверяйте вывод по шагам.</h3><p>Наличие рекомендации не подтверждает экономию. Решение, выполнение и замер — отдельные этапы.</p><Link href="/methodology">Как устроены методики <ArrowRight size={16}/></Link></article>
  </div>;
}
