"use client";

import { useState } from "react";
import { RecommendationCard } from "@/components/app/problem";
import { useDemo } from "@/components/app/store";
import { PageHeader, StateBox } from "@/components/ui";
import type { RecStatus } from "@/lib/demo";

const TABS: { key: RecStatus | "all"; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "new", label: "Новые" },
  { key: "viewed", label: "Просмотренные" },
  { key: "accepted", label: "Приняты к выполнению" },
  { key: "applied", label: "Выполнены вручную" },
  { key: "measured", label: "Эффект измерен" },
  { key: "postponed", label: "Отложенные" },
  { key: "rejected", label: "Не буду" },
];

export default function Recommendations() {
  const { problems } = useDemo();
  const [tab, setTab] = useState<RecStatus | "all">("all");
  const shown = tab === "all" ? problems : problems.filter((p) => p.status === tab);

  return (
    <>
      <PageHeader title="Рекомендации" sub="AdPilot не меняет кабинет. Вы принимаете решение, вносите изменение в Яндекс Директе вручную, а AdPilot сверяет его по данным Директа и измеряет эффект." />
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
        <StateBox
          kind="empty"
          title="Здесь пока пусто"
          text={
            tab === "measured"
              ? "Эффект измеряется через 7 дней после сверки ручного изменения. Прошлые замеры — в «Истории решений»."
              : "Рекомендации появятся здесь, когда вы примете по ним решение."
          }
        />
      )}
    </>
  );
}
