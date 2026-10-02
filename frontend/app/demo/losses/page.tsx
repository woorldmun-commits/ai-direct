"use client";

import { useState } from "react";
import { LossesList, MetricCard } from "@/components/app/problem";
import { useDemo } from "@/components/app/store";
import { PageHeader, StateBox } from "@/components/ui";
import { exposureTotal, PERIOD, RECOVERABLE, SAVED, type Priority } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_NOTE, rub, SAVED_NOTE } from "@/lib/site";

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
  const { total, cards, overlap } = exposureTotal(problems);

  return (
    <>
      <PageHeader
        title="Где бюджет расходуется неэффективно"
        sub={`${problems.length} проблемы за ${PERIOD}. Сортировка — по сумме расхода с признаками неэффективности.`}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard
          label={EXPOSURE}
          value={rub(total)}
          approx
          tone="text-danger"
          note={overlap > 0 ? `Карточки ≈ ${rub(cards)} · пересечение −${rub(overlap)} · оценка` : "оценка, без двойного счёта"}
        />
        <MetricCard label="Можно сэкономить" value={rub(RECOVERABLE)} approx tone="text-warning" note="оценка по рекомендациям с высокой уверенностью" />
        <MetricCard label="Сэкономлено" value={rub(SAVED)} approx tone="text-success" note={SAVED_NOTE} />
      </div>
      <p className="mt-3 text-xs text-muted">{EXPOSURE_NOTE}</p>

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
