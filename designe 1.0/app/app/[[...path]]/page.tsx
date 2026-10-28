import type {Metadata} from 'next';
import {notFound, redirect} from 'next/navigation';
import {isSection} from '@/components/ix/live/router';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = {title: 'Кабинет INROU', robots: {index: false, follow: false}};
const aliases: Record<string, string> = {
  signals: 'alerts', pricing: 'plans', 'settings/business': 'business-profile',
  'connections/health': 'data-health', 'reports/new': 'report-builder', 'team/roles': 'roles', 'ai/history': 'ai-history',
};

export default async function AppPage({params, searchParams}: {
  params: Promise<{path?: string[]}>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const {path = []} = await params;
  if (!path.length) redirect('/app/analysis');
  const key = path.join('/');
  const section = aliases[key] ?? aliases[path[0]] ?? path[0];
  if (path.length > 2 || !isSection(section)) notFound();
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (Array.isArray(value)) value.forEach(item => query.append(key, item));
    else if (value !== undefined) query.set(key, value);
  }
  const id = aliases[key] ? undefined : path[1];
  redirect(`/workspace/${section}${id ? '/' + encodeURIComponent(id) : ''}${query.size ? '?' + query : ''}`);
}
