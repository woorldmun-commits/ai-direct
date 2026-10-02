"use client";

import { useState } from "react";
import { LossesList, MetricCard } from "@/components/app/problem";
import { useDemo } from "@/components/app/store";
import { PageHeader, StateBox } from "@/components/ui";
import { PERIOD, RECOVERABLE, SAVED, type Priority } from "@/lib/demo";
import { rub } from "@/lib/site";

const FILTERS: { key: Priority | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "critical", label: "Критичные" },
  { key: "medium", label: "Средние" },
  { key: "low", label: "Низкие" },
];

export default function Losses() {
  const { problems } = useDemo();
  const [filter, setFilter] = useState<Priority | "all">("all");
  const shown = filter === "all" ? problems : problems.filter((p) => p.priority === filter);
  const total = problems.reduce((s, p) => s + p.loss, 0);

  return (
    <>
      <PageHeader title="Где теряются деньги" sub={`${problems.length} проблемы за ${PERIOD}. Сортировка — по сумме потерь.`} />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="Потеряно" value={rub(total)} approx tone="text-danger" />
        <MetricCard label="Можно вернуть" value={rub(RECOVERABLE)} approx tone="text-warning" note="по рекомендациям с высокой уверенностью" />
        <MetricCard label="Сэкономлено" value={rub(SAVED)} approx tone="text-success" note="расчётная оценка, сентябрь" />
      </div>

      <div className="mt-6 mb-4 flex flex-wrap gap-2" role="group" aria-label="Фильтр по приоритету">
        {FILTERS.map((f) => {
          const n = f.key === "all" ? problems.length : problems.filter((p) => p.priority === f.key).length;
          return (
            <button key={f.key} className="chip" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
              {f.label} ({n})
            </button>
          );
        })}
      </div>

      {shown.length ? (
        <LossesList key={filter} problems={shown} />
      ) : (
        <StateBox kind="empty" title="Проблем с таким приоритетом нет" text="Выберите другой фильтр." />
      )}
    </>
  );
}
