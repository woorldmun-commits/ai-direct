'use client';
import {Info, X} from 'lucide-react';

export function StatusToast({title, message, onDismiss}: {title: string; message: string; onDismiss: () => void}) {
  return <div className="ix-status-toast" role="status" aria-atomic="true">
    <Info size={21} aria-hidden/><div><strong>{title}</strong><p>{message}</p></div><button type="button" onClick={onDismiss} aria-label="Закрыть уведомление"><X size={18} aria-hidden/></button>
  </div>;
}
