"use client";

import Link from "next/link";
import { useState } from "react";
import { useDemo } from "@/components/app/store";
import { LineChart } from "@/components/charts";
import { PageHeader, StateBox } from "@/components/ui";
import { DeltaBadge, ValueView } from "@/components/value-view";
import { cpaSeries, DAYS, P7, PREV7, PREV_WEEK, PREV_WEEK_VALUES, WEEK, WEEK_DELTAS, WEEK_VALUES } from "@/lib/demo";
import { formatPeriod } from "@/lib/value";

const METRICS = [
  { name: "CPA", cur: WEEK_VALUES.cpa, prev: PREV_WEEK_VALUES.cpa, delta: WEEK_DELTAS.cpa, a: cpaSeries(WEEK), b: cpaSeries(PREV_WEEK), down: true },
  { name: "Расход", cur: WEEK_VALUES.spend, prev: PREV_WEEK_VALUES.spend, delta: WEEK_DELTAS.spend, a: WEEK.spend, b: PREV_WEEK.spend, down: true },
  { name: "Конверсии", cur: WEEK_VALUES.conversions, prev: PREV_WEEK_VALUES.conversions, delta: WEEK_DELTAS.conversions, a: WEEK.conversions, b: PREV_WEEK.conversions, down: false },
  { name: "Неэффективный расход", cur: WEEK_VALUES.exposure, prev: PREV_WEEK_VALUES.exposure, delta: WEEK_DELTAS.exposure, a: WEEK.exposure, b: PREV_WEEK.exposure, down: true },
];

// Axis ticks of the chart only; numbers in text go through <ValueView>.
const k = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

export default function Changes() {
  const [metric, setMetric] = useState<"cpa" | "roas">("cpa");
  const { changes } = useDemo().today("fresh");
  return (
    <>
      <PageHeader title="Что изменилось" sub={`${formatPeriod(P7)} против ${formatPeriod(PREV7)}`}>
        <div role="group" aria-label="Основная метрика" className="flex gap-2">
          <button className="chip" aria-pressed={metric === "cpa"} onClick={() => setMetric("cpa")}>
            CPA
          </button>
          <button className="chip" aria-pressed={metric === "roas"} onClick={() => setMetric("roas")}>
            ROAS / ДРР
          </button>
        </div>
      </PageHeader>

      <section id="day" className="card mb-4 scroll-mt-24 p-5" aria-labelledby="day-t">
        <h2 id="day-t" className="font-bold">
          За сутки
        </h2>
        <p className="text-xs text-muted">{formatPeriod(changes.period)}: последний день к предыдущему</p>
        <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm">
          {[
            { l: "Расход", v: changes.spent_delta_pct, down: true },
            { l: "Конверсии", v: changes.conversions_delta_pct, down: false },
            { l: "CPA", v: changes.cpa_delta_pct, down: true },
          ].map((m) => (
            <div key={m.l} className="flex items-center gap-2">
              <dt className="text-muted">{m.l}</dt>
              <dd>
                <DeltaBadge v={m.v} goodWhenDown={m.down} />
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {metric === "roas" ? (
        <StateBox
          kind="insufficient"
          title="Недостаточно данных: источник выручки не подключён"
          text="ROAS и ДРР считаются только по фактической выручке. Без неё мы их не показываем, чтобы не выдумывать цифры."
          action={
            <Link href="/demo/integrations" className="btn btn-secondary btn-sm">
              Перейти в интеграции
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {METRICS.map((m) => (
            <section key={m.name} className="card p-5" aria-label={m.name}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm text-muted">{m.name}</p>
                  <div className="mt-1">
                    <ValueView v={m.cur} className="text-[28px] leading-tight" />
                  </div>
                  <p className="text-xs text-muted">
                    было <ValueView v={m.prev} className="font-semibold" />
                  </p>
                </div>
                <DeltaBadge v={m.delta} goodWhenDown={m.down} />
              </div>
              <div className="mt-4">
                <LineChart
                  height={120}
                  labels={DAYS}
                  format={k}
                  series={[
                    { name: "Эта неделя", values: m.a, color: "var(--brand)" },
                    { name: "Прошлая неделя", values: m.b, color: "var(--muted)", dashed: true },
                  ]}
                />
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
