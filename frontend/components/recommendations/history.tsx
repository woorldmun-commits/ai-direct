"use client";

import { Check, Clock, Minus } from "lucide-react";
import { useApp, type Decision } from "@/components/layout/app-state";
import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { DemoBadge, PageHeader } from "@/components/ui/misc";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/formatters";
import type { Measurement, Verdict } from "@/lib/types/domain";

export const VERDICT: Record<Verdict, [string, Tone, string]> = {
  effect: ["Есть эффект", "success", "Метрика улучшилась при сопоставимом объёме конверсий."],
  no_effect: ["Нет эффекта", "neutral", "Изменение не улучшило показатели."],
  not_confirmed: ["Не подтверждено", "warning", "CPA снизился, но конверсий стало меньше — эффект не засчитан."],
  insufficient: ["Мало данных", "neutral", "Данных после изменения недостаточно для вывода."],
  pending: ["Идёт замер", "brand", "Окно «после» ещё не закончилось."],
};

const DECISION: Record<Decision, string> = { approve: "Подтверждено", postpone: "Отложено", reject: "Отклонено", checked: "Проверено" };

function Steps({ m }: { m: Measurement }) {
  const executed = m.execution_mode === "api" ? "Применено через API" : m.verification === "confirmed" ? "Выполнено вручную · подтверждено" : "Выполнено вручную · не подтверждено";
  const steps = [
    { label: "Рекомендация", sub: m.recommendation, done: true },
    { label: "Подтверждено", sub: `${m.approved_by} · ${dateTime(m.approved_at)}`, done: true },
    { label: "Исполнено", sub: executed, done: m.execution_mode === "api" || m.verification === "confirmed", warn: m.verification === "not_confirmed" },
    { label: "Замер", sub: `до ${m.windows.before} · после ${m.windows.after}`, done: m.verdict !== "pending" },
    { label: "Вердикт", sub: VERDICT[m.verdict][0], done: m.verdict !== "pending" },
  ];
  return (
    <ol className="grid gap-3 sm:grid-cols-5">
      {steps.map((s, i) => (
        <li key={s.label} className="relative">
          <div className="flex items-center gap-2">
            <span className={`grid size-6 shrink-0 place-items-center rounded-full ${s.warn ? "bg-warning-soft text-warning" : s.done ? "bg-success-soft text-success" : "bg-surface-2 text-subtle"}`}>
              {s.warn ? <Minus size={13} /> : s.done ? <Check size={13} strokeWidth={3} /> : <Clock size={12} />}
            </span>
            <span className="text-[12px] font-semibold">{s.label}</span>
            {i < steps.length - 1 && <span className="hidden h-px flex-1 bg-line sm:block" aria-hidden />}
          </div>
          <p className="mt-1 pl-8 text-[12px] text-muted sm:pl-0">{s.sub}</p>
        </li>
      ))}
    </ol>
  );
}

function MeasurementCard({ m }: { m: Measurement }) {
  const [label, tone, hint] = VERDICT[m.verdict];
  return (
    <Card as="article" className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold">{m.recommendation}</h3>
          <p className="text-[12px] text-muted">{m.campaign}</p>
        </div>
        <Badge tone={tone} dot>
          {label}
        </Badge>
      </div>
      <div className="mt-4">
        <Steps m={m} />
      </div>
      <div className="mt-4 grid gap-4 border-t border-line pt-4 md:grid-cols-[1fr_260px]">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-[12px] text-muted">
              <th scope="col" className="pb-1.5 font-medium">
                Метрика
              </th>
              <th scope="col" className="pb-1.5 text-right font-medium">
                До
              </th>
              <th scope="col" className="pb-1.5 text-right font-medium">
                После
              </th>
            </tr>
          </thead>
          <tbody>
            {m.rows.map((r) => (
              <tr key={r.label} className="border-t border-line">
                <td className="py-2">{r.label}</td>
                <td className="num py-2 text-right">{r.before}</td>
                <td className="num py-2 text-right font-semibold">{r.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="rounded-xl bg-bg p-3.5">
          <p className="text-[12px] text-muted">Оценка экономии</p>
          {m.saved ? (
            <>
              <p className="text-[18px] font-semibold text-success-ink">
                <ValueText value={m.saved} />
              </p>
              <ValueMeta value={m.saved} className="mt-1" />
            </>
          ) : (
            <p className="mt-0.5 text-[13px] font-medium">Не засчитывается</p>
          )}
          <p className="mt-1.5 text-[12px] text-muted">{hint}</p>
        </div>
      </div>
    </Card>
  );
}

export function History() {
  const { log } = useApp();
  const items = api.measurements();
  const total = api.measuredTotal();
  const count = (v: Verdict) => items.filter((m) => m.verdict === v).length;
  return (
    <>
      <PageHeader title="История решений" sub="Что рекомендовали, кто подтвердил, что произошло и каким оказался результат." actions={<DemoBadge />} />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-5">
          <p className="text-[13px] text-muted">Измеренный эффект</p>
          <p className="mt-1 text-[24px] font-semibold text-success-ink">
            <ValueText value={total} />
          </p>
          <ValueMeta value={total} className="mt-1" />
        </Card>
        {(
          [
            ["Есть эффект", count("effect")],
            ["Нет эффекта или не подтверждено", count("no_effect") + count("not_confirmed")],
            ["Идёт замер", count("pending")],
          ] as const
        ).map(([l, v]) => (
          <Card key={l} className="p-5">
            <p className="text-[13px] text-muted">{l}</p>
            <p className="num mt-1 text-[24px] font-semibold">{v}</p>
            <p className="mt-1 text-[12px] text-muted">из {items.length} решений с замером</p>
          </Card>
        ))}
      </div>

      {log.length > 0 && (
        <Card className="mb-6 p-5">
          <CardHeader title="Решения в этой сессии" sub="Замер появится через 7 дней после исполнения" />
          <ul className="mt-3 divide-y divide-line">
            {log.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-[13px]">
                <span>
                  <b>{l.title}</b> <span className="text-muted">· {l.campaign}</span>
                </span>
                <span className="flex items-center gap-2">
                  <Badge tone={l.decision === "approve" ? "success" : l.decision === "reject" ? "neutral" : "brand"}>{DECISION[l.decision]}</Badge>
                  <span className="text-[12px] text-subtle">{dateTime(l.at)}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="space-y-4">
        {items.map((m) => (
          <MeasurementCard key={m.id} m={m} />
        ))}
      </div>
    </>
  );
}
