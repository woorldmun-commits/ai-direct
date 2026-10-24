import {notFound} from 'next/navigation';
import {MidnightPreview} from '@/components/midnight/preview';
import '@/components/midnight/midnight.css';
import '@/components/midnight/reference.css';

export default async function Page({params}: {params: Promise<{screen: string}>}) {
  const {screen} = await params;
  if (!['landing', 'overview', 'recommendation'].includes(screen)) notFound();
  return <MidnightPreview screen={screen as 'landing' | 'overview' | 'recommendation'} />;
}
