import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { pilotGet, PilotError } from '@/lib/pilot';
import { isMe } from '@/lib/pilot-contract';
import { isPassport, type RecommendationPassport } from '@/lib/insights-contract';
import { ValueView } from '@/components/value-view';
import { ActionInstructions } from '@/components/workspace/action-instructions';
import { MeasurementView } from '@/components/workspace/measurement';
import { DecisionForm } from '@/components/workspace/actions';
import '@/components/reference/reference.css';
import '../../pilot.css';

export const metadata: Metadata = {title:'Паспорт рекомендации',robots:{index:false,follow:false}};
export const dynamic = 'force-dynamic';
const labels: Record<string,string> = {created:'Создана',seen_again:'Основания обновлены',postponed:'Отложена',rejected:'Отклонена',done:'Заявлено ручное выполнение',checked:'Проверена специалистом',measured:'Выполнен замер',measurement_skipped:'Замер пропущен',unpostponed:'Возвращена к рассмотрению'};
const statuses: Record<string,string> = {new:'Ожидает решения',postponed:'Отложена',rejected:'Отклонена',applied:'Решение записано',resolved:'Проблема закрыта'};
export default async function PassportPage({params,searchParams}:{params:Promise<{id:string}>;searchParams:Promise<{workspace?:string}>}) {
  const {id} = await params, {workspace} = await searchParams;
  let data: RecommendationPassport | undefined;
  let message = '';
  try {
    const me = await pilotGet('/me',isMe);
    if (!workspace || !me.organizations.some(org=>org.workspaces.some(item=>item.id===workspace)) || !/^rec_[1-9]\d{0,18}$/.test(id)) throw new PilotError('access');
    data = await pilotGet(`/workspaces/${workspace}/recommendations/${id}`,isPassport);
  } catch(error) {
    if(error instanceof PilotError && error.code==='session') redirect('/login');
    message = error instanceof PilotError && error.code==='access' ? 'Нет доступа к этой рекомендации.' : 'Не удалось проверить данные рекомендации. Обновите страницу.';
  }
  return <div className="ref-ui ap-app pilot-page"><main className="pilot-main" id="main-content"><Link className="ref-button" href={workspace&&/^ws_[1-9]\d{0,18}$/.test(workspace)?`/workspace?view=recommendations&workspace=${workspace}`:'/workspace'}>← Рабочий кабинет</Link>
    {data && workspace ? <><div className="pilot-heading"><div><p className="pilot-eyebrow">{statuses[data.status]??'Статус требует проверки'}</p><h1>{data.title??'Паспорт рекомендации'}</h1><p>{data.version_id} · Доказательства и история решений</p></div></div>
      <section className="pilot-card"><h2>Расход с признаками неэффективности</h2><ValueView v={data.exposure} caption/><p>Это оценка по правилу, а не подтверждённая экономия.</p>{data.explanation && <p>{data.explanation.text}</p>}</section>
      <section className="pilot-card"><h2>Основания</h2><div className="pilot-grid">{Object.entries(data.evidence).map(([key,value])=><article key={key}><h3>{({clicks:'Клики',cost:'Расход',conversions:'Конверсии',cpa:'Стоимость конверсии'} as Record<string,string>)[key]??key}</h3><ValueView v={value} caption/></article>)}</div></section>
      <section className="pilot-card"><h2>Решение специалиста</h2><p>Объект: {data.object.type === 'campaign' ? 'кампания' : data.object.type === 'account' ? 'аккаунт' : 'площадка'} · {data.object.id}</p>{!data.evidence_current && <p className="pilot-warning">Основания относятся к предыдущему аудиту или исключённому аккаунту. Новое выполнение недоступно.</p>}<ActionInstructions action={data.action}/><p>Действия в рекламном кабинете выполняются вручную. Отметка выполнения не подтверждает изменение, экономию или причинный эффект. Автоматическая сверка пока недоступна.</p>{data.allowed_actions.length ? <DecisionForm workspace={workspace} rec={id} version={data.version_id} state={data.state_version} allowed={data.allowed_actions}/> : <p>Для текущего состояния, роли или доступа новые решения недоступны.</p>}</section>
      <MeasurementView measurement={data.latest_measurement}/><section className="pilot-card"><h2>История</h2>{data.history.length ? <ol>{data.history.map(event=><li key={event.id}>{labels[event.type]??'Событие рекомендации'} · {new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Moscow'}).format(new Date(event.created_at))} МСК</li>)}</ol> : <p>Решений ещё нет.</p>}</section>
    </> : <section className="pilot-card" role="status"><h1>Рекомендация недоступна</h1><p>{message}</p></section>}
  </main></div>;
}
