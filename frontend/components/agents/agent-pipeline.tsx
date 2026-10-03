import { Bot, BrainCircuit, Calculator, ClipboardCheck, Database, Gauge, MessageSquareText, Search, ShieldCheck, UserCheck } from "lucide-react";
import { AGENT_STATUS, Badge } from "@/components/ui/badge";
import type { Agent, AgentKind } from "@/lib/types/domain";

const ICON: Record<string, typeof Bot> = {
  collector: Database,
  audit: Search,
  safety: ShieldCheck,
  root: BrainCircuit,
  explain: MessageSquareText,
  engine: Calculator,
  human: UserCheck,
  measure: Gauge,
};
const TINT: Record<string, string> = {
  collector: "bg-[#eef0ff] text-brand",
  audit: "bg-[#eff6ff] text-sky",
  safety: "bg-success-soft text-success",
  root: "bg-[#f4f0ff] text-violet",
  explain: "bg-[#f4f0ff] text-violet",
  engine: "bg-[#eff6ff] text-sky",
  human: "bg-warning-soft text-warning",
  measure: "bg-[#eef0ff] text-brand",
};

export const KIND_LABEL: Record<AgentKind, { label: string; hint: string }> = {
  deterministic: { label: "Детерминированный", hint: "Правила и расчёты, без LLM" },
  llm: { label: "LLM", hint: "Только язык и рассуждение, без новых чисел" },
  human: { label: "Человек", hint: "Решение принимает пользователь" },
};

export function AgentIcon({ id, size = 36 }: { id: string; size?: number }) {
  const Icon = ICON[id] ?? ClipboardCheck;
  return (
    <span className={`grid shrink-0 place-items-center rounded-full ${TINT[id] ?? "bg-surface-2 text-muted"}`} style={{ width: size, height: size }} aria-hidden>
      <Icon size={size * 0.47} strokeWidth={2} />
    </span>
  );
}

/** Compact vertical flow for the «Сегодня» card. */
export function AgentFlow({ agents }: { agents: Agent[] }) {
  return (
    <ol className="relative">
      {agents.map((a, i) => (
        <li key={a.id} className="relative flex gap-3 pb-4 last:pb-0">
          {i < agents.length - 1 && <span className="absolute top-10 bottom-0 left-[17px] w-px bg-line" aria-hidden />}
          <AgentIcon id={a.id} />
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[13px] font-semibold">{a.name}</p>
              <Badge tone={AGENT_STATUS[a.status].tone}>{AGENT_STATUS[a.status].label}</Badge>
            </div>
            <p className="truncate text-[12px] text-muted">{a.last}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Full numbered pipeline for /agents. */
export function AgentPipeline({ agents }: { agents: Agent[] }) {
  return (
    <ol className="relative space-y-3">
      {agents.map((a, i) => (
        <li key={a.id} className="relative flex gap-4">
          <div className="flex flex-col items-center">
            <span className={`num grid size-7 shrink-0 place-items-center rounded-full border-2 text-[12px] font-semibold ${a.status === "active" ? "border-brand bg-brand text-white" : "border-line bg-surface text-muted"}`}>{i + 1}</span>
            {i < agents.length - 1 && <span className="mt-1 w-px flex-1 bg-line" aria-hidden />}
          </div>
          <div className={`mb-1 flex-1 rounded-2xl border p-4 ${a.status === "active" ? "border-[#c7c9fb] bg-[#fafaff]" : "border-line bg-surface"}`}>
            <div className="flex flex-wrap items-start gap-3">
              <AgentIcon id={a.id} size={40} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[15px] font-semibold">{a.name}</h3>
                  <span className="text-[13px] text-muted">— {a.role}</span>
                </div>
                <p className="mt-1 text-[13px] text-[#475467]">{a.description}</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone={a.kind === "llm" ? "brand" : a.kind === "human" ? "warning" : "neutral"}>{KIND_LABEL[a.kind].label}</Badge>
                <Badge tone={AGENT_STATUS[a.status].tone} dot>
                  {AGENT_STATUS[a.status].label}
                </Badge>
              </div>
            </div>
            <dl className="mt-3 grid gap-2 border-t border-line pt-3 text-[12px] sm:grid-cols-3">
              <div>
                <dt className="text-subtle">Вход</dt>
                <dd>{a.input}</dd>
              </div>
              <div>
                <dt className="text-subtle">Выход</dt>
                <dd>{a.output}</dd>
              </div>
              <div>
                <dt className="text-subtle">Последний запуск</dt>
                <dd>{a.last}</dd>
              </div>
            </dl>
          </div>
        </li>
      ))}
    </ol>
  );
}
