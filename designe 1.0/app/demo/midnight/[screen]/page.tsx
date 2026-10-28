import {notFound, redirect} from 'next/navigation';

const currentPages: Record<string, string> = {
  landing: '/', overview: '/demo/overview', recommendation: '/demo/recommendations',
};

export default async function Page({params}: {params: Promise<{screen: string}>}) {
  const {screen} = await params;
  if (!Object.hasOwn(currentPages, screen)) notFound();
  redirect(currentPages[screen]);
}
