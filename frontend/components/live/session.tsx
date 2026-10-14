"use client";
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { ArrowRight, Building2, RefreshCw, ShieldCheck } from 'lucide-react';
import { api, ApiError, errorText } from '@/lib/api';
import { Logo } from '@/components/ui';

type Workspace = { id: string; name: string; ws_role: string | null };
type Session = { user: { id: string; phone: string | null; email: string | null }; workspaces: Workspace[] };
const SessionContext = createContext<Session | null>(null);

export function SessionGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    api<Session>('/me', { signal: abort.signal }).then(setSession).catch((error: unknown) => {
      if (abort.signal.aborted) return;
      if (error instanceof ApiError && error.status === 401) router.replace('/login');
      else setError(errorText(error));
    });
    return () => abort.abort();
  }, [router, revision]);
  if (!session) return <main id="main-content" className="auth-page grid min-h-dvh place-items-center p-6"><section className="card w-full max-w-lg p-8"><Logo /><ShieldCheck className="my-6 size-10 text-brand" /><h1 className="text-2xl font-bold">Ваше рабочее пространство</h1><p className="mt-3 text-muted" role={error ? 'alert' : 'status'}>{error || 'Проверяем безопасную сессию…'}</p>{error && <button className="btn btn-primary mt-6" onClick={() => { setError(''); setRevision((v) => v + 1); }}><RefreshCw size={16} />Повторить</button>}<Link href="/demo" className="btn btn-secondary mt-6 ml-2">Посмотреть демо</Link></section></main>;
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function WorkspaceEntry({ onboarding = false }: { onboarding?: boolean }) {
  const session = useContext(SessionContext);
  return <main id="main-content" className="auth-page grid min-h-dvh place-items-center p-6"><section className="card w-full max-w-2xl p-8"><Link href="/"><Logo /></Link><p className="mt-8 text-sm text-brand">{session?.user.phone || session?.user.email || 'Личный кабинет'}</p><h1 className="mt-2 text-3xl font-bold">{onboarding ? 'Настройка бизнеса' : 'Ваши рабочие пространства'}</h1><p className="mt-3 text-muted">{session?.workspaces.length ? 'Выберите бизнес, с которым хотите работать.' : 'Ваш аккаунт подтверждён. Подключение бизнеса станет доступно после настройки сервиса.'}</p><div className="mt-6 space-y-3">{session?.workspaces.map((workspace) => <Link className="card flex items-center gap-4 p-5" href={'/app/' + encodeURIComponent(workspace.id)} key={workspace.id}><Building2 className="text-brand" /><span className="flex-1 font-semibold">{workspace.name}</span><ArrowRight size={18} /></Link>)}</div><Link className="btn btn-secondary mt-6" href="/demo">Открыть демонстрационный кабинет</Link></section></main>;
}
