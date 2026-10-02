"use client";

import { Bot, Check, ChevronDown, Database, X } from "lucide-react";
import { useEffect } from "react";
import { Approx, PriorityBadge } from "@/components/ui";
import { PERIOD, SYNC } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_NOTE, rub } from "@/lib/site";
import { RecActions } from "./rec-actions";
import { useDemo } from "./store";

export function WhyDrawer() {
  const { problems, whyId, closeWhy } = useDemo();
  const p = problems.find((x) => x.id === whyId);

  useEffect(() => {
    if (!p) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeWhy();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [p, closeWhy]);

  if (!p) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-black/25" onClick={closeWhy}>
      <aside
        role="dialog"
        aria-modal
        aria-labelledby="why-title"
        onClick={(e) => e.stopPropagation()}
        className="glass anim-slide absolute inset-0 overflow-y-auto p-5 md:inset-y-3 md:right-3 md:left-auto md:w-[460px] md:rounded-3xl md:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <PriorityBadge priority={p.priority} />
            <h2 id="why-title" className="mt-3 text-xl leading-snug font-bold">
              Почему AdPilot так решил
            </h2>
            <p className="mt-1 font-semibold">{p.recommendation}</p>
            <p className="text-sm text-muted">{p.campaign}</p>
          </div>
          <button className="btn btn-ghost size-10 shrink-0 p-0" aria-label="Закрыть" onClick={closeWhy} autoFocus>
            <X size={20} />
          </button>
        </div>

        <div className="mt-5 rounded-2xl bg-surface p-4">
          <p className="label">{EXPOSURE} за период</p>
          <Approx className="text-[28px] text-danger">{rub(p.loss)}</Approx>
          <p className="mt-1 text-xs text-muted">{EXPOSURE_NOTE}</p>
        </div>

        <section className="mt-5">
          <h3 className="text-sm font-semibold">Факты</h3>
          <dl className="mt-2 grid grid-cols-3 gap-2">
            {p.facts.map((f) => (
              <div key={f.label} className="rounded-xl bg-surface p-3">
                <dt className="label">{f.label}</dt>
                <dd className="money mt-1">{f.value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-muted">Период: {PERIOD}</p>
        </section>

        <section className="mt-5">
          <h3 className="text-sm font-semibold">Расчёт</h3>
          <p className="mt-2 rounded-xl bg-surface p-3 font-mono text-sm">{p.calc}</p>
        </section>

        <section className="mt-5">
          <h3 className="text-sm font-semibold">Данных достаточно</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {p.checks.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <Check size={15} className="shrink-0 text-success" /> {c}
              </li>
            ))}
            <li className="flex items-center gap-2">
              <Check size={15} className="shrink-0 text-success" /> Качество данных: {p.quality}
            </li>
          </ul>
        </section>

        <section className="mt-5 rounded-2xl border border-line bg-surface p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Bot size={16} className="text-brand" /> Объяснение AI
          </h3>
          <p className="mt-2 text-sm">{p.ai}</p>
          <p className="mt-2 text-xs text-muted">Пояснение сгенерировано AI по цифрам выше и не добавляет новых. Проверьте его, прежде чем вносить изменение в Директе.</p>
        </section>

        <p className="mt-5 flex items-center gap-2 text-xs text-muted">
          <Database size={14} /> Источник: Яндекс Директ{p.id === "cpa" ? " + Яндекс Метрика" : ""} · {SYNC.date}, {SYNC.direct}
        </p>

        <details className="group mt-4 rounded-xl border border-line px-4">
          <summary className="flex cursor-pointer list-none items-center justify-between py-3 text-sm font-semibold">
            Технические детали
            <ChevronDown size={16} className="text-muted transition-transform group-open:rotate-180" />
          </summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 pb-3 font-mono text-xs">
            <dt className="text-muted">rule_version</dt>
            <dd>{p.rule}</dd>
            <dt className="text-muted">snapshot</dt>
            <dd>#4815 · {SYNC.date}</dd>
            <dt className="text-muted">code_version</dt>
            <dd>3.2.0</dd>
            <dt className="text-muted">evidence</dt>
            <dd>ev_{p.id}_0930</dd>
          </dl>
        </details>

        <div className="mt-6">
          <RecActions id={p.id} status={p.status} onDone={closeWhy} />
        </div>
      </aside>
    </div>
  );
}
