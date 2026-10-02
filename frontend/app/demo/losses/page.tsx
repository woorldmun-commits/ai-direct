"use client";

import { useState } from "react";
import { LossesList, MetricCard } from "@/components/app/problem";
import { SAVED_NOTE } from "@/components/app/rec-parts";
import { useDemo } from "@/components/app/store";
import { PageHeader, StateBox } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { ruleName, RULE_TITLE } from "@/lib/contract";
import { P7 } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_NOTE } from "@/lib/site";
import { formatPeriod } from "@/lib/value";

const FILTERS = [
  { key: "all", label: "Все" },
  { key: "high_cpa", label: "Высокий CPA" },
  { key: "zero_conv_campaign", label: "Без конверсий" },
  { key: "zero_conv_placements", label: "Площадки РСЯ" },
] as const;

export default function Losses() {
  const { active, today: getToday } = useDemo();
  const today = getToday("fresh");
  const open = active.filter((r) => r.status !== "applied" && r.status !== "rejected");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const shown = filter === "all" ? open : open.filter((r) => ruleName(r.evidence.rule_version).startsWith(filter));
  const { exposure } = today;

  return (
    <>
      <PageHeader title="Где бюджет расходуется неэффективно" sub={`Открытые проблемы за ${formatPeriod(P7)}. Порядок — по сумме расхода с признаками неэффективности.`} />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label={EXPOSURE} v={exposure.total} tone="text-danger" />
        <MetricCard label="Можно сэкономить" v={today.can_save.total} tone="text-warning" note="оценка по открытым рекомендациям, без двойного учёта" />
        <MetricCard label="Сэкономлено" v={today.saved} tone="text-success" note={SAVED_NOTE} />
      </div>
      <div className="mt-3 space-y-1 text-xs text-muted">
        <p>{EXPOSURE_NOTE}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>
            Пересечение карточек вычтено: <ValueView v={exposure.overlap} />
          </span>
          {exposure.components.map((c) => (
            <span key={c.issue_type}>
              {RULE_TITLE[c.issue_type] ?? c.issue_type}: <ValueView v={c.amount} />
            </span>
          ))}
          {exposure.coverage.unavailable > 0 && <span>без суммы в итог не вошли: {exposure.coverage.unavailable}</span>}
        </p>
      </div>

      <div className="mt-6 mb-4 flex flex-wrap gap-2" role="group" aria-label="Фильтр по правилу">
        {FILTERS.map((f) => (
          <button key={f.key} className="chip" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label} ({f.key === "all" ? open.length : open.filter((r) => ruleName(r.evidence.rule_version).startsWith(f.key)).length})
          </button>
        ))}
      </div>

      {shown.length ? (
        <LossesList key={filter} recs={shown} />
      ) : (
        <StateBox kind="empty" title="По этому правилу проблем не найдено" text={`Правило проверено на всех кампаниях за ${formatPeriod(P7)}.`} />
      )}
    </>
  );
}
