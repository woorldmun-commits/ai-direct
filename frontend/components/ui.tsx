import { AlertTriangle, CircleSlash, Database, LayoutGrid, Search } from "lucide-react";
import type { ReactNode } from "react";
import type { Platform } from "@/lib/demo";

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

export function PlatformIcon({ platform }: { platform: Platform }) {
  const Icon = platform === "search" ? Search : LayoutGrid;
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted" title={platform === "search" ? "Поиск" : "РСЯ"}>
      <Icon size={15} />
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
