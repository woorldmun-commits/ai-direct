"use client";
import { useState } from "react";
import Link from "next/link";
import { Search, ArrowUpRight } from "lucide-react";
import { PageHeader, PlatformIcon } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { CAMPAIGNS, actual, P7 } from "@/lib/demo";
import { formatPeriod } from "@/lib/value";

export default function Campaigns() {
  const [filter,setFilter]=useState("all");
  const [query,setQuery]=useState("");
  const rows=CAMPAIGNS.filter(c=>(filter==="all"||c.platform===filter)&&c.name.toLocaleLowerCase("ru").includes(query.toLocaleLowerCase("ru")));
  return <><PageHeader title="Кампании" sub={`Статистика Яндекс Директа · ${formatPeriod(P7)}`}><Link href="/demo/integrations" className="btn btn-secondary">Источники <ArrowUpRight size={16}/></Link></PageHeader>
    <div className="mb-5 flex flex-wrap items-center gap-2">{[["all","Все кампании"],["search","Поиск"],["network","РСЯ"]].map(([v,t])=><button key={v} className="chip" aria-pressed={filter===v} onClick={()=>setFilter(v)}>{t}</button>)}<label className="ml-auto flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2"><Search size={16} className="text-muted"/><input aria-label="Поиск кампаний" placeholder="Найти кампанию" value={query} onChange={e=>setQuery(e.target.value)} className="w-40 bg-transparent text-sm outline-none"/></label></div>
    <div className="card overflow-x-auto"><table className="cabinet-table"><thead><tr><th>Кампания</th><th>Расход</th><th>Конверсии</th><th>CPA</th><th>Действия</th></tr></thead><tbody>{rows.map(c=><tr key={c.id}><td><div className="flex items-center gap-3"><PlatformIcon platform={c.platform}/><div className="min-w-44 font-medium">{c.name}<small className="block text-xs text-muted">ID {c.id}</small></div></div></td><td><ValueView v={actual(c.spend,"rub","yandex_direct")} hint={false}/></td><td>{c.conversions}</td><td>{c.conversions?<ValueView v={actual(c.spend/c.conversions,"rub","yandex_direct+yandex_metrika")} hint={false}/>:"Нет конверсий"}</td><td><Link href={`/demo/recommendations?campaign=${encodeURIComponent(c.id)}`} aria-label={`Проверить кампанию ${c.name}`} className="btn btn-secondary btn-sm">Проверить</Link></td></tr>)}</tbody></table>{!rows.length&&<p role="status" className="p-8 text-center text-muted">Кампании не найдены. Измените фильтр или запрос.</p>}</div><p className="mt-4 text-xs text-muted">Демонстрационные кампании. Изменения рекламы выполняются вручную в Директе.</p></>;
}

