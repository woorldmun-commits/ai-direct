"use client";

import { useState } from "react";
import { StateBox } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { objectLabel, REJECT_LABEL, type Recommendation } from "@/lib/contract";
import { formatDate, formatMoment } from "@/lib/value";
import { StatusBadge } from "./rec-actions";
import { ActionText, MeasurementView, SAVED_NOTE } from "./rec-parts";
import { useDemo } from "./store";

/**
 * «История решений» (PRODUCT_SPEC §4.4): one card per recommendation cycle — found → recommended → your decision
 * → verification by Direct data → 7-day check. Built only from the append-only events; nothing is recomputed.
 */
export type Outcome = "confirmed" | "not_confirmed" | "awaiting" | "rejected" | "in_progress";

export function outcomeOf(r: Recommendation): Outcome {
  const vs = r.execution.verification_status;
  const m = r.measurement;
  if (r.status === "rejected") return "rejected";
  if (vs === "not_confirmed") return "not_confirmed";
  if (r.status === "applied" && (vs === "pending" || m?.status === "pending")) return "awaiting";
  if (m?.status === "measured") return vs === "confirmed" && m.verdict === "effect" ? "confirmed" : "not_confirmed";
  return "in_progress";
}

const FILTERS: { key: Outcome | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "confirmed", label: "Результат подтверждён" },
  { key: "not_confirmed", label: "Не подтверждён" },
  { key: "awaiting", label: "Ждёт замера" },
  { key: "rejected", label: "Отклонено" },
];

const day = (iso: string) => formatMoment(iso).slice(0, 5);
const USER_STEP: Record<string, string> = {
  accepted: "приняли к выполнению",
  manual_claimed: "отметили «выполнено вручную»",
  recommendation_checked: "проверили",
  postponed: "отложили",
  rejected: "отклонили",
};

function CycleCard({ r }: { r: Recommendation }) {
  const steps = r.history.filter((h) => h.actor !== "system" && USER_STEP[h.event]);
  const verification = r.history.find((h) => h.event.startsWith("verification_"));
  const vs = r.execution.verification_status;
  return (
    <article className="card anim-fade p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          {formatDate(r.created_at.slice(0, 10))} · AdPilot нашёл: <b className="text-text">{r.title}</b>{" "}
          <span className="font-mono text-xs">({r.evidence.rule_version})</span>
        </p>
        <StatusBadge r={r} />
      </div>
      <p className="mt-1 text-xs text-muted">{objectLabel(r.object)}</p>
      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-[150px_1fr]">
        <dt className="text-muted">Рекомендация</dt>
        <dd className="font-semibold">
          <ActionText r={r} /> · <ValueView v={r.exposure} className="text-danger" />
        </dd>
        <dt className="text-muted">Вы</dt>
        <dd>
          {steps.length ? steps.map((s) => `${USER_STEP[s.event]} ${day(s.at)}`).join(" · ") : "решение ещё не принято"}
          {r.decision?.reason && (
            <span className="block text-muted">
              Причина: {REJECT_LABEL[r.decision.reason]}
              {r.decision.comment && ` — «${r.decision.comment}»`}
            </span>
          )}
        </dd>
        {r.execution.execution_mode === "manual" && (
          <>
            <dt className="text-muted">Сверка</dt>
            <dd>
              {vs === "confirmed" && `Изменение подтверждено по данным Директа${verification ? ` ${day(verification.at)}` : ""}`}
              {vs === "not_confirmed" && `Выполнение не подтверждено: изменения в Директе не найдено${verification ? ` (${day(verification.at)})` : ""}`}
              {vs === "pending" && "Ждём следующей синхронизации Директа"}
              {r.execution.before_state?.reliability === "reduced" && (
                <span className="block text-xs text-muted">Исходное состояние зафиксировано в момент отметки — сверка менее надёжна</span>
              )}
            </dd>
          </>
        )}
        {r.measurement && (
          <>
            <dt className="text-muted">Проверка через 7 дней</dt>
            <dd>
              <MeasurementView m={r.measurement} />
            </dd>
          </>
        )}
      </dl>
    </article>
  );
}

export function HistoryCycles() {
  const { all } = useDemo();
  const [filter, setFilter] = useState<Outcome | "all">("all");
  const cycles = all
    .filter((r) => r.history.some((h) => h.actor !== "system" && USER_STEP[h.event]))
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const shown = filter === "all" ? cycles : cycles.filter((r) => outcomeOf(r) === filter);

  return (
    <>
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Результат">
        {FILTERS.map((f) => (
          <button key={f.key} className="chip shrink-0" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label} ({f.key === "all" ? cycles.length : cycles.filter((r) => outcomeOf(r) === f.key).length})
          </button>
        ))}
      </div>
      {shown.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {shown.map((r) => (
            <CycleCard key={r.id} r={r} />
          ))}
        </div>
      ) : (
        <StateBox kind="empty" title="Таких решений пока нет" text="Карточка появляется, когда вы принимаете решение по рекомендации." />
      )}
      <p className="mt-4 text-xs text-muted">«Сэкономлено ≈» — только по подтверждённым выполнениям. {SAVED_NOTE}.</p>
    </>
  );
}
