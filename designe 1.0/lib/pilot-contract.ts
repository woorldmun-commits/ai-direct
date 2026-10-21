import type { Value } from './value';

type RecordValue = Record<string, unknown>;
export type Workspace = { id: string; name: string };
export type PilotMe = { organizations: { name: string; workspaces: Workspace[] }[] };
export type PilotRecommendation = {
  id: string; title: string; version_id: string; computed_at: string;
  exposure: Value; exposure_overlap: Value; action_level: string;
};
export type SourceFreshness = { status: string | null; data_to: string | null; last_success_at: string | null };
export type PilotToday = {
  top?: PilotRecommendation[];
  audit_scope?: null|{rules:string[];period:{from:string;to:string};ad_accounts:{checked:number;excluded:number};campaigns:number};
  spent: Value; exposure: { total: Value }; counts: { active: number };
  last_audit_at: string | null; data_status: 'complete' | 'partial';
  data_freshness: { yandex_direct: SourceFreshness; yandex_metrika: SourceFreshness };
};
export type PilotRecommendations = { items: PilotRecommendation[]; next_cursor: string | null };
const record = (v: unknown): v is RecordValue => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length <= 4000;
const optionalText = (v: unknown) => v === null || text(v);
const date = (v: unknown): v is string => text(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,10) === v;
const enumValue = (v: unknown, values: readonly string[]) => typeof v === 'string' && values.includes(v);
const instant = (v: unknown) => v === null || (text(v) && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v)));
export const workspaceId = (v: unknown): v is string => text(v) && /^ws_[1-9]\d{0,18}$/.test(v);
export const cursor = (v: unknown): v is string => text(v) && /^o\d{1,9}$/.test(v);

export function isValue(v: unknown): v is Value {
  if (!record(v) || !enumValue(v.unit, ['rub', 'count', 'pct']) || !text(v.source)
    || !/^(yandex_direct|yandex_metrika|user_input)(\+(yandex_direct|yandex_metrika|user_input))*$/.test(v.source)
    || !record(v.period) || !date(v.period.from) || !date(v.period.to) || v.period.from > v.period.to
    || !enumValue(v.data_status, ['complete', 'partial']) || !optionalText(v.rule_version)
    || !optionalText(v.formula)) return false;
  if (v.calculation_type === 'unavailable') return v.amount === null && v.data_sufficiency === 'insufficient'
    && enumValue(v.unavailable_reason, ['source_missing', 'no_conversions', 'history_insufficient', 'volume_insufficient', 'no_forecast', 'no_data']);
  return (v.calculation_type === 'actual' || v.calculation_type === 'estimated')
    && text(v.amount) && /^-?\d{1,30}(\.\d{1,6})?$/.test(v.amount)
    && v.data_sufficiency === 'sufficient' && v.unavailable_reason === null
    && (v.calculation_type !== 'estimated' || (text(v.formula) && v.formula.trim().length > 0));
}
export function isMe(v: unknown): v is PilotMe {
  return record(v) && Array.isArray(v.organizations) && v.organizations.length <= 100
    && v.organizations.every(o => record(o) && text(o.name) && Array.isArray(o.workspaces)
      && o.workspaces.length <= 1000 && o.workspaces.every(w => record(w) && workspaceId(w.id) && text(w.name)));
}
function source(v: unknown): v is SourceFreshness {
  return record(v) && optionalText(v.status) && (v.data_to === null || date(v.data_to)) && instant(v.last_success_at);
}
export function isToday(v: unknown): v is PilotToday {
  return record(v) && isValue(v.spent) && record(v.exposure) && isValue(v.exposure.total)
    && record(v.counts) && Number.isSafeInteger(v.counts.active) && Number(v.counts.active) >= 0
    && instant(v.last_audit_at) && enumValue(v.data_status, ['complete', 'partial'])
    && record(v.data_freshness) && source(v.data_freshness.yandex_direct) && source(v.data_freshness.yandex_metrika)
    &&(v.top===undefined||Array.isArray(v.top)&&v.top.length<=3&&isRecommendations({items:v.top,next_cursor:null}))
    &&(v.audit_scope===undefined||v.audit_scope===null||record(v.audit_scope)&&Array.isArray(v.audit_scope.rules)&&v.audit_scope.rules.every(text)&&record(v.audit_scope.period)&&date(v.audit_scope.period.from)&&date(v.audit_scope.period.to)&&v.audit_scope.period.from<=v.audit_scope.period.to&&record(v.audit_scope.ad_accounts)&&[v.audit_scope.ad_accounts.checked,v.audit_scope.ad_accounts.excluded,v.audit_scope.campaigns].every(n=>Number.isSafeInteger(n)&&Number(n)>=0));
}
export function isRecommendations(v: unknown): v is PilotRecommendations {
  return record(v) && (v.next_cursor === null || cursor(v.next_cursor)) && Array.isArray(v.items)
    && v.items.length <= 100 && v.items.every(r => record(r) && text(r.id) && text(r.title)
      && text(r.version_id) && r.computed_at !== null && instant(r.computed_at)
      && enumValue(r.action_level, ['change', 'review', 'inspect_only'])
      && isValue(r.exposure) && isValue(r.exposure_overlap));
}
