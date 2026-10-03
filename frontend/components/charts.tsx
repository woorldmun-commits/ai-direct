// Dependency-free SVG charts drawn like a statement's graph paper. Colors come from CSS variables.

const H = 160;
const LABEL = { fontSize: 10, fill: "var(--muted)", fontFamily: "var(--font-mono)" };

function scale(values: number[], h: number, pad = 8) {
  const max = Math.max(...values);
  const min = Math.min(0, ...values);
  return (v: number) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
}

export function LineChart({
  series,
  labels,
  height = H,
  format = (v: number) => String(v),
  label,
}: {
  series: { name: string; values: number[]; color: string; dashed?: boolean }[];
  labels: string[];
  height?: number;
  format?: (v: number) => string;
  label: string;
}) {
  const w = 600;
  const all = series.flatMap((s) => s.values);
  const y = scale(all, height - 20);
  const step = w / (labels.length - 1);
  const ticks = [Math.max(...all), Math.round((Math.max(...all) + Math.min(0, ...all)) / 2), Math.min(0, ...all)];
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${height}`} className="w-full overflow-visible" style={{ height }} role="img" aria-label={label}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={0} y={y(t) - 4} {...LABEL}>
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
            strokeWidth={s.dashed ? 1.5 : 2}
            strokeDasharray={s.dashed ? "5 4" : undefined}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {series
          .filter((s) => !s.dashed)
          .map((s) =>
            s.values.map((v, i) => (
              <rect key={`${s.name}${i}`} x={i * step - 2.5} y={y(v) - 2.5} width={5} height={5} fill="var(--surface)" stroke={s.color} strokeWidth={1.5} />
            )),
          )}
        {labels.map((l, i) => (
          <text key={l + i} x={i * step} y={height - 2} {...LABEL} textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}>
            {l}
          </text>
        ))}
      </svg>
      <figcaption className="caption mt-2 flex flex-wrap gap-4">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <svg width="18" height="4" aria-hidden>
              <line x1="0" x2="18" y1="2" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "4 3" : undefined} />
            </svg>
            {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

/** Stacked bars: `a` is the base (useful spend, ink), `b` sits on top (losses, red ink). `split` draws a period divider. */
export function Bars({ a, b, labels, height = H, split, label }: { a: number[]; b: number[]; labels: string[]; height?: number; split?: number; label: string }) {
  const w = 600;
  const totals = a.map((v, i) => v + b[i]);
  const max = Math.max(...totals);
  const bw = w / a.length;
  const k = (height - 22) / max;
  const base = height - 20;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="w-full" style={{ height }} role="img" aria-label={label}>
      {a.map((v, i) => {
        const x = i * bw + bw * 0.22;
        const ha = v * k;
        const hb = b[i] * k;
        return (
          <g key={i}>
            <rect x={x} y={base - ha} width={bw * 0.56} height={ha} fill="var(--text)" opacity={0.82} />
            <rect x={x} y={base - ha - hb} width={bw * 0.56} height={hb} fill="var(--danger)" />
          </g>
        );
      })}
      <line x1={0} x2={w} y1={base} y2={base} stroke="var(--rule)" />
      {split !== undefined && <line x1={split * bw} x2={split * bw} y1={0} y2={base} stroke="var(--rule)" strokeDasharray="3 3" />}
      {labels.map((l, i) =>
        l ? (
          <text key={i} x={i * bw + bw / 2} y={height - 4} {...LABEL} textAnchor="middle">
            {l}
          </text>
        ) : null,
      )}
    </svg>
  );
}
