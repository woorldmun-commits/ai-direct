"use client";

import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export const CHART_COLORS = { brand: "#5B5BF7", violet: "#7C5CFF", sky: "#3B82F6", success: "#12B76A", warning: "#F79009", danger: "#F04438", muted: "#98A2B3", grid: "#EEF1F5" };
const PALETTE = [CHART_COLORS.brand, CHART_COLORS.sky, CHART_COLORS.violet, "#A5B4FC", CHART_COLORS.success];

type Fmt = (n: number) => string;
export type Series = { key: string; name: string; color: string; dashed?: boolean; area?: boolean };

const axis = { tick: { fill: "#98A2B3", fontSize: 11 }, tickLine: false, axisLine: false } as const;

type TipProps = { active?: boolean; payload?: readonly { dataKey?: unknown; name?: unknown; value?: unknown; color?: string }[]; label?: unknown };

function ChartTooltip({ active, payload, label, fmt, labelFmt }: TipProps & { fmt: Fmt; labelFmt?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2.5 text-[12px] shadow-[0_8px_24px_rgba(15,23,42,0.12)]">
      <p className="mb-1.5 font-semibold">{labelFmt ? labelFmt(String(label)) : String(label ?? "")}</p>
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="flex items-center gap-2 text-muted">
          <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
          {String(p.name)}
          <span className="num ml-auto pl-4 font-semibold text-text">{fmt(Number(p.value))}</span>
        </p>
      ))}
    </div>
  );
}

/** Line / area trend with optional comparison series, target line and a highlighted point. */
export function TrendChart<T extends object>({
  data,
  xKey,
  series,
  fmt,
  axisFmt = fmt,
  xFmt,
  height = 260,
  target,
  highlight,
  ariaLabel,
}: {
  data: T[];
  xKey: keyof T & string;
  series: Series[];
  fmt: Fmt;
  axisFmt?: Fmt;
  xFmt?: (v: string) => string;
  height?: number;
  target?: { value: number; label: string };
  highlight?: number;
  ariaLabel: string;
}) {
  const hp = highlight !== undefined ? data[highlight] : undefined;
  return (
    <div role="img" aria-label={ariaLabel} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.18} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
          <XAxis dataKey={(d: T) => d[xKey] as unknown as string} {...axis} tickFormatter={xFmt} minTickGap={24} dy={6} />
          <YAxis {...axis} tickFormatter={axisFmt} width={64} />
          <Tooltip cursor={{ stroke: "#D0D5DD", strokeDasharray: "3 3" }} content={(p) => <ChartTooltip active={p.active} payload={p.payload} label={p.label} fmt={fmt} labelFmt={xFmt} />} />
          {target && <ReferenceLine y={target.value} stroke={CHART_COLORS.warning} strokeDasharray="4 4" label={{ value: target.label, position: "insideTopRight", fill: "#B54708", fontSize: 11 }} />}
          {series.map((s) =>
            s.area ? (
              <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2.25} fill={`url(#g-${s.key})`} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }} animationDuration={500} />
            ) : (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={s.dashed ? 1.75 : 2.25} strokeDasharray={s.dashed ? "5 5" : undefined} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }} animationDuration={500} />
            ),
          )}
          {hp && <ReferenceDot x={hp[xKey] as unknown as string} y={(hp as Record<string, unknown>)[series[0].key] as number} r={5} fill={series[0].color} stroke="#fff" strokeWidth={2.5} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BarsChart<T extends object>({ data, xKey, series, fmt, axisFmt = fmt, xFmt, height = 240, ariaLabel }: { data: T[]; xKey: keyof T & string; series: Series[]; fmt: Fmt; axisFmt?: Fmt; xFmt?: (v: string) => string; height?: number; ariaLabel: string }) {
  return (
    <div role="img" aria-label={ariaLabel} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={3}>
          <CartesianGrid vertical={false} stroke={CHART_COLORS.grid} />
          <XAxis dataKey={(d: T) => d[xKey] as unknown as string} {...axis} tickFormatter={xFmt} minTickGap={16} dy={6} />
          <YAxis {...axis} tickFormatter={axisFmt} width={64} />
          <Tooltip cursor={{ fill: "rgba(91,91,247,0.06)" }} content={(p) => <ChartTooltip active={p.active} payload={p.payload} label={p.label} fmt={fmt} labelFmt={xFmt} />} />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={14} animationDuration={500} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Actual vs target per item (e.g. CPA by campaign against target CPA). */
export function ComparisonChart({ data, target, targetLabel = "цель", fmt, height, ariaLabel }: { data: { name: string; value: number }[]; target: number; targetLabel?: string; fmt: Fmt; height?: number; ariaLabel: string }) {
  return (
    <div role="img" aria-label={ariaLabel} style={{ height: height ?? data.length * 34 + 30 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke={CHART_COLORS.grid} />
          <XAxis type="number" {...axis} tickFormatter={fmt} />
          <YAxis type="category" dataKey="name" {...axis} width={150} tick={{ fill: "#475467", fontSize: 12 }} />
          <Tooltip cursor={{ fill: "rgba(91,91,247,0.06)" }} content={(p) => <ChartTooltip active={p.active} payload={p.payload} label={p.label} fmt={fmt} />} />
          <ReferenceLine x={target} stroke={CHART_COLORS.warning} strokeDasharray="4 4" label={{ value: `${targetLabel} ${fmt(target)}`, position: "top", fill: "#B54708", fontSize: 11 }} />
          <Bar dataKey="value" name="CPA" radius={[0, 4, 4, 0]} maxBarSize={14} animationDuration={500}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.value > target ? CHART_COLORS.danger : CHART_COLORS.brand} fillOpacity={d.value > target ? 0.85 : 1} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DonutChart({ data, fmt, center, ariaLabel, size = 180 }: { data: { name: string; value: number }[]; fmt: Fmt; center?: { label: string; value: string }; ariaLabel: string; size?: number }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div role="img" aria-label={ariaLabel} className="relative shrink-0" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="100%" paddingAngle={2} stroke="none" animationDuration={500}>
              {data.map((d, i) => (
                <Cell key={d.name} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip content={(p) => <ChartTooltip active={p.active} payload={p.payload} label={p.label} fmt={fmt} />} />
          </PieChart>
        </ResponsiveContainer>
        {center && (
          <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
            <span className="text-[11px] text-muted">{center.label}</span>
            <span className="num text-[15px] font-semibold">{center.value}</span>
          </div>
        )}
      </div>
      <ul className="min-w-[180px] flex-1 space-y-2 text-[13px]">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden />
            <span className="text-muted">{d.name}</span>
            <span className="num ml-auto font-medium">{fmt(d.value)}</span>
            <span className="num w-11 text-right text-subtle">{Math.round((d.value / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sparkline({ data, color = CHART_COLORS.brand, height = 36, width = 96 }: { data: number[]; color?: string; height?: number; width?: number }) {
  const points = data.map((v, i) => ({ i, v }));
  return (
    <div style={{ width, height }} aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 2, left: 2, bottom: 4 }}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
