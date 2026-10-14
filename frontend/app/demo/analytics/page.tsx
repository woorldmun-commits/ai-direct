"use client";
import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ReferenceChart } from "@/components/app/reference-chart";
import { CalendarDays, ChevronRight, ShieldCheck, Plug, Lightbulb, ArrowUpRight } from "lucide-react";
import { PageHeader, PlatformIcon } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { LineChart, Sparkline } from "@/components/charts";
import { WEEK, PREV_WEEK, WEEK_VALUES, PREV_WEEK_VALUES, DAYS, P7, PREV7, CAMPAIGNS, cpaSeries, actual } from "@/lib/demo";
import { formatPeriod } from "@/lib/value";
import { useDemo } from "@/components/app/store";

export default function Analytics(){
 const [period,setPeriod]=useState("current");
 const [metric,setMetric]=useState<"all"|"spend"|"conversions"|"cpa">("all");
 const { active, openWhy }=useDemo();
 const week=period==="current"?WEEK:PREV_WEEK;
 const values=period==="current"?WEEK_VALUES:PREV_WEEK_VALUES;
 const chartValues=metric==="cpa"?cpaSeries(week):week[metric==="all"?"spend":metric];
 const previous=metric==="cpa"?cpaSeries(PREV_WEEK):PREV_WEEK[metric==="all"?"spend":metric];
 return <><PageHeader title="Анализ" sub="Итоговый анализ кампаний за выбранный период"><label className="analytics-period"><CalendarDays size={16}/><select aria-label="Период анализа" value={period} onChange={e=>setPeriod(e.target.value)}><option value="current">{formatPeriod(P7)}</option><option value="previous">{formatPeriod(PREV7)}</option></select></label></PageHeader>
 <div className="analytics-kpis">{([["Расход","spend"],["Конверсии","conversions"],["CPA","cpa"]] as const).map(([label,key])=><article className="card" key={key}><h2>{label}</h2><div className="analytics-value"><ValueView v={values[key]} hint={false}/></div>{period==="current"?<Image src="/figma/liquid/6-40708-img2.svg" alt="" width={113.357} height={26.7674} unoptimized className="reference-kpi-line"/>:<Sparkline values={key==="cpa"?cpaSeries(week):week[key]} color="#42cfa4"/>}</article>)}<article className="card"><h2>Выручка</h2><div className="analytics-value text-muted">—</div><Link href="/demo/integrations" className="analytics-revenue">Подключите источник выручки <ArrowUpRight size={12}/></Link></article></div>
 <div className="analytics-grid"><div className="analytics-main"><section className="card analytics-panel"><div className="analytics-panel-header"><h2>Динамика показателей</h2><div className="flex flex-wrap gap-2">{([["all","Все"],["spend","Расход"],["conversions","Конверсии"],["cpa","CPA"]] as const).map(([key,label])=><button key={key} className="chip" aria-pressed={metric===key} onClick={()=>setMetric(key)}>{label}</button>)}</div></div>{period==="current"?<ReferenceChart metric={metric} labels={DAYS}/>:<LineChart bars labels={period==="current"?DAYS:["18","19","20","21","22","23","24"]} height={260} series={[{name:period==="current"?"Текущий период":"Предыдущий период",values:chartValues,color:metric==="spend"?"#48c6ff":metric==="conversions"?"#43dbbe":"#a293ff"},...(period==="current"?[{name:"Предыдущие 7 дней",values:previous,color:"#a293ff",dashed:true}]:[])]} format={v=>new Intl.NumberFormat("ru-RU",{notation:"compact"}).format(v)}/>}</section>
 <section className="card analytics-panel"><div className="analytics-panel-header"><h2>Ключевые находки · последний аудит</h2><Link href="/demo/recommendations" aria-label="Все рекомендации"><ChevronRight size={18}/></Link></div><div className="analytics-findings">{active.slice(0,3).map(r=><article key={r.id}><span className="analytics-finding-mark"><Lightbulb size={18}/></span><div><h3>{r.title}</h3><p>Проверьте доказательства перед изменением рекламы</p></div><button className="btn btn-secondary btn-sm" onClick={()=>openWhy(r.id)}>Подробнее</button></article>)}</div></section></div>
 <aside className="analytics-side"><section className="card analytics-panel"><div className="analytics-panel-header"><h2>Расход по кампаниям</h2><Link href="/demo/campaigns" aria-label="Все кампании"><ChevronRight size={18}/></Link></div>{CAMPAIGNS.map(c=><Link href={`/demo/recommendations?campaign=${c.id}`} key={c.id} className="analytics-campaign"><PlatformIcon platform={c.platform}/><span><strong>{c.name}</strong><small>{c.conversions} конверсий</small></span><b><ValueView v={actual(c.spend,"rub","yandex_direct")} hint={false}/></b></Link>)}<Link href="/demo/campaigns" className="btn btn-secondary btn-sm mt-4 w-full">Все кампании</Link></section>
 <section className="card analytics-panel"><div className="analytics-panel-header"><h2>Здоровье данных</h2><span className="analytics-healthy"><ShieldCheck size={12}/> Демо</span></div>{[{name:"Яндекс Директ",sub:"Подключён · 1 аккаунт",mark:"➤",tone:"direct"},{name:"Яндекс Метрика",sub:"Подключена · 3 цели",mark:"↗",tone:"metrika"},{name:"Рекомендации",sub:`Последний аудит · ${active.length} находок`,mark:"✓",tone:"audit"}].map(s=><Link key={s.name} href="/demo/integrations" className="analytics-source"><span className={`source-mark ${s.tone}`}>{s.mark}</span><div><strong>{s.name}</strong><small>{s.sub}</small></div><ChevronRight size={15}/></Link>)}{["VK Реклама","Avito","CRM"].map(name=><Link key={name} href="/demo/integrations" className="analytics-source"><span className="source-mark"><Plug size={16}/></span><div><strong>{name}</strong><small>Не подключено</small></div><ChevronRight size={15}/></Link>)}</section></aside></div>
 <p className="mt-4 text-xs text-muted">Демонстрационные данные. Конверсии последних дней могут пересчитываться. Сравнение периодов не доказывает эффект решений.</p></>;
}



