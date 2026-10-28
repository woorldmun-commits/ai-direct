import type {Metadata} from 'next';
import {navLabel} from '@/components/ix/nav';
import {renderLive} from '@/components/ix/live/router';

export const dynamic = 'force-dynamic';

export async function generateMetadata({params}: {params: Promise<{section: string}>}): Promise<Metadata> {
  const {section} = await params;
  return {title: navLabel(section) === 'INROU' ? 'Рабочий кабинет' : navLabel(section), robots: {index: false, follow: false}};
}

export default async function WorkspaceSection({params, searchParams}: {params: Promise<{section: string}>; searchParams: Promise<Record<string, string | string[] | undefined>>}) {
  const {section} = await params;
  return renderLive(section, undefined, await searchParams);
}
