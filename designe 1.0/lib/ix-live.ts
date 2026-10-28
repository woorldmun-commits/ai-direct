import 'server-only';
import {PilotError, pilotGet} from './pilot';
import {isMe, workspaceId, type Workspace} from './pilot-contract';

export type LiveCode = PilotError['code'];
export type Res<T> = {ok: true; data: T} | {ok: false; code: LiveCode};

/** Ответ API → результат без исключения: экран сам показывает честное состояние вместо подставных данных. */
export async function safe<T>(promise: Promise<T>): Promise<Res<T>> {
  try { return {ok: true, data: await promise}; }
  catch (error) { return {ok: false, code: error instanceof PilotError ? error.code : 'unavailable'}; }
}

export type Selected = {ok: true; workspaces: Workspace[]; selected?: Workspace} | {ok: false; code: LiveCode};

/** /me → доступные пространства → выбранное по `?workspace=` (по умолчанию первое). Чужой id = «нет доступа». */
export async function resolveWorkspace(query: {workspace?: string}): Promise<Selected> {
  const me = await safe(pilotGet('/me', isMe));
  if (!me.ok) return me;
  const workspaces = me.data.organizations.flatMap(o => o.workspaces);
  if (query.workspace !== undefined) {
    if (!workspaceId(query.workspace)) return {ok: false, code: 'access'};
    const selected = workspaces.find(w => w.id === query.workspace);
    return selected ? {ok: true, workspaces, selected} : {ok: false, code: 'access'};
  }
  return {ok: true, workspaces, selected: workspaces[0]};
}

const MSK = new Intl.DateTimeFormat('ru-RU', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Moscow'});
export const stamp = (iso: string | null) => (iso ? MSK.format(new Date(iso)) + ' МСК' : 'ещё не было');

export function recommendationHref(workspace: string, query: {cursor?: string; rec?: string} = {}): string {
  const params = new URLSearchParams({workspace});
  if (query.cursor) params.set('cursor', query.cursor);
  if (query.rec) params.set('rec', query.rec);
  return `/workspace/recommendations?${params}`;
}

export function verificationLabel(verification: {status: string; reason?: string | null}): string {
  if (verification.status === 'confirmed') return 'Состояние объекта подтверждено в источнике. Это не подтверждение экономии или причинного эффекта.';
  if (verification.status === 'not_confirmed') return 'На момент чтения часть площадок отсутствовала в исключениях Директа. Проверьте выполненное действие.';
  if (verification.status === 'pending' || verification.status === 'queued') return 'Независимая сверка ожидает чтения источника. Ручная отметка ещё не подтверждена.';
  if (verification.reason === 'verification_worker_not_implemented') return 'Независимая сверка пока не подключена. Ручное действие не подтверждено.';
  if (verification.reason === 'manual_execution_required') return 'Для сверки сначала отметьте ручное выполнение рекомендации.';
  if (verification.reason === 'execution_version_outdated') return 'После ручной отметки появились новые основания. Предыдущая сверка не подтверждает новую версию рекомендации.';
  if (verification.reason === 'not_requested') return 'Ручное выполнение отмечено. Можно запросить независимое чтение исключений площадок.';
  if (verification.reason === 'masked_exclusions') return 'Часть исключений скрыта в источнике. Подтверждённых данных для вывода недостаточно.';
  if (verification.reason === 'retries_exhausted' || verification.reason === 'worker_error') return 'Сверку не удалось завершить. Состояние не подтверждено; требуется проверка подключения и очереди администратором.';
  if (verification.status === 'not_required') return 'Для этого решения независимая сверка не требуется.';
  return 'Подтверждённых данных для сверки пока недостаточно. Проверьте доступность источника и основания рекомендации.';
}

export const STATE_TEXT: Record<LiveCode, [string, string]> = {
  setup: ['Сервис временно недоступен', 'Сервис временно недоступен. Попробуйте позже или обратитесь к администратору.'],
  session: ['Требуется вход', 'Войдите в аккаунт, чтобы продолжить.'],
  access: ['Нет доступа', 'Выберите доступное пространство. Возможно, доступ изменился, у вашей роли нет прав на этот раздел или пространство удалено.'],
  unavailable: ['Не удалось получить данные', 'Источник временно недоступен. Попробуйте обновить страницу. Недоступные показатели не подставляются.'],
  invalid: ['Данные требуют проверки', 'Ответ сервера не соответствует контракту. Значения скрыты, чтобы не показывать неверные показатели. Сообщите об этом в поддержку.'],
};

export type Member = {user: {id: string; email: string}; org_role: string; ws_role: string | null};
const rec = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export function isMembers(v: unknown): v is {items: Member[]} {
  return rec(v) && Array.isArray(v.items) && v.items.length <= 1000 && v.items.every(m => rec(m) && rec(m.user)
    && typeof m.user.id === 'string' && typeof m.user.email === 'string' && m.user.email.length <= 320
    && typeof m.org_role === 'string' && (m.ws_role === null || typeof m.ws_role === 'string'));
}
