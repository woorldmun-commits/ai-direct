import { AlertTriangle, CheckCircle2, CircleSlash, Info, TrendingDown } from "lucide-react";
import type { ReactNode } from "react";
import type { AgentStatus, RecStatus, Recommendation, Severity } from "@/lib/types/domain";

export type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info";

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  brand: "bg-brand-soft text-brand",
  success: "bg-success-soft text-success-ink",
  warning: "bg-warning-soft text-warning-ink",
  danger: "bg-danger-soft text-danger-ink",
  info: "bg-[#eff6ff] text-[#1d4ed8]",
};
const DOT: Record<Tone, string> = {
  neutral: "bg-subtle",
  brand: "bg-brand",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-sky",
};

export function Badge({ tone = "neutral", dot = false, children, className = "" }: { tone?: Tone; dot?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium whitespace-nowrap ${TONE[tone]} ${className}`}>
      {dot && <span className={`size-1.5 rounded-full ${DOT[tone]}`} aria-hidden />}
      {children}
    </span>
  );
}

export const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  high: { label: "Высокий", tone: "danger" },
  medium: { label: "Средний", tone: "warning" },
  low: { label: "Низкий", tone: "brand" },
};

/** Round severity mark used in problem lists (reference: colored circle with an icon). */
export function SeverityIcon({ severity, blocked = false, done = false }: { severity: Severity; blocked?: boolean; done?: boolean }) {
  const [Icon, cls] = done
    ? [CheckCircle2, "bg-success-soft text-success"]
    : blocked
      ? [CircleSlash, "bg-surface-2 text-muted"]
      : severity === "high"
        ? [AlertTriangle, "bg-danger-soft text-danger"]
        : severity === "medium"
          ? [TrendingDown, "bg-warning-soft text-warning"]
          : [Info, "bg-brand-soft text-violet"];
  return (
    <span className={`grid size-9 shrink-0 place-items-center rounded-full ${cls}`} aria-label={done ? "Выполнено" : blocked ? "Заблокировано" : `Приоритет: ${SEVERITY[severity].label}`}>
      <Icon size={17} strokeWidth={2.2} />
    </span>
  );
}

const STATUS: Record<RecStatus, { label: string; tone: Tone }> = {
  new: { label: "Новая", tone: "brand" },
  requires_decision: { label: "Требует решения", tone: "warning" },
  approved: { label: "Одобрена", tone: "info" },
  applied: { label: "Применено", tone: "success" },
  postponed: { label: "Отложена", tone: "neutral" },
  rejected: { label: "Отклонена", tone: "neutral" },
  failed: { label: "Не выполнена", tone: "danger" },
  cancelled: { label: "Отменена", tone: "neutral" },
};

/** API_CONTRACT §3.3: an applied recommendation is labeled by how it was executed. */
export function RecStatusBadge({ rec }: { rec: Pick<Recommendation, "status" | "execution" | "safety"> }) {
  if (rec.safety.verdict === "blocked") return <Badge tone="neutral">Недостаточно данных</Badge>;
  if (rec.status === "applied") {
    const { mode, verification } = rec.execution;
    if (mode === "none") return <Badge tone="success">Проверено</Badge>;
    if (mode === "manual") return <Badge tone={verification === "confirmed" ? "success" : "warning"}>{verification === "confirmed" ? "Выполнено вручную · подтверждено" : "Выполнено вручную · не подтверждено"}</Badge>;
  }
  const s = STATUS[rec.status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export const AGENT_STATUS: Record<AgentStatus, { label: string; tone: Tone }> = {
  active: { label: "Активен", tone: "brand" },
  waiting: { label: "Ожидание", tone: "warning" },
  passed: { label: "Пройдено", tone: "success" },
  blocked: { label: "Заблокировано", tone: "danger" },
};
