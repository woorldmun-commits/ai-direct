"use client";

import { useMemo, useState } from "react";
import { TrendChart, CHART_COLORS } from "@/components/charts/charts";
import { Card, CardHeader } from "@/components/ui/card";
import { Segmented } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { compact, num, rub, shortDay } from "@/lib/formatters";

type Range = "7" | "30" | "90";
type Metric = "cpa" | "spend" | "conversions";

const METRIC: Record<Metric, { label: string; prev: string; fmt: (n: number) => string; axis: (n: number) => string }> = {
  cpa: { label: "CPA", prev: "prevCpa", fmt: rub, axis: (n) => `${num(n)} ₽` },
  spend: { label: "Расход", prev: "prevSpend", fmt: rub, axis: compact },
  conversions: { label: "Конверсии", prev: "prevConversions", fmt: num, axis: num },
};

/** «Динамика эффективности»: current period vs the previous one, CPA against the target. */
export function PerformanceCard({ height = 280 }: { height?: number }) {
  const [range, setRange] = useState<Range>("30");
  const [metric, setMetric] = useState<Metric>("cpa");
  const data = useMemo(() => api.series().slice(-Number(range)), [range]);
  const m = METRIC[metric];
  const peak = useMemo(() => data.reduce((best, p, i) => (p[metric] > data[best][metric] ? i : best), 0), [data, metric]);

  return (
    <Card className="p-5">
      <CardHeader
        title="Динамика эффективности"
        sub="Сплошная линия — текущий период, пунктир — предыдущий. Точка — максимум периода."
        action={
          <Segmented
            label="Период"
            value={range}
            onChange={setRange}
            options={[
              { value: "7", label: "7 дней" },
              { value: "30", label: "30 дней" },
              { value: "90", label: "90 дней" },
            ]}
          />
        }
      />
      <div className="mt-4 flex flex-wrap items-center gap-4 text-[12px] text-muted">
        <Segmented
          label="Метрика"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "cpa", label: "CPA" },
            { value: "spend", label: "Расход" },
            { value: "conversions", label: "Конверсии" },
          ]}
        />
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-brand" aria-hidden /> {m.label}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0 w-4 border-t-2 border-dashed border-subtle" aria-hidden /> Прошлый период
        </span>
        {metric === "cpa" && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-4 border-t-2 border-dashed border-warning" aria-hidden /> Цель CPA
          </span>
        )}
      </div>
      <div className="mt-3">
        <TrendChart
          ariaLabel={`${m.label} по дням за ${range} дней в сравнении с предыдущим периодом`}
          data={data}
          xKey="date"
          xFmt={shortDay}
          fmt={m.fmt}
          axisFmt={m.axis}
          height={height}
          highlight={peak}
          target={metric === "cpa" ? { value: api.targetCpa(), label: "цель" } : undefined}
          series={[
            { key: metric, name: m.label, color: CHART_COLORS.brand, area: true },
            { key: m.prev, name: "Прошлый период", color: CHART_COLORS.muted, dashed: true },
          ]}
        />
      </div>
      <p className="mt-2 text-[12px] text-subtle">Факт · Яндекс Директ + Метрика · демо-данные</p>
    </Card>
  );
}
