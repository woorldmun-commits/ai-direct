/* eslint-disable react-hooks/purity -- серверные компоненты: «сейчас» фиксируется один раз на HTTP-запрос. */
import Link from 'next/link';
import {ValueView} from '@/components/value-view';
import {ActionInstructions} from '@/components/workspace/action-instructions';
import {DecisionForm, VerificationForm} from '@/components/workspace/actions';
import {InsightsPanel} from '@/components/workspace/insights';
import {MeasurementView} from '@/components/workspace/measurement';
import {isInsights, isPassport, type RecommendationPassport} from '@/lib/insights-contract';
import {recommendationHref, safe, stamp, verificationLabel} from '@/lib/ix-live';
import {pilotGet} from '@/lib/pilot';
import {cursor, isRecommendations, isToday, type PilotRecommendation} from '@/lib/pilot-contract';
import {formatPeriod} from '@/lib/value';
import {Gap, Info, LinkBtn, PageHead, RowLine, Tag} from '../ui';
import {FilterList, PassportDrawer} from './filter-list';
import {ErrorState, HealthBanner, NoSeries, ValueKpi} from './parts';
import {DetailTabs} from '../detail-tabs';
import {LiveStats} from './stats';

export type Query = {workspace?: string; rec?: string; cursor?: string; activity?: string; days?: string; ad_account?: string; offset?:string};
const ACTION: Record<string, string> = {change: 'Изменение вручную', review: 'Нужна проверка', inspect_only: 'Только наблюдение'};
const STATUS: Record<string, string> = {new: 'Ожидает решения', postponed: 'Отложена', rejected: 'Отклонена', applied: 'Решение записано', resolved: 'Проблема закрыта'};
const HISTORY: Record<string, string> = {created: 'Создана', seen_again: 'Основания обновлены', postponed: 'Отложена', rejected: 'Отклонена', done: 'Заявлено ручное выполнение', checked: 'Проверена специалистом', measured: 'Выполнен замер', measurement_skipped: 'Замер пропущен', unpostponed: 'Возвращена к рассмотрению'};
function RecRow({rec, ws, pageCursor}: {rec: PilotRecommendation; ws: string; pageCursor?: string}) {
  return <div className="ix-recommendation-row"><RowLine>
    <div className="ix-recommendation-description"><span className="ix-recommendation-icon" aria-hidden="true">↗</span><div><div style={{fontWeight: 600}}>{rec.title.replace(/^high_cpa\b/u, 'Высокий CPA')}</div><div className="ix-muted ix-mini">{ACTION[rec.action_level] ?? 'Требует проверки'} · рассчитано {stamp(rec.computed_at)}</div><div className="ix-mini"><ValueView v={rec.exposure} caption /></div></div></div>
    <div style={{textAlign: 'right'}}><Tag tone={rec.action_level === 'change' ? 'warn' : 'gray'}>{ACTION[rec.action_level] ?? 'Проверка'}</Tag>
      <div><Link className="ix-btn" style={{marginTop: 7}} href={recommendationHref(ws, {rec: rec.id, cursor: pageCursor})} scroll={false}>Подробнее →</Link></div></div>
  </RowLine></div>;
}

export async function Overview({ws, q}: {ws: string; q: Query}) {
  const checkedAt = Date.now();
  const [today, insights] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/today`, isToday)), safe(pilotGet(`/workspaces/${ws}/insights`, isInsights))]);
  if (!today.ok) return <ErrorState page code={today.code} />;
  const t = today.data;
  const needsConnection = t.data_freshness.yandex_direct.status === null;
  const connectHref = `/onboarding/connect?workspace=${encodeURIComponent(ws)}`;
  return <>
    <PageHead title="Обзор" sub={`Последний аудит: ${stamp(t.last_audit_at)}. Сначала доказательства — затем решение.`} actions={<LinkBtn variant="primary" href={needsConnection?connectHref:`/workspace/analysis?workspace=${ws}`}>{needsConnection?'Подключить Яндекс Директ':'Открыть анализ'}</LinkBtn>} />
    {needsConnection&&<><Info>Начните с подключения своего рекламного кабинета. Укажите счётчик и цели Метрики, затем дождитесь загрузки и первого аудита. Данные других пользователей в ваш обзор не подставляются.</Info><Gap /></>}
    <HealthBanner ws={ws} today={t} checkedAt={checkedAt} /><Gap />
    <LiveStats ws={ws} q={q} title="Динамика показателей" compact /><Gap />
    <div className="ix-grid ix-kpis">
      <ValueKpi label="Расход за проверенный период" v={t.spent} />
      <ValueKpi label="Расход с признаками неэффективности" v={t.exposure.total} />
      <div className="ix-card ix-kpi"><div className="ix-muted ix-mini">Активные рекомендации</div><div className="ix-value">{t.counts.active}</div><span className="ix-muted ix-mini">Основания последнего аудита</span></div>
      {insights.ok ? <ValueKpi label="Факт минус план бюджета" v={insights.data.budget.variance} /> : <div className="ix-card ix-kpi"><div className="ix-muted ix-mini">Факт минус план бюджета</div><div className="ix-value" style={{fontSize: 18}}>Недоступно</div><span className="ix-muted ix-mini">Сводка не загрузилась — значение не подставляется</span></div>}
    </div>
    <div className="ix-grid ix-split">
      <section className="ix-card"><h2>Приоритетные решения</h2>
        {t.top?.length ? <FilterList items={t.top.map(r => ({key: r.id, text: r.title, kind:r.action_level, exposure:r.exposure, computedAt:r.computed_at, node: <RecRow rec={r} ws={ws} />}))} /> : <p className="ix-muted">{t.last_audit_at ? 'Активных сигналов в проверенной области нет. Это не оценка всей рекламы.' : 'Аудит ещё не выполнен. Подключите источник и дождитесь данных.'}</p>}
        {t.audit_scope && <p className="ix-muted ix-mini">Проверено аккаунтов: {t.audit_scope.ad_accounts.checked}, исключено: {t.audit_scope.ad_accounts.excluded}, кампаний: {t.audit_scope.campaigns}. Период: {formatPeriod(t.audit_scope.period)}.</p>}
      </section>
      <section className="ix-card ix-assistant-preview"><h2>AI-аналитик</h2><p>Разбор начинается с данных, источников и ограничений. Доступность расчётов определяется возможностями вашего пространства.</p><LinkBtn variant="primary" href={`/workspace/ai?workspace=${ws}`}>Открыть аналитика</LinkBtn></section>
    </div></>;
}

export async function Analysis({ws, q}: {ws: string; q: Query}) {
  const insights = await safe(pilotGet(`/workspaces/${ws}/insights`, isInsights));
  return <><LiveStats ws={ws} q={q} /><Gap />{insights.ok ? <InsightsPanel workspace={ws} data={insights.data} /> : <ErrorState code={insights.code} />}</>;
}

export async function Recommendations({ws, q}: {ws: string; q: Query}) {
  const checkedAt = Date.now();
  if (q.cursor && !cursor(q.cursor)) return <ErrorState page code="invalid" />;
  const [today, list] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/today`, isToday)), safe(pilotGet(`/workspaces/${ws}/recommendations?limit=50${q.cursor ? '&cursor=' + q.cursor : ''}`, isRecommendations))]);
  if (!list.ok) return <ErrorState page code={list.code} />;
  const base = recommendationHref(ws, {cursor: q.cursor});
  const passport = q.rec && /^rec_[1-9]\d{0,18}$/.test(q.rec) ? await safe(pilotGet(`/workspaces/${ws}/recommendations/${q.rec}`, isPassport)) : null;
  return <>
    <PageHead title="Рекомендации" sub="Приоритеты, доказательства, решения человека." />
    {today.ok && <HealthBanner ws={ws} today={today.data} checkedAt={checkedAt} />}<Gap h={14} />
    <div className="ix-card"><h2>Решения к рассмотрению</h2>
      {list.data.items.length ? <FilterList items={list.data.items.map(r => ({key: r.id, text: r.title, kind:r.action_level, exposure:r.exposure, computedAt:r.computed_at, node: <RecRow rec={r} ws={ws} pageCursor={q.cursor} />}))} />
        : <p className="ix-muted">{today.ok && today.data.last_audit_at ? 'Активных рекомендаций нет. Проверьте свежесть и полноту данных перед выводом об эффективности.' : 'Аудит ещё не выполнен. Отсутствие рекомендаций пока не означает отсутствие проблем.'}</p>}
      <p className="ix-muted ix-mini">Суммы по карточкам нельзя складывать: общий итог на «Обзоре» уже учитывает пересечения.</p>
      <div className="ix-actions">{q.cursor && <LinkBtn href={recommendationHref(ws)}>К началу списка</LinkBtn>}{list.data.next_cursor && <LinkBtn href={recommendationHref(ws, {cursor: list.data.next_cursor})}>Следующие рекомендации</LinkBtn>}</div>
    </div>
    {passport && (passport.ok ? <Passport ws={ws} id={q.rec!} data={passport.data} closeHref={base} /> : <PassportDrawer title="Рекомендация недоступна" closeHref={base}><ErrorState code={passport.code} /></PassportDrawer>)}
  </>;
}

function Passport({ws, id, data, closeHref}: {ws: string; id: string; data: RecommendationPassport; closeHref: string}) {
  const label: Record<string, string> = {clicks: 'Клики', cost: 'Расход', conversions: 'Конверсии', cpa: 'Стоимость конверсии'};
  const evidence = <div className="ix-card"><h2>Доказательства</h2>
    {!data.evidence_current && <Info warning role="alert">Основания относятся к предыдущему аудиту или исключённому аккаунту. Новое выполнение недоступно.</Info>}
    <RowLine><span>Расход с признаками неэффективности</span><span><ValueView v={data.exposure} caption /></span></RowLine>
    {Object.entries(data.evidence).map(([k, v]) => <RowLine key={k}><span>{label[k] ?? k}</span><span><ValueView v={v} caption /></span></RowLine>)}
    <RowLine><span>Объект</span><b>{data.object.type === 'campaign' ? 'Кампания' : data.object.type === 'account' ? 'Аккаунт' : 'Площадка'} · {data.object.name ?? data.object.id}</b></RowLine>
  </div>;
  const calculation = <div className="ix-card"><h2>Расчёт и последствия</h2><p>{data.explanation?.text ?? 'Формула и правило указаны в блоке «Как посчитано» у каждого значения.'}</p>{data.explanation && <p className="ix-muted ix-mini">Источник пояснения: {data.explanation.source}</p>}<Info warning>Это оценка по правилу, а не подтверждённая экономия и не прогноз. Эффект подтверждается только замером после ручного изменения.</Info></div>;
  const risk = <div className="ix-card"><h2>Риски</h2><p>Изменение может снизить охват или число конверсий. Перед действием проверьте объём выборки. Отметка выполнения не подтверждает изменение, экономию или причинный эффект.</p></div>;
  const verification = <div className="ix-card"><h2>Проверка результата</h2><p className="ix-muted">{verificationLabel(data.verification)}</p>{data.verification.checked_at&&<p className="ix-mini">Источник: Яндекс Директ · прочитано {stamp(data.verification.checked_at)}</p>}{data.verification.can_request&&<VerificationForm workspace={ws} rec={id} version={data.version_id} state={data.state_version} returnTo={recommendationHref(ws,{cursor:new URL(closeHref,'https://inrou.invalid').searchParams.get('cursor')??undefined,rec:id})}/>}<MeasurementView measurement={data.latest_measurement} /></div>;
  const history = <div className="ix-card"><h2>История</h2>{data.history.length ? <ol className="ix-timeline">{data.history.map(e => <li key={e.id}>{HISTORY[e.type] ?? 'Событие рекомендации'} · {stamp(e.created_at)}</li>)}</ol> : <p className="ix-muted">Решений ещё нет.</p>}</div>;
  return <PassportDrawer title={data.title?.replace(/^high_cpa\b/u, 'Высокий CPA') ?? 'Паспорт рекомендации'} closeHref={closeHref}>
    <Tag tone="warn">{STATUS[data.status] ?? 'Статус требует проверки'}</Tag><p className="ix-muted ix-mini">{data.version_id} · состояние {data.state_version} · основания от {stamp(data.computed_at)}</p>
    <DetailTabs tabs={[
      {id: 'overview', title: 'Обзор', body: <><div className="ix-detail-columns"><div className="ix-card"><h2>Динамика CPA</h2><NoSeries /></div>{evidence}</div><Gap h={12} />{calculation}<Gap h={12} />{verification}<Gap h={12} /><div className="ix-card"><ActionInstructions action={data.action} /><p className="ix-muted ix-mini">Решение, ручное выполнение и проверка результата — отдельные шаги. Автоматических изменений рекламы нет. Сверка исключений площадок доступна отдельно, если это действие поддерживается.</p></div></>},
      {id: 'evidence', title: 'Данные', body: evidence},
      {id: 'calculation', title: 'Расчёты', body: calculation},
      {id: 'risks', title: 'Риски', body: risk},
      {id: 'history', title: 'История', body: history},
    ]} />
    <div className="ix-decision-actions"><h2>Решение человека</h2>{data.allowed_actions.length ? <DecisionForm workspace={ws} rec={id} version={data.version_id} state={data.state_version} allowed={data.allowed_actions} /> : <p>Для текущего состояния, роли или доступа новые решения недоступны.</p>}</div>
  </PassportDrawer>;
}
