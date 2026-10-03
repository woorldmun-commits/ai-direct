import type { ReactNode } from "react";

/** AdPilot mark: a stylised «A» flight path in the brand gradient. */
export function Logo({ dark = false, size = 28, withText = true }: { dark?: boolean; size?: number; withText?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2" aria-label="AdPilot">
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
        <defs>
          <linearGradient id="ap-g" x1="4" y1="28" x2="28" y2="4" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3B82F6" />
            <stop offset="0.55" stopColor="#5B5BF7" />
            <stop offset="1" stopColor="#7C5CFF" />
          </linearGradient>
        </defs>
        <path d="M14.2 4.5c.7-1.4 2.9-1.4 3.6 0l10 21.3c.6 1.3-.8 2.7-2.1 2l-8.8-4.6a2 2 0 0 0-1.8 0l-8.8 4.6c-1.3.7-2.7-.7-2.1-2z" fill="url(#ap-g)" />
        <path d="M16 11.5 21.4 23l-4.5-2.3a2 2 0 0 0-1.8 0L10.6 23z" fill={dark ? "#07111f" : "#ffffff"} opacity="0.92" />
      </svg>
      {withText && <span className={`text-[18px] font-bold tracking-[-0.02em] ${dark ? "text-white" : "text-text"}`}>AdPilot</span>}
    </span>
  );
}

export function Avatar({ initials, size = 32 }: { initials: string; size?: number }) {
  return (
    <span className="grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#7c5cff] to-[#3b82f6] font-semibold text-white" style={{ width: size, height: size, fontSize: size * 0.38 }} aria-hidden>
      {initials}
    </span>
  );
}

export function DemoBadge() {
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-[#fedf89] bg-warning-soft px-2.5 text-[11px] font-semibold tracking-wide text-warning-ink uppercase" title="Все значения на экране — демонстрационные">
      <span className="size-1.5 rounded-full bg-warning" aria-hidden /> Демо-данные
    </span>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[24px] leading-8 font-semibold tracking-[-0.02em]">{title}</h1>
        {sub && <p className="mt-1 text-[14px] text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Usage against an entitlement: «5 из 10». `limit = null` — not limited. */
export function Meter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const tone = pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warning" : "bg-brand";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-[13px]">
        <span className="text-muted">{label}</span>
        <span className="num font-semibold">
          {used} <span className="font-normal text-subtle">{limit === null ? "· без лимита" : `из ${limit}`}</span>
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label={label} aria-valuenow={used} aria-valuemin={0} aria-valuemax={limit ?? undefined}>
        {limit !== null && <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />}
      </div>
    </div>
  );
}
