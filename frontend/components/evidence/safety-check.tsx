import { CheckCircle2, CircleAlert, CircleX, ShieldCheck, ShieldOff, ShieldQuestion } from "lucide-react";
import type { CheckStatus, SafetyCheck } from "@/lib/types/domain";

const ICON: Record<CheckStatus, [typeof CheckCircle2, string]> = {
  passed: [CheckCircle2, "text-success"],
  warning: [CircleAlert, "text-warning"],
  failed: [CircleX, "text-danger"],
};

export const VERDICT = {
  allowed: { label: "Рекомендация разрешена", icon: ShieldCheck, cls: "bg-success-soft text-success-ink" },
  review_only: { label: "Только ручная проверка", icon: ShieldQuestion, cls: "bg-warning-soft text-warning-ink" },
  blocked: { label: "Вывод заблокирован", icon: ShieldOff, cls: "bg-danger-soft text-danger-ink" },
} as const;

export function SafetyVerdict({ safety }: { safety: SafetyCheck }) {
  const v = VERDICT[safety.verdict];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-semibold ${v.cls}`}>
      <v.icon size={14} aria-hidden /> {v.label}
    </span>
  );
}

export function SafetyCheckList({ safety, dense = false }: { safety: SafetyCheck; dense?: boolean }) {
  return (
    <div>
      <ul className={dense ? "space-y-1.5" : "space-y-2.5"}>
        {safety.checks.map((c) => {
          const [Icon, cls] = ICON[c.status];
          return (
            <li key={c.id} className="flex items-start gap-2.5 text-[13px]">
              <Icon size={16} className={`mt-0.5 shrink-0 ${cls}`} aria-label={c.status === "passed" ? "Пройдено" : c.status === "warning" ? "Предупреждение" : "Не пройдено"} />
              <span className="min-w-0">
                <span className="font-medium">{c.label}</span>
                {!dense && <span className="block text-[12px] text-muted">{c.detail}</span>}
              </span>
            </li>
          );
        })}
      </ul>
      {safety.reason && <p className={`mt-3 rounded-lg px-3 py-2 text-[13px] font-medium ${VERDICT[safety.verdict].cls}`}>{safety.reason}</p>}
    </div>
  );
}
