"use client";

import { AlertOctagon, CheckCircle2, ChevronDown, CircleSlash, Inbox, Loader2, RefreshCw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { dateTime } from "@/lib/formatters";

export function EmptyState({ icon = <Inbox size={22} />, title, text, action, compact = false }: { icon?: ReactNode; title: string; text?: ReactNode; action?: ReactNode; compact?: boolean }) {
  return (
    <div className={`flex flex-col items-center text-center ${compact ? "py-8" : "py-14"}`}>
      <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">{icon}</span>
      <p className="mt-4 text-[15px] font-semibold">{title}</p>
      {text && <p className="mt-1 max-w-[46ch] text-[13px] text-muted">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Instead of an empty chart: say there is not enough data and why. */
export function NoData({ title = "Недостаточно данных для расчёта.", why, action, className = "" }: { title?: string; why: ReactNode; action?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-xl border border-dashed border-[#d0d5dd] bg-bg px-4 py-3.5 ${className}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <CircleSlash size={16} className="shrink-0 text-subtle" aria-hidden />
        <p className="text-[13px] font-medium">{title}</p>
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="inline-flex items-center gap-0.5 text-[13px] font-medium text-brand hover:underline">
          Почему? <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      </div>
      {open && (
        <div className="anim-fade mt-2 pl-7 text-[13px] text-muted">
          {why}
          {action && <div className="mt-3">{action}</div>}
        </div>
      )}
    </div>
  );
}

export function ErrorState({ title, integration, at, reference, onRetry }: { title: string; integration: string; at: string; reference: string; onRetry?: () => void }) {
  const [retrying, setRetrying] = useState(false);
  return (
    <div role="alert" className="rounded-xl border border-[#fecdca] bg-danger-soft px-4 py-3.5">
      <div className="flex items-start gap-3">
        <AlertOctagon size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold text-danger-ink">{title}</p>
          <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] text-[#912018]">
            <div>
              <dt className="inline">Интеграция: </dt>
              <dd className="inline">{integration}</dd>
            </div>
            <div>
              <dt className="inline">Время: </dt>
              <dd className="inline">{dateTime(at)}</dd>
            </div>
            <div>
              <dt className="inline">Код обращения: </dt>
              <dd className="inline font-mono">{reference}</dd>
            </div>
          </dl>
        </div>
        {onRetry && (
          <button
            type="button"
            className="btn btn-danger btn-sm shrink-0"
            disabled={retrying}
            onClick={() => {
              setRetrying(true);
              setTimeout(() => {
                setRetrying(false);
                onRetry();
              }, 900);
            }}
          >
            <RefreshCw size={14} className={retrying ? "animate-spin" : ""} /> Повторить
          </button>
        )}
      </div>
    </div>
  );
}

export function SuccessState({ title, text }: { title: string; text?: ReactNode }) {
  return (
    <div role="status" className="flex items-start gap-3 rounded-xl border border-[#abefc6] bg-success-soft px-4 py-3.5">
      <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-success" aria-hidden />
      <div>
        <p className="text-[13px] font-semibold text-success-ink">{title}</p>
        {text && <p className="mt-0.5 text-[12px] text-[#05603a]">{text}</p>}
      </div>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`skeleton block ${className}`} aria-hidden />;
}

export function Spinner({ label = "Загрузка" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-[13px] text-muted">
      <Loader2 size={16} className="animate-spin text-brand" aria-hidden /> {label}
    </span>
  );
}
