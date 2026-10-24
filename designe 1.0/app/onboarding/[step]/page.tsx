import type {Metadata} from 'next';
import {Onboarding} from '@/components/ix/onboarding';

export const dynamic = 'force-dynamic';
export const metadata: Metadata = {title: 'Первый запуск', robots: {index: false, follow: false}};

export default async function OnboardingStep({params, searchParams}: {params: Promise<{step: string}>; searchParams: Promise<{workspace?: string}>}) {
  const {step} = await params;
  const {workspace} = await searchParams;
  return <Onboarding step={step === 'business' ? 'business-profile' : step === 'connections' ? 'connect' : step} workspace={workspace} />;
}
