import Link from 'next/link';
import {InsightsPanel} from '@/components/workspace/insights';
import {ValueView} from '@/components/value-view';
import {isInsights} from '@/lib/insights-contract';
import {pilotGet} from '@/lib/pilot';
import {isToday} from '@/lib/pilot-contract';
import {safe} from '@/lib/ix-live';
import {Card, Gap, Info, LinkBtn, PageHead, RowLine, StateBlock} from '../ui';
import {Recommendations} from './core';
import {Ai, BusinessProfile, Settings, Team} from './misc';
import {History, Impact, Reports} from './more';
import {ErrorState} from './parts';

export const CONTEXT_PAGES: Record<string, string> = {
  changes: 'Что изменилось', 'budget-losses': 'Потенциально неэффективные расходы', budgets: 'Бюджеты',
  creatives: 'Креативы', rules: 'Правила', help: 'Помощь', 'report-builder': 'Конструктор отчётов',
  roles: 'Роли и доступ', 'ai-history': 'История аналитики', decisions: 'Центр решений', agency: 'Клиенты агентства',
  'data-catalog': 'Каталог показателей', 'effect-methods': 'Проверка эффекта',
  'security-center': 'Центр безопасности', 'niche-knowledge': 'Знания о нише', 'action-verification': 'Сверка действия',
};

export async function ContextPage({section, ws, workspaces}: {section: string; ws: string; workspaces: {id: string; name: string}[]}) {
  const href = (slug: string) => `/workspace/${slug}?workspace=${encodeURIComponent(ws)}`;
  const links = <nav className="ix-context-links" aria-label="Связанные разделы">{Object.entries(CONTEXT_PAGES).map(([slug, title]) => <Link key={slug} className="ix-pill" href={href(slug)} aria-current={slug === section ? 'page' : undefined}>{title}</Link>)}</nav>;
  let body;
  switch (section) {
    case 'decisions': body = <Recommendations ws={ws} q={{}} />; break;
    case 'changes': body = <History ws={ws} q={{}} />; break;
    case 'roles': body = <><Info>В рабочем пространстве действуют права, возвращённые сервером. Изменение ролей и приглашения пока недоступны.</Info><Gap /><Team ws={ws} /></>; break;
    case 'ai-history': body = <Ai ws={ws} />; break;
    case 'niche-knowledge': body = <BusinessProfile ws={ws} />; break;
    case 'security-center': body = <Settings ws={ws} />; break;
    case 'agency': body = <><PageHead title="Клиенты агентства" sub="Только рабочие пространства, доступ к которым подтвердил сервер." /><Card>{workspaces.map(w => <RowLine key={w.id}><div><b>{w.name}</b><div className="ix-muted ix-mini">Отдельное рабочее пространство</div></div><LinkBtn href={`/workspace/analysis?workspace=${encodeURIComponent(w.id)}`}>Открыть</LinkBtn></RowLine>)}<p className="ix-muted ix-mini">Сводные показатели клиентов и назначение менеджеров пока недоступны. Показатели разных организаций не суммируются.</p></Card></>; break;
    case 'budget-losses': {
      const data = await safe(pilotGet(`/workspaces/${ws}/today`, isToday));
      body = <><PageHead title={CONTEXT_PAGES[section]} sub="Расходы с признаками неэффективности по последнему аудиту." />{data.ok ? <Card><h2>Расходы, требующие проверки</h2><ValueView v={data.data.exposure.total} caption /><p className="ix-muted">Оценка учитывает пересечения правил. Расход не равен потере или подтверждённой экономии.</p><LinkBtn href={href('recommendations')}>Проверить основания</LinkBtn></Card> : <ErrorState code={data.code} />}</>;
      break;
    }
    case 'budgets': {
      const data = await safe(pilotGet(`/workspaces/${ws}/insights`, isInsights));
      body = <><PageHead title={CONTEXT_PAGES[section]} sub="Показатели и ограничения проверенного периода." />{data.ok ? <InsightsPanel workspace={ws} data={data.data} /> : <ErrorState code={data.code} />}</>;
      break;
    }
    case 'report-builder': body = <><PageHead title="Конструктор отчётов" sub="Отчёт формируется только по доступным данным организации." /><StateBlock kind="insufficient" title="Произвольные шаблоны пока недоступны">Сохранение шаблонов, PDF, XLSX и расписание ещё не подключены. Доступный недельный отчёт можно открыть и выгрузить ниже.</StateBlock><Gap /><Reports ws={ws} q={{}} /></>; break;
    case 'effect-methods': body = <><PageHead title="Проверка эффекта" sub="Исполнение действия и изменение показателя проверяются отдельно." /><Card><h2>Методика сравнения</h2><ol><li>Зафиксировать сопоставимые периоды и источник конверсий.</li><li>Отдельно записать решение и ручное выполнение.</li><li>Подтвердить фактическое изменение по независимым данным источника.</li><li>Сравнить расход и конверсии, проверить достаточность выборки и внешние факторы.</li></ol><Info>Изменение CPA после действия само по себе не доказывает причинный эффект. Отсутствие независимой сверки сохраняет статус «не проверено».</Info></Card><Gap /><Impact ws={ws} q={{}} /></>; break;
    case 'action-verification': body = <><PageHead title="Сверка действия" sub="Решение → ручное выполнение → независимая проверка → замер." /><Info warning>Автоматическая сверка с рекламным источником пока недоступна. Отметка человека не подтверждает фактическое изменение или экономию.</Info><Gap /><History ws={ws} q={{}} /></>; break;
    case 'data-catalog': body = <><PageHead title="Каталог показателей" sub="Единицы, формулы и ограничения доступны до принятия решения." /><Card>{[
      ['Расход', 'RUB · данные рекламного источника за период. Налоговая база и охват указаны у значения.'],
      ['CPA', 'RUB/конверсия · сумма расходов / сумма сопоставимых конверсий. При отсутствии конверсий значение недоступно.'],
      ['Конверсии', 'Директ — основной источник рекламных конверсий. Цели Метрики — отдельная диагностика, без молчаливого сложения.'],
      ['План и факт', 'План задаётся человеком. Факт берётся из источника. Отклонение не означает прогноз экономии.'],
      ['Качество заявки', 'Стоимость квалифицированной заявки рассчитывается только при загруженных и проверенных заявках.'],
      ['Недоступные данные', 'Нет данных ≠ ноль. Каждый Value раскрывает источник, период, тип расчёта и ограничения.'],
    ].map(([title, text]) => <RowLine key={title}><div><h2>{title}</h2><p className="ix-muted ix-mini">{text}</p></div></RowLine>)}<LinkBtn href={href('data-health')}>Проверить качество источников</LinkBtn></Card></>; break;
    case 'help': body = <><PageHead title="Помощь" sub="От подключения до проверки результата." /><Card><div className="ix-actions"><LinkBtn href="/faq">Вопросы и ответы</LinkBtn><LinkBtn href="/how-it-works">Как работает INROU</LinkBtn><LinkBtn href={`/onboarding/organization?workspace=${ws}`}>Настройка</LinkBtn><LinkBtn href={href('data-health')}>Качество данных</LinkBtn></div></Card></>; break;
    default: body = <><PageHead title={CONTEXT_PAGES[section]} /><StateBlock kind="insufficient" title={section === 'creatives' ? 'Каталог креативов пока не подключён' : 'Редактирование правил пока недоступно'}>{section === 'creatives' ? 'Источник не передаёт объявления и метрики креативов. Оценка выгорания не рассчитывается без этих данных.' : 'Аудит использует детерминированные серверные правила. Конструктор, тестовый прогон и согласование новых правил ещё не подключены.'}<div className="ix-actions" style={{marginTop: 12}}><LinkBtn href={href('recommendations')}>Текущие рекомендации</LinkBtn></div></StateBlock></>;
  }
  return <>{body}<Gap />{links}</>;
}
