'use client';
import {useId, useState, type CSSProperties} from 'react';
import {allocateDemo} from '../ix/demo-data';

// Synthetic cost series, isolated under the existing INROU_DEMO server gate.
const SERIES = [
  {id: 'brand', name: 'Поиск · бренд', values: allocateDemo(100000,[4,7,6,12,18,17,21,19,16,20,23,22,20,26])},
  {id: 'network', name: 'РСЯ · каталог', values: allocateDemo(70000,[6,9,8,14,11,12,15,13,12,16,18,17,19,21])},
  {id: 'category', name: 'Поиск · категории', values: allocateDemo(50000,[2,4,3,7,8,6,9,7,8,6,11,10,12,15])},
  {id: 'retarget', name: 'Ретаргетинг', values: allocateDemo(28640,[1,2,2,4,5,3,4,3,4,3,6,5,6,8])},
];
export function SapphireChart({small = false, metric = 'cost'}: {small?: boolean; metric?: 'cost' | 'cpa'}) {
  const id = useId().replaceAll(':', '');
  const [hidden, setHidden] = useState<string[]>([]);
  const [point, setPoint] = useState<number | null>(null);
  const [tab, setTab] = useState(0);
  const [granularity, setGranularity] = useState('Дни');
  const [table, setTable] = useState(false);
  const groups = granularity === 'Дни' ? 1 : granularity === 'Недели' ? 7 : 14;
  const base = metric === 'cpa' ? [
    {id:'current',name:'Текущий период · CPA',values:[900,1500,1300,2500,2200,3100,2600,3800,3100,4200,3900,5200,5000,6000]},
    {id:'previous',name:'Сравнение · CPA',values:[600,900,1000,1400,1200,1900,1600,2200,2100,2800,3000,3600,4000,4500]},
  ] : SERIES;
  const series = base.map(s => ({...s, values: Array.from({length: Math.ceil(s.values.length / groups)}, (_, i) => {const values=s.values.slice(i * groups,(i+1)*groups);return values.reduce((a,b)=>a+b,0)/(metric==='cpa'?values.length:1);})}));
  const max = Math.ceil(Math.max(...series.flatMap(s => s.values)) / (metric === 'cpa' ? 50 : 1000)) * (metric === 'cpa' ? 50 : 1000);
  const count = series[0].values.length;
  const x = (i: number) => count === 1 ? 500 : i * 960 / (count - 1) + 20;
  const y = (value: number) => 290 - value / max * 260;
  const date = (i: number) => groups === 14 ? '1–14 октября' : groups === 7 ? `${i * 7 + 1}–${i * 7 + 7} октября` : `${i + 1} октября`;
  return <div className={`ms-chart ${small ? 'ms-chart-small' : ''} ${metric==='cpa'?'ms-chart-cpa':''}`}>
    {!small && metric==='cost' && <div className="ms-card-head"><div><h2>Динамика расходов</h2><p>Яндекс Директ · синтетический пример · ₽</p></div><div className="ms-segment" aria-label="Группировка по периоду">{['Дни', 'Недели', 'Месяцы'].map(t => <button key={t} aria-pressed={granularity === t} onClick={() => {setGranularity(t); setPoint(null); setTab(0);}}>{t}</button>)}</div></div>}
    <div className="ms-plot" onPointerLeave={e => {if(e.pointerType === 'mouse') setPoint(null);}} onBlur={e => {if(!e.currentTarget.contains(e.relatedTarget)) setPoint(null);}}>
      <div className="ms-y-axis" aria-hidden>{[4,3,2,1,0].map(n => <span key={n}>{new Intl.NumberFormat('ru-RU', {maximumFractionDigits:0}).format(max * n / 4)}</span>)}</div>
      <div className="ms-plot-body">
        <svg viewBox="0 0 1000 320" preserveAspectRatio="none" role="img" aria-label={metric==='cpa'?'Динамика CPA в демонстрационном сценарии, рубли':'Расходы четырёх демонстрационных кампаний, рубли'}>
          <defs>{series.map(s => <linearGradient key={s.id} id={`${id}-${s.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={`var(--ms-series-${s.id})`} stopOpacity=".12"/><stop offset="100%" stopColor={`var(--ms-series-${s.id})`} stopOpacity="0"/></linearGradient>)}</defs>
          {[30,95,160,225,290].map(v => <line key={v} x1="20" x2="980" y1={v} y2={v} className="ms-grid-line"/>)}
          {[0,1,2,3,4,5,6].map(v => <line key={v} x1={20+v*160} x2={20+v*160} y1="20" y2="290" className="ms-grid-line"/>)}
          {series.map(s => {const d = 'M' + s.values.map((v,i) => `${x(i)},${y(v)}`).join(' L'); return <g key={s.id} opacity={hidden.includes(s.id) ? 0 : 1} className="ms-series"><path d={`${d} L${x(count-1)},290 L${x(0)},290 Z`} fill={`url(#${id}-${s.id})`}/><path d={d} fill="none" stroke={`var(--ms-series-${s.id})`} strokeWidth="2" vectorEffect="non-scaling-stroke"/>{s.values.map((v,i) => (i === count-1 || i === point) && <circle key={i} cx={x(i)} cy={y(v)} r={i === point ? 5 : 3} fill={`var(--ms-series-${s.id})`} stroke="var(--inrou-surface)" strokeWidth="1.5"/>)}</g>;})}
          {point !== null && <line x1={x(point)} x2={x(point)} y1="20" y2="290" stroke="var(--inrou-text-muted)" strokeDasharray="3 3"/>}
        </svg>
        {!small && <div className="ms-chart-points" role="group" aria-label="Точки графика">{series[0].values.map((_, i) => <button key={i} tabIndex={i === Math.min(tab, count - 1) ? 0 : -1} style={{left: `${x(i)/10}%`, width: `${90/count}%`}} aria-label={`${date(i)}, показать ${metric==='cpa'?'CPA':'расходы'}`} onPointerEnter={e => {if(e.pointerType === 'mouse') setPoint(i);}} onClick={() => {setPoint(i); setTab(i);}} onFocus={() => {setPoint(i); setTab(i);}} onKeyDown={e => {if(e.key === 'Escape') setPoint(null); if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)) {e.preventDefault(); const next = e.key === 'Home' ? 0 : e.key === 'End' ? count-1 : Math.max(0,Math.min(count-1,i+(e.key === 'ArrowRight'?1:-1))); (e.currentTarget.parentElement?.children[next] as HTMLButtonElement)?.focus();}}}/>)}</div>}
        {!small && point !== null && <div className="ms-chart-tooltip" style={{left: `clamp(0px, ${Math.min(64, Math.max(0, x(point)/10-12))}%, calc(100% - 250px))`}} role="status"><strong>{date(point)} 2026 · МСК</strong>{series.filter(s => !hidden.includes(s.id)).map(s => <p key={s.id}><i style={{background:`var(--ms-series-${s.id})`}}/>{s.name}<b>{new Intl.NumberFormat('ru-RU').format(s.values[point])} ₽</b></p>)}<small>Синтетические данные · не отчёт источника</small></div>}
      </div>
    </div>
    <div className="ms-x-axis" aria-hidden>{[0, Math.floor((count-1)/2), count-1].filter((v,i,a)=>a.indexOf(v)===i).map(i => <span key={i}>{date(i)}</span>)}</div>
    {!small && <>{series.every(s => hidden.includes(s.id)) && <p role="status" className="ms-caption">Все ряды скрыты. Выберите кампанию в легенде.</p>}<div className="ms-legend">{series.map(s => <button key={s.id} aria-pressed={!hidden.includes(s.id)} style={{'--series-color':`var(--ms-series-${s.id})`} as CSSProperties} onClick={() => setHidden(h => h.includes(s.id)?h.filter(v=>v!==s.id):[...h,s.id])}><i/>{s.name}</button>)}<button className="ms-table-toggle" aria-expanded={table} onClick={()=>setTable(!table)}>Таблица данных</button></div>{table && <div className="ms-table-scroll"><table><caption>Синтетические {metric==='cpa'?'CPA':'расходы'} · ₽</caption><thead><tr><th>Период</th>{series.filter(s=>!hidden.includes(s.id)).map(s=><th key={s.id}>{s.name}</th>)}</tr></thead><tbody>{series[0].values.map((_,i)=><tr key={i}><th>{date(i)}</th>{series.filter(s=>!hidden.includes(s.id)).map(s=><td key={s.id}>{s.values[i]}</td>)}</tr>)}</tbody></table></div>}</>}
  </div>;
}
