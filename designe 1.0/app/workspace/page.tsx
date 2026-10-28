import {redirect} from 'next/navigation';

export const dynamic = 'force-dynamic';

// Прежний адрес /workspace?view=… сохранён как редирект: закладки и ссылки из писем продолжают работать.
const LEGACY: Record<string, string> = {analysis: 'analysis', recommendations: 'recommendations', effect: 'impact', integrations: 'connections', settings: 'settings', analyst: 'ai', reports: 'reports'};

export default async function WorkspaceIndex({searchParams}: {searchParams: Promise<Record<string, string | string[] | undefined>>}) {
  const params = await searchParams;
  const workspace = typeof params.workspace === 'string' ? params.workspace : undefined;
  const view = typeof params.view === 'string' ? params.view : undefined;
  const target = LEGACY[view ?? ''] ?? 'overview';
  const query = new URLSearchParams();
  if (workspace && /^ws_[1-9]\d{0,18}$/.test(workspace)) query.set('workspace', workspace);
  for (const key of ['rec', 'cursor', 'activity']) if (typeof params[key] === 'string') query.set(key, params[key]);
  if (view === 'analyst' && typeof params.analysis_cursor === 'string') query.set('cursor', params.analysis_cursor);
  redirect(`/workspace/${target}${query.size ? '?' + query : ''}`);
}
