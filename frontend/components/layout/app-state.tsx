"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Recommendation } from "@/lib/types/domain";

export type Decision = "approve" | "postpone" | "reject" | "checked";
export interface DecisionLog {
  id: string;
  recId: string;
  title: string;
  campaign: string;
  decision: Decision;
  at: string;
}
interface Toast {
  id: number;
  text: string;
}

interface AppState {
  recs: Recommendation[];
  decide: (recId: string, d: Decision) => void;
  log: DecisionLog[];
  evidenceId: string | null;
  openEvidence: (id: string | null) => void;
  approvalId: string | null;
  openApproval: (id: string | null) => void;
  workspace: string;
  setWorkspace: (id: string) => void;
  toasts: Toast[];
  notify: (text: string) => void;
}

const Ctx = createContext<AppState | null>(null);

// Demo: decisions live in memory and reset on reload. Nothing is sent to an ad account.
export function AppStateProvider({ children }: { children: ReactNode }) {
  const [recs, setRecs] = useState(api.recommendations);
  const [log, setLog] = useState<DecisionLog[]>([]);
  const [evidenceId, openEvidence] = useState<string | null>(null);
  const [approvalId, openApproval] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState(api.workspaces()[0].id);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const notify = useCallback((text: string) => {
    const id = Date.now();
    setToasts((t) => [...t, { id, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const patch = useCallback((id: string, p: (r: Recommendation) => Partial<Recommendation>) => setRecs((all) => all.map((r) => (r.id === id ? { ...r, ...p(r) } : r))), []);

  const decide = useCallback(
    (recId: string, d: Decision) => {
      const rec = recs.find((r) => r.id === recId);
      if (!rec) return;
      const at = new Date().toISOString();
      const user = api.user().fullName;
      setLog((l) => [{ id: `${recId}-${at}`, recId, title: rec.action ?? rec.title, campaign: rec.campaign, decision: d, at }, ...l]);
      if (d === "approve") {
        patch(recId, () => ({ status: "approved", execution: { mode: null, verification: "pending", approved_by: user, approved_at: at } }));
        notify("Подтверждено. Изменение отправлено в Яндекс Директ (демо).");
        // Simulated API execution; the real one is async (202 + polling, API_CONTRACT §5).
        setTimeout(() => patch(recId, (r) => ({ status: "applied", execution: { ...r.execution, mode: "api", verification: "confirmed" } })), 1500);
      } else if (d === "checked") {
        patch(recId, () => ({ status: "applied", execution: { mode: "none", verification: "not_required", approved_by: user, approved_at: at } }));
        notify("Отмечено как проверенное.");
      } else {
        patch(recId, () => ({ status: d === "postpone" ? "postponed" : "rejected" }));
        notify(d === "postpone" ? "Рекомендация отложена на 7 дней." : "Рекомендация отклонена. Изменений не будет.");
      }
    },
    [recs, patch, notify],
  );

  const value = useMemo<AppState>(
    () => ({ recs, decide, log, evidenceId, openEvidence, approvalId, openApproval, workspace, setWorkspace, toasts, notify }),
    [recs, decide, log, evidenceId, approvalId, workspace, toasts, notify],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside <AppStateProvider>");
  return v;
}

export const isOpenRec = (r: Recommendation) => (r.status === "new" || r.status === "requires_decision") && r.safety.verdict !== "blocked";
