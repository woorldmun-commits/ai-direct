'use client';
import {useState} from 'react';
import Link from 'next/link';
import {isWeeklyReport, decisionLabels as labels, type WeeklyReportData} from '@/lib/insights-contract';
import {valueText, formatPeriod} from '@/lib/value';
import {ValueView} from '@/components/value-view';

export function WeeklyReport({workspace,report}:{workspace:string;report?:WeeklyReportData}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function download(){
  if(busy)return;setBusy(true);setError('');
  try{
   let body:unknown=report;
   if(!body){const response=await fetch(`/api/workspaces/${workspace}/weekly-report`,{cache:'no-store'});if(!response.ok)throw new Error('Не удалось получить отчёт. Проверьте доступ и повторите.');body=await response.json();}
   if(!isWeeklyReport(body))throw new Error('Данные отчёта требуют проверки.');
   const data=body.insights;
   const lines=['inrou — отчёт за 7 завершённых дней',`Пространство: ${workspace}`,`Период: ${formatPeriod(data.period)}`,`Сформирован: ${data.summary.generated_at}`,'','ДАННЫЕ',...data.summary.facts.flatMap(f=>[f.label+': '+(f.value?valueText(f.value):'Нет значения'),f.detail,f.value?`Источник: ${f.value.source}; период: ${formatPeriod(f.value.period)}; формула: ${f.value.formula??'значение источника'}`:'']),'','СОСТОЯНИЕ ИСТОЧНИКОВ',...data.health.checks.map(c=>`${c.id}: ${c.status}. ${c.action}`),'','РЕШЕНИЯ ЗА ПЕРИОД',...body.decisions.map((d:{type:string;count:number})=>`${labels[d.type]}: ${d.count}`),'Это число событий, а не уникальных проблем. Подробные основания и история — в защищённом кабинете.','','ОГРАНИЧЕНИЯ',...data.summary.limitations,'Сравнение до/после не доказывает причинность. Ручное выполнение не подтверждает изменение в Директе.','Полнота когорты лидов заявляется пользователем; сопоставление из CSV не является проверенной атрибуцией.','Отчёт сформирован по запросу. Автоматическая доставка не подключена.'];
   const url=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}));
   const link=document.createElement('a');link.href=url;link.download=`inrou-week-${data.period.to}.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(e instanceof Error?e.message:'Не удалось сформировать отчёт.');}finally{setBusy(false);}
 }
 if(!report)return <Link className="ref-button" href={`/workspace?view=reports&workspace=${workspace}`}>Открыть недельный отчёт</Link>;
 const data=report.insights;
 return <section aria-label="Недельный отчёт"><h2>Недельный отчёт</h2><p>{formatPeriod(data.period)} · 7 завершённых дней по Москве</p><p>Сформирован: {new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Moscow'}).format(new Date(data.summary.generated_at))} МСК. Состояние источников — на момент формирования.</p><div className="pilot-grid">{data.summary.facts.map(fact=><article className="pilot-card" key={fact.id}><h3>{fact.label}</h3>{fact.value&&<ValueView v={fact.value} caption/>}<p>{fact.detail}</p></article>)}</div><section className="pilot-card"><h3>Состояние источников</h3><ul>{data.health.checks.map(check=><li key={check.id}>{({direct:'Директ',metrika:'Метрика',goals:'Цели',freshness:'Свежесть'} as Record<string,string>)[check.id]??check.id}: {check.status==='ok'?'проверка пройдена':check.status==='attention'?'требует внимания':'нет данных для проверки'}. {check.action}</li>)}</ul></section><section className="pilot-card"><h3>Решения за неделю</h3>{report.decisions.length?<ul>{report.decisions.map(d=><li key={d.type}>{labels[d.type]}: {d.count}</li>)}</ul>:<p>За этот период записанных решений нет.</p>}<p>Показано число событий, а не уникальных проблем.</p><Link className="ref-button" href={`/workspace?view=effect&workspace=${workspace}`}>Открыть решения и замеры</Link></section><section className="pilot-card"><h3>Ограничения отчёта</h3><ul>{data.summary.limitations.map((text,index)=><li key={index}>{text}</li>)}</ul><p>Сравнение до/после не доказывает причинность. Ручное выполнение не подтверждает изменение в Директе. Полнота когорты заявляется пользователем.</p></section><button type="button" className="ref-button" disabled={busy} onClick={()=>void download()}>{busy?'Готовим отчёт…':'Скачать недельный отчёт'}</button>{error&&<p role="alert">{error}</p>}</section>;
}
