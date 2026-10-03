import { AlertTriangle, ArrowDownRight, ArrowUpRight, CircleSlash, Database, LayoutGrid, Search } from "lucide-react";
import type { ReactNode } from "react";
import { PRIORITY_LABEL, STATUS_LABEL, type Platform, type Priority, type RecStatus } from "@/lib/demo";
import { rub, signed } from "@/lib/site";

export function Logo({ light = false, size = 28 }: { light?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2 font-bold tracking-tight" style={{ fontSize: size * 0.66 }}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
        <path d="M4 26 13 6h5L9 26z" fill={light ? "#ffffff" : "var(--text)"} />
        <path d="M14 26 23 6h5l-9 20z" fill={light ? "#b8beff" : "var(--brand)"} />
      </svg>
      <span className={light ? "text-white" : "text-text"}>AdPilot</span>
    </span>
  );
}

/** Money type (PRD §5): fact «Потрачено», estimate «Потери ≈ / Можно сэкономить ≈», measured «Сэкономлено ≈». */
export type MoneyKind = "fact" | "loss" | "saveable" | "saved";

const KIND_CLASS: Record<MoneyKind, string> = {
  fact: "u-fact",
  loss: "u-est text-danger",
  saveable: "u-est",
  saved: "u-total text-success",
};

/** `bare` drops the ≈ sign when the row label already carries it («Потери ≈»). */
export function Amount({ value, kind, className = "", bare = false }: { value: number; kind: MoneyKind; className?: string; bare?: boolean }) {
  return (
    <span className={`money ${KIND_CLASS[kind]} ${className}`}>
      {kind !== "fact" && !bare && <span className="mr-[0.18em] font-normal opacity-80">≈</span>}
      {rub(value)}
    </span>
  );
}

/** One line of the statement: name, dot leader, amount. */
export function LedgerLine({ label, note, children, size = "md" }: { label: ReactNode; note?: ReactNode; children: ReactNode; size?: "md" | "lg" }) {
  return (
    <div className="py-2.5">
      <div className="flex items-baseline">
        <span className={size === "lg" ? "text-[17px] font-semibold" : "font-medium"}>{label}</span>
        <span className="leader" aria-hidden />
        <span className={size === "lg" ? "text-[30px] leading-none md:text-[40px]" : "text-[17px]"}>{children}</span>
      </div>
      {note && <p className="caption mt-1">{note}</p>}
    </div>
  );
}

/** The approval stamp: decision recorded by a human. */
export function Stamp({ text, sub, animate = false, tone = "brand" }: { text: string; sub?: string; animate?: boolean; tone?: "brand" | "success" | "muted" }) {
  const color = tone === "success" ? "var(--success)" : tone === "muted" ? "var(--muted)" : "var(--brand)";
  return (
    <span
      className={`inline-flex -rotate-[8deg] flex-col items-center px-2.5 py-1 leading-none ${animate ? "anim-stamp" : ""}`}
      style={{ color, border: `2px solid ${color}`, outline: `1px solid ${color}`, outlineOffset: 2, borderRadius: 3 }}
    >
      <span className="text-[12px] font-extrabold tracking-[0.12em] uppercase">{text}</span>
      {sub && <span className="mt-1 font-mono text-[10px]">{sub}</span>}
    </span>
  );
}

const STATUS_TONE: Record<RecStatus, string> = {
  new: "text-text",
  needs_decision: "text-danger",
  applied: "text-success",
  checked: "text-success",
  postponed: "text-muted",
  rejected: "text-muted line-through",
};

export function StatusMark({ status }: { status: RecStatus }) {
  return <span className={`badge ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}

const PRIORITY_TONE: Record<Priority, string> = {
  critical: "text-danger",
  medium: "text-warning",
  low: "text-muted",
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <span className={`badge ${PRIORITY_TONE[priority]}`}>{PRIORITY_LABEL[priority]}</span>;
}

export function PlatformIcon({ platform }: { platform: Platform }) {
  const Icon = platform === "search" ? Search : LayoutGrid;
  return <Icon size={14} className="shrink-0 text-muted" aria-label={platform === "search" ? "Поиск" : "РСЯ"} />;
}

/** Change against the previous period. `goodWhenDown` flips colors for costs and losses. */
export function Delta({ value, goodWhenDown = false }: { value: number; goodWhenDown?: boolean }) {
  const good = goodWhenDown ? value < 0 : value > 0;
  const Icon = value >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`money inline-flex items-center gap-0.5 text-[13px] ${value === 0 ? "text-muted" : good ? "text-success" : "text-danger"}`}>
      <Icon size={14} strokeWidth={2.4} />
      {signed(value)}%
    </span>
  );
}

export function DemoBadge({ className = "" }: { className?: string }) {
  return <span className={`badge text-warning ${className}`}>ДЕМО-ДАННЫЕ</span>;
}

/** Document heading: title on a heavy rule, requisites on the right. */
export function PageHeader({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b-2 border-text pb-3">
      <div className="min-w-0">
        <h1 className="text-[28px] leading-tight font-bold tracking-[-0.02em] text-balance md:text-[34px]">{title}</h1>
        {sub && <p className="mt-1 max-w-[70ch] text-muted">{sub}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-x-5 gap-y-2">{children}</div>}
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
  const tone = kind === "error" ? "text-danger" : kind === "insufficient" ? "text-warning" : "text-muted";
  return (
    <div className="flex items-start gap-3 border border-dashed border-rule p-4">
      <Icon size={18} className={`mt-0.5 shrink-0 ${tone}`} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        {text && <p className="mt-0.5 max-w-[70ch] text-sm text-muted">{text}</p>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

/** A part of the form: caption on a thin rule. */
export function Section({ title, aside, children, id }: { title: string; aside?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section aria-labelledby={id ? `${id}-t` : undefined} id={id} className="scroll-mt-24">
      <div className="flex items-baseline justify-between gap-3 border-b border-rule pb-1.5">
        <h2 id={id ? `${id}-t` : undefined} className="text-[15px] font-bold">
          {title}
        </h2>
        {aside && <div className="text-sm">{aside}</div>}
      </div>
      {children}
    </section>
  );
}
