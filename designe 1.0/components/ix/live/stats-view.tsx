'use client';
import Link from 'next/link';
import {useState} from 'react';
import {ValueView} from '@/components/value-view';
import {STAT_LABEL, type CampaignStats, type StatKey} from '@/lib/campaign-stats-contract';

import {ChartPlot} from '../chart';
import {Card, Info, Kpi, Table} from '../ui';
import {useIxSearch} from '../shell';

// Cost is a nonnegative SQL Decimal with two fractional places; sorting stays exact.
const cents = (amount:string|null) => amount===null ? BigInt(-1) : BigInt(amount.split('.')[0])*BigInt(100)+BigInt((amount.split('.')[1]??'').padEnd(2,'0'));

export function StatsView({data, ws, days, detail=false}: {data:CampaignStats;ws:string;days:string;detail?:boolean}) {
  const [metric, setMetric] = useState<StatKey>('cost');
  const [sort, setSort] = useState<'cost'|'campaign'>('cost');
  const query = useIxSearch();
  const rows = data.campaigns.filter(row=>!query||`${row.campaign_id} ${row.ad_account}`.includes(query)).toSorted((a,b)=>sort==='campaign'?a.campaign_id.localeCompare(b.campaign_id,undefined,{numeric:true}):(cents(a.metrics.cost.amount)<cents(b.metrics.cost.amount)?1:cents(a.metrics.cost.amount)>cents(b.metrics.cost.amount)?-1:0));
  const values = data.daily.map(point=>point.metrics[metric]);
  const hasPoints = values.some(value=>value.amount!==null);
  const unit = metric==='cost'?'₽':metric==='cpa'?'₽/конверсия':'шт.';
  // Number is used only for SVG coordinates. Exact values are rendered by ValueView.
  const points = data.daily.map(point=>{const value=point.metrics[metric], amount=value.amount;const coordinate=amount===null?null:Number(amount);return {label:point.date,value:coordinate!==null&&Number.isFinite(coordinate)?coordinate:null,prev:null,display:null,prevDisplay:null,evidence:value,status:value.calculation_type};});
  return <>
    <div className="ix-grid ix-kpis">{(['cost','clicks','conversions','cpa'] as StatKey[]).map(key=><Kpi key={key} label={STAT_LABEL[key]} value={<ValueView v={data.summary[key]}/>} tone="muted" />)}</div>
    <Card className="ix-chart-card"><div className="ix-head"><h2>Динамика показателей</h2><label className="ix-mini">Показатель <select className="ix-pill" value={metric} onChange={event=>setMetric(event.target.value as StatKey)}>{Object.entries(STAT_LABEL).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
      {hasPoints ? <ChartPlot points={points} showPrev={false} seriesName={`${STAT_LABEL[metric]} · ${unit}`} source="Яндекс Директ · строки кампаний" period={`${data.period.from} — ${data.period.to}`} updated={data.provenance.map(p=>p.sealed_at).toSorted().at(0)} ariaLabel={`${STAT_LABEL[metric]} по дням, ${unit}`} fit caption="Пропуски не заменяются нулём. Данные последних дней могут уточняться." /> : <Info warning>Наблюдений за выбранный период недостаточно. Проверьте источники или измените период.</Info>}
    </Card>
    {!detail&&<Card className="ix-campaign-list"><div className="ix-head"><h2>Кампании</h2><label className="ix-mini">Сортировка <select className="ix-pill" value={sort} onChange={e=>setSort(e.target.value as 'cost'|'campaign')}><option value="cost">По расходу</option><option value="campaign">По номеру</option></select></label></div>{rows.length?<Table label="Кампании выбранного периода" head={['Кампания','Аккаунт','Расход','Клики','Конверсии','CPA']} rows={rows.map(row=>[<Link key="name" href={`/workspace/campaigns/${row.campaign_id}?workspace=${ws}&ad_account=${row.ad_account}&days=${days}`}>Кампания {row.campaign_id}</Link>,row.ad_account,...(['cost','clicks','conversions','cpa'] as StatKey[]).map(key=><ValueView key={key} v={row.metrics[key]}/> )])}/>:<p className="ix-muted">Кампании по выбранным условиям не найдены.</p>}</Card>}
  </>;
}
