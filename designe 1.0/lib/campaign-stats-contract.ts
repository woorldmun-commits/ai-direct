import {isValue} from './pilot-contract';
import type {Value} from './value';

export const STAT_LABEL = {cost:'Расход', clicks:'Клики', impressions:'Показы', conversions:'Конверсии', cpa:'CPA'} as const;
export type StatKey = keyof typeof STAT_LABEL;
export type StatMetrics = Record<StatKey, Value>;
export type CampaignStats = {
  accounts: string[];
  campaign_count:number; next_offset:number|null;
  period: {from:string;to:string};
  scope: {selected:number;included:number;complete:boolean;excluded:{ad_account:string;reason:string}[]};
  provenance: {ad_account:string;snapshot_id:string;sealed_at:string;partial_from:string;conversion_definition:unknown}[];
  summary: StatMetrics; daily: {date:string;metrics:StatMetrics}[];
  campaigns: {ad_account:string;campaign_id:string;metrics:StatMetrics}[]; limitations:string[];
};
const record = (v:unknown):v is Record<string,unknown> => !!v && typeof v==='object' && !Array.isArray(v);
const day = (v:unknown):v is string => typeof v==='string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v));
const account = (v:unknown):v is string => typeof v==='string' && /^acc_[1-9]\d{0,18}$/.test(v);
const metrics = (v:unknown):v is StatMetrics => record(v) && Object.keys(STAT_LABEL).every(key=>isValue(v[key]));
export function isCampaignStats(v:unknown):v is CampaignStats {
  return record(v) && record(v.period) && day(v.period.from) && day(v.period.to) && v.period.from<=v.period.to
    && Array.isArray(v.accounts) && v.accounts.length<=1000 && v.accounts.every(account)
    && record(v.scope) && Number.isSafeInteger(v.scope.selected) && Number.isSafeInteger(v.scope.included) && typeof v.scope.complete==='boolean'
    && Array.isArray(v.scope.excluded) && v.scope.excluded.length<=1000 && v.scope.excluded.every(x=>record(x)&&account(x.ad_account)&&typeof x.reason==='string')
    && Array.isArray(v.provenance) && v.provenance.length<=1000 && v.provenance.every(x=>record(x)&&account(x.ad_account)&&typeof x.snapshot_id==='string'&&/^\d+$/.test(x.snapshot_id)&&typeof x.sealed_at==='string'&&Number.isFinite(Date.parse(x.sealed_at))&&day(x.partial_from))
    && metrics(v.summary) && Array.isArray(v.daily) && v.daily.length<=30 && v.daily.every(x=>record(x)&&day(x.date)&&metrics(x.metrics))
    && Number.isSafeInteger(v.campaign_count) && (v.next_offset===null || Number.isSafeInteger(v.next_offset))
    && Array.isArray(v.campaigns) && v.campaigns.length<=200 && v.campaigns.every(x=>record(x)&&account(x.ad_account)&&typeof x.campaign_id==='string'&&/^[1-9]\d{0,18}$/.test(x.campaign_id)&&metrics(x.metrics))
    && Array.isArray(v.limitations) && v.limitations.length<=20 && v.limitations.every(x=>typeof x==='string'&&x.length<2000);
}
