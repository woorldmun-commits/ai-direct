/* eslint-disable react-hooks/purity -- серверные компоненты: «сейчас» фиксируется один раз на HTTP-запрос. */
import Link from 'next/link';
import {ValueView} from '@/components/value-view';
import {BillingCheckout} from '@/components/workspace/billing';
import {isBillingCatalog,isBillingRecovery} from '@/lib/billing-contract';
import {DirectConnect} from '@/components/workspace/direct-connect';
import {IntelligencePanel} from '@/components/workspace/intelligence';
import {isInsights} from '@/lib/insights-contract';
import {isChiefHistory,isChiefReport,isIntelligence,isSnapshotAnalysis} from '@/lib/intelligence-contract';
import {isSubscriptionRead} from '@/lib/subscription-contract';
import {formatAmount} from '@/lib/value';
import {isMembers, safe, stamp} from '@/lib/ix-live';
import {pilotGet} from '@/lib/pilot';
import {isToday} from '@/lib/pilot-contract';
import {Card, DataHealth, Gap, Info, LinkBtn, PageHead, RowLine, StateBlock, Tag} from '../ui';
import {CHECK_TITLE} from './more';
import {ErrorState, sourceState} from './parts';
import {ThemeRow} from './theme-row';

export async function Ai({ws, cursor}: {ws: string; cursor?: string}) {
  if (cursor && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(cursor)) return <ErrorState page code="invalid" />;
  const [intel, insights, snapshots, today, chief, chiefHistory] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/intelligence${cursor ? '?cursor=' + cursor : ''}`, isIntelligence)), safe(pilotGet(`/workspaces/${ws}/insights`, isInsights)),safe(pilotGet(`/workspaces/${ws}/intelligence/snapshot-analysis`,isSnapshotAnalysis)),safe(pilotGet(`/workspaces/${ws}/today`,isToday)),safe(pilotGet(`/workspaces/${ws}/intelligence/chief-analyst?days=30`,isChiefReport)),safe(pilotGet(`/workspaces/${ws}/intelligence/chief-history`,isChiefHistory))]);
  return <>
    <PageHead title="AI-аналитик" sub="Объяснения только на основе проверенных данных и расчётов." />
    <Info>Анализ по данным пространства и вашим агрегатам. Внешняя языковая модель не подключена.</Info><Gap />
    <Card label="Разбор подключённых данных"><h2>Подключённые данные и основания</h2>
      {snapshots.ok?snapshots.data.available?<>
        <p>Период: {snapshots.data.result.context.period_start} — {snapshots.data.result.context.period_end} (конец не включён). Качество: {{complete:'полные',partial:'частичные',stale:'требуют обновления',unknown:'не подтверждено'}[snapshots.data.result.context.quality_status]??'требует проверки'}.</p>
        <div className="ix-grid ix-kpis">{(['cost','conversions','cpa','cvr'] as const).map(key=>{const metric=snapshots.data.available?snapshots.data.result.metrics[key]:null;const short=metric?.value?.replace(/(\.\d{2})\d+$/,'$1');
          // eslint-disable-next-line no-restricted-syntax -- Intelligence MetricValue has explicit missing and shortened-display states; the raw Decimal remains in title.
          const display=metric?.value===null||!metric||!short?'Нет данных':`${short!==metric.value?'≈ ':''}${formatAmount(short,metric.currency==='RUB'?'rub':metric.unit==='pct'?'pct':'count')}`;
          return <div key={key}><b>{{cost:'Расход',conversions:'Конверсии',cpa:'CPA',cvr:'CVR'}[key]}</b><p title={metric?.value??undefined}>{display}</p></div>;})}</div>
        {snapshots.data.profile?<p>Профиль бизнеса: {snapshots.data.profile.fields.name} · редакция {snapshots.data.profile.revision}. Факты профиля подтверждены пользователем.</p>:<p>Добавьте бизнес-профиль для контекста; отраслевые нормы не подставляются.</p>}
        <details><summary>Снимки и ограничения расчёта</summary>{snapshots.data.provenance.map(p=><p key={p.ad_account}>{p.ad_account} · снимок {p.snapshot_id} · обновлён {stamp(p.sealed_at)}</p>)}<ul>{snapshots.data.limitations.map(text=><li key={text}>{text}</li>)}</ul></details>
      </>:<p>{snapshots.data.reason==='no_snapshot'?'Нет пригодных снимков выбранных аккаунтов. Проверьте подключение и период данных.':'Разбор подключённых данных откроется после допуска реальных источников. Синтетический пример доступен отдельно.'}</p>:<ErrorState code={snapshots.code}/>}
      {today.ok&&!!today.data.top?.length&&<><h3>Рекомендации последнего аудита</h3><p className="ix-muted ix-mini">Период аудита может отличаться от периода расчёта выше. Проверяйте дату и основания в паспорте.</p><ul>{today.data.top.map(rec=><li key={rec.id}><Link href={`/workspace/recommendations?workspace=${ws}&rec=${rec.id}`}>{rec.title}</Link></li>)}</ul></>}
    </Card><Gap />
    {chiefHistory.ok&&<Card label="История автоматического анализа"><h2>Chief Analyst · фоновые запуски</h2>
      {!chiefHistory.data.items.length&&<p>После успешного аудита здесь появятся результаты, если оператор включит автоматизацию.</p>}
      {chiefHistory.data.items.map(item=><details key={item.id}><summary>Аудит {item.audit_run_id} · {stamp(item.created_at)} · {item.status}</summary>
        <p>Статус: {item.status==='completed'?'Предварительный анализ':'Требуется проверка или данные недоступны'}.</p>
        {item.error_code&&<p>Код ограничения: {item.error_code}</p>}
      </details>)}
      <p className="ix-muted ix-mini">История не является разрешением изменять кампании или подтверждением экономии.</p>
    </Card>}
    {chief.ok&&chief.data.available&&<Card label="Главный аналитик"><h2>Chief Analyst · проверка 8 специалистов</h2>
      <p className="ix-muted ix-mini">Автоматическая диагностика по сохранённым агрегатам. Это локальные правила, а не восемь запущенных нейросетей. Ни один вывод не разрешает менять рекламу; независимая проверка источников и причин пока не завершена.</p>
      <p role="status">Статус: {chief.data.status==='blocked'?'Требуется устранить ограничения данных':'Нужна проверка человеком и независимым контролёром'}.</p>
      <ul>{chief.data.specialists.map(agent=><li key={agent.role}>
        <b>{{lead_quality:'Качество лидов',tracking_integrity:'Цели и конверсии',search_intent:'Поисковые намерения',landing_cro:'Конверсия посадочных',anomaly_sentinel:'Аномалии расходов',customer_value:'Ценность клиентов',knowledge_steward:'Отраслевые знания',recommendation_challenger:'Критическая проверка'}[agent.role as 'lead_quality']??agent.role}</b>
        {' — '}{agent.status==='unavailable'?'Нужен дополнительный источник':agent.status==='blocked'?'Заблокировано до проверки':'Предварительная диагностика'}
        {agent.role==='lead_quality'&&typeof agent.observations.qualified_lead_share_pct==='string'&&<span> · доля квалифицированных обращений: {agent.observations.qualified_lead_share_pct}%</span>}
        {agent.role==='anomaly_sentinel'&&agent.observations.large_spend_change_candidate===true&&<span> · возможное изменение расходов: требует проверки</span>}
      </li>)}</ul>
      <p className="ix-muted ix-mini">При отсутствии CRM, данных по поисковым запросам или воронке агент честно сообщает о недоступном анализе. Причинный финансовый эффект не подтверждён.</p>
    </Card>}
    {chief.ok&&!chief.data.available&&<Info>Chief Analyst: анализ на реальных снимках пока недоступен. {chief.data.reason==='no_snapshot'?'Нет сохранённой статистики.':'Нужны допуск данных и активные подключения.'}</Info>}
    {!chief.ok&&<Info warning>Не удалось проверить диагностические результаты Chief Analyst. Рекомендации на их основе не публикуются.</Info>}
    <Gap />
    <details className="ix-card"><summary>Ручной импорт и отдельные расчёты</summary><p>Этот раздел не нужен для разбора подключённого Директа. Он работает с загруженными агрегатами; синтетические примеры не относятся к вашему кабинету.</p>{intel.ok ? <IntelligencePanel workspace={ws} data={intel.data} /> : <ErrorState code={intel.code} />}</details>
    <Gap /><details className="ix-card ix-analyst-method"><summary>Методика, факты и ограничения</summary>
      <p className="ix-muted ix-mini">Расчёты выполняет детерминированный код на сервере. Результат сохраняется с источниками и ограничениями. Уверенность зависит от полноты данных; при нехватке показано «Недостаточно данных».</p>
      {insights.ok && <div><b>Факты за период</b>
        {insights.data.summary.facts.map(f => <div key={f.id}><h2 className="ix-h3" style={{marginTop: 12}}>{f.label}</h2>{f.value && <ValueView v={f.value} caption />}<p className="ix-muted ix-mini">{f.detail}</p></div>)}
        <h2 className="ix-h3">Ограничения</h2><ul>{insights.data.summary.limitations.map(l => <li key={l}>{l}</li>)}</ul></div>}
      {!insights.ok && <ErrorState code={insights.code} />}
    </details></>;
}

export async function BusinessProfile({ws}: {ws: string}) {
  const intel = await safe(pilotGet(`/workspaces/${ws}/intelligence`, isIntelligence));
  return <>
    <PageHead title="Бизнес-профиль" sub="Контекст компании для корректного анализа рекомендаций." />
    <Info warning>Поля подтверждает владелец. AI не переписывает подтверждённый профиль; предположения отделены от фактов.</Info><Gap />
    {intel.ok ? <IntelligencePanel workspace={ws} data={intel.data} profileOnly /> : <ErrorState code={intel.code} />}</>;
}

export async function Team({ws, id}: {ws: string; id?: string}) {
  const roles:Record<string,string>={owner:'Владелец',admin:'Администратор',member:'Участник',viewer:'Просмотр',approver:'Согласование'};
  const members = await safe(pilotGet(`/workspaces/${ws}/members`, isMembers));
  const member = members.ok && id ? members.data.items.find(m => m.user.id === id) : undefined;
  if (members.ok && id && !member) return <StateBlock level={1} kind="empty" title="Участник не найден">Участник отсутствует в доступном списке рабочего пространства.</StateBlock>;
  return <>
    <PageHead title={id ? 'Участник команды' : 'Участники'} sub="Просмотр участников и действующих прав доступа." actions={id && <LinkBtn href={`/workspace/team?workspace=${ws}`}>← Все участники</LinkBtn>} />
    {members.ok ? <Card className="ix-team-list"><h2>Участники пространства</h2>
      {(member ? [member] : members.data.items).map(m => <RowLine key={m.user.id}><div className="ix-member-identity"><span className="ix-member-avatar" aria-hidden="true">{m.user.email.slice(0,1).toLocaleUpperCase('ru-RU')}</span><Link href={`/workspace/team/${encodeURIComponent(m.user.id)}?workspace=${ws}`}><b>{m.user.email}</b></Link></div><div className="ix-member-roles"><Tag tone="gray">Организация: {roles[m.org_role]??m.org_role}</Tag>{m.ws_role&&<Tag>Пространство: {roles[m.ws_role]??m.ws_role}</Tag>}</div></RowLine>)}
      {member && <Info>Роли и доступ к этому списку проверяются сервером. Изменение роли и отзыв доступа пока недоступны.</Info>}
      <p className="ix-muted ix-mini">Просмотр. Приглашения, смена ролей и отзыв доступа появятся с расширением backend; права проверяются на сервере.</p></Card>
      : members.code === 'access' ? <StateBlock kind="forbidden" title="Список участников недоступен">Он виден только владельцу и администратору. Это ограничение сервера, а не ошибка.</StateBlock> : <ErrorState code={members.code} />}</>;
}

export async function Plans({ws}: {ws:string}) {
  const [result,catalog,recovery]=await Promise.all([safe(pilotGet(`/workspaces/${ws}/subscription`,isSubscriptionRead)),safe(pilotGet('/billing/plans',isBillingCatalog)),safe(pilotGet(`/workspaces/${ws}/billing/orders/current`,isBillingRecovery))]);
  if(!result.ok)return <><PageHead title="Тарифы" sub="Подписка и доступ рабочего пространства." />{result.code==='access'?<StateBlock kind="forbidden" title="Сведения о подписке доступны владельцу и администратору">Обратитесь к владельцу организации, чтобы уточнить тариф и доступ. Ваша роль не позволяет просматривать финансовые сведения.</StateBlock>:<ErrorState code={result.code}/>}</>;
  const {subscription:s,access,checked_at,workspace_status}=result.data;
  const names={start:'Контроль',business:'Бизнес',business_plus:'Агентство'};
  const statuses={active:'Активна',past_due:'Ожидает продления',canceled:'Продление отменено',expired:'Истекла'};
  return <>
    <PageHead title="Тарифы" sub="Подписка и доступ рабочего пространства." />
    <div className="ix-grid ix-split ix-subscription">
      <Card label="Текущая подписка"><div className="ix-eyebrow">Текущий тариф</div><h2>{s?names[s.plan]:'Подписка не оформлена'}</h2>
        {s?<><div className="ix-value" style={{fontSize:26,fontWeight:700}}>{
          // eslint-disable-next-line no-restricted-syntax -- Stored subscription price is a billing amount, not an analytical Value or estimate.
          formatAmount(s.price_amount,'rub')
        }</div><p className="ix-muted ix-mini">Стоимость сохранённого периода</p>
          <RowLine><span>Статус записи</span><Tag tone={access.paid?undefined:'gray'}>{statuses[s.status]}</Tag></RowLine>
          <RowLine><span>Период подписки</span><span>{stamp(s.period_start)} — {stamp(s.period_end)}</span></RowLine>
          <RowLine><span>Автопродление</span><span>{s.auto_renew?'Включено':'Выключено'}</span></RowLine></>:<p className="ix-muted">У этого пространства нет начавшегося периода подписки. Пилотный доступ, если он выдан, показан отдельно.</p>}
      </Card>
      <Card label="Доступ к анализу"><div className="ix-eyebrow">Доступ</div><h2>{access.analysis_allowed?'Анализ доступен':'Анализ недоступен'}</h2>
        <RowLine><span>Основание</span><Tag tone={access.basis==='none'?'gray':undefined}>{{subscription:'Подписка',pilot:'Пилотный доступ',trial:'7 дней бесплатно',none:'Нет действующего доступа'}[access.basis]}</Tag></RowLine>
        {result.data.limits&&<RowLine><span>Рекламные аккаунты пространства</span><span>{result.data.limits.accounts_used} / {result.data.limits.accounts}</span></RowLine>}
        {access.paid_until&&<p>{s&&Date.parse(access.paid_until)>Date.parse(s.period_end)?'Доступ с учётом срока на продление':'Доступ по подписке'} — до {stamp(access.paid_until)}.</p>}
        {access.pilot_until&&<p>Пилот — до {stamp(access.pilot_until)}. Пилот не означает оплаченную подписку.</p>}
        {result.data.trial&&<p role="status">{result.data.trial.active?'Бесплатный период':'Бесплатный период завершён'}: {stamp(result.data.trial.started_at)} — {stamp(result.data.trial.ends_at)}. Без карты и автосписаний.{!result.data.trial.active&&!access.analysis_allowed&&' Для нового анализа нужен действующий доступ.'}</p>}
        {s&&access.paid&&Date.parse(checked_at)>=Date.parse(s.period_end)&&<Info warning>Действует льготный период на продление. Оплаченный период завершён.</Info>}
        {workspace_status!=='active'&&<Info warning>Рабочее пространство приостановлено. Наличие подписки не разрешает запуск анализа.</Info>}
        <p className="ix-muted ix-mini">Проверено сервером: {stamp(checked_at)}. Доступ к данным также зависит от прав пользователя и состояния источников.</p>
      </Card>
    </div><Gap />
    {catalog.ok&&recovery.ok?<BillingCheckout workspace={ws} catalog={catalog.data} paid={access.paid} recovered={recovery.data.order}/>:<ErrorState code={!catalog.ok?catalog.code:!recovery.ok?recovery.code:'unavailable'}/>}<Gap />
    <p className="ix-muted ix-mini">Рекламный бюджет оплачивается отдельно. Подписка не гарантирует экономию или рост заявок. Условия — в <Link href="/legal/offer" style={{textDecoration: 'underline'}}>договоре-оферте</Link>.</p></>;
}

export function Settings({ws, name}: {ws: string; name?: string}) {
  return <>
    <PageHead title="Настройки" sub="Профиль, безопасность, уведомления и оформление." actions={<LinkBtn href={`/workspace/business-profile?workspace=${ws}`}>Бизнес-профиль</LinkBtn>} />
    <div className="ix-grid ix-split">
      <div className="ix-card"><h2>Настройки интерфейса</h2><ThemeRow /><RowLine><span>Анимации</span><span className="ix-muted">С учётом настроек системы</span></RowLine>
        <RowLine><span>Уведомления</span><Tag tone="gray">Недоступно: нет API</Tag></RowLine></div>
      <div className="ix-card"><h2>Безопасность и документы</h2><p>Сессией управляет сервер; токены Яндекса и пароль в браузере не хранятся.</p>
        <p className="ix-muted">Пространство: {name ?? ws}</p>
        <div className="ix-actions"><LinkBtn href="/legal">Правовая информация</LinkBtn><LinkBtn href={`/workspace/data-health?workspace=${ws}`}>Качество данных</LinkBtn></div>
        <form action="/api/auth/logout" method="post" style={{marginTop: 12}}><button className="ix-btn ix-btn--wine" type="submit">Выйти</button></form></div>
    </div></>;
}

export async function DataHealthPage({ws}: {ws: string}) {
  const checkedAt = Date.now();
  const [today, insights, intel] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/today`, isToday)), safe(pilotGet(`/workspaces/${ws}/insights`, isInsights)), safe(pilotGet(`/workspaces/${ws}/intelligence`, isIntelligence))]);
  if (!today.ok) return <ErrorState page code={today.code} />;
  const f = today.data.data_freshness;
  const conv = intel.ok ? intel.data.profile?.fields.conversion_definition : undefined;
  return <>
    <PageHead title="Качество данных" sub="Свежесть, полнота и определения, на которых построены все показатели." />
    <DataHealth warning={today.data.data_status === 'partial'}>Данные за период: {today.data.data_status === 'partial' ? 'неполные, последние дни могут уточниться' : 'полные'} · последний аудит: {stamp(today.data.last_audit_at)}</DataHealth><Gap />
    <div className="ix-grid ix-split">
      <Card><h2>Источники</h2>
        {([['yandex_direct', 'Яндекс Директ'], ['yandex_metrika', 'Яндекс Метрика']] as const).map(([k, n]) => { const s = sourceState(f[k], checkedAt); return <RowLine key={k}><div><b>{n}</b><div className="ix-muted ix-mini">Данные по: {f[k].data_to ?? 'нет данных'} · успешная синхронизация: {stamp(f[k].last_success_at)}</div></div><Tag tone={s.warn ? 'warn' : undefined}>{s.label}</Tag></RowLine>; })}</Card>
      <Card><h2>Определения</h2><dl className="ix-kv"><dt>Часовой пояс</dt><dd>Europe/Moscow</dd><dt>Валюта</dt><dd>RUB</dd><dt>Конверсия</dt><dd>{conv ?? 'не задана — укажите в «Бизнес-профиле»'}</dd><dt>Атрибуция</dt><dd>не передаётся API</dd></dl></Card>
    </div>
    <Gap />
    <Card><h2>Проверки</h2>{insights.ok ? insights.data.health.checks.map(c => <RowLine key={c.id}><div><b>{CHECK_TITLE[c.id] ?? c.id}</b><div className="ix-muted ix-mini">{c.reason} · {c.action}</div></div><Tag tone={c.status === 'ok' ? undefined : 'warn'}>{c.status === 'ok' ? 'Пройдена' : c.status === 'attention' ? 'Внимание' : 'Нет данных'}</Tag></RowLine>) : <ErrorState code={insights.code} />}</Card></>;
}

export async function OnboardingReview({ws}: {ws: string}) {
  const [today, intel] = await Promise.all([safe(pilotGet(`/workspaces/${ws}/today`, isToday)), safe(pilotGet(`/workspaces/${ws}/intelligence`, isIntelligence))]);
  if (!today.ok) return <ErrorState page code={today.code} />;
  const d = today.data.data_freshness;
  const steps: [string, boolean, string][] = [
    ['Яндекс Директ подключён', d.yandex_direct.status === 'connected', 'connections'],
    ['Яндекс Метрика подключена', d.yandex_metrika.status === 'connected', 'connections'],
    ['Бизнес-профиль сохранён', intel.ok && !!intel.data.profile, 'business-profile'],
    ['Первый аудит выполнен', !!today.data.last_audit_at, 'overview'],
  ];
  return <>
    <PageHead title="Проверка запуска" sub="Что уже настроено в пространстве. Состояние берётся с сервера." />
    <Card>{steps.map(([t, ok, to]) => <RowLine key={t}><span>{t}</span>{ok ? <Tag>Готово</Tag> : <Link className="ix-btn" href={`/workspace/${to}?workspace=${ws}`}>Настроить</Link>}</RowLine>)}</Card></>;
}

export async function ConnectionDetail({ws, id}: {ws: string; id: string}) {
  const checkedAt = Date.now();
  const today = await safe(pilotGet(`/workspaces/${ws}/today`, isToday));
  if (!today.ok) return <ErrorState page code={today.code} />;
  if (id !== 'yandex_direct' && id !== 'yandex_metrika') return <StateBlock level={1} kind="empty" title="Источник не найден">Поддерживаются только Яндекс Директ и Яндекс Метрика.</StateBlock>;
  const s = today.data.data_freshness[id], st = sourceState(s, checkedAt);
  return <>
    <PageHead title={id === 'yandex_direct' ? 'Яндекс Директ' : 'Яндекс Метрика'} sub="Права, свежесть и последняя синхронизация." actions={<LinkBtn href={`/workspace/connections?workspace=${ws}`}>← Все подключения</LinkBtn>} />
    <Card><dl className="ix-kv"><dt>Состояние</dt><dd><Tag tone={st.warn ? 'warn' : undefined}>{st.label}</Tag></dd><dt>Данные по</dt><dd>{s.data_to ?? 'нет данных'}</dd><dt>Последняя успешная синхронизация</dt><dd>{stamp(s.last_success_at)}</dd><dt>Права</dt><dd>только чтение статистики</dd></dl>
      <p className="ix-muted ix-mini">Журнал синхронизаций и срок действия токена API пока не передаёт.</p></Card><Gap />
    {id === 'yandex_direct' ? <DirectConnect workspace={ws} /> : <Card><p>Счётчик и цели Метрики задаются при подключении Директа. Для смены подтвердите настройки нужного рекламного аккаунта заново.</p><LinkBtn variant="primary" href={`/onboarding/connect?workspace=${encodeURIComponent(ws)}`}>Настроить счётчик и цели</LinkBtn></Card>}</>;
}

export async function AlertDetail({ws, id}: {ws: string; id: string}) {
  const insights = await safe(pilotGet(`/workspaces/${ws}/insights`, isInsights));
  if (!insights.ok) return <ErrorState page code={insights.code} />;
  const c = insights.data.health.checks.find(x => x.id === id);
  if (!c) return <StateBlock level={1} kind="empty" title="Сигнал не найден">Проверка с таким идентификатором в текущем снимке отсутствует.</StateBlock>;
  return <>
    <PageHead title={CHECK_TITLE[c.id] ?? c.id} sub="Правило проверки и что сделать." actions={<LinkBtn href={`/workspace/alerts?workspace=${ws}`}>← Все сигналы</LinkBtn>} />
    <Card><dl className="ix-kv"><dt>Статус</dt><dd><Tag tone={c.status === 'ok' ? undefined : 'warn'}>{c.status}</Tag></dd><dt>Причина</dt><dd>{c.reason}</dd><dt>Что сделать</dt><dd>{c.action}</dd></dl></Card></>;
}
