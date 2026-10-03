"use client";

import { ChevronDown, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { ValueView } from "@/components/value-view";
import { ACTION_LEVEL_LABEL, objectLabel, REJECT_LABEL, resultLabel } from "@/lib/contract";
import { CALCULATION_LABEL, formatPeriod, sourceLabel } from "@/lib/value";
import { EXPOSURE, EXPOSURE_NOTE } from "@/lib/site";
import { RecActions, StatusBadge } from "./rec-actions";
import { ActionText, FACT_LABEL, HeldNote, LIMITATION_LABEL, MeasurementView, Origin, OverlapNote, POLICY_REASON_LABEL } from "./rec-parts";
import { useDemo } from "./store";

/** One block of the fixed order Что → Почему → Что сделать → Решение → Проверка (PRODUCT_SPEC §4.3). */
function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="relative mt-5 pl-9" aria-label={title}>
      <span aria-hidden className="absolute top-0 left-0 grid size-6 place-items-center rounded-full bg-brand-soft text-xs font-bold text-brand">
        {n}
      </span>
      <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

/** Passport «Почему AdPilot так решил». Works without an LLM: the text is a template over the finding's facts. */
export function WhyDrawer() {
  const { get, whyId, closeWhy } = useDemo();
  const r = whyId ? get(whyId) : undefined;

  useEffect(() => {
    if (!r) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeWhy();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [r, closeWhy]);

  if (!r) return null;
  const facts = Object.entries(r.evidence.facts);
  const lowered = r.safety.candidate_level !== r.action_level;

  return (
    <div className="fixed inset-0 z-[60] bg-black/25" onClick={closeWhy}>
      <aside
        role="dialog"
        aria-modal
        aria-labelledby="why-title"
        onClick={(e) => e.stopPropagation()}
        className="glass anim-slide absolute inset-0 overflow-y-auto p-5 md:inset-y-3 md:right-3 md:left-auto md:w-[500px] md:rounded-3xl md:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge r={r} />
            <span className="badge bg-surface-2 text-text">{ACTION_LEVEL_LABEL[r.action_level]}</span>
          </div>
          <button className="btn btn-ghost size-10 shrink-0 p-0" aria-label="Закрыть" onClick={closeWhy} autoFocus>
            <X size={20} />
          </button>
        </div>
        <p id="why-title" className="mt-3 text-xs text-muted">
          Почему AdPilot так решил
        </p>

        <Step n={1} title="Что">
          <h2 className="text-xl leading-snug font-bold">
            {r.title}
          </h2>
          <p className="text-sm text-muted">
            {objectLabel(r.object)} · кабинет {r.ad_account.login}
          </p>
          <div className="mt-3 rounded-2xl bg-surface p-4">
            <p className="label">{EXPOSURE}</p>
            <ValueView v={r.exposure} caption className="text-[28px] text-danger" />
            <p className="mt-1 text-xs text-muted">{EXPOSURE_NOTE}</p>
            <OverlapNote r={r} className="mt-1 block text-xs font-semibold text-muted" />
            <HeldNote r={r} className="mt-1 block text-xs font-semibold text-muted" />
          </div>
        </Step>

        <Step n={2} title="Почему">
          <p className="text-sm">{r.explanation.text}</p>
          <p className="mt-1 text-xs text-muted">
            {r.explanation.source === "llm" ? "Текст написал AI только по фактам ниже — новых чисел он не добавляет." : "Шаблонный текст по фактам ниже."}
          </p>
          <ul className="mt-3 space-y-2">
            {facts.map(([k, v]) => (
              <li key={k} className="rounded-xl bg-surface p-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="label">{FACT_LABEL[k] ?? k}</span>
                  <ValueView v={v} className="text-base" />
                </div>
                <Origin r={r} v={v} />
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">
            Источник: {sourceLabel(r.exposure.source)} · {formatPeriod(r.exposure.period)} · {CALCULATION_LABEL[r.exposure.calculation_type].toLowerCase()}
          </p>
        </Step>

        <Step n={3} title="Что сделать">
          <p className="text-lg font-bold">
            <ActionText r={r} />
          </p>
          <p className="text-sm text-muted">
            {r.action_level === "inspect_only"
              ? "Только проверка: настройки кампании по этой рекомендации не меняются."
              : "Вручную в Яндекс Директе — AdPilot в v1.0 не меняет кабинет."}
          </p>
          <div className="mt-3 rounded-xl bg-surface p-3">
            <p className="label">Можно сэкономить</p>
            <ValueView v={r.can_save} caption className="text-lg text-warning" />
          </div>
          {(lowered || r.limitations.length > 0) && (
            <ul className="mt-2 space-y-1 text-xs text-muted">
              {lowered && (
                <li>
                  Уровень снижен политикой безопасности до «{ACTION_LEVEL_LABEL[r.action_level]}»:{" "}
                  {r.safety.policy_reasons.map((p) => POLICY_REASON_LABEL[p] ?? p).join(", ")}.
                </li>
              )}
              {r.limitations.map((l) => (
                <li key={l}>Ограничение: {LIMITATION_LABEL[l] ?? l}.</li>
              ))}
            </ul>
          )}
        </Step>

        <Step n={4} title="Решение">
          <RecActions r={r} />
        </Step>

        <Step n={5} title="Проверка">
          {r.measurement ? (
            <MeasurementView m={r.measurement} />
          ) : r.status === "rejected" ? (
            <p className="text-sm text-muted">
              Замера не будет: рекомендация отклонена{r.decision?.reason ? ` (${REJECT_LABEL[r.decision.reason].toLowerCase()})` : ""}.
            </p>
          ) : (
            <p className="text-sm">Через 7 дней после выполнения AdPilot сравнит 7 дней до и после — без контрольной группы.</p>
          )}
          {r.status === "applied" && <p className="mt-2 text-xs text-muted">{resultLabel(r)}.</p>}
          {r.execution.before_state?.reliability === "reduced" && (
            <p className="mt-1 text-xs text-muted">Исходное состояние зафиксировано в момент отметки — сверка менее надёжна.</p>
          )}
        </Step>

        <details className="group mt-6 rounded-xl border border-line px-4">
          <summary className="flex cursor-pointer list-none items-center justify-between py-3 text-sm font-semibold">
            Технические детали
            <ChevronDown size={16} className="text-muted transition-transform group-open:rotate-180" />
          </summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 pb-3 font-mono text-xs">
            <dt className="text-muted">rule_version</dt>
            <dd>{r.evidence.rule_version}</dd>
            <dt className="text-muted">safety_policy</dt>
            <dd>{r.safety.safety_policy}</dd>
            <dt className="text-muted">version_id</dt>
            <dd>{r.version_id}</dd>
            <dt className="text-muted">explanation</dt>
            <dd>{r.explanation.source}</dd>
          </dl>
        </details>
      </aside>
    </div>
  );
}
