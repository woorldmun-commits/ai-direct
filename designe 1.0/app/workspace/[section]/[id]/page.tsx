import type {Metadata} from 'next';
import {renderLive} from '@/components/ix/live/router';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = {title: 'Рабочий кабинет', robots: {index: false, follow: false}};

export default async function WorkspaceDetail({params, searchParams}: {params: Promise<{section: string; id: string}>; searchParams: Promise<Record<string, string | string[] | undefined>>}) {
  const {section, id} = await params;
  return renderLive(section, id, await searchParams);
}
