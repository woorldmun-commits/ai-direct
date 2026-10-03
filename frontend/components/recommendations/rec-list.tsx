"use client";

import { History, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { isOpenRec, useApp } from "@/components/layout/app-state";
import { buttonCls } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/misc";
import { EmptyState } from "@/components/ui/states";
import { FilterTabs } from "@/components/ui/tabs";
import type { Recommendation } from "@/lib/types/domain";
import { RecCard } from "./rec-card";

type Filter = "all" | "high" | "medium" | "low" | "new" | "done";
type Sort = "effect" | "recent" | "priority";

const PRIORITY = ["high", "medium", "low"];
const MATCH: Record<Filter, (r: Recommendation) => boolean> = {
  all: () => true,
  high: (r) => r.severity === "high",
  medium: (r) => r.severity === "medium",
  low: (r) => r.severity === "low",
  new: (r) => r.status === "new",
  done: (r) => r.status === "applied",
};
const effectOf = (r: Recommendation) => (r.effect.value.calculation_type !== "unavailable" && r.effect.value.unit === "rub" ? r.effect.value.amount : -1);
const SORT: Record<Sort, (a: Recommendation, b: Recommendation) => number> = {
  effect: (a, b) => effectOf(b) - effectOf(a),
  recent: (a, b) => b.created_at.localeCompare(a.created_at),
  priority: (a, b) => PRIORITY.indexOf(a.severity) - PRIORITY.indexOf(b.severity),
};

export function RecList({ openId }: { openId: string | null }) {
  const { recs, openEvidence } = useApp();
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("effect");
  const [q, setQ] = useState("");

  useEffect(() => {
    if (openId) openEvidence(openId);
  }, [openId, openEvidence]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return recs.filter((r) => MATCH[filter](r) && (!s || `${r.title} ${r.campaign} ${r.client}`.toLowerCase().includes(s))).sort(SORT[sort]);
  }, [recs, filter, sort, q]);

  const count = (f: Filter) => recs.filter(MATCH[f]).length;
  const waiting = recs.filter(isOpenRec).length;

  return (
    <>
      <PageHeader
        title="Рекомендации"
        sub={`Конкретные действия для роста эффективности. Ждут решения: ${waiting}.`}
        actions={
          <Link href="/history" className={buttonCls("secondary", "sm")}>
            <History size={15} /> История решений
          </Link>
        }
      />
      <div className="card mb-5 flex flex-wrap items-center justify-between gap-3 p-3">
        <FilterTabs
          label="Фильтр рекомендаций"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "Все", count: count("all") },
            { value: "high", label: "Высокий приоритет", count: count("high") },
            { value: "medium", label: "Средний", count: count("medium") },
            { value: "low", label: "Низкий", count: count("low") },
            { value: "new", label: "Новые", count: count("new") },
            { value: "done", label: "Выполненные", count: count("done") },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="relative">
            <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Кампания или клиент" aria-label="Поиск по рекомендациям" className="input h-9 w-[200px] pl-8 text-[13px]" />
          </span>
          <Select aria-label="Сортировка" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="effect">По потенциальному эффекту</option>
            <option value="recent">По новизне</option>
            <option value="priority">По приоритету</option>
          </Select>
        </div>
      </div>

      {list.length ? (
        <div className="space-y-4">
          {list.map((r) => (
            <RecCard key={r.id} rec={r} />
          ))}
        </div>
      ) : (
        <div className="card">
          <EmptyState title="Ничего не найдено" text="Измените фильтр или строку поиска." />
        </div>
      )}
    </>
  );
}
