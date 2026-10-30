'use client';
import {useRouter, useSearchParams} from 'next/navigation';
import {useState, type FormEvent} from 'react';
import {ChartCard, ChartPlot, type SeriesPoint} from './chart';
import {DEMO_ALERTS, DEMO_ANOMALY, DEMO_CAMPAIGNS, DEMO_DATA, DEMO_DAYS, DEMO_KPIS, DEMO_METRIC_SERIES, DEMO_PREV, DEMO_PROFILE, DEMO_RECS, DEMO_REPORTS, DEMO_SNAPSHOT, DEMO_SOURCES, DEMO_TEAM} from './demo-data';
import {demoLabel, useDemo} from './demo-store';
import {Drawer} from './drawer';
import {DetailTabs} from './detail-tabs';
import {useIxSearch} from './shell';
import {DataHealth, Gap, Info, Kpi, LinkBtn, PageHead, RowLine, Spark, StateBlock, Table, Tag, btnClass} from './ui';
import {cycleTheme} from './theme';
import {DemoMetrics} from './demo-metrics';
import {DemoAgency} from './demo-agency';
import {FilterList} from './live/filter-list';

const EYEBROW = 'INROU / Демо';
const HEALTH = <DataHealth>Яндекс Директ: синтетический снимок · {DEMO_SNAPSHOT} · Статус: демонстрация. Источники и расчёты не подтверждены реальными подключениями.</DataHealth>;
const points = (from = 0): SeriesPoint[] => DEMO_DATA.slice(from).map((v, i) => ({
  label: DEMO_DAYS[from + i], value: v, prev: DEMO_PREV[from + i], display: `${v} усл. ед.`, prevDisplay: `${DEMO_PREV[from + i]} усл. ед.`, status: 'estimated',
}));
const SERIES = {seriesName: 'Динамика показателей (индекс)', source: 'Синтетический снимок (демо)', period: '01–31 марта', updated: DEMO_SNAPSHOT};
const head = (title: string, sub: string, actions?: React.ReactNode) => <PageHead eyebrow={EYEBROW} title={title} sub={sub} actions={actions} />;

function RecList() {
  const q = useIxSearch();
  const {recs} = useDemo();
  const router = useRouter();
  const items = DEMO_RECS.map((r, i) => ({r, i})).filter(({r}) => !q || r.title.toLowerCase().includes(q));
  if (!items.length) return <p className="ix-muted">По запросу ничего не найдено.</p>;
  return <FilterList items={items.map(({r,i})=>({key:String(i),text:r.title,kind:i===2?'inspect_only':'review',computedAt:'2025-03-31T12:00:00Z',node:<div className="ix-recommendation-row"><RowLine>
    <div><div style={{fontWeight: 650}}>{r.icon} {r.title}</div><div className="ix-muted ix-mini">{r.note}</div></div>
    <div style={{textAlign: 'right'}}><div className={'ix-tag' + (i < 2 ? ' ix-tag--warn' : '')}>{demoLabel(recs[i]) ?? r.level}</div>
      <div><button type="button" className="ix-btn" style={{marginTop: 7}} onClick={() => router.push(`?rec=${i}`, {scroll: false})}>Подробнее →</button></div></div>
  </RowLine></div>}))}/>;
}

function Passport({index}: {index: number}) {
  const router = useRouter();
  const {recs, events, decide, markManual, verify} = useDemo();
  const [problem, setProblem] = useState<string | null>(null);
  const r = DEMO_RECS[index];
  const close = () => router.replace('?', {scroll: false});
  const act = (fn: () => string | null) => { const err = fn(); setProblem(err); if (!err) close(); };
  const evidence = <div className="ix-card"><h2>Доказательства</h2><RowLine><span>Источник</span><b>Синтетический снимок</b></RowLine><RowLine><span>Период</span><b>01–31.03.2025</b></RowLine><RowLine><span>Фактический CPA</span><b>Недоступно</b></RowLine><RowLine><span>Целевой CPA</span><b>Не задан</b></RowLine><Tag tone="warn">Достаточность не подтверждена</Tag></div>;
  const calculation = <div className="ix-card"><h2>Расчёт и последствия</h2><p>CPA = расход / число атрибутированных конверсий. Для расчёта необходимы единое определение конверсии, период и подтверждённые исходные значения.</p><Info warning>Предполагаемый эффект {r.effect} — только иллюстрация интерфейса, не прогноз и не подтверждённая экономия.</Info></div>;
  const risk = <div className="ix-card"><h2>Риски</h2><p>Изменения могут ухудшить охват или объём конверсий. Перед действием проверьте объём выборки. Причинный эффект без замера не утверждается.</p></div>;
  const metrics = <div className="ix-card"><h2>Показатели</h2><RowLine><span>Текущий CPA</span><b>Недоступно</b></RowLine><RowLine><span>Предыдущий CPA</span><b>Недоступно</b></RowLine><RowLine><span>Изменение</span><b>Не рассчитано</b></RowLine><Tag tone="warn">Демо · не подтверждено</Tag></div>;
  return <Drawer title={r.title} onClose={close}>
    <Tag tone="warn">{demoLabel(recs[index]) ?? 'Требует решения'}</Tag><p className="ix-muted ix-mini">Демонстрационный паспорт · ревизия demo-01</p>
    <DetailTabs tabs={[
      {id: 'overview', title: 'Обзор', body: <><div className="ix-card"><h2>Текущая ситуация</h2><p>{r.note}. Основания требуют подтверждения.</p></div><div className="ix-detail-columns"><div className="ix-card ix-detail-chart"><h2>Динамика CPA · пример</h2><ChartPlot points={points()} showPrev seriesName="Иллюстративный индекс CPA" source="Синтетический пример, не фактический CPA" period="март 2025" ariaLabel="Демонстрационная форма CPA, не фактические рубли" caption="Индекс · не подтверждённая история CPA" /></div>{metrics}</div><div className="ix-detail-columns ix-detail-consequences"><div className="ix-card"><h2>Ожидаемый эффект</h2><p>Не подтверждён</p><p className="ix-mini ix-muted">Нужны исходные значения, ручное выполнение и замер результата.</p></div>{risk}</div></>},
      {id: 'evidence', title: 'Данные', body: evidence},
      {id: 'calculation', title: 'Расчёты', body: calculation},
      {id: 'risks', title: 'Риски', body: risk},
      {id: 'history', title: 'История', body: <div className="ix-card"><h2>История рекомендации</h2>{events.filter(event=>event.text.includes(r.title)).length ? events.filter(event=>event.text.includes(r.title)).map(event=><RowLine key={event.id}><span>{event.text}</span><Tag tone="gray">{event.tag}</Tag></RowLine>) : <p className="ix-muted">Демонстрационных решений ещё нет.</p>}</div>},
    ]} />
    <div className="ix-card"><h2>План действий</h2><ol><li>Проверить источник, период и достаточность выборки.</li><li>Принять решение на основании доказательств.</li><li>Выполнить изменение вручную и измерить результат.</li></ol><div className="ix-actions"><button type="button" className="ix-btn" onClick={() => act(() => markManual(index, r.title))}>Отметить ручное выполнение</button><button type="button" className="ix-btn" onClick={() => act(() => verify(index, r.title))}>Проверить результат</button></div></div>
    <div className="ix-decision-actions"><div className="ix-actions"><button type="button" className="ix-btn ix-btn--primary" onClick={() => act(() => { decide(index, r.title, 'approved'); return null; })}>Одобрить</button><button type="button" className="ix-btn" onClick={() => act(() => { decide(index, r.title, 'postponed'); return null; })}>Отложить</button><button type="button" className="ix-btn ix-btn--wine" onClick={() => act(() => { decide(index, r.title, 'rejected'); return null; })}>Отклонить</button></div><p className="ix-muted ix-mini">Демо: решение сохраняется до перезагрузки. Реклама не изменяется.</p>{problem && <p role="alert" className="ix-bad">{problem}</p>}</div>
  </Drawer>;
}

function useRec() { const p = useSearchParams().get('rec'); return p !== null && /^[0-3]$/.test(p) ? Number(p) : null; }

function KpiRow({direct, week, insufficient, compare = true}: {direct: boolean; week: boolean; insufficient: boolean; compare?: boolean}) {
  return <div className="ix-grid ix-kpis">{DEMO_KPIS.map(([k, v, d], i) => {
    const conv = insufficient && (k === 'Конверсии' || k === 'CPA');
    if (!direct) return <Kpi key={k} label={k} value="Нет данных" tone="muted" foot="Источник не подтверждён как доступный" />;
    if (week) return <Kpi key={k} label={k} value="Недостаточно данных" tone="muted" foot="Недельные агрегаты не входят в демо-снимок" />;
    const s = DEMO_METRIC_SERIES[i];
    return <div key={k} style={{'--ix-chart-line': s.color} as React.CSSProperties}><Kpi label={k} value={conv ? 'Недостаточно данных' : v} tone="muted" trend={!conv && compare ? {text: d, direction: d.startsWith('−') ? 'down' : 'up', tone: k === 'Расходы' ? 'neutral' : 'good'} : undefined} foot={conv ? 'Нужны подтверждённые конверсии' : compare ? 'К прошлому периоду · демо' : 'Текущий период · демо'} spark={conv ? undefined : <Spark data={s.values} prev={compare ? s.previous : undefined} label={`Демонстрационная динамика: ${k}`} />} /></div>;
  })}</div>;
}

function CampaignTable({platform = 'Все источники'}: {platform?: string}) {
  const q = useIxSearch();
  const rows = DEMO_CAMPAIGNS.filter(c => (platform === 'Все источники' || c[1] === platform) && (!q || c[0].toLowerCase().includes(q)));
  if (!rows.length) return <StateBlock kind="empty" title="Нет кампаний по выбранным условиям">Измените площадку или строку поиска.</StateBlock>;
  return <Table label="Кампании" head={['Кампания', 'Источник', 'Статус', 'Расходы', 'Конверсии', 'CPA']} rows={rows.map(c => c.map((x, i) => i === 2 ? <Tag key={i} tone={x === 'Активна' ? undefined : 'gray'}>{x}</Tag> : x))} />;
}

function MetricDetails({compare}: {compare: boolean}) {
  const cost = DEMO_METRIC_SERIES[0], revenue = DEMO_METRIC_SERIES[3];
  const roas = {id: 'roas', name: 'ROAS', values: cost.values.map((v, i) => v > 0 ? revenue.values[i] / v : null), previous: cost.previous.map((v, i) => v > 0 ? revenue.previous[i] / v : null)};
  const metrics = [...DEMO_METRIC_SERIES.slice(0, 3), {...roas, display: roas.values.map(v => v === null ? null : v.toFixed(2) + '×'), previousDisplay: roas.previous.map(v => v === null ? null : v.toFixed(2) + '×')}, revenue];
  return <details className="ix-card ix-metric-details"><summary>Детальный график и данные по дням</summary><p className="ix-mini ix-muted">Синтетические интервалы марта. ROAS = выручка / расход; суммы, конверсии и коэффициенты отображаются на отдельных шкалах.</p><DetailTabs tabs={metrics.map(s => ({id: s.id, title: s.name, body: <ChartPlot points={s.values.map((value, i) => ({label: DEMO_DAYS[i], value, prev: s.previous[i], display: s.display[i], prevDisplay: s.previousDisplay[i], status: 'estimated'}))} showPrev={compare} fit seriesName={s.name} source="Синтетический снимок (демо)" period="01–31 марта" ariaLabel={`Демонстрационная динамика: ${s.name}`} table /> }))} /></details>;
}

function Analysis() {
  const params = useSearchParams();
  const platform = ['Яндекс Директ', 'VK Реклама', 'Авито'].find(p => p === params.get('platform')) ?? 'Все источники';
  const period = params.get('period') === 'week' ? 'Неделя' : 'Месяц';
  const insufficient = params.get('insufficient') === '1';
  const compare = params.get('compare') !== '0';
  const filter = (key: string, value: string | null) => { const next = new URLSearchParams(window.location.search); if (value === null) next.delete(key); else next.set(key, value); window.history.replaceState(null, '', `?${next}`); };
  const [zoom, setZoom] = useState(100);
  const direct = platform === 'Все источники' || platform === 'Яндекс Директ';
  const week = period === 'Неделя';
  const from = week ? 7 : 0;
  return <>
    {head('Анализ рекламы', 'Доказательные показатели и сравнение периодов.')}
    <div className="ix-actions ix-analysis-filters" style={{marginBottom: 14}}>
      <select className="ix-field" style={{maxWidth: 210}} aria-label="Площадка" value={platform} onChange={e => filter('platform', e.target.value === 'Все источники' ? null : e.target.value)}><option>Все источники</option><option>Яндекс Директ</option><option>VK Реклама</option><option>Авито</option></select>
      <select className="ix-field" style={{maxWidth: 160}} aria-label="Период" value={period} onChange={e => filter('period', e.target.value === 'Неделя' ? 'week' : null)}><option>Месяц</option><option>Неделя</option></select>
      <details className="ix-chart-options"><summary className="ix-btn">Параметры графика</summary><div className="ix-actions">
      <button type="button" className="ix-btn" aria-pressed={insufficient} onClick={() => filter('insufficient', insufficient ? null : '1')}>Недостаточно данных</button>
      <button type="button" className="ix-btn" aria-pressed={compare} onClick={() => filter('compare', compare ? '0' : null)}>Сравнение с прошлым периодом</button>
      <button type="button" className="ix-btn" onClick={() => setZoom(100)}>Сбросить масштаб</button>
      </div></details>
    </div>
    {!direct && <Info warning role="status">Этот источник ещё не подтверждён как доступный. Реальные показатели отсутствуют.</Info>}
    <Gap h={12} />
    <KpiRow direct={direct} week={week} insufficient={insufficient} compare={compare} />
    {direct && !insufficient && !week ? <div className="metric-analysis-layout"><ChartCard title="Динамика и аномалии" subtitle="Синтетические интервалы марта · пунктир: сравнение · точка: пример аномалии" zoom={zoom} onZoom={setZoom} points={points(from)} showPrev={compare} series={DEMO_METRIC_SERIES} {...SERIES}
      anomalies={[{...DEMO_ANOMALY, index: DEMO_ANOMALY.index - from}].filter(a => a.index >= 0)} ariaLabel="Демонстрационный график расходов за март">
      <p className="ix-mini ix-muted">Аномалия — синтетический пример. Причина изменения CPA не утверждается.</p>
    </ChartCard><aside className="metric-analysis-aside"><span className="metric-label">Синтетический пример</span><h2 style={{marginTop:18}}>Перед сравнением</h2><dl><div><dt>Текущий период</dt><dd>Март 2025</dd></div><div><dt>Предыдущий период</dt><dd>{compare ? 'Учебный пример' : 'Скрыт'}</dd></div><div><dt>Достоверность</dt><dd>Не подтверждена</dd></div></dl><p className="metric-note">На графике — нормализованный индекс. Рубли и точные значения по интервалам доступны ниже, на отдельной шкале.</p><a href="#demo-budget">Смотреть бюджет и заявки →</a></aside></div> : <StateBlock kind={direct ? 'insufficient' : 'empty'} title={direct ? 'Недостаточно данных для графика' : 'Нет данных источника'}>{direct ? 'Для построения графика не хватает подтверждённых конверсий. Линия не рисуется нулями.' : 'Источник не подключён: график и таблица не подменяются примерами.'}</StateBlock>}
    {direct && !week && <DemoMetrics compare={compare} unavailable={insufficient}/>}
    {direct && !insufficient && !week && <MetricDetails compare={compare} />}
    <div className="ix-analysis-bottom"><div className="ix-card"><h2>Кампании</h2>{week ? <StateBlock kind="insufficient" title="Нет недельного среза">Недельные агрегаты не входят в демо-снимок. Месячные значения не выдаются за недельные.</StateBlock> : <CampaignTable platform={platform} />}</div><aside className="ix-card"><h2>Демо срез кампаний</h2>{direct && !week && !insufficient ? <><div className="ix-source-donut" role="img" aria-label="Демонстрационный срез кампаний: Бренд 60 000, Каталог 40 000, Категории 80 000 рублей; всего 180 000 рублей." /><p className="ix-mini ix-muted">Бренд 33,3% · Каталог 22,2%<br />Категории 44,5% · всего 180 000 ₽</p><Tag>Синтетический снимок</Tag></> : <p className="ix-muted">Нет подтверждённого распределения.</p>}</aside><aside className="ix-card"><h2>Качество данных</h2><p className="ix-mini">Яндекс Директ · демо</p><Tag tone="gray">Не подтверждено</Tag><details><summary className="ix-mini">Источник и ограничения</summary>{HEALTH}</details><p className="ix-mini ix-muted">Период и источник проверяются перед решением. Доли доступны только при известном знаменателе.</p></aside></div>
  </>;
}

function Chat() {
  const [log, setLog] = useState<{q: string}[]>([]);
  const [value, setValue] = useState('');
  const ask = (q: string) => { const t = q.trim(); if (!t) return; setLog(l => [...l, {q: t}]); setValue(''); };
  return <>
    {head('AI-аналитик', 'Объяснения только на основе проверенных данных и расчётов.')}
    <div className="ix-chat">
      <div className="ix-bubble"><b>INROU · аналитический помощник</b><p>В деморежиме я могу показать структуру ответа, но не выдаю синтетические цифры за реальные.</p><Info>Источник: демонстрационный набор · Период: март 2025 · Уверенность: не определена</Info></div>
      <div aria-live="polite">{log.map((m, i) => <div key={i}><div className="ix-bubble ix-bubble--user" style={{marginLeft: 'auto', marginTop: 14}}>{m.q}</div>
        <div className="ix-bubble" style={{marginTop: 14}}><b>INROU · ответ с ограничениями</b><p>Для обоснованного ответа нужны подтверждённые расходы, конверсии, CPC, CVR, период и атрибуция. В деморежиме я не могу назвать причину или численный эффект.</p><Info>Источники: недоступны · Статус: insufficient · Следующий шаг: подключить и проверить данные.</Info></div></div>)}</div>
      <div className="ix-actions">{['Почему вырос CPA?', 'Покажи источники', 'История запросов'].map(t => <button key={t} type="button" className="ix-btn" onClick={() => ask(t)}>{t}</button>)}</div>
      <form className="ix-chatinput" onSubmit={(e: FormEvent) => { e.preventDefault(); ask(value); }}>
        <input className="ix-field" aria-label="Вопрос аналитику" placeholder="Задайте вопрос по вашим данным…" value={value} onChange={e => setValue(e.target.value)} />
        <button className="ix-btn ix-btn--primary" type="submit">Отправить →</button>
      </form>
      <div className="ix-muted ix-mini">Демонстрационный сценарий. Внешняя LLM не подключена.</div>
    </div></>;
}

export function DemoScreen({section}: {section: string}) {
  const rec = useRec();
  const {events} = useDemo();
  const [overviewZoom, setOverviewZoom] = useState(100);
  const body = (() => {
    switch (section) {
      case 'overview': return <>
        {head('Обзор', 'Ключевые показатели и динамика вашего бизнеса.', <LinkBtn variant="primary" href="/demo/analysis">Открыть анализ</LinkBtn>)}
        {HEALTH}<Gap />
        <ChartCard zoom={overviewZoom} onZoom={setOverviewZoom} ariaLabel="Демонстрационная динамика показателей: нормализованный индекс" title="Динамика показателей" subtitle="Синтетические интервалы марта · нормализованный индекс" points={points()} showPrev series={DEMO_METRIC_SERIES} {...SERIES}/>
        <Gap /><KpiRow direct week={false} insufficient={false} />
        <div className="ix-grid ix-split"><section className="ix-card"><h2>Приоритетные решения</h2><RecList /></section>
          <section className="ix-card ix-assistant-preview"><h2>AI-аналитик</h2><p>Показатели, основания и следующие шаги — в одном разборе.</p><p className="ix-muted">Демонстрационный режим. Ответы не относятся к вашему рекламному кабинету.</p><LinkBtn variant="primary" href="/demo/ai">Посмотреть разбор</LinkBtn></section></div></>;
      case 'analysis': return <Analysis />;
      case 'recommendations': return <>{head('Рекомендации', 'Приоритеты, доказательства, решения человека.')}{HEALTH}<Gap h={14} /><div className="ix-card"><h2>Решения к рассмотрению</h2><RecList /></div></>;
      case 'campaigns': return <>{head('Кампании', 'Все рекламные кампании в одном контуре.')}<div className="ix-card"><h2>Рекламные кампании</h2><CampaignTable /></div></>;
      case 'connections': return <>{head('Подключения', 'Только подтверждённые возможности; остальные — этапы развития.')}
        <div className="ix-grid ix-split"><div className="ix-card"><h2>Источники данных</h2>{DEMO_SOURCES.map(([a, b], i) => <RowLine key={a}><div><b>{a}</b><div className="ix-muted ix-mini">{b}</div></div><Tag tone={i > 1 ? 'gray' : undefined}>{i > 1 ? 'Планируется' : 'Проверить подключение'}</Tag></RowLine>)}</div>
          <div className="ix-card"><h2>Доверие к источникам</h2><p>Реальное подключение, права, свежесть и ошибки синхронизации должны приходить из backend.</p><Info warning>В этом прототипе OAuth и API не выполняются.</Info></div></div></>;
      case 'impact': return <>{head('Эффект', 'Подтверждённый результат отделяется от потенциального.')}{HEALTH}<Gap h={14} />
        <div className="ix-grid ix-split"><div className="ix-card"><h2>Динамика результата</h2><ChartPlot points={points()} showPrev anomalies={[DEMO_ANOMALY]} ariaLabel="Демонстрационный график результата" {...SERIES} caption="Пример визуализации; не является доказательством экономии." /></div>
          <div className="ix-card"><h2>Экономический эффект</h2><div className="ix-value" style={{fontSize: 34, fontWeight: 700}}>—</div><p className="ix-muted">Недостаточно подтверждённых данных для оценки.</p><Info>После ручного действия требуется сверка факта и периода, затем оценка эффекта.</Info></div></div></>;
      case 'reports': return <>{head('Отчёты', 'Прозрачная отчётность для бизнеса и агентств.')}<div className="ix-grid ix-featuregrid">{DEMO_REPORTS.map(x => <div key={x} className="ix-card"><div className="ix-eyebrow">Шаблон</div><h2>{x}</h2><p className="ix-muted">Экспорт доступен после интеграции с отчётным backend.</p><Tag tone="gray">Прототип</Tag></div>)}</div></>;
      case 'alerts': return <>{head('Сигналы', 'Риски, изменения и уведомления с проверяемыми причинами.')}<div className="ix-card">{DEMO_ALERTS.map(([a, b]) => <RowLine key={a}><div><b>◉ {a}</b><div className="ix-muted ix-mini">Требуется проверка источника и периода</div></div><Tag tone="warn">{b}</Tag></RowLine>)}</div></>;
      case 'ai': return <Chat />;
      case 'history': return <>{head('История', 'Неизменяемый журнал действий, решений и проверок.')}<div className="ix-card" id="history">{events.map(e => <RowLine key={e.id}><span>{e.text}</span><Tag tone="gray">{e.tag}</Tag></RowLine>)}<RowLine><span>Создан демонстрационный снимок</span><Tag tone="gray">Демо</Tag></RowLine></div></>;
      case 'team': return <>{head('Команда', 'Участники, роли и права доступа.')}<div className="ix-card"><h2>Участники организации</h2>{DEMO_TEAM.map(([a, b]) => <RowLine key={a}><b>{a}</b><span className="ix-muted">{b}</span></RowLine>)}<p className="ix-muted ix-mini">Приглашения и права должны проверяться на сервере.</p></div></>;
      case 'plans': return <>{head('Тарифы и клиентские пространства', 'Демонстрация пакета без создания подписки или оплаты.')}<DemoAgency/></>;
      case 'settings': return <>{head('Настройки', 'Профиль, безопасность, уведомления и оформление.')}
        <div className="ix-grid ix-split"><div className="ix-card"><h2>Настройки интерфейса</h2><RowLine><span>Цветовая тема</span><button type="button" className={btnClass()} onClick={cycleTheme}>Переключить</button></RowLine><RowLine><span>Анимации</span><span className="ix-muted">С учётом настроек системы</span></RowLine></div>
          <div className="ix-card"><h2>Безопасность</h2><p>Доступы и сессии должны управляться сервером. В прототипе нет настоящих аккаунтов.</p></div></div></>;
      case 'business-profile': return <>{head('Бизнес-профиль', 'Контекст компании для корректного анализа рекомендаций.')}
        <div className="ix-card" style={{maxWidth: 680}}><h2>Параметры бизнеса</h2>{DEMO_PROFILE.map(([a, b]) => <label key={a} style={{display: 'block', margin: '12px 0'}}><span className="ix-muted">{a}</span><input className="ix-field" defaultValue={b} /></label>)}<Info warning>Демо: изменения не сохраняются на сервере. AI не должен самостоятельно переписывать подтверждённый профиль.</Info></div></>;
      default: return <StateBlock kind="empty" title="Раздел не найден" />;
    }
  })();
  return <>{body}{rec !== null && <Passport index={rec} />}</>;
}

