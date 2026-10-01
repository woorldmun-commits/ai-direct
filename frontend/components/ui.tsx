import { AlertTriangle, CircleSlash, Database, LayoutGrid, Search, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { PRIORITY_LABEL, type Platform, type Priority } from "@/lib/demo";
import { signed } from "@/lib/site";

export function Logo({ light = false, size = 28 }: { light?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2 font-bold tracking-tight" style={{ fontSize: size * 0.68 }}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
        <path d="M4 26 13 6h5L9 26z" fill={light ? "#39BFA0" : "#0D6B5B"} />
        <path d="M14 26 23 6h5l-9 20z" fill={light ? "#7FE0C6" : "#39BFA0"} />
      </svg>
      <span className={light ? "text-white" : "text-text"}>AdPilot</span>
    </span>
  );
}

const PRIORITY_STYLE: Record<Priority, string> = {
  critical: "bg-danger-bg text-danger",
  medium: "bg-warning-bg text-warning",
  low: "bg-info-bg text-info",
};
const PRIORITY_DOT: Record<Priority, string> = {
  critical: "bg-danger",
  medium: "bg-warning",
  low: "bg-info",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return (
    <span className={`badge ${PRIORITY_STYLE[priority]}`}>
      <span className={`size-1.5 rounded-full ${PRIORITY_DOT[priority]}`} />
      {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function PriorityIcon({ priority, size = 36 }: { priority: Priority; size?: number }) {
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full ${PRIORITY_STYLE[priority]}`}
      style={{ width: size, height: size }}
    >
      <AlertTriangle size={size * 0.45} strokeWidth={2.2} />
    </span>
  );
}

export function PlatformIcon({ platform }: { platform: Platform }) {
  const Icon = platform === "search" ? Search : LayoutGrid;
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted" title={platform === "search" ? "Поиск" : "РСЯ"}>
      <Icon size={15} />
    </span>
  );
}

/** Change badge. `goodWhenDown` flips colors for costs and losses. */
export function Delta({ value, goodWhenDown = false }: { value: number; goodWhenDown?: boolean }) {
  const good = goodWhenDown ? value < 0 : value > 0;
  const Icon = value >= 0 ? TrendingUp : TrendingDown;
  return (
    <span className={`badge ${good ? "bg-success-bg text-success" : "bg-danger-bg text-danger"}`}>
      <Icon size={12} />
      {signed(value)}%
    </span>
  );
}

export function DemoBadge({ className = "" }: { className?: string }) {
  return (
    <span className={`badge border border-warning/30 bg-warning-bg text-warning tracking-wide ${className}`}>ДЕМО-ДАННЫЕ</span>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[28px] leading-tight font-bold tracking-tight md:text-[32px]">{title}</h1>
        {sub && <p className="mt-1 text-muted">{sub}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

const STATE_ICON = { empty: Database, insufficient: CircleSlash, error: AlertTriangle };

export function StateBox({
  kind,
  title,
  text,
  action,
}: {
  kind: keyof typeof STATE_ICON;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  const Icon = STATE_ICON[kind];
  const tone = kind === "error" ? "bg-danger-bg text-danger" : kind === "insufficient" ? "bg-warning-bg text-warning" : "bg-surface-2 text-muted";
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-dashed border-line p-4">
      <span className={`grid size-9 shrink-0 place-items-center rounded-full ${tone}`}>
        <Icon size={16} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        {text && <p className="mt-0.5 text-sm text-muted">{text}</p>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function Approx({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span className={`money ${className}`}>
      <span className="mr-1 font-semibold opacity-70">≈</span>
      {children}
    </span>
  );
}
