import {notFound, redirect} from 'next/navigation';
import {Suspense} from 'react';
import {resolveWorkspace} from '@/lib/ix-live';
import {SLUGS} from '../nav';
import {IxShell} from '../shell';
import {Skeleton, StateBlock} from '../ui';
import {Analysis, Overview, Recommendations, type Query} from './core';
import {Ai, AlertDetail, BusinessProfile, ConnectionDetail, DataHealthPage, OnboardingReview, Plans, Settings, Team} from './misc';
import {Alerts, CampaignDetail, Campaigns, Connections, History, Impact, Reports} from './more';
import {ErrorState} from './parts';
import {CONTEXT_PAGES, ContextPage} from './context';

export const EXTRA_SLUGS = ['data-health', 'onboarding-review'];
export const isSection = (s: string) => SLUGS.includes(s) || EXTRA_SLUGS.includes(s) || Object.hasOwn(CONTEXT_PAGES, s);

const one = (v: string | string[] | undefined) => (typeof v === 'string' ? v : undefined);
export const pickQuery = (sp: Record<string, string | string[] | undefined>): Query => ({workspace: one(sp.workspace), rec: one(sp.rec), cursor: one(sp.cursor), activity: one(sp.activity), days: one(sp.days), ad_account: one(sp.ad_account), offset: one(sp.offset)});

function Loading() {
  return <StateBlock kind="loading" title="Загружаем данные"><Skeleton rows={4} /></StateBlock>;
}

async function Screen({section, id, ws, name, q, workspaces}: {section: string; id?: string; ws: string; name?: string; q: Query; workspaces: {id: string; name: string}[]}) {
  if (!id && Object.hasOwn(CONTEXT_PAGES, section)) return <ContextPage section={section} ws={ws} workspaces={workspaces} />;
  if (id) {
    switch (section) {
      case 'recommendations':
        if (!/^rec_[1-9]\d{0,18}$/.test(id)) return <StateBlock level={1} kind="empty" title="Рекомендация не найдена">Нужен фактический идентификатор из списка рекомендаций. Номер из дизайн-примера не является записью сервера.</StateBlock>;
        redirect(`/workspace/recommendations?workspace=${ws}&rec=${encodeURIComponent(id)}`);
      case 'history': redirect(/^rec_[1-9]\d{0,18}$/.test(id) ? `/workspace/recommendations?workspace=${ws}&rec=${id}` : `/workspace/history?workspace=${ws}`);
      case 'connections': return <ConnectionDetail ws={ws} id={id} />;
      case 'alerts': return <AlertDetail ws={ws} id={id} />;
      case 'reports': return id === 'weekly' ? <Reports ws={ws} q={q} expanded /> : <StateBlock level={1} kind="empty" title="Отчёт не найден">Сейчас доступен один сформированный отчёт — недельный.</StateBlock>;
      case 'campaigns': return <CampaignDetail ws={ws} q={q} id={id} />;
      case 'team': return <Team ws={ws} id={id} />;
      default: notFound();
    }
  }
  switch (section) {
    case 'overview': return <Overview ws={ws} q={q} />;
    case 'analysis': return <Analysis ws={ws} q={q} />;
    case 'recommendations': return <Recommendations ws={ws} q={q} />;
    case 'campaigns': return <Campaigns ws={ws} q={q} />;
    case 'connections': return <Connections ws={ws} q={q} />;
    case 'impact': return <Impact ws={ws} q={q} />;
    case 'reports': return <Reports ws={ws} q={q} />;
    case 'alerts': return <Alerts ws={ws} q={q} />;
    case 'ai': return <Ai ws={ws} cursor={q.cursor} />;
    case 'history': return <History ws={ws} q={q} />;
    case 'team': return <Team ws={ws} />;
    case 'plans': return <Plans ws={ws} />;
    case 'settings': return <Settings ws={ws} name={name} />;
    case 'business-profile': return <BusinessProfile ws={ws} />;
    case 'data-health': return <DataHealthPage ws={ws} />;
    case 'onboarding-review': return <OnboardingReview ws={ws} />;
    default: notFound();
  }
}

/** Общая точка входа для /workspace/<раздел>[/<id>]: сессия → пространство → оболочка → экран. */
export async function renderLive(section: string, id: string | undefined, sp: Record<string, string | string[] | undefined>) {
  if (!isSection(section)) notFound();
  const q = pickQuery(sp);
  const sel = await resolveWorkspace(q);
  if (!sel.ok && sel.code === 'session') redirect('/login');
  const ws = sel.ok ? sel.selected : undefined;
  if (ws && !q.workspace) {
    // Канонический адрес всегда содержит пространство: ссылки и обновление страницы не теряют контекст.
    const query = new URLSearchParams({...Object.fromEntries(Object.entries(q).filter((entry): entry is [string, string] => entry[1] !== undefined)), workspace: ws.id});
    redirect(`/workspace/${section}${id ? '/' + encodeURIComponent(id) : ''}?${query}`);
  }
  return <IxShell base="/workspace" mode="live" workspace={ws?.id} workspaces={sel.ok ? sel.workspaces : []} periodLabel="Только чтение">
    {!sel.ok ? <ErrorState page code={sel.code} />
      : !ws ? <StateBlock level={1} kind="empty" title="Пока нет рабочих пространств">Обратитесь к администратору, чтобы получить доступ к проекту.</StateBlock>
      : <Suspense fallback={<Loading />}><Screen section={section} id={id} ws={ws.id} name={ws.name} q={q} workspaces={sel.workspaces} /></Suspense>}
  </IxShell>;
}
