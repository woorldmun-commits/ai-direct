'use client';
import {useEffect, useId, useRef, useState, type ReactNode} from 'react';

export function DetailTabs({tabs}: {tabs: {id: string; title: string; body: ReactNode}[]}) {
  const id = useId(), refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [active, setActive] = useState(0);
  const track = useRef<HTMLDivElement>(null), indicator = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const update = () => { const button = refs.current[active], bar = indicator.current; if (button && bar) { bar.style.width = `${button.offsetWidth}px`; bar.style.transform = `translateX(${button.offsetLeft}px)`; } };
    update();
    const observer = new ResizeObserver(update);
    if (track.current) observer.observe(track.current);
    refs.current.forEach(button => { if (button) observer.observe(button); });
    return () => observer.disconnect();
  }, [active]);
  return <><div ref={track} className="ix-detail-tabs" role="tablist" aria-label="Разделы рекомендации"><span ref={indicator} className="ix-tab-indicator" aria-hidden="true" />{tabs.map((t, i) => <button key={t.id} ref={n => { refs.current[i] = n; }} id={`${id}-tab-${t.id}`} aria-controls={`${id}-panel-${t.id}`} role="tab" aria-selected={active === i} tabIndex={active === i ? 0 : -1} type="button" onClick={() => setActive(i)} onKeyDown={e => {
    const next = e.key === 'ArrowRight' ? (i + 1) % tabs.length : e.key === 'ArrowLeft' ? (i + tabs.length - 1) % tabs.length : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
    if (next !== null) { e.preventDefault(); setActive(next); refs.current[next]?.focus(); }
  }}>{t.title}</button>)}</div>{tabs.map((t, i) => <div key={t.id} className="ix-detail-panel" role="tabpanel" id={`${id}-panel-${t.id}`} aria-labelledby={`${id}-tab-${t.id}`} hidden={active !== i} tabIndex={0}>{t.body}</div>)}</>;
}
