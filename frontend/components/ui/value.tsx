"use client";

import { ArrowDownRight, ArrowUpRight, Info } from "lucide-react";
import type { MetricValue } from "@/lib/types/domain";
import { CALC_LABEL, day, formatValue, signed, sources } from "@/lib/formatters";
import { Badge } from "./badge";
import { Popover } from "./overlay";

/** The number itself. Unavailable values render as text, never as 0 or a dash. */
export function ValueText({ value, className = "" }: { value: MetricValue; className?: string }) {
  if (value.calculation_type === "unavailable") return <span className={`text-muted ${className} !text-[0.6em] font-medium`}>Недостаточно данных</span>;
  return <span className={`num ${className}`}>{formatValue(value)}</span>;
}

export function CalcTag({ value }: { value: MetricValue }) {
  const t = value.calculation_type;
  return <Badge tone={t === "actual" ? "neutral" : t === "estimated" ? "brand" : "warning"}>{CALC_LABEL[t]}</Badge>;
}

/** «Факт · Яндекс Директ · последние 7 дней» + a popover with every provenance field. */
export function ValueMeta({ value, className = "" }: { value: MetricValue; className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px] text-muted ${className}`}>
      <span className={value.calculation_type === "actual" ? "" : value.calculation_type === "estimated" ? "text-brand" : "text-warning-ink"}>{CALC_LABEL[value.calculation_type]}</span>
      <span aria-hidden>·</span>
      <span>{sources(value.source)}</span>
      <span aria-hidden>·</span>
      <span>{value.period.label}</span>
      {value.data_status === "partial" && <span className="text-warning-ink">· данные за последние дни могут уточниться</span>}
      <ValueInfo value={value} />
    </div>
  );
}

export function ValueInfo({ value }: { value: MetricValue }) {
  const rows: [string, string][] = [
    ["Тип значения", CALC_LABEL[value.calculation_type]],
    ["Источник", sources(value.source)],
    ["Период", `${day(value.period.from)} — ${day(value.period.to)}`],
    ["Статус данных", value.data_status === "complete" ? "Полные" : "Частичные — могут уточниться"],
    ["Достаточность", value.data_sufficiency === "sufficient" ? "Достаточно" : "Недостаточно"],
    ["Формула", value.formula ?? "—"],
    ["Правило", value.rule_version ?? "—"],
    ["Снимок", value.snapshot_id ?? "—"],
  ];
  return (
    <Popover
      label="Как посчитано"
      align="left"
      width={320}
      trigger={({ open, toggle }) => (
        <button type="button" onClick={toggle} aria-expanded={open} aria-label="Как посчитано" className="grid size-5 place-items-center rounded-full text-subtle hover:bg-surface-2 hover:text-brand">
          <Info size={13} />
        </button>
      )}
    >
      <div className="p-4">
        <p className="text-[13px] font-semibold">Как посчитано</p>
        {value.calculation_type === "unavailable" && <p className="mt-1 text-[12px] text-warning-ink">{value.missing}</p>}
        <dl className="mt-2 space-y-1.5 text-[12px]">
          {rows.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[104px_1fr] gap-2">
              <dt className="text-muted">{k}</dt>
              <dd className={k === "Формула" || k === "Снимок" || k === "Правило" ? "font-mono text-[11px] break-words" : ""}>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Popover>
  );
}

/** Change vs previous period. `goodWhenDown` flips colors for costs. */
export function Delta({ value, goodWhenDown = false, suffix = "к прошлому периоду" }: { value: number | null; goodWhenDown?: boolean; suffix?: string }) {
  if (value === null) return <span className="text-[12px] text-subtle">нет данных для сравнения</span>;
  const good = goodWhenDown ? value < 0 : value > 0;
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px]">
      <span className={`num inline-flex items-center gap-0.5 font-semibold ${value === 0 ? "text-muted" : good ? "text-success-ink" : "text-danger-ink"}`}>
        <Icon size={13} strokeWidth={2.5} aria-hidden />
        {signed(value)}%
      </span>
      <span className="text-subtle">{suffix}</span>
    </span>
  );
}
