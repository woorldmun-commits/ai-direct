import {notFound} from 'next/navigation';
import {Suspense} from 'react';
import {DemoScreen} from '@/components/ix/demo-screens';
import {SLUGS, navLabel} from '@/components/ix/nav';
import {IxShell} from '@/components/ix/shell';
import {StateGallery} from '@/components/ix/state-gallery';

export async function generateMetadata({params}: {params: Promise<{section: string}>}) {
  const {section} = await params;
  return {title: `${navLabel(section)} — демо`};
}

export default async function DemoSection({params}: {params: Promise<{section: string}>}) {
  const {section} = await params;
  if (!SLUGS.includes(section) && section !== 'states') notFound();
  return <IxShell base="/demo" mode="demo"><Suspense>{section === 'states' ? <StateGallery /> : <DemoScreen section={section} />}</Suspense></IxShell>;
}
