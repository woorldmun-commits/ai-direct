"use client";

import { Check, Clock, Hand, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { REJECT_REASONS, STATUS_LABEL, type RecStatus, type RejectReason } from "@/lib/demo";
import { useDemo } from "./store";

const STATUS_STYLE: Record<RecStatus, string> = {
  new: "bg-info-bg text-info",
  viewed: "bg-surface-2 text-text",
  accepted: "bg-warning-bg text-warning",
  applied: "bg-brand-soft text-brand",
  measured: "bg-success-bg text-success",
  postponed: "bg-surface-2 text-muted",
  rejected: "bg-surface-2 text-muted",
};

export function StatusBadge({ status }: { status: RecStatus }) {
  return <span className={`badge ${STATUS_STYLE[status]}`}>{STATUS_LABEL[status]}</span>;
}

/** "Не буду" always asks why: the reason is a pilot metric (false positives, missing context). */
function RejectForm({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: (r: RejectReason) => void }) {
  const [reason, setReason] = useState<RejectReason | null>(null);
  return (
    <fieldset className="w-full rounded-2xl border border-line bg-surface p-4">
      <legend className="px-1 text-sm font-semibold">Почему не будете выполнять?</legend>
      <div className="mt-1 flex flex-wrap gap-2">
        {REJECT_REASONS.map((r) => (
          <label key={r} className="chip cursor-pointer has-[:checked]:border-brand has-[:checked]:text-brand">
            <input type="radio" name="reject-reason" className="sr-only" checked={reason === r} onChange={() => setReason(r)} />
            {r}
          </label>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button className="btn btn-primary btn-sm" disabled={!reason} onClick={() => reason && onConfirm(reason)}>
          Сохранить решение
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </fieldset>
  );
}

/**
 * Human decision buttons. In v1.0 AdPilot never changes the ad account: the user makes the change
 * by hand in Yandex Direct, AdPilot verifies it against Direct data and later measures the effect.
 */
export function RecActions({ id, status, onDone, compact = false }: { id: string; status: RecStatus; onDone?: () => void; compact?: boolean }) {
  const { setStatus, problems } = useDemo();
  const [rejecting, setRejecting] = useState(false);
  const set = (s: RecStatus, reason?: RejectReason) => {
    setStatus(id, s, reason);
    setRejecting(false);
    onDone?.();
  };
  const sm = compact ? "btn-sm" : "";
  const reset = (
    <button className="inline-flex items-center gap-1 text-xs font-semibold text-muted underline-offset-2 hover:underline" onClick={() => setStatus(id, "new")}>
      <RotateCcw size={12} /> Вернуть в новые
    </button>
  );

  if (rejecting) return <RejectForm onCancel={() => setRejecting(false)} onConfirm={(r) => set("rejected", r)} />;

  if (status === "rejected" || status === "measured") {
    const reason = problems.find((p) => p.id === id)?.rejectReason;
    return (
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge status={status} />
        {reason && <span className="text-xs text-muted">Причина: {reason}</span>}
        {reset}
      </div>
    );
  }

  if (status === "applied") {
    return (
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={status} />
          {reset}
        </div>
        <p className="text-xs text-muted">Сверяем по данным Директа в следующем снимке. Эффект измерим через 7 дней после сверки.</p>
      </div>
    );
  }

  const reject = (
    <button className={`btn btn-ghost ${sm}`} onClick={() => setRejecting(true)}>
      <X size={16} /> Не буду
    </button>
  );

  if (status === "accepted") {
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted">Внесите изменение в Яндекс Директе вручную, затем отметьте здесь.</p>
        <div className="flex flex-wrap gap-2">
          <button className={`btn btn-primary ${sm}`} onClick={() => set("applied")}>
            <Hand size={16} /> Выполнено вручную
          </button>
          {reject}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <button className={`btn btn-primary ${sm}`} onClick={() => set("accepted")}>
        <Check size={16} /> Принять к выполнению
      </button>
      <button className={`btn btn-secondary ${sm}`} onClick={() => set("postponed")} disabled={status === "postponed"}>
        <Clock size={16} /> Отложить
      </button>
      {reject}
    </div>
  );
}
