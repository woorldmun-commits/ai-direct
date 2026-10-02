// Dependency-free SVG charts. Colors come from CSS variables so dark mode just works.

const H = 160;

function scale(values: number[], h: number, pad = 8) {
  const max = Math.max(...values);
  const min = Math.min(0, ...values);
  return (v: number) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
}

export function Sparkline({ values, color = "var(--brand)", height = 36 }: { values: number[]; color?: string; height?: number }) {
  const w = 120;
  const y = scale(values, height, 4);
  const step = w / (values.length - 1);
  const d = values.map((v, i) => `${i ? "L" : "M"}${i * step},${y(v)}`).join("");
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none" aria-hidden>
      <path d={`${d}L${w},${height}L0,${height}z`} fill={color} opacity={0.1} />
      <path d={d} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

export function LineChart({
  series,
  labels,
  height = H,
  format = (v: number) => String(v),
}: {
  series: { name: string; values: number[]; color: string; dashed?: boolean }[];
  labels: string[];
  height?: number;
  format?: (v: number) => string;
}) {
  const w = 600;
  const all = series.flatMap((s) => s.values);
  const y = scale(all, height - 20);
  const step = w / (labels.length - 1);
  const ticks = [Math.max(...all), Math.round((Math.max(...all) + Math.min(0, ...all)) / 2), Math.min(0, ...all)];
  return (
    <figure className="anim-fade">
      <svg viewBox={`0 0 ${w} ${height}`} className="w-full overflow-visible" style={{ height }} role="img" aria-label={series.map((s) => s.name).join(", ")}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeDasharray="3 4" />
            <text x={0} y={y(t) - 4} fontSize={10} fill="var(--muted)">
              {format(t)}
            </text>
          </g>
        ))}
        {series.map((s) => (
          <path
            key={s.name}
            d={s.values.map((v, i) => `${i ? "L" : "M"}${i * step},${y(v)}`).join("")}
            fill="none"
            stroke={s.color}
            strokeWidth={2.2}
            strokeDasharray={s.dashed ? "5 5" : undefined}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {series
          .filter((s) => !s.dashed)
          .map((s) =>
            s.values.map((v, i) => <circle key={`${s.name}${i}`} cx={i * step} cy={y(v)} r={3} fill="var(--surface)" stroke={s.color} strokeWidth={2} />),
          )}
        {labels.map((l, i) => (
          <text key={l + i} x={i * step} y={height - 2} fontSize={10} fill="var(--muted)" textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}>
            {l}
          </text>
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-muted">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: s.color, opacity: s.dashed ? 0.6 : 1 }} />
            {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

/** Stacked bars: `a` is the base (e.g. useful spend), `b` sits on top (e.g. losses). */
export function Bars({ a, b, labels, height = H }: { a: number[]; b: number[]; labels: string[]; height?: number }) {
  const w = 600;
  const totals = a.map((v, i) => v + b[i]);
  const max = Math.max(...totals);
  const bw = w / a.length;
  const k = (height - 20) / max;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="anim-fade w-full" style={{ height }} role="img" aria-label="Расход и потери по дням">
      {a.map((v, i) => {
        const x = i * bw + bw * 0.2;
        const hb = b[i] * k;
        const ha = v * k;
        return (
          <g key={i}>
            <rect x={x} y={height - 20 - ha} width={bw * 0.6} height={ha} rx={2} fill="var(--brand)" opacity={0.85} />
            <rect x={x} y={height - 20 - ha - hb} width={bw * 0.6} height={hb} rx={2} fill="var(--danger)" opacity={0.75} />
          </g>
        );
      })}
      {labels.map((l, i) =>
        l ? (
          <text key={i} x={i * bw + bw / 2} y={height - 4} fontSize={10} fill="var(--muted)" textAnchor="middle">
            {l}
          </text>
        ) : null,
      )}
    </svg>
  );
}

export function Donut({ parts, size = 132 }: { parts: { label: string; value: number; color: string }[]; size?: number }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  const r = 15.9155; // circumference = 100
  const arcs = parts.map((p, i) => {
    const pct = (p.value / total) * 100;
    const before = parts.slice(0, i).reduce((s, q) => s + (q.value / total) * 100, 0);
    return { ...p, pct, offset: 25 - before };
  });
  return (
    <svg viewBox="0 0 36 36" width={size} height={size} role="img" aria-label="Структура расходов">
      <circle cx={18} cy={18} r={r} fill="none" stroke="var(--surface-2)" strokeWidth={4} />
      {arcs.map((p) => (
        <circle
          key={p.label}
          cx={18}
          cy={18}
          r={r}
          fill="none"
          stroke={p.color}
          strokeWidth={4}
          strokeDasharray={`${p.pct - 0.8} ${100 - p.pct + 0.8}`}
          strokeDashoffset={p.offset}
        />
      ))}
    </svg>
  );
}
