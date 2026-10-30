import Link from 'next/link';
import type {ReactNode} from 'react';
import {GRID, H, W, scaleFor, segments, xAt} from './geometry';
import {CountUp} from './count-up';
import {MetricTrend} from '@/components/workspace/metric-cards';

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ');
export const btnClass = (variant?: 'primary' | 'wine') => cx('ix-btn', variant && `ix-btn--${variant}`);

export function PageHead({title, sub, actions, eyebrow = 'INROU / Кабинет'}: {title: string; sub?: ReactNode; actions?: ReactNode; eyebrow?: string}) {
  return <div className="ix-head"><div><div className="ix-eyebrow">{eyebrow}</div><h1>{title}</h1>{sub && <div className="ix-muted">{sub}</div>}</div>{actions && <div className="ix-actions">{actions}</div>}</div>;
}

export const Gap = ({h = 16}: {h?: number}) => <div style={{height: h}} aria-hidden />;
export const Card = ({children, className, id, label}: {children: ReactNode; className?: string; id?: string; label?: string}) => <section id={id} aria-label={label} className={cx('ix-card', className)}>{children}</section>;
export const Tag = ({children, tone}: {children: ReactNode; tone?: 'warn' | 'gray'}) => <span className={cx('ix-tag', tone && `ix-tag--${tone}`)}>{children}</span>;
export const Info = ({children, warning, role}: {children: ReactNode; warning?: boolean; role?: 'status' | 'alert'}) => <div role={role} className={cx('ix-info', warning && 'ix-info--warning')}>{children}</div>;
export const RowLine = ({children}: {children: ReactNode}) => <div className="ix-rowline">{children}</div>;
export const LinkBtn = ({href, children, variant, prefetch}: {href: string; children: ReactNode; variant?: 'primary' | 'wine'; prefetch?: boolean}) => <Link className={btnClass(variant)} href={href} prefetch={prefetch}>{children}</Link>;

/** Баннер Data Health: источник, момент снимка, статус. Всегда над данными экрана. */
export function DataHealth({children, warning}: {children: ReactNode; warning?: boolean}) {
  return <Info warning={warning} role="status">◉ Data Health · {children}</Info>;
}

/** Мини-график карточки KPI: те же линии, что в эталоне, без осей. */
export function Spark({data, prev, label}: {data: (number | null)[]; prev?: (number | null)[]; label: string}) {
  const scale = scaleFor([...data, ...(prev ?? [])], true);
  return <svg className="ix-spark-reveal" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
    <g stroke="var(--line)" strokeWidth="1">{GRID.map(y => <line key={y} x1="0" x2={W} y1={y} y2={y} />)}</g>
    {prev && segments(prev, scale).map((p, i) => <polyline key={'p' + i} points={p} fill="none" stroke="var(--ix-chart-prev)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />)}
    {segments(data, scale).map((p, i) => <polyline key={'d' + i} points={p} fill="none" stroke="var(--ix-chart-line)" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />)}
  </svg>;
}

export function Kpi({label, value, foot, tone, spark, count, trend}: {label: string; value: ReactNode; foot?: ReactNode; tone?: 'good' | 'bad' | 'muted'; spark?: ReactNode; count?: {amount: number; suffix?: string}; trend?: {text: string; direction: 'up' | 'down'; tone?: 'good' | 'bad' | 'neutral'}}) {
  return <div className="ix-card ix-kpi">
    <div className="ix-muted ix-mini">{label}</div>
    <div className="ix-value">{count ? <CountUp {...count}>{value}</CountUp> : value}</div>
    {trend && <div><MetricTrend {...trend}/></div>}
    {foot && <span className={tone === 'bad' ? 'ix-bad ix-kpi-footer' : 'ix-kpi-footer'}>{foot}</span>}
    {spark}
  </div>;
}

export type StateKind = 'empty' | 'error' | 'insufficient' | 'stale' | 'partial' | 'forbidden' | 'expired' | 'loading' | 'success';
const STATE_TITLE: Record<StateKind, string> = {
  empty: 'Пока нет данных', error: 'Не удалось получить данные', insufficient: 'Недостаточно данных', stale: 'Данные устарели',
  partial: 'Данные неполные', forbidden: 'Нет доступа', expired: 'Подключение истекло', loading: 'Загружаем…', success: 'Изменение сохранено',
};
/** Единый блок состояний экрана. Недоступное значение никогда не показывается как 0 или прочерк без причины. */
export function StateBlock({kind, title, children, action, level = 2}: {kind: StateKind; title?: string; children?: ReactNode; action?: ReactNode; level?: 1 | 2}) {
  const Heading = level === 1 ? 'h1' : 'h2';
  const live = kind === 'error' || kind === 'forbidden' ? 'alert' : 'status';
  return <section className="ix-card ix-state" role={live} aria-live={kind === 'loading' ? 'polite' : undefined} data-state={kind}>
    <div className="ix-eyebrow">{kind === 'loading' ? 'Загрузка' : kind === 'error' ? 'Ошибка' : kind === 'forbidden' ? 'Доступ' : 'Состояние данных'}</div>
    <Heading>{title ?? STATE_TITLE[kind]}</Heading>
    {children && <div className="ix-state-text">{children}</div>}
    {action}
  </section>;
}

export function Skeleton({rows = 3, height = 18}: {rows?: number; height?: number}) {
  return <div aria-hidden>{Array.from({length: rows}, (_, i) => <div key={i} className="ix-skeleton" style={{height, margin: '12px 0', width: i % 2 ? '70%' : '100%'}} />)}</div>;
}

export function Table({head, rows, label}: {head: string[]; rows: ReactNode[][]; label: string}) {
  return <div className="ix-tablewrap" tabIndex={0} role="region" aria-label={label}><table><thead><tr>{head.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table></div>;
}

export {xAt};
