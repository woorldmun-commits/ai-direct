/* eslint-disable react-hooks/purity -- серверный компонент: «сейчас» фиксируется один раз на HTTP-запрос. */
import Link from 'next/link';
import {BrandMark} from '@/components/brand-mark';
import Image from 'next/image';
import {notFound, redirect} from 'next/navigation';
import {DirectConnect} from '@/components/workspace/direct-connect';
import {IntelligencePanel} from '@/components/workspace/intelligence';
import {isIntelligence} from '@/lib/intelligence-contract';
import {resolveWorkspace, safe, stamp} from '@/lib/ix-live';
import {pilotGet} from '@/lib/pilot';
import {isToday} from '@/lib/pilot-contract';
import './ix.css';
import './public/public.css';
import {ErrorState, sourceState} from './live/parts';
import {Card, LinkBtn, RowLine, StateBlock, Tag} from './ui';

export const STEPS = [
  {slug: 'organization', title: 'Организация', lead: 'Рабочее пространство, в котором будут расходы, источники и рекомендации.'},
  {slug: 'connect', title: 'Подключение источника', lead: 'Яндекс Директ подключается отдельно от входа через OAuth, доступ только для чтения.'},
  {slug: 'business-profile', title: 'Бизнес-профиль', lead: 'Необязательный контекст для импортного анализа: отрасль, цель и определение конверсии. Можно пропустить и вернуться позже.'},
  {slug: 'first-audit', title: 'Первый аудит', lead: 'Загрузка данных, проверка, снимок и рекомендации. Статусы — с сервера, без имитации прогресса.'},
] as const;

export async function Onboarding({step, workspace}: {step: string; workspace?: string}) {
  const idx = STEPS.findIndex(s => s.slug === step);
  if (idx < 0) notFound();
  const sel = await resolveWorkspace({workspace});
  if (!sel.ok && sel.code === 'session') redirect('/login');
  const ws = sel.ok ? sel.selected : undefined;
  if (ws && !workspace) redirect(`/onboarding/${step}?workspace=${ws.id}`);
  const q = ws ? `?workspace=${ws.id}` : '';
  const cur = STEPS[idx];
  const checkedAt = Date.now();
  let body;
  if (!sel.ok) body = <ErrorState code={sel.code} />;
  else if (!ws) body = <StateBlock level={1} kind="empty" title="Пока нет рабочих пространств">Обратитесь к администратору, чтобы получить доступ к проекту. Создание организации через API сейчас недоступно.</StateBlock>;
  else if (step === 'organization') body = <><Card className="ix-welcome"><div><h2>Добро пожаловать в INROU!</h2><ul><li>Подключите рекламный кабинет</li><li>Заполните бизнес-профиль</li><li>Проверьте данные первого аудита</li><li>Получите первые рекомендации</li></ul><LinkBtn variant="primary" href={`/onboarding/connect${q}`}>Начать настройку</LinkBtn></div><Image src="/reference/inrou-process-glass-v1.png" alt="Архитектурная композиция из стекла и камня" width={256} height={320} /></Card><Card><h2>Ваши рабочие пространства</h2>{sel.workspaces.map(w => <RowLine key={w.id}><b>{w.name}</b>{w.id === ws.id ? <Tag>Выбрано</Tag> : <Link className="ix-btn" href={`/onboarding/organization?workspace=${w.id}`}>Выбрать</Link>}</RowLine>)}
    <p className="ix-muted ix-mini">Организация создаётся при регистрации. Добавление организаций и приглашения появятся с расширением backend.</p></Card></>;
  else if (step === 'business-profile') { const intel = await safe(pilotGet(`/workspaces/${ws.id}/intelligence`, isIntelligence)); body = intel.ok ? <IntelligencePanel workspace={ws.id} data={intel.data} profileOnly /> : <ErrorState code={intel.code} />; }
  else if (step === 'connect') body = <DirectConnect workspace={ws.id} />;
  else {
    const today = await safe(pilotGet(`/workspaces/${ws.id}/today`, isToday));
    if (!today.ok) body = <ErrorState code={today.code} />;
    else {
      const d = sourceState(today.data.data_freshness.yandex_direct, checkedAt);
      const phases: [string, boolean, string][] = [
        ['Яндекс Директ подключён и данные загружены', today.data.data_freshness.yandex_direct.status === 'connected' && !!today.data.data_freshness.yandex_direct.data_to, `${d.label} · данные по ${today.data.data_freshness.yandex_direct.data_to ?? 'нет данных'}`],
        ['Данные проверены', today.data.data_status === 'complete', today.data.data_status === 'complete' ? 'Полные за период' : 'Неполные: последние дни могут уточниться'],
        ['Снимок и аудит выполнены', !!today.data.last_audit_at, `Последний аудит: ${stamp(today.data.last_audit_at)}`],
        ['Проверка рекомендаций', !!today.data.last_audit_at, today.data.last_audit_at ? `Активных рекомендаций: ${today.data.counts.active}. Аудит завершён и при отсутствии находок; это не гарантия отсутствия проблем.` : 'Дождитесь завершения первого аудита.'],
      ];
      body = <Card><h2>Что уже сделано</h2>{phases.map(([t, ok, note]) => <RowLine key={t}><div><b>{t}</b><div className="ix-muted ix-mini">{note}</div></div><Tag tone={ok ? undefined : 'gray'}>{ok ? 'Готово' : 'Не выполнено'}</Tag></RowLine>)}</Card>;
    }
  }
  return <div className="ix ix-pub" lang="ru"><a className="ix-skip" href="#main-content">Перейти к содержимому</a>
    <header className="ix-pub-header"><Link className="ix-logo" href="/" style={{padding: 0}}><BrandMark/>INROU<small>INTELLIGENCE ATELIER</small></Link><div className="ix-pub-actions" style={{marginLeft: 'auto'}}><Link className="ix-pill" href={`/workspace/overview${q}`}>Пропустить в кабинет</Link></div></header>
    <main id="main-content" className="ix-onboarding-main" tabIndex={-1}>
      <nav className="ix-onboarding-steps" aria-label="Шаги первого запуска"><ol className="ix-pub-steps" style={{marginBottom: 24}}>{STEPS.map((s, i) => <li key={s.slug} aria-current={i === idx ? 'step' : undefined} style={i === idx ? {borderColor: 'var(--accent)'} : undefined}><b>0{i + 1}</b><h3 style={{margin: 0}}><Link href={`/onboarding/${s.slug}${q}`}>{s.title}</Link></h3></li>)}</ol></nav>
      <div className="ix-onboarding-body"><div className="ix-eyebrow">Шаг {idx + 1} из {STEPS.length}</div><h1>{cur.title}</h1><p className="ix-pub-lead">{cur.lead}</p>
      <div style={{maxWidth: 820}}>{body}</div>
      <div className="ix-actions" style={{marginTop: 20}}>{idx > 0 && <LinkBtn href={`/onboarding/${STEPS[idx - 1].slug}${q}`}>← Назад</LinkBtn>}{idx < STEPS.length - 1 ? <LinkBtn variant="primary" href={`/onboarding/${STEPS[idx + 1].slug}${q}`}>Далее →</LinkBtn> : <LinkBtn variant="primary" href={`/workspace/overview${q}`}>Открыть кабинет</LinkBtn>}</div>
    </div></main></div>;
}
