'use client';
import {useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode} from 'react';
import {BASELINE, GRID, H, W, scaleFor, segments, xAt} from './geometry';
import {Table} from './ui';
import {ValueView} from '@/components/value-view';
import type {Value} from '@/lib/value';

export type SeriesPoint = {label: string; value: number | null; prev: number | null; display: string | null; prevDisplay: string | null; evidence?: Value; status: 'actual' | 'estimated' | 'unavailable'};
export type Anomaly = {index: number; title: string; rule: string; evidence: string; seriesId?: string};
export type ChartSeries = {id: string; name: string; color: string; values: (number | null)[]; previous?: (number | null)[]; display: (string | null)[]; previousDisplay?: (string | null)[]};
const STATUS = {actual: 'Факт', estimated: 'Оценка', unavailable: 'Нет данных'} as const;
export const indexValues = (values: (number | null)[], base: number | null | undefined) => values.map(v => v === null ? null : base && base > 0 ? v / base * 100 : v);

type PlotProps = {
  points: SeriesPoint[]; showPrev: boolean; zoom?: number; seriesName: string; source: string; period: string; updated?: string;
  anomalies?: Anomaly[]; ariaLabel: string; fit?: boolean;
  /** Табличная альтернатива: управляется родителем или (если не задано) самим графиком вместе с подписью `caption`. */
  table?: boolean; caption?: ReactNode;
  series?: ChartSeries[];
};

/**
 * График. Геометрия — как в эталоне (viewBox 500×185, сетка, две линии, маркер аномалии).
 * Поверх — кнопки точек: подсказка по наведению и с клавиатуре (←/→/Home/End, Esc), null = разрыв линии,
 * таблица-альтернатива. Подписи значений приходят отформатированными (`display`): график их не вычисляет.
 */
export function ChartPlot({points, showPrev, zoom = 100, seriesName, source, period, updated, anomalies = [], ariaLabel, fit = false, table, caption, series}: PlotProps) {
  const fillId = useId().replaceAll(':', '');
  const [own, setOwn] = useState(false);
  const tableOpen = table ?? own;
  const [active, setActive] = useState<number | null>(null);
  const [hidden, setHidden] = useState<string[]>([]);
  const chart = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = chart.current, tip = tooltip.current;
    if (!container || !tip || active === null) return;
    const rect = container.getBoundingClientRect(), width = tip.offsetWidth;
    const inset = parseFloat(getComputedStyle(container).paddingLeft) || 0;
    const x = xAt(active, points.length) / W * (rect.width - inset) * zoom / 100 + inset;
    tip.style.left = `${Math.max(0, Math.min(x + 8, rect.width - width, innerWidth - rect.left - width - 12))}px`;
    tip.style.transform = 'none';
  }, [active, points.length, zoom, hidden, showPrev]);
  useEffect(() => {
    const outside = (e: PointerEvent) => { if (!chart.current?.contains(e.target as Node)) setActive(null); };
    document.addEventListener('pointerdown', outside);
    const observer = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) { chart.current?.setAttribute('data-entered', 'true'); observer.disconnect(); } });
    if (chart.current) observer.observe(chart.current);
    return () => { document.removeEventListener('pointerdown', outside); observer.disconnect(); };
  }, []);
  const [tab, setTab] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const visible = series?.filter(s => !hidden.includes(s.id));
  const plotted = series?.map(s => { const base = s.values.find(v => v !== null && v > 0); return {...s, current: indexValues(s.values, base), prior: indexValues(s.previous ?? [], base)}; });
  const n = points.length;
  const scale = scaleFor(plotted ? plotted.flatMap(s => [...s.current, ...(showPrev ? s.prior : [])]) : [...points.map(p => p.value), ...(showPrev ? points.map(p => p.prev) : [])], plotted ? true : fit);
  const move = (e: KeyboardEvent, i: number) => {
    if (e.key === 'Escape') { setActive(null); return; }
    const to = e.key === 'ArrowRight' ? Math.min(n - 1, i + 1) : e.key === 'ArrowLeft' ? Math.max(0, i - 1) : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : null;
    if (to === null) return;
    e.preventDefault(); setTab(to); setActive(to); refs.current[to]?.focus();
  };
  const p = active === null ? null : points[active];
  const an = active === null ? undefined : anomalies.find(a => a.index === active);
  const pct = active === null ? 0 : Math.min(100, (xAt(active, n) / W) * 100 * (zoom / 100));

  return <>
    {series && <><div className="ix-series-legend" aria-label="Ряды графика">{series.map(s => <button key={s.id} type="button" aria-pressed={!hidden.includes(s.id)} onClick={() => setHidden(h => h.includes(s.id) ? h.filter(id => id !== s.id) : [...h, s.id])}><i style={{background: s.color}} aria-hidden="true" />{s.name}</button>)}</div><details className="ix-muted ix-mini ix-chart-index"><summary>Индекс · единицы</summary>Первая положительная точка текущего ряда = 100. Единицы — в подсказке и таблице.</details>{!visible?.length && <p role="status">Все ряды скрыты. Выберите показатель в легенде.</p>}</>}
    {!series && <div className="ix-plot-key" aria-label="Обозначения графика"><span><i/>{seriesName}</span>{showPrev && <span><i className="is-previous"/>Предыдущий период</span>}</div>}
    <div ref={chart} className="ix-chartwrap" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setActive(null); }}>          <div className="ix-y-axis" aria-hidden="true">{GRID.map(y => <span key={y} style={{top: `${y / H * 100}%`}}>{new Intl.NumberFormat('ru-RU', {notation: 'compact', maximumFractionDigits: 1}).format((BASELINE - y) / scale)}</span>)}</div>
      <div style={{overflow: 'hidden'}}>
        <div style={{transform: `scaleX(${zoom / 100})`, transformOrigin: 'left center', position: 'relative'}}>
          <svg className="ix-chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={ariaLabel}>
            <defs><linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--ix-chart-line)" stopOpacity=".14"/><stop offset="100%" stopColor="var(--ix-chart-line)" stopOpacity="0"/></linearGradient>{series?.map(s => <linearGradient key={s.id} id={`${fillId}-${s.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={s.color} stopOpacity=".12"/><stop offset="100%" stopColor={s.color} stopOpacity="0"/></linearGradient>)}</defs>
            <g stroke="var(--line)" strokeWidth="1">{GRID.map(y => <line key={y} x1="0" x2={W} y1={y} y2={y} />)}{Array.from({length: 7}, (_, i) => <line key={'x' + i} x1={i * W / 6} x2={i * W / 6} y1={GRID[0]} y2={BASELINE} opacity={.45} />)}</g>
            <g className="ix-chart-lines">{plotted ? plotted.map(s => <g key={s.id} data-series={s.id} className="ix-chart-series" opacity={hidden.includes(s.id) ? 0 : 1}>
              {showPrev && segments(s.prior, scale).map((p, i) => <path key={'p' + i} d={('M' + p.replaceAll(' ', ' L'))} fill="none" stroke={s.color} strokeWidth={1.2} vectorEffect="non-scaling-stroke" strokeDasharray="4 4" opacity={.4} />)}
              {segments(s.current, scale).map((p, i) => <g key={i}><path className="ix-chart-fill" d={`${('M' + p.replaceAll(' ', ' L'))} L${p.split(' ').at(-1)?.split(',')[0]},${BASELINE} L${p.split(' ')[0].split(',')[0]},${BASELINE} Z`} fill={`url(#${fillId}-${s.id})`} /><path d={('M' + p.replaceAll(' ', ' L'))} fill="none" stroke={s.color} strokeWidth={1.7} vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" /></g>)}
            </g>) : <>{showPrev && segments(points.map(q => q.prev), scale).map((s, i) => <polyline key={'p' + i} points={s} fill="none" stroke="var(--ix-chart-prev)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeDasharray="4 4" />)}{segments(points.map(q => q.value), scale).map((s, i) => <g key={'d' + i}><path d={`M${s.replaceAll(' ', ' L')} L${s.split(' ').at(-1)?.split(',')[0]},${BASELINE} L${s.split(' ')[0].split(',')[0]},${BASELINE} Z`} fill={`url(#${fillId})`}/><polyline points={s} fill="none" stroke="var(--ix-chart-line)" strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" /></g>)}</>}</g>
            {active !== null && <g className="ix-crosshair" aria-hidden="true"><line x1={xAt(active, n)} x2={xAt(active, n)} y1={GRID[0]} y2={BASELINE} stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />{(plotted ?? [{id: 'current', color: 'var(--ix-chart-line)', current: points.map(q => q.value)}]).filter(s => !hidden.includes(s.id)).map(s => { const value = s.current[active]; return value === null || value === undefined ? null : <circle key={s.id} cx={xAt(active, n)} cy={BASELINE - value * scale} r={4} fill={s.color} stroke="var(--panel)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />; })}</g>}
            {anomalies.map(a => { const selected = plotted?.find(s => s.id === (a.seriesId ?? plotted[0]?.id)); const v = selected && hidden.includes(selected.id) ? null : plotted ? selected?.current[a.index] : points[a.index]?.value; return v === null || v === undefined ? null : <circle key={a.index} cx={xAt(a.index, n)} cy={BASELINE - v * scale} r={4} fill={selected?.color ?? 'var(--ix-chart-line)'}><title>{a.title}</title></circle>; })}
          </svg>

          <div role="group" aria-label={`Точки графика: ${seriesName}. Стрелки влево и вправо — перейти, Esc — закрыть подсказку`} onPointerLeave={e => { if (e.pointerType === 'mouse') setActive(null); }}>
            {points.map((q, i) => <button key={i} ref={el => { refs.current[i] = el; }} type="button" className="ix-hit" tabIndex={i === tab ? 0 : -1}
              style={{left: `${(xAt(i, n) / W) * 100 - 50 / n}%`, width: `${100 / n}%`}}
              aria-label={q.evidence ? undefined : `${q.label}: ${visible ? visible.map(s => `${s.name}: ${s.display[i] ?? 'нет данных'}`).join('; ') || 'ряды скрыты' : q.display ?? 'нет данных'}${anomalies.some(a => a.index === i) ? '. Отмечена аномалия' : ''}`}
              onPointerEnter={e => { if (e.pointerType === 'mouse') setActive(i); }} onFocus={() => { setActive(i); setTab(i); }} onPointerDown={e => { if (e.pointerType !== 'mouse') { e.preventDefault(); setActive(v => v === i ? null : i); setTab(i); } }} onKeyDown={e => move(e, i)}>{q.evidence&&<span className="sr-only-ix">{q.label}: <ValueView v={q.evidence} hint={false}/></span>}</button>)}
          </div>
        </div>
      </div>
      {n > 0 && <div className="ix-chart-dates" aria-hidden="true">{Array.from(new Set(Array.from({length: Math.min(n, 7)}, (_, j) => Math.round(j * (n - 1) / Math.min(n - 1 || 1, 6))))).map((i, tick) => <span key={i} className={tick % 3 === 0 ? undefined : 'ix-date-extra'}>{points[i]?.label}</span>)}</div>}
      {p && <div ref={tooltip} className="ix-tooltip" role="status" style={{left: `${pct}%`, top: 8, transform: pct > 70 ? 'translateX(-105%)' : 'translateX(8px)'}}>
        <b>{p.label}</b>
        <dl>
          <dt>Показатель</dt><dd>{seriesName}</dd>
          {!series && <><dt>Значение</dt><dd>{p.evidence ? <ValueView v={p.evidence} hint={false}/> : p.display ?? 'Нет данных'}</dd></>}
          {visible?.map(s => <div key={s.id} style={{display: 'contents'}}><dt>{s.name}</dt><dd>{s.display[active!] ?? 'Нет данных'}{showPrev && <> / {s.previousDisplay?.[active!] ?? 'Нет сравнения'}</>}</dd></div>)}
          {showPrev && !series && <><dt>Сравнение</dt><dd>{p.prevDisplay ?? 'Нет данных'}</dd></>}
          <dt>Статус</dt><dd>{STATUS[p.status]}</dd>
          <dt>Источник</dt><dd>{source}</dd>
          <dt>Период</dt><dd>{period}</dd>
          {updated && <><dt>Обновлено</dt><dd>{updated}</dd></>}
        </dl>
        {an && <p style={{margin: '6px 0 0'}}><b>{an.title}</b>Правило: {an.rule}. {an.evidence}</p>}
      </div>}
    </div>
    {caption !== undefined && <div className="ix-muted ix-mini">{caption}{table === undefined && <> · <button type="button" className="ix-linkbtn" aria-expanded={own} onClick={() => setOwn(v => !v)}>{own ? 'Скрыть таблицу' : 'Показать таблицу'}</button></>}</div>}
    {tableOpen && (visible ? <Table label={`Таблица: ${seriesName}`} head={['Дата', ...visible.flatMap(s => [s.name, ...(showPrev ? [s.name + ' · сравнение'] : [])]), 'Статус']} rows={points.map((q, i) => [q.label, ...visible.flatMap(s => [s.display[i] ?? 'Нет данных', ...(showPrev ? [s.previousDisplay?.[i] ?? 'Нет данных'] : [])]), STATUS[q.status]])} /> : <Table label={`Таблица: ${seriesName}`} head={['Дата', 'Текущий период', 'Сравнение', 'Статус']} rows={points.map(q => [q.label, q.evidence ? <ValueView v={q.evidence} /> : q.display ?? 'Нет данных', showPrev ? (q.prevDisplay ?? 'Нет данных') : '—', STATUS[q.status]])} />)}
  </>;
}

/** Карточка «Динамика и аномалии»: заголовок, масштаб, график, пояснение. */
export function ChartCard({title, subtitle, zoom, onZoom, children, extraActions, ...plot}: PlotProps & {title: string; subtitle: ReactNode; zoom: number; onZoom: (v: number) => void; children?: ReactNode; extraActions?: ReactNode}) {
  const id = useId();
  const [table, setTable] = useState(false);
  return <div className="ix-card ix-chart-card">
    <div className="ix-head">
      <div><h2>{title}</h2><details className="ix-chart-method ix-muted ix-mini"><summary>Источник и методика</summary>{subtitle}<p>{plot.source} · {plot.period}</p></details></div>
      <div className="ix-actions" style={{alignItems: 'center'}}>
        <label htmlFor={id}>Масштаб</label>
        <input className="ix-range" id={id} type="range" min={80} max={160} value={zoom} onChange={e => onZoom(Number(e.target.value))} aria-valuetext={`${zoom}%`} />
        <span aria-hidden>{zoom}%</span>
        <button type="button" className="ix-btn" aria-expanded={table} onClick={() => setTable(v => !v)}>{table ? 'Скрыть таблицу' : 'Таблица'}</button>
        {extraActions}
      </div>
    </div>
    <ChartPlot {...plot} zoom={zoom} table={table} />
    {children}
  </div>;
}


