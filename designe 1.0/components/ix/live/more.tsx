/* eslint-disable react-hooks/purity -- серверные компоненты: «сейчас» фиксируется один раз на HTTP-запрос. */
import Link from 'next/link';
import {DirectConnect} from '@/components/workspace/direct-connect';
import {ActivityPanel} from '@/components/workspace/measurement';
import {WeeklyReport} from '@/components/workspace/weekly-report';
import {isActivity, isInsights, isWeeklyReport, decisionLabels} from '@/lib/insights-contract';
import {safe, stamp} from '@/lib/ix-live';
import {pilotGet} from '@/lib/pilot';
import {isToday} from '@/lib/pilot-contract';
import {Gap, Info, LinkBtn, PageHead, RowLine, Tag} from '../ui';
import type {Query} from './core';
import {LiveStats} from './stats';
import {ErrorState, HealthBanner, sourceState} from './parts';

export const CHECK_TITLE: Record<string, string> = {direct: 'Яндекс Директ', metrika: 'Яндекс Метрика', goals: 'Цели конверсий', freshness: 'Свежесть данных'};
const CHECK_TAG: Record<string, string> = {ok: 'Проверка пройдена', attention: 'Требует внимания', unavailable: 'Нет данных для проверки'};

export function CampaignDetail({ws, q, id}: {ws: string; q: Query; id: string}) {
  return <LiveStats ws={ws} q={q} campaign={id} />;
}

export function Campaigns({ws, q}: {ws: string; q: Query}) {
  return <LiveStats ws={ws} q={q} title="Кампании" />;
}

export async function Connections({ws}: {ws: string; q: Query}) {
  const checkedAt = Date.now();
  const today = await safe(pilotGet(`/workspaces/${ws}/today`, isToday));
  if (!today.ok) return <ErrorState page code={today.code} />;
  const fresh = today.data.data_freshness;
  return <>
    <PageHead title="Подключения" sub="Только подтверждённые возможности; остальные — этапы развития." />
    <HealthBanner ws={ws} today={today.data} checkedAt={checkedAt} /><Gap />
    <div className="ix-grid ix-split">
      <div className="ix-card"><h2>Источники данных</h2>
        {([['yandex_direct', 'Яндекс Директ'], ['yandex_metrika', 'Яндекс Метрика']] as const).map(([key, name]) => {
          const s = sourceState(fresh[key], checkedAt);
          return <RowLine key={key}><div><Link href={`/workspace/connections/${key}?workspace=${ws}`}><b>{name}</b></Link><div className="ix-muted ix-mini">Данные по: {fresh[key].data_to ?? 'нет данных'} · синхронизация: {stamp(fresh[key].last_success_at)}</div></div><Tag tone={s.warn ? 'warn' : undefined}>{s.label}</Tag></RowLine>;
        })}
        {['VK Реклама', 'Авито', 'CRM / коллтрекинг'].map(n => <RowLine key={n}><div><b>{n}</b><div className="ix-muted ix-mini">Не поддерживается текущей версией</div></div><Tag tone="gray">Планируется</Tag></RowLine>)}
      </div>
      <div className="ix-card"><h2>Доверие к источникам</h2><p>Состояние, свежесть и ошибки синхронизации приходят с сервера. Права доступа к рекламным данным — только чтение.</p><Info warning>Неподключённые источники не показываются как активные и не участвуют в расчётах.</Info></div>
    </div>
    <Gap /><DirectConnect workspace={ws} /></>;
}

export async function Impact({ws, q, embedded=false}: {ws: string; q: Query; embedded?:boolean}) {
  if (q.activity && !/^[1-9]\d{0,18}$/.test(q.activity)) return <ErrorState page={!embedded} code="invalid" />;
  const activity = await safe(pilotGet(`/workspaces/${ws}/recommendation-activity${q.activity ? '?cursor=' + q.activity : ''}`, isActivity));
  if (!activity.ok) return <ErrorState page={!embedded} code={activity.code} />;
  return <>
    {!embedded&&<PageHead title="Эффект" sub="Подтверждённый результат отделяется от потенциального." />}
    <div className="ix-grid ix-split">
      <div className="ix-card"><h2>Замеры после ручных изменений</h2><ActivityPanel data={activity.data} workspace={ws} /></div>
      <div className="ix-card"><h2>Экономический эффект</h2><div className="ix-value" style={{fontSize: 22, fontWeight: 700}}>Недостаточно данных</div>
        <p className="ix-muted">Замеры сравнивают периоды до и после ручного изменения без контрольной группы. Они не суммируются в «сэкономлено» и не доказывают причинность.</p><Info>Сначала решение и ручное действие, затем сверка периода и замер.</Info></div>
    </div></>;
}

export async function Reports({ws, expanded=false, embedded=false}: {ws: string; q: Query; expanded?:boolean; embedded?:boolean}) {
  const report = await safe(pilotGet(`/workspaces/${ws}/weekly-report`, isWeeklyReport));
  return <>
    {!embedded&&<PageHead title="Отчёты" sub="Факты, источники и решения за выбранный период." actions={<LinkBtn variant="primary" href={`/workspace/reports/weekly?workspace=${ws}#weekly-report`}>Недельный отчёт</LinkBtn>} />}
    <section className="ix-card ix-report-list" aria-label="Доступные отчёты и данные">
      {[
        ['Недельный сводный','7 завершённых дней · факты и ограничения','reports/weekly','TXT'],
        ['История решений','Решения и замеры рабочего пространства','history','Просмотр'],
        ['Качество данных','Свежесть, полнота и состояние источников','data-health','Просмотр'],
        ['По кампаниям','Расход, конверсии и CPA · 7 или 30 дней','campaigns','Просмотр'],
        ['План / факт','Бюджет и показатели проверенного периода','budgets','Просмотр'],
      ].map(([title,description,path,format])=><div className="ix-report-row" key={path}><span className="ix-report-icon" aria-hidden="true">▤</span><div><Link href={`/workspace/${path}?workspace=${ws}`}><b>{title}</b></Link><p className="ix-muted ix-mini">{description}</p></div><Tag tone={format==='TXT'?undefined:'gray'}>{format}</Tag><Link className="ix-report-open" href={`/workspace/${path}?workspace=${ws}`} aria-label={`Открыть: ${title}`}>→</Link></div>)}
    </section>
    <p className="ix-muted ix-mini">PDF, XLSX, произвольные шаблоны и расписание пока не подключены. «Просмотр» открывает действующие данные без экспорта.</p>
    <details className="ix-card ix-weekly-preview" id="weekly-report" open={expanded}><summary>Недельный отчёт · просмотр и скачивание TXT</summary><Gap />{report.ok ? <WeeklyReport workspace={ws} report={report.data} /> : <ErrorState code={report.code} />}</details></>;
}

export async function Alerts({ws}: {ws: string; q: Query}) {
  const [insights, today] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/insights`, isInsights)), safe(pilotGet(`/workspaces/${ws}/today`, isToday))]);
  if (!insights.ok) return <ErrorState page code={insights.code} />;
  const items = insights.data.health.checks.filter(c => c.status !== 'ok');
  return <>
    <PageHead title="Сигналы" sub="Риски и изменения с проверяемыми причинами: каждый сигнал — результат проверки на сервере." />
    {today.ok && today.data.data_status === 'partial' && <><Info warning role="status">Данные за период неполные: последние дни могут уточниться.</Info><Gap h={12} /></>}
    <div className="ix-card">
      {items.length ? items.map(c => <RowLine key={c.id}><div><Link href={`/workspace/alerts/${c.id}?workspace=${ws}`}><b>{CHECK_TITLE[c.id] ?? c.id}</b></Link><div className="ix-muted ix-mini">{c.reason} · {c.action}</div></div><Tag tone="warn">{CHECK_TAG[c.status]}</Tag></RowLine>)
        : <p className="ix-muted">Сигналов нет: все проверки данных пройдены. Это не оценка эффективности рекламы.</p>}
    </div></>;
}

export async function History({ws, q, embedded=false}: {ws: string; q: Query; embedded?:boolean}) {
  if (q.activity && !/^[1-9]\d{0,18}$/.test(q.activity)) return <ErrorState page={!embedded} code="invalid" />;
  const activity = await safe(pilotGet(`/workspaces/${ws}/recommendation-activity${q.activity ? '?cursor=' + q.activity : ''}`, isActivity));
  if (!activity.ok) return <ErrorState page={!embedded} code={activity.code} />;
  const status: Record<string, string> = {applied: 'Проверка записана', postponed: 'Отложено', rejected: 'Отклонено', resolved: 'Проблема закрыта', new: 'Ожидает решения'};
  return <>
    {!embedded&&<PageHead title="История" sub="Неизменяемый журнал решений и проверок; автор и версия — в паспорте рекомендации." />}
    <div className="ix-card">
      {activity.data.items.length ? activity.data.items.map(i => <RowLine key={i.id}><div><Link href={`/workspace/history/${i.id}?workspace=${ws}`}><b>{i.title}</b></Link><div className="ix-muted ix-mini">{stamp(i.updated_at)}{i.execution_mode === 'manual' ? ' · ручное выполнение заявлено, сверка ещё не подтверждена' : ''}</div></div><Tag tone="gray">{status[i.status] ?? 'Решение записано'}</Tag></RowLine>)
        : <p className="ix-muted">Записанных решений пока нет. Откройте рекомендацию и зафиксируйте результат проверки.</p>}
      {activity.data.next_cursor && <div className="ix-actions"><LinkBtn href={`/workspace/history?workspace=${ws}&activity=${activity.data.next_cursor}`}>Более ранние записи</LinkBtn></div>}
    </div>
    <p className="ix-muted ix-mini">Типы событий: {Object.values(decisionLabels).join(' · ')}.</p></>;
}
