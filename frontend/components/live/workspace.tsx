"use client";
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BarChart3, Lightbulb, RefreshCw } from 'lucide-react';
import { api, errorText } from '@/lib/api';
import type { TodayResponse } from '@/lib/contract';
import { Logo } from '@/components/ui';
import { ValueView } from '@/components/value-view';

export function WorkspaceOverview({ workspaceId }: { workspaceId: string }) {
  const [data, setData] = useState<TodayResponse | null>(null);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    api<TodayResponse>('/workspaces/' + encodeURIComponent(workspaceId) + '/today', { signal: abort.signal })
      .then(setData).catch((error: unknown) => { if (!abort.signal.aborted) setError(errorText(error)); });
    return () => abort.abort();
  }, [workspaceId, revision]);
  return <main id="main-content" className="auth-page min-h-dvh p-6 md:p-12"><div className="mx-auto max-w-5xl"><header className="flex items-center justify-between gap-4"><Logo /><Link className="btn btn-secondary" href="/app">Рабочие пространства</Link></header><h1 className="mt-12 text-3xl font-bold">Обзор рекламы</h1><p className="mt-3 text-muted">Данные вашего бизнеса из последнего аудита.</p>{error ? <section className="card mt-8 p-8"><p role="alert">{error}</p><button className="btn btn-primary mt-5" onClick={() => { setError(''); setRevision((v) => v + 1); }}><RefreshCw size={16} />Повторить</button></section> : !data ? <p className="mt-8 text-muted" role="status">Загружаем данные…</p> : <><div className="mt-8 grid gap-5 md:grid-cols-3"><section className="card p-6"><BarChart3 className="mb-4 text-brand" /><p className="text-sm text-muted">Расход за период аудита</p><div className="mt-3 text-3xl font-bold"><ValueView v={data.spent} /></div></section><section className="card p-6"><Lightbulb className="mb-4 text-brand" /><p className="text-sm text-muted">Расход с признаками неэффективности</p><div className="mt-3 text-3xl font-bold"><ValueView v={data.exposure.total} /></div></section><section className="card p-6"><p className="text-sm text-muted">Активные рекомендации</p><p className="mt-3 text-3xl font-bold">{data.counts.active}</p></section></div><section className="card mt-6 p-6"><h2 className="font-semibold">Статус данных</h2><p className="mt-3 text-muted">{data.last_audit_at ? 'Последний аудит: ' + new Date(data.last_audit_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) : 'Аудит ещё не проводился.'}</p><p className="mt-2 text-sm text-muted">{data.data_status === 'partial' ? 'Часть данных недоступна. Выводы могут быть неполными.' : 'Доступные данные обработаны.'}</p></section></>}</div></main>;
}

