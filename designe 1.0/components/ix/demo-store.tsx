'use client';
import {createContext, useContext, useMemo, useState, type ReactNode} from 'react';

/** Состояние демо живёт только в памяти вкладки (как в эталоне): ничего не отправляется на сервер и не меняет рекламу. */
export type DemoRec = {decision?: 'approved' | 'postponed' | 'rejected'; manual?: boolean; verify?: boolean};
export type DemoEvent = {id: number; text: string; tag: string};
type Store = {recs: Record<number, DemoRec>; events: DemoEvent[]; decide: (i: number, title: string, d: NonNullable<DemoRec['decision']>) => void; markManual: (i: number, title: string) => string | null; verify: (i: number, title: string) => string | null};

const Ctx = createContext<Store | null>(null);
export const useDemo = () => { const v = useContext(Ctx); if (!v) throw new Error('DemoProvider отсутствует'); return v; };

export const DEMO_LABEL: Record<NonNullable<DemoRec['decision']>, string> = {approved: 'Одобрено', postponed: 'Отложено', rejected: 'Отклонено'};
/** Отдельные оси статусов: решение ≠ выполнение ≠ проверка. Подпись показывает самую позднюю стадию. */
export const demoLabel = (r?: DemoRec) => !r ? undefined : r.verify ? 'Ожидает сверки' : r.manual ? 'Выполнено вручную' : r.decision ? DEMO_LABEL[r.decision] : undefined;

export function DemoProvider({children}: {children: ReactNode}) {
  const [recs, setRecs] = useState<Record<number, DemoRec>>({});
  const [events, setEvents] = useState<DemoEvent[]>([]);
  const value = useMemo<Store>(() => {
    const log = (text: string, tag: string) => setEvents(e => [{id: e.length + 1, text, tag}, ...e]);
    return {
      recs, events,
      decide(i, title, d) { setRecs(r => ({...r, [i]: {...r[i], decision: d}})); log(`${DEMO_LABEL[d]}: ${title}`, 'Демо'); },
      markManual(i, title) {
        if (recs[i]?.decision !== 'approved') return 'Сначала одобрите решение: одобрение и ручное выполнение — разные шаги.';
        setRecs(r => ({...r, [i]: {...r[i], manual: true}})); log(`Отмечено ручное выполнение: ${title}`, 'Демо'); return null;
      },
      verify(i, title) {
        if (!recs[i]?.manual) return 'Проверка результата доступна после отметки ручного выполнения.';
        setRecs(r => ({...r, [i]: {...r[i], verify: true}})); log(`Запрошена сверка результата: ${title}`, 'Демо'); return null;
      },
    };
  }, [recs, events]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
