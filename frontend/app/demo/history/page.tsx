"use client";

import { AlertTriangle, Hand, Lightbulb, Ruler, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { useDemo } from "@/components/app/store";
import { Approx, PageHeader } from "@/components/ui";
import { HISTORY, SYSTEM_LOG, type HistoryKind } from "@/lib/demo";
import { rub } from "@/lib/site";

const KIND: Record<HistoryKind, { icon: LucideIcon; tone: string; label: string }> = {
  found: { icon: AlertTriangle, tone: "bg-danger-bg text-danger", label: "Проблема" },
  rec: { icon: Lightbulb, tone: "bg-info-bg text-info", label: "Рекомендация" },
  action: { icon: Hand, tone: "bg-brand-soft text-brand", label: "Ваше решение" },
  measure: { icon: Ruler, tone: "bg-success-bg text-success", label: "Замер · сэкономлено" },
};

export default function HistoryPage() {
  const { actions } = useDemo();
  const [tab, setTab] = useState<"decisions" | "log">("decisions");
  const events = [
    ...actions.map((a) => ({ date: `Сегодня, ${a.at}`, kind: "action" as const, title: a.title, detail: "Отмечено в демо", amount: undefined })),
    ...HISTORY,
  ];

  return (
    <>
      <PageHeader title="История решений" sub="Проблема → рекомендация → ваше действие → замер → сэкономлено ≈.">
        <div role="group" aria-label="Раздел истории" className="flex gap-2">
          <button className="chip" aria-pressed={tab === "decisions"} onClick={() => setTab("decisions")}>
            Решения
          </button>
          <button className="chip" aria-pressed={tab === "log"} onClick={() => setTab("log")}>
            Журнал системы
          </button>
        </div>
      </PageHeader>

      {tab === "decisions" ? (
        <ol className="card relative p-5 md:p-6">
          <span aria-hidden className="absolute top-10 bottom-10 left-[37px] w-px bg-line md:left-[41px]" />
          {events.map((e, i) => {
            const k = KIND[e.kind];
            return (
              <li key={i} className="anim-fade relative flex gap-4 py-3">
                <span className={`relative z-10 grid size-9 shrink-0 place-items-center rounded-full ring-4 ring-[var(--surface)] ${k.tone}`}>
                  <k.icon size={16} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-muted">
                    {e.date} · {k.label}
                  </p>
                  <p className="font-semibold">{e.title}</p>
                  <p className="text-sm text-muted">{e.detail}</p>
                </div>
                {e.amount !== undefined && (
                  <Approx className={`whitespace-nowrap ${e.kind === "measure" ? "text-success" : "text-danger"}`}>{rub(e.amount)}</Approx>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <ul className="card divide-y divide-line font-mono text-sm">
          {SYSTEM_LOG.map((l) => (
            <li key={l.date + l.text} className="flex gap-4 px-5 py-3">
              <span className="shrink-0 text-muted">{l.date}</span>
              <span>{l.text}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
