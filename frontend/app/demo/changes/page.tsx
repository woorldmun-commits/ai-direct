"use client";

import Link from "next/link";
import { useState } from "react";
import { LineChart } from "@/components/charts";
import { Delta, PageHeader, StateBox } from "@/components/ui";
import { DAYS, KPI, PERIOD, PREV_KPI, PREV_PERIOD, PREV_WEEK, WEEK } from "@/lib/demo";
import { pctChange, rub } from "@/lib/site";

const prevCpaDaily = PREV_WEEK.spend.map((s, i) => Math.round(s / PREV_WEEK.conversions[i]));

const METRICS = [
  { name: "CPA", cur: KPI.cpa, prev: PREV_KPI.cpa, fmt: rub, a: KPI.cpaDaily, b: prevCpaDaily, down: true },
  { name: "Расход", cur: KPI.spend, prev: PREV_KPI.spend, fmt: rub, a: WEEK.spend, b: PREV_WEEK.spend, down: true },
  { name: "Конверсии", cur: KPI.conversions, prev: PREV_KPI.conversions, fmt: String, a: WEEK.conversions, b: PREV_WEEK.conversions, down: false },
  { name: "Неэффективный расход", cur: KPI.losses, prev: PREV_KPI.losses, fmt: (n: number) => `≈ ${rub(n)}`, a: WEEK.losses, b: PREV_WEEK.losses, down: true },
];

const k = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

export default function Changes() {
  const [metric, setMetric] = useState<"cpa" | "roas">("cpa");
  return (
    <>
      <PageHeader title="Что изменилось" sub={`${PERIOD} против ${PREV_PERIOD}`}>
        <div role="group" aria-label="Основная метрика" className="flex gap-2">
          <button className="chip" aria-pressed={metric === "cpa"} onClick={() => setMetric("cpa")}>
            CPA
          </button>
          <button className="chip" aria-pressed={metric === "roas"} onClick={() => setMetric("roas")}>
            ROAS / ДРР
          </button>
        </div>
      </PageHeader>

      {metric === "roas" ? (
        <StateBox
          kind="insufficient"
          title="Подключите источник выручки"
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
                  <p className="money mt-1 text-[28px] leading-tight">{m.fmt(m.cur)}</p>
                  <p className="text-xs text-muted">было {m.fmt(m.prev)}</p>
                </div>
                <Delta value={pctChange(m.prev, m.cur)} goodWhenDown={m.down} />
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
