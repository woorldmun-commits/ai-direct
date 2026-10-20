'use client';
import {useId,useRef,useState} from 'react';
import {campaigns,seriesFor,rub,num,type Campaign} from './model';
import type {Metric} from './demo-data';
export const chartMetrics = [{key:'spend',label:'Расходы',color:'var(--chart-spend)'},{key:'conversions',label:'Конверсии',color:'var(--chart-conversions)'},{key:'cpa',label:'CPA',color:'var(--chart-cpa)'},{key:'revenue',label:'Выручка',color:'var(--chart-revenue)'}] as const;
export function curve(points:number[][]) {
 return points.map(([x,y],i)=>(i?'L ':'M ')+x+' '+y).join(' ');
}
export function ReferenceChart({days=31,metric='all',compact=false,rows=campaigns}:{days?:number;metric?:Metric|'all';compact?:boolean;rows?:Campaign[]}) {
 const id=useId().replaceAll(':',''),[selected,setSelected]=useState<number|null>(compact?null:14),[hidden,setHidden]=useState<string[]>([]);
 const pointRefs=useRef<(SVGRectElement|null)[]>([]);
 const data=seriesFor(rows,days),spend=data.spend,conversions=data.conversions;
 const active=chartMetrics.filter(m=>(metric==='all'||metric===m.key)&&!hidden.includes(m.key));
 const points=(key:Metric)=>data[key].map((v,i)=>[spend.length===1?343:48+i*590/(spend.length-1),220-v/Math.max(1,...data[key])*180]);
 const point=selected===null?null:Math.min(selected,spend.length-1);
 return <div className={'ap-chart '+(compact?'ap-chart-compact':'')} onMouseLeave={e=>{if(!e.currentTarget.contains(document.activeElement))setSelected(null);}} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setSelected(null);}}>
 {!compact&&<div className="ap-legend">{chartMetrics.map(m=><button key={m.key} aria-pressed={!hidden.includes(m.key)} onClick={()=>setHidden(v=>v.includes(m.key)?v.filter(k=>k!==m.key):[...v,m.key])} className={hidden.includes(m.key)?'is-muted':''}><i style={{background:m.color}}/>{m.label}</button>)}<small>% от максимума каждой метрики</small></div>}
 <svg viewBox="0 0 660 254" preserveAspectRatio="none" role="group" aria-label="Динамика показателей. Стрелки влево и вправо — по датам, Home и End — начало и конец периода.">
 <defs>{active.map(m=><linearGradient id={id+'-'+m.key} key={m.key} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={m.color} stopOpacity=".22"/><stop offset="1" stopColor={m.color} stopOpacity=".015"/></linearGradient>)}</defs>
 {[0,25,50,75,100].map((v,i)=><g key={v}><line x1="48" x2="638" y1={220-i*45} y2={220-i*45} stroke="var(--border)"/><text x="34" y={224-i*45} textAnchor="end">{v}</text></g>)}
 {(days===1?[.5]:[0,.25,.5,.75,1]).map(v=><g key={v}><line x1={48+590*v} x2={48+590*v} y1="40" y2="220" stroke="var(--border)"/><text x={48+590*v} y="244" textAnchor="middle">{Math.round(32-days+(days-1)*v)} мар</text></g>)}
 {active.map(m=><g key={m.key}>{spend.length===1?<circle cx={points(m.key)[0][0]} cy={points(m.key)[0][1]} r={4} fill={m.color}/>:<><path d={curve(points(m.key))+' L638 220 L48 220 Z'} fill={'url(#'+id+'-'+m.key+')'}/><path className="ap-chart-line" d={curve(points(m.key))} fill="none" stroke={m.color} strokeWidth="1.8"/></>}</g>)}
 {point!==null&&<line x1={points('spend')[point][0]} x2={points('spend')[point][0]} y1="35" y2="220" stroke="#9aa9da" strokeDasharray="3 3"/>}
 {spend.map((_,i)=><rect key={i} ref={node=>{pointRefs.current[i]=node;}} className="ap-chart-point" x={points('spend')[i][0]-Math.max(6,590/spend.length/2)} y="30" width={Math.max(12,590/spend.length)} height="190" fill="transparent" role="button" tabIndex={(point??0)===i?0:-1} aria-label={(32-days+i)+' марта: '+active.map(m=>m.label+' '+(m.key==='cpa'&&!conversions[i]?'—':m.key==='conversions'?num(data[m.key][i]):rub(data[m.key][i]))).join(', ')} onPointerEnter={()=>setSelected(i)} onClick={()=>setSelected(i)} onFocus={()=>setSelected(i)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(i);}if(e.key==='Escape')setSelected(null);if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?spend.length-1:Math.max(0,Math.min(spend.length-1,i+(e.key==='ArrowRight'?1:-1)));pointRefs.current[next]?.focus();}}}/>)}
 </svg>
 {point!==null&&<div className="ap-tooltip" role="status" style={{left:`min(calc(100% - var(--ap-tooltip-width, 185px) - 8px), ${spend.length===1?55:12+point/(spend.length-1)*90}%)`}}><strong>{32-days+point} марта 2025</strong>{active.map(m=><span key={m.key}><i style={{background:m.color}}/>{m.label}<b>{m.key==='cpa'&&!conversions[point]?'—':m.key==='conversions'?num(data[m.key][point]):rub(data[m.key][point])}</b></span>)}</div>}
 </div>;
}
export function MiniChart({metric='spend',values,color:lineColor}:{metric?:Metric;days?:number;values?:number[];color?:string}) {
 const id=useId().replaceAll(':',''),color=lineColor||{spend:'var(--chart-spend)',conversions:'var(--chart-conversions)',cpa:'var(--chart-cpa)',revenue:'var(--chart-revenue)'}[metric];
 const data=values||[2,1,3,4,3,5,5,8,7,9,8,12,14,12,17,15,20];
 const pts=data.map((v,i)=>[i*180/Math.max(1,data.length-1),35-v/Math.max(1,...data)*31]);
 return <svg className="ap-spark" viewBox="0 0 180 38" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop stopColor={color} stopOpacity=".26"/><stop offset="1" stopColor={color} stopOpacity=".03"/></linearGradient></defs><path d={curve(pts)+' L180 38 L0 38 Z'} fill={'url(#'+id+')'}/><path d={curve(pts)} fill="none" stroke={color} strokeWidth="1"/></svg>;
}
