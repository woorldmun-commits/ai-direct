/* eslint-disable react-hooks/purity -- server component: freshness is checked once per request. */
import {pilotGet} from '@/lib/pilot';
import {safe} from '@/lib/ix-live';
import {isCampaignStats} from '@/lib/campaign-stats-contract';
import {Info, LinkBtn, PageHead} from '../ui';
import {StatsView} from './stats-view';
import {ErrorState} from './parts';
import type {Query} from './core';
import Link from 'next/link';

export async function LiveStats({ws, q, campaign, title='Анализ рекламы', compact=false}: {ws:string;q:Query;campaign?:string;title?:string;compact?:boolean}) {
  const days = q.days ?? '30';
  if (!['7','30'].includes(days) || q.ad_account && !/^acc_[1-9]\d{0,18}$/.test(q.ad_account) || campaign && (!/^[1-9]\d{0,18}$/.test(campaign)||!q.ad_account)) return <ErrorState page code="invalid"/>;
  if(q.offset && (!/^\d{1,5}$/.test(q.offset)||Number(q.offset)>20000))return <ErrorState page code="invalid"/>;
  const query = new URLSearchParams({days});
  if(q.ad_account)query.set('ad_account',q.ad_account);
  if(campaign)query.set('campaign_id',campaign);
  if(q.offset)query.set('offset',q.offset);
  const result = await safe(pilotGet(`/workspaces/${ws}/campaign-stats?${query}`,isCampaignStats));
  if(!result.ok)return <ErrorState page code={result.code}/>;
  const data=result.data;
  const stale=Date.now()-Date.parse(data.period.to+'T21:00:00Z')>72*3_600_000;
  return <>
    <div className="ix-stats-toolbar"><>{compact?<h2>{title}</h2>:<PageHead title={campaign?`Кампания ${campaign}`:title} sub="Яндекс Директ · выбранные аккаунты" />}</>
    <form className="ix-actions ix-stats-filters" method="get"><input type="hidden" name="workspace" value={ws}/><label>Период <select name="days" className="ix-pill" defaultValue={days}><option value="7">7 дней</option><option value="30">30 дней</option></select></label><label>Аккаунт <select name="ad_account" className="ix-pill" defaultValue={q.ad_account??''} required={!!campaign}>{!campaign&&<option value="">Все выбранные</option>}{data.accounts.map(account=><option key={account} value={account}>{account}</option>)}</select></label><button type="submit" className="ix-btn">Показать</button></form></div>
    <Info warning={!data.scope.complete||stale}>{stale&&'Данные требуют обновления · '}{data.period.from} — {data.period.to} · аккаунтов {data.scope.included}/{data.scope.selected}.{data.scope.excluded.length>0&&` Исключено: ${data.scope.excluded.map(x=>`${x.ad_account} (${x.reason})`).join(', ')}.`} <Link href={`/workspace/data-health?workspace=${ws}`}>Качество данных →</Link></Info>
    <div className="ix-stats-content"><StatsView data={data} ws={ws} days={days} detail={!!campaign} compact={compact}/></div>
    {!campaign&&!compact&&<div className="ix-actions" style={{marginTop:12}}>{q.offset&&<LinkBtn href={`?workspace=${ws}&days=${days}${q.ad_account?'&ad_account='+q.ad_account:''}`}>К началу</LinkBtn>}{data.next_offset!==null&&<LinkBtn href={`?workspace=${ws}&days=${days}${q.ad_account?'&ad_account='+q.ad_account:''}&offset=${data.next_offset}`}>Следующие кампании</LinkBtn>}<span className="ix-muted ix-mini">Всего кампаний: {data.campaign_count}. Поиск и сортировка — в текущей странице списка.</span></div>}
    <details className="ix-mini ix-muted"><summary>Источники и ограничения</summary>{data.provenance.map(p=><p key={p.ad_account}>{p.ad_account} · снимок {p.snapshot_id} · обновлён {p.sealed_at} · предварительные данные с {p.partial_from}</p>)}<ul>{data.limitations.map(text=><li key={text}>{text}</li>)}</ul></details>
  </>;
}
