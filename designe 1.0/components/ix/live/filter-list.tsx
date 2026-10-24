'use client';
import {useRouter} from 'next/navigation';
import {useRef, type ReactNode} from 'react';
import {Drawer} from '../drawer';
import {useIxSearch} from '../shell';

/** Список, который фильтруется строкой поиска из верхней панели. `text` — то, по чему ищем. */
export function FilterList({items, empty = 'По запросу ничего не найдено.'}: {items: {key: string; text: string; node: ReactNode}[]; empty?: string}) {
  const q = useIxSearch();
  const shown = items.filter(i => !q || i.text.toLowerCase().includes(q));
  return shown.length ? <>{shown.map(i => <div key={i.key}>{i.node}</div>)}</> : <p className="ix-muted">{empty}</p>;
}

/** Паспорт рекомендации в правой панели; закрытие возвращает на список с сохранением пространства. */
export function PassportDrawer({title, closeHref, children}: {title: string; closeHref: string; children: ReactNode}) {
  const router = useRouter();
  const done = useRef(false);
  const close = () => { if (done.current) return; done.current = true; router.replace(closeHref, {scroll: false}); };
  return <Drawer title={title} onClose={close}>{children}</Drawer>;
}
