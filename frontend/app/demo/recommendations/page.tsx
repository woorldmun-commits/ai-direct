"use client";

import { useState } from "react";
import { RecommendationCard } from "@/components/app/problem";
import { useDemo } from "@/components/app/store";
import { PageHeader, StateBox } from "@/components/ui";
import type { RecStatus } from "@/lib/demo";

const TABS: { key: RecStatus | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "new", label: "Новые" },
  { key: "in_progress", label: "В работе" },
  { key: "done", label: "Выполненные" },
  { key: "postponed", label: "Отложенные" },
  { key: "rejected", label: "Отклонённые" },
];

export default function Recommendations() {
  const { problems } = useDemo();
  const [tab, setTab] = useState<RecStatus | "all">("all");
  const shown = tab === "all" ? problems : problems.filter((p) => p.status === tab);

  return (
    <>
      <PageHeader title="Рекомендации" sub="Каждое действие вы выполняете сами в Яндекс Директе, а здесь отмечаете решение." />
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Статус">
        {TABS.map((t) => {
          const n = t.key === "all" ? problems.length : problems.filter((p) => p.status === t.key).length;
          return (
            <button key={t.key} className="chip shrink-0" aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label} ({n})
            </button>
          );
        })}
      </div>
      {shown.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {shown.map((p) => (
            <RecommendationCard key={p.id} p={p} />
          ))}
        </div>
      ) : (
        <StateBox kind="empty" title="Здесь пока пусто" text="Рекомендации появятся, когда вы примете по ним решение." />
      )}
    </>
  );
}
