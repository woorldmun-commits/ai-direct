import type { Metadata } from 'next';
import { SessionGate, WorkspaceEntry } from '@/components/live/session';
export const metadata: Metadata = { title: 'Рабочие пространства', robots: { index: false, follow: false } };
export default function AppPage() { return <SessionGate><WorkspaceEntry /></SessionGate>; }
