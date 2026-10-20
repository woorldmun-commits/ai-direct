/* eslint-disable @next/next/no-html-link-for-pages -- Full document navigation separates public analytics and private workspace state. */
import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { InsightsPanel } from '@/components/workspace/insights';
import { isInsights, type WorkspaceInsights } from '@/lib/insights-contract';
import { ThemeControl } from '@/components/theme-control';
import {MidnightShell,type WorkspaceView} from '@/components/workspace/midnight-shell';
import {PlatformBadge} from '@/components/reference/shared';
import { ArrowRight, ShieldCheck, RefreshCw, Database, Search } from 'lucide-react';
import { ValueView } from '@/components/value-view';
import { pilotGet, PilotError } from '@/lib/pilot';
import { cursor, isMe, isToday, isRecommendations, type PilotToday, type PilotRecommendations } from '@/lib/pilot-contract';
import { sourceLabel, formatPeriod, type Value } from '@/lib/value';
import '@/components/reference/reference.css';
import './pilot.css';

export const metadata: Metadata = { title: 'Рабочий кабинет', robots: { index: false, follow: false } };
export const dynamic = 'force-dynamic';
const messages = {
  setup: ['Сервис временно недоступен', 'Сервис временно недоступен. Попробуйте позже или обратитесь к администратору.'],
  session: ['Требуется вход', 'Войдите в аккаунт, чтобы продолжить.'],
  access: ['Рабочее пространство недоступно', 'Выберите доступное пространство. Возможно, доступ изменился или пространство удалено.'],
  unavailable: ['Не удалось получить данные', 'Источник временно недоступен. Попробуйте обновить страницу. Ранее показанные или модельные значения не подставляются.'],
  invalid: ['Данные требуют проверки', 'Ответ сервера не соответствует контракту. Значения скрыты, чтобы не показывать неверные показатели. Сообщите об этом службе поддержки.'],
} as const;
function stamp(value: string | null) { return value ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Moscow' }).format(new Date(value)) + ' МСК' : 'Ещё не было'; }
function Metric({ title, value }: { title: string; value: Value }) {
  return <section className="pilot-card pilot-metric"><h2>{title}</h2><ValueView v={value} caption className="pilot-number" />{value.calculation_type === 'unavailable' && <p>{sourceLabel(value.source)} · {formatPeriod(value.period)}</p>}</section>;
}
export default async function PilotPage({ searchParams }: { searchParams: Promise<{ workspace?: string; cursor?: string; view?:string }> }) {
  const query = await searchParams;
  // This force-dynamic server page evaluates freshness once per HTTP request, never in a client render.
  // eslint-disable-next-line react-hooks/purity
  const checkedAt = Date.now();
  let state: keyof typeof messages | null = null;
  let workspaces: { id: string; name: string }[] = [];
  let selected: { id: string; name: string } | undefined;
  let today: PilotToday | undefined;
  let recommendations: PilotRecommendations | undefined;
  let insights: WorkspaceInsights | undefined;
  try {
    const me = await pilotGet('/me', isMe);
    workspaces = me.organizations.flatMap(org => org.workspaces);
    selected = query.workspace ? workspaces.find(w => w.id === query.workspace) : workspaces[0];
    if (query.workspace && !selected) throw new PilotError('access');
    if (query.cursor && !cursor(query.cursor)) throw new PilotError('invalid');
    if (selected) [today, insights, recommendations] = await Promise.all([
      pilotGet(`/workspaces/${selected.id}/today`, isToday),
      pilotGet(`/workspaces/${selected.id}/insights`, isInsights),
      pilotGet(`/workspaces/${selected.id}/recommendations?limit=50${query.cursor ? '&cursor=' + query.cursor : ''}`, isRecommendations),
    ]);
  } catch (error) { state = error instanceof PilotError ? error.code : 'unavailable'; }
  if (state === 'session') redirect('/login');
    const view:WorkspaceView=['analysis','recommendations','effect','integrations','settings','analyst'].includes(query.view||'')?query.view as WorkspaceView:'analysis';
    const titles={analysis:'Анализ',recommendations:'Рекомендации',effect:'Эффект',integrations:'Подключения',settings:'Настройки',analyst:'AI-аналитик'};
  const location = selected ? '/workspace?view='+view+'&workspace=' + selected.id : '/workspace?view='+view;
    return <MidnightShell workspace={selected?.id} workspaceName={selected?.name} view={view}>
      <main id="main-content" className="pilot-main" tabIndex={-1}>
        <div className="pilot-heading"><div><h1>{titles[view]}</h1><p>{view==='analysis'?'Динамика и эффективность рекламных кампаний':view==='recommendations'?'Проверяемые основания для каждого решения':view==='effect'?'Проверка изменений после выполненных действий':view==='integrations'?'Источники, права и свежесть данных':view==='settings'?'Рабочее пространство и внешний вид':'Факты и ограничения выбранного периода'}</p></div><a className="ref-button" href={location}><RefreshCw size={16}/>Обновить</a></div>
        {workspaces.length>0&&<form className="pilot-selector" action="/workspace"><input type="hidden" name="view" value={view}/><label htmlFor="workspace">Рабочее пространство</label><select id="workspace" name="workspace" defaultValue={selected?.id}>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select><button className="ref-button ref-primary">Открыть</button></form>}
        {state?<section className="pilot-card pilot-state" role="status"><Database size={36}/><h2>{messages[state][0]}</h2><p>{messages[state][1]}</p><Link href="/login" className="ref-button ref-primary">Вернуться ко входу</Link></section>:!selected?<section className="mc-empty"><Database size={30}/><h2>Пока нет рабочих пространств</h2><p>Обратитесь к администратору, чтобы получить доступ к проекту.</p></section>:today&&recommendations&&<>
        {view==='analysis'&&<><div className="pilot-section-title"><h2>{selected.name}</h2><p>Последний аудит: {stamp(today.last_audit_at)}</p></div><div className="pilot-grid"><Metric title="Расход за проверенный период" value={today.spent}/><Metric title="Потенциально неэффективные расходы" value={today.exposure.total}/><section className="pilot-card pilot-metric"><h2>Активные рекомендации</h2><strong className="pilot-number">{today.counts.active}</strong><p>Основания последнего аудита</p></section></div>            <section className="pilot-card pilot-sources"><h2>Свежесть источников</h2><div className="pilot-grid">{(['yandex_direct', 'yandex_metrika'] as const).map(key => {
              const source = today.data_freshness[key];
              const stale = !source.data_to || checkedAt - Date.parse(source.data_to + 'T21:00:00Z') > 72 * 3_600_000;
              return <article key={key}><h3>{sourceLabel(key)}</h3><span className={source.status !== 'connected' || stale ? 'pilot-warning' : 'pilot-ok'}>{source.status === 'connected' ? stale ? 'Данные требуют обновления' : 'Подключён' : source.status === null ? 'Не подключён' : 'Нужна проверка подключения'}</span><p>Данные по: {source.data_to ?? 'нет данных'}<br />Успешная синхронизация: {stamp(source.last_success_at)}</p></article>;
            })}</div>{today.data_status === 'partial' && <p className="pilot-warning">Данные за период неполные. Выводы требуют дополнительной проверки.</p>}</section>
<section className="mc-empty"><Database size={28}/><h2>Динамика по дням</h2><p>Дневной ряд расходов, конверсий и CPA не передан текущим API. График появится после подключения этого набора данных.</p><p>Недоступные значения не подменяются нулями или демонстрацией.</p></section>{insights&&<InsightsPanel workspace={selected.id} data={insights}/>}</>}
        {view==='recommendations'&&<>            <section aria-labelledby="pilot-recommendations"><div className="pilot-section-title"><h2 id="pilot-recommendations">Рекомендации</h2><span>Основания из последнего аудита</span></div>
              {recommendations.items.length === 0 ? <div className="pilot-card pilot-state"><Search size={30} /><h3>Активных рекомендаций нет</h3><p>{today.last_audit_at ? 'Проверьте свежесть и полноту данных перед выводом об эффективности.' : 'Аудит ещё не выполнен. Отсутствие рекомендаций пока не означает отсутствие проблем.'}</p></div> : recommendations.items.map(rec => <article className="pilot-card pilot-recommendation" key={rec.id}><div><span className="pilot-eyebrow">{rec.action_level === 'change' ? 'Изменение вручную' : rec.action_level === 'review' ? 'Нужна проверка' : 'Только наблюдение'}</span><h3>{rec.title}</h3><p>Рассчитано: {stamp(rec.computed_at)}</p></div><ValueView v={rec.exposure} caption className="pilot-rec-number" /><details><summary>Основание и ограничения</summary><dl><dt>Версия рекомендации</dt><dd>{rec.version_id}</dd><dt>Правило</dt><dd>{rec.exposure.rule_version ?? 'Не передано сервером'}</dd><dt>Источник</dt><dd>{sourceLabel(rec.exposure.source)}</dd><dt>Период</dt><dd>{formatPeriod(rec.exposure.period)}</dd><dt>Формула</dt><dd>{rec.exposure.formula ?? 'Значение из источника'}</dd></dl><p>Пересечение с другими рекомендациями: <ValueView v={rec.exposure_overlap} />. Карточки нельзя суммировать: общий итог уже учитывает пересечения.</p><p><Link className="ref-button" href={`/workspace/recommendations/${rec.id}?workspace=${selected.id}`}>Паспорт и решение <ArrowRight size={16}/></Link></p></details></article>)}
              {recommendations.next_cursor && <a className="ref-button" href={location + '&cursor=' + recommendations.next_cursor}>Следующие рекомендации <ArrowRight size={16} /></a>}
              {query.cursor && <Link className="ref-button" href={location}>К началу списка</Link>}
            </section>
</>}
        {view==='effect'&&<section className="mc-empty"><ShieldCheck size={30}/><h2>Недостаточно данных для оценки эффекта</h2><p>Для оценки нужны выполненное действие и сопоставимые периоды до и после изменения. Прогноз не считается подтверждённой экономией.</p><Link className="ref-button" href={'/workspace?view=recommendations&workspace='+selected.id}>Открыть рекомендации <ArrowRight size={16}/></Link></section>}
        {view==='integrations'&&<>            <section className="pilot-card pilot-sources"><h2>Свежесть источников</h2><div className="pilot-grid">{(['yandex_direct', 'yandex_metrika'] as const).map(key => {
              const source = today.data_freshness[key];
              const stale = !source.data_to || checkedAt - Date.parse(source.data_to + 'T21:00:00Z') > 72 * 3_600_000;
              return <article key={key}><h3>{sourceLabel(key)}</h3><span className={source.status !== 'connected' || stale ? 'pilot-warning' : 'pilot-ok'}>{source.status === 'connected' ? stale ? 'Данные требуют обновления' : 'Подключён' : source.status === null ? 'Не подключён' : 'Нужна проверка подключения'}</span><p>Данные по: {source.data_to ?? 'нет данных'}<br />Успешная синхронизация: {stamp(source.last_success_at)}</p></article>;
            })}</div>{today.data_status === 'partial' && <p className="pilot-warning">Данные за период неполные. Выводы требуют дополнительной проверки.</p>}</section>
<div className="mc-source-grid">{['Яндекс Директ','Яндекс Метрика','VK Ads','Telegram Ads','Авито'].map((name,i)=><article className="mc-source-card" key={name}><PlatformBadge platform={name} size={40}/><h2>{name}</h2><p>{i<2?'Поддерживается текущей версией. Статус вашего подключения и последняя синхронизация показаны выше. Подключение выполняется администратором отдельно от входа.':'В разработке. Подключение и синхронизация недоступны.'}</p></article>)}</div></>}
        {view==='settings'&&<div className="mc-live-settings"><section className="pilot-card"><h2>Внешний вид</h2><p>Тёмная, светлая или системная тема. Выбор сохраняется в этом браузере.</p><ThemeControl/></section><section className="pilot-card"><h2>Рабочее пространство</h2><p>{selected.name}</p><p>Доступные пространства выбираются выше. Управление участниками и профилем недоступно в текущем интерфейсе.</p></section><section className="pilot-card"><h2>Подписка и документы</h2><p>Оплата пока не подключена. Условия запуска будут опубликованы в правовом разделе.</p><Link href="/pricing" className="ref-button">Посмотреть тарифы</Link> <Link href="/legal" className="ref-button">Правовая информация</Link></section></div>}
        {view==='analyst'&&<section className="pilot-card"><div className="pilot-section-title"><h2>Сводка по данным</h2><span>Детерминированный анализ</span></div><p>Объяснение сформировано из проверенных сервером фактов. Внешняя языковая модель не подключена.</p>{insights?<div className="mc-live-summary">{insights.summary.facts.map(f=><article key={f.id}><h3>{f.label}</h3>{f.value&&<ValueView v={f.value} caption/>}<p>{f.detail}</p></article>)}<h3>Ограничения</h3><ul>{insights.summary.limitations.map(l=><li key={l}>{l}</li>)}</ul><p>Период: {formatPeriod(insights.summary.period)} · Обновлено: {stamp(insights.summary.generated_at)}</p></div>:<p>Для сводки пока недостаточно данных. Проверьте источники.</p>}</section>}
        <aside className="pilot-note"><ShieldCheck size={20}/><p>AdPilot читает данные. Изменения в Директе выполняет специалист вручную. Демонстрационные показатели не используются в рабочем кабинете.</p></aside></>}
      </main><footer className="pilot-footer">AdPilot · Рабочий кабинет<a href="/legal">Правовая информация</a></footer>
    </MidnightShell>;
  }
