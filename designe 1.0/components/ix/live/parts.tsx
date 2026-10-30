import Link from 'next/link';
import {ValueView} from '@/components/value-view';
import {STATE_TEXT, stamp, type LiveCode} from '@/lib/ix-live';
import type {PilotToday} from '@/lib/pilot-contract';
import {CALCULATION_LABEL, UNAVAILABLE_REASON_LABEL, formatPeriod, sourceLabel, type Value} from '@/lib/value';
import {DataHealth, Info, Kpi, StateBlock} from '../ui';

export function ErrorState({code, page}: {code: LiveCode; page?: boolean}) {
  const [title, text] = STATE_TEXT[code];
  return <StateBlock level={page ? 1 : 2} kind={code === 'access' ? 'forbidden' : 'error'} title={title} action={code === 'session' ? <Link className="ix-btn ix-btn--primary" href="/login">Войти</Link> : undefined}>{text}</StateBlock>;
}

/** Показатель из контракта Value: число — только через ValueView, подпись — тип, источник и период. */
export function ValueKpi({label, v}: {label: string; v: Value}) {
  if (v.calculation_type === 'unavailable') return <Kpi label={label} value={<span className="ix-value-na">{CALCULATION_LABEL.unavailable}</span>} tone="muted" foot={`${UNAVAILABLE_REASON_LABEL[v.unavailable_reason] ?? UNAVAILABLE_REASON_LABEL.no_data} · ${sourceLabel(v.source)} · ${formatPeriod(v.period)}`} />;
  return <Kpi label={label} value={<ValueView v={v} />} tone="muted" foot={`${CALCULATION_LABEL[v.calculation_type]} · ${sourceLabel(v.source)} · ${formatPeriod(v.period)}`} />;
}

export const NoSeries = ({what = 'график'}: {what?: string}) => <Info warning role="status">
  Для этого объекта сопоставимый ряд по дням пока недоступен, поэтому {what} не строится. Недостающие точки не заменяются нулями. Доступные показатели и их период указаны в карточках.
</Info>;

type Fresh = PilotToday['data_freshness']['yandex_direct'];
/** Состояние источника по данным сервера: подключён / нужна проверка / не подключён и устарели ли данные (> 72 ч). */
export function sourceState(s: Fresh, checkedAt: number) {
  const stale = !s.data_to || checkedAt - Date.parse(s.data_to + 'T21:00:00Z') > 72 * 3_600_000;
  if (s.status === null) return {label: 'Не подключён', warn: true, stale: true};
  if (s.status !== 'connected') return {label: 'Нужна проверка подключения', warn: true, stale};
  return stale ? {label: 'Данные требуют обновления', warn: true, stale} : {label: 'Подключён, данные свежие', warn: false, stale};
}

export function HealthBanner({today, checkedAt, ws}: {today: PilotToday; checkedAt: number; ws: string}) {
  const d = sourceState(today.data_freshness.yandex_direct, checkedAt);
  const m = sourceState(today.data_freshness.yandex_metrika, checkedAt);
  const warn = d.warn || m.warn || today.data_status === 'partial';
  return <><DataHealth warning={warn}>Яндекс Директ: {d.label.toLowerCase()}, данные по {today.data_freshness.yandex_direct.data_to ?? 'нет данных'} · Метрика: {m.label.toLowerCase()} · последняя синхронизация Директа: {stamp(today.data_freshness.yandex_direct.last_success_at)}{today.data_status === 'partial' ? ' · данные за период неполные, последние дни могут уточниться' : ''}. <Link href={`/workspace/data-health?workspace=${ws}`} style={{textDecoration: 'underline'}}>О качестве данных</Link></DataHealth><AuditLimitations today={today} ws={ws}/></>;
}

export function AuditLimitations({today,ws}:{today:PilotToday;ws:string}) {
  if(!today.audit_limitations?.length)return null;
  const labels:Record<string,string>={business_context_required:'Подтвердите выбранную цель и задержку конверсии в бизнес-профиле.',goal_mismatch:'Цель или атрибуция профиля не совпадает со снимком источника.',maturity_insufficient:'Для выбранной задержки пока нет достаточного зрелого периода.',outcome_data_required:'Не подтверждены данные качества, состоявшихся визитов или продаж.',source_missing:'Нет необходимого источника или определения конверсии.',no_conversions:'Недостаточно конверсий для сравнения CPA.',baseline_history_insufficient:'Истории для базового сравнения недостаточно.',baseline_data_insufficient:'В базовом периоде недостаточно сопоставимых данных.',volume_insufficient:'Выборка не достигает согласованного порога проверки.'};
  return <Info warning role="status"><strong>Часть проверок не выполнена.</strong> Отсутствие рекомендаций не означает отсутствие проблем.<ul>{today.audit_limitations.map(item=><li key={item.code}>{labels[item.code]??'Проверка ограничена доступными данными.'} Проверок: {item.count}.</li>)}</ul><Link href={`/workspace/business-profile?workspace=${ws}`}>Проверить профиль и определение результата →</Link></Info>;
}
