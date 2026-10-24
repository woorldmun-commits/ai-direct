'use client';
import {useId, useRef, type ReactNode} from 'react';
import {X} from 'lucide-react';
import {useDialog} from './use-dialog';

/** Правая панель: паспорт решения. Esc, клик по фону, фокус-ловушка и возврат фокуса; на телефоне — во весь экран. */
export function Drawer({title, eyebrow = 'INROU / Паспорт решения', onClose, children}: {title: string; eyebrow?: string; onClose: () => void; children: ReactNode}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useDialog(true, ref, onClose);
  return <div className="ix-drawer" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div ref={ref} className="ix-drawerbox" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="ix-drawerhead"><span className="ix-eyebrow">{eyebrow}</span><button type="button" className="ix-pill" onClick={onClose} aria-label="Закрыть"><X size={16} aria-hidden /></button></div>
      <h1 id={titleId}>{title}</h1>
      {children}
    </div>
  </div>;
}
