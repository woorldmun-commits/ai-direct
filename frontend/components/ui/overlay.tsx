"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** Native <dialog>: focus trap, Esc and backdrop come from the platform. */
function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const onCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    d.addEventListener("cancel", onCancel);
    return () => d.removeEventListener("cancel", onCancel);
  }, [onClose]);
  return ref;
}

export function Modal({ open, onClose, title, children, footer, width = 520 }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; width?: number }) {
  const ref = useDialog(open, onClose);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      className="m-auto w-[calc(100%-32px)] rounded-[20px] border border-line bg-surface p-0 text-text shadow-[0_24px_64px_rgba(15,23,42,0.24)] open:anim-pop"
      style={{ maxWidth: width }}
    >
      {open && (
        <div className="flex max-h-[85dvh] flex-col">
          <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
            <h2 className="text-[17px] font-semibold">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Закрыть" className="btn btn-ghost -mt-1 -mr-2 size-8 p-0">
              <X size={18} />
            </button>
          </div>
          <div className="overflow-y-auto px-6 pb-5">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-bg px-6 py-4">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

export function Drawer({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  const ref = useDialog(open, onClose);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      className="mt-0 mr-0 mb-0 ml-auto h-dvh max-h-dvh w-full max-w-[560px] border-l border-line bg-surface p-0 text-text open:anim-slide"
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
            <h2 className="text-[16px] font-semibold">{title}</h2>
            <button type="button" onClick={onClose} aria-label="Закрыть" className="btn btn-ghost -mr-2 size-8 p-0">
              <X size={18} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="flex flex-wrap gap-2 border-t border-line px-6 py-4">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/** Click-to-open panel anchored to its trigger; closes on outside click and Esc. */
export function Popover({ trigger, children, align = "right", width = 300, label }: { trigger: (p: { open: boolean; toggle: () => void }) => ReactNode; children: ReactNode | ((close: () => void) => ReactNode); align?: "left" | "right"; width?: number; label: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const close = () => setOpen(false);
  return (
    <div ref={box} className="relative">
      {trigger({ open, toggle: () => setOpen(!open) })}
      {open && (
        <div role="dialog" aria-label={label} className={`glass anim-fade absolute z-50 mt-2 ${align === "right" ? "right-0" : "left-0"}`} style={{ width: `min(${width}px, calc(100vw - 32px))` }}>
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}
