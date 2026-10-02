"use client";

import { Check, CheckCheck, Clock, Hand, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import {
  BLOCKED_LABEL,
  REJECT_LABEL,
  REJECT_REASONS,
  resultLabel,
  STATUS_LABEL,
  type Recommendation,
  type RecStatus,
  type RejectReason,
  type UserAction,
} from "@/lib/contract";
import { formatDate } from "@/lib/value";
import { useDemo } from "./store";

const STATUS_STYLE: Record<RecStatus, string> = {
  new: "bg-info-bg text-info",
  requires_decision: "bg-warning-bg text-warning",
  accepted: "bg-brand-soft text-brand",
  applied: "bg-success-bg text-success",
  postponed: "bg-surface-2 text-muted",
  rejected: "bg-surface-2 text-muted",
};

/** Short badge text; «Применена» is never shown (API_CONTRACT §3.3). */
function badgeText(r: Pick<Recommendation, "status" | "execution">): string {
  if (r.status !== "applied") return STATUS_LABEL[r.status];
  const { execution_mode: mode, verification_status: vs } = r.execution;
  if (mode === "none") return "Проверено";
  if (vs === "confirmed") return "Выполнено · подтверждено";
  if (vs === "not_confirmed") return "Выполнено · не подтверждено";
  return "Выполнено вручную · сверка";
}

export function StatusBadge({ r }: { r: Pick<Recommendation, "status" | "execution"> }) {
  const tone = r.status === "applied" && r.execution.verification_status === "not_confirmed" ? "bg-warning-bg text-warning" : STATUS_STYLE[r.status];
  return <span className={`badge ${tone}`}>{badgeText(r)}</span>;
}

/** «Не буду» always asks why (closed list, §4.1): it is the pilot metric of rule quality. */
function RejectForm({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: (r: RejectReason, comment: string) => void }) {
  const [reason, setReason] = useState<RejectReason | null>(null);
  const [comment, setComment] = useState("");
  const needsComment = reason === "other" && !comment.trim();
  return (
    <fieldset className="w-full rounded-2xl border border-line bg-surface p-4">
      <legend className="px-1 text-sm font-semibold">Почему не будете выполнять?</legend>
      <div className="mt-1 flex flex-wrap gap-2">
        {REJECT_REASONS.map((r) => (
          <label key={r.code} className="chip cursor-pointer has-[:checked]:border-brand has-[:checked]:text-brand">
            <input type="radio" name="reject-reason" className="sr-only" checked={reason === r.code} onChange={() => setReason(r.code)} />
            {r.label}
          </label>
        ))}
      </div>
      <label className="mt-3 block text-sm">
        <span className="label">Комментарий {reason === "other" ? "(обязательно)" : "(по желанию)"}</span>
        <textarea
          value={comment}
          maxLength={500}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          className="mt-1 w-full rounded-xl border border-line bg-surface p-2 text-sm outline-none focus:border-brand"
        />
      </label>
      <div className="mt-3 flex gap-2">
        <button className="btn btn-primary btn-sm" disabled={!reason || needsComment} onClick={() => reason && onConfirm(reason, comment.trim())}>
          Сохранить решение
        </button>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </fieldset>
  );
}

const BUTTON: Record<Exclude<UserAction, "view" | "reject">, { label: string; icon: typeof Check; style: string }> = {
  accept: { label: "Принять к выполнению", icon: Check, style: "btn-primary" },
  mark_done_manually: { label: "Выполнено вручную", icon: Hand, style: "btn-secondary" },
  check: { label: "Проверил", icon: CheckCheck, style: "btn-primary" },
  postpone: { label: "Позже", icon: Clock, style: "btn-secondary" },
};

/**
 * Decision buttons, drawn only from `allowed_actions` (blocked ones show their reason). In v1.0 AdPilot never
 * changes the ad account: the user changes it by hand in Direct; AdPilot verifies it by reading Direct data
 * and measures the effect 7 days later.
 */
export function RecActions({ r, onDone, compact = false }: { r: Recommendation; onDone?: () => void; compact?: boolean }) {
  const { act, reset } = useDemo();
  const [rejecting, setRejecting] = useState(false);
  const sm = compact ? "btn-sm" : "";
  const run = (a: UserAction, payload?: Parameters<typeof act>[2]) => {
    act(r.id, a, payload);
    setRejecting(false);
    onDone?.();
  };

  if (rejecting) return <RejectForm onCancel={() => setRejecting(false)} onConfirm={(reason, comment) => run("reject", { reason, comment })} />;

  const resetLink = (
    <button className="inline-flex items-center gap-1 text-xs font-semibold text-muted underline-offset-2 hover:underline" onClick={() => reset(r.id)}>
      <RotateCcw size={12} /> Сбросить решение (демо)
    </button>
  );
  const allowed = r.allowed_actions.filter((a) => a !== "view");

  if (!allowed.length) {
    return (
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge r={r} />
          {r.decision?.reason && <span className="text-xs text-muted">Причина: {REJECT_LABEL[r.decision.reason]}</span>}
          {resetLink}
        </div>
        {r.status === "applied" && <p className="text-xs text-muted">{resultLabel(r)}.</p>}
        {r.decision?.comment && <p className="text-xs text-muted">«{r.decision.comment}»</p>}
        {r.blocked_actions.map((b) => (
          <p key={b.action} className="text-xs text-muted">
            {BLOCKED_LABEL[b.reason]}
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {r.status === "accepted" && <p className="text-xs text-muted">{resultLabel(r)}.</p>}
      {r.status === "postponed" && r.postponed_until && <p className="text-xs text-muted">Отложена до {formatDate(r.postponed_until)}. Решить можно и раньше.</p>}
      <div className="flex flex-wrap gap-2">
        {allowed.map((a) =>
          a === "reject" ? (
            <button key={a} className={`btn btn-ghost ${sm}`} onClick={() => setRejecting(true)}>
              <X size={16} /> Не буду
            </button>
          ) : (
            <button
              key={a}
              className={`btn ${BUTTON[a].style} ${sm}`}
              disabled={a === "postpone" && r.status === "postponed"}
              onClick={() => run(a, a === "postpone" ? { until: "2026-10-09" } : undefined)}
            >
              {(() => {
                const Icon = BUTTON[a].icon;
                return <Icon size={16} />;
              })()}
              {BUTTON[a].label}
            </button>
          ),
        )}
      </div>
      {r.status !== "accepted" && allowed.includes("mark_done_manually") && (
        <p className="text-xs text-muted">Уже внесли изменение в Директе сами? Отметьте «Выполнено вручную» — сверка будет менее надёжной.</p>
      )}
    </div>
  );
}
