"use client";

import { useState } from "react";
import { HistoryCycles } from "@/components/app/history";
import { PageHeader } from "@/components/ui";
import { SYSTEM_LOG } from "@/lib/demo";

export default function HistoryPage() {
  const [tab, setTab] = useState<"decisions" | "log">("decisions");
  return (
    <>
      <PageHeader title="История решений" sub="Проблема → рекомендация → ваше решение → изменение вручную → сверка с Директом → замер через 7 дней.">
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
        <HistoryCycles />
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
