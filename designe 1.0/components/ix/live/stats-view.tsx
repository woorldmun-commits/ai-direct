'use client';
import Link from 'next/link';
import {useState} from 'react';
import {ValueView} from '@/components/value-view';
import {STAT_LABEL, type CampaignStats, type StatKey} from '@/lib/campaign-stats-contract';

import {ChartPlot} from '../chart';
import {Card, Info, Kpi, Table} from '../ui';
import {useIxSearch} from '../shell';
import {PeriodComparison} from '@/components/workspace/metric-cards';
import {formatPeriod, sourceLabel} from '@/lib/value';

// Cost is a nonnegative SQL Decimal with two fractional places; sorting stays exact.
const cents = (amount:string|null) => amount===null ? BigInt(-1) : BigInt(amount.split('.')[0])*BigInt(100)+BigInt((amount.split('.')[1]??'').padEnd(2,'0'));

export function StatsView({data, ws, days, detail=false, compact=false}: {data:CampaignStats;ws:string;days:string;detail?:boolean;compact?:boolean}) {
  const [metric, setMetric] = useState<StatKey>('cost');
  const [sort, setSort] = useState<'cost'|'campaign'>('cost');
  const query = useIxSearch();
  const rows = data.campaigns.filter(row=>!query||`${row.campaign_id} ${row.ad_account}`.includes(query)).toSorted((a,b)=>sort==='campaign'?a.campaign_id.localeCompare(b.campaign_id,undefined,{numeric:true}):(cents(a.metrics.cost.amount)<cents(b.metrics.cost.amount)?1:cents(a.metrics.cost.amount)>cents(b.metrics.cost.amount)?-1:0));
  const values = data.daily.map(point=>point.metrics[metric]);
  const hasPoints = values.some(value=>value.amount!==null);
  const unit = metric==='cost'?'₽':metric==='cpa'?'₽/конверсия':'шт.';
  // Number is used only for SVG coordinates. Exact values are rendered by ValueView.
  const points = data.daily.map(point=>{const value=point.metrics[metric], amount=value.amount;const coordinate=amount===null?null:Number(amount);return {label:point.date,value:coordinate!==null&&Number.isFinite(coordinate)?coordinate:null,prev:null,display:null,prevDisplay:null,evidence:value,status:value.calculation_type};});
  const comparisonPoints = data.daily.map(point=>{const value=point.metrics[metric], amount=value.amount;return {label:point.date.slice(8),current:amount===null?null:Number(amount),display:<ValueView v={value}/>};});
  return <>
    {!compact&&<div className="ix-grid ix-kpis">{(['cost','clicks','conversions','cpa'] as StatKey[]).map(key=><Kpi key={key} label={STAT_LABEL[key]} value={<ValueView v={data.summary[key]}/>} tone="muted" foot={`${sourceLabel(data.summary[key].source)} · ${formatPeriod(data.summary[key].period)}`}/>)}</div>}
    <div className={compact ? undefined : 'metric-analysis-layout'}>
    <Card className="ix-chart-card"><div className="ix-head"><h2>Динамика показателей</h2><label className="ix-mini">Показатель <select className="ix-pill" value={metric} onChange={event=>setMetric(event.target.value as StatKey)}>{Object.entries(STAT_LABEL).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
      {hasPoints ? <ChartPlot points={points} showPrev={false} seriesName={`${STAT_LABEL[metric]} · ${unit}`} source="Яндекс Директ · строки кампаний" period={`${data.period.from} — ${data.period.to}`} updated={data.provenance.map(p=>p.sealed_at).toSorted().at(0)} ariaLabel={`${STAT_LABEL[metric]} по дням, ${unit}`} fit caption="Пропуски не заменяются нулём. Данные последних дней могут уточняться." /> : <Info warning>Наблюдений за выбранный период недостаточно. Проверьте источники или измените период.</Info>}
    </Card>
    {!compact&&<aside className="metric-analysis-aside"><span className="metric-label">Контекст показателя</span><h2 style={{marginTop:18}}>{STAT_LABEL[metric]} за период</h2><div className="metric-hero-number"><ValueView v={data.summary[metric]}/></div><p className="metric-note">{sourceLabel(data.summary[metric].source)} · {formatPeriod(data.period)}</p><dl><div><dt>Аккаунтов в расчёте</dt><dd>{data.scope.included} / {data.scope.selected}</dd></div><div><dt>Кампаний в выборке</dt><dd>{data.campaign_count}</dd></div><div><dt>Охват данных</dt><dd>{data.scope.complete ? 'Полный' : 'Неполный'}</dd></div></dl><p className="metric-note">Сравнение с прошлым периодом недоступно: предыдущий ряд не передан источником.</p><Link href={`/workspace/data-health?workspace=${ws}`}>Проверить качество данных →</Link></aside>}
    </div>
    {!compact&&<details className="ix-card" style={{marginTop:16}}><summary style={{minHeight:44,alignContent:'center',cursor:'pointer'}}>Столбики по дням и точные значения</summary><PeriodComparison title={`${STAT_LABEL[metric]} по дням`} note={`Текущий период · ${unit}. Пропуски не заменяются нулями. Предыдущий ряд недоступен.`} points={comparisonPoints}/></details>}
    {!detail&&!compact&&<Card className="ix-campaign-list"><div className="ix-head"><h2>Кампании</h2><label className="ix-mini">Сортировка <select className="ix-pill" value={sort} onChange={e=>setSort(e.target.value as 'cost'|'campaign')}><option value="cost">По расходу</option><option value="campaign">По номеру</option></select></label></div>{rows.length?<Table label="Кампании выбранного периода" head={['Кампания','Аккаунт','Расход','Клики','Конверсии','CPA']} rows={rows.map(row=>[<Link key="name" href={`/workspace/campaigns/${row.campaign_id}?workspace=${ws}&ad_account=${row.ad_account}&days=${days}`}>Кампания {row.campaign_id}</Link>,row.ad_account,...(['cost','clicks','conversions','cpa'] as StatKey[]).map(key=><ValueView key={key} v={row.metrics[key]}/> )])}/>:<p className="ix-muted">Кампании по выбранным условиям не найдены.</p>}</Card>}
  </>;
}
