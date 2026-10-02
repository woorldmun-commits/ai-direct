"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { PROBLEMS, STATUS_LABEL, type Problem, type RecStatus, type RejectReason } from "@/lib/demo";

interface UserAction {
  id: string;
  title: string;
  status: RecStatus;
  at: string;
}

export type DemoProblem = Problem & { rejectReason?: RejectReason };

interface DemoState {
  problems: DemoProblem[];
  setStatus: (id: string, status: RecStatus, reason?: RejectReason) => void;
  actions: UserAction[];
  whyId: string | null;
  openWhy: (id: string) => void;
  closeWhy: () => void;
}

const Ctx = createContext<DemoState | null>(null);

// Demo only: decisions live in memory and reset on reload. Nothing is sent anywhere,
// and nothing is ever changed in an ad account: the user makes changes by hand.
export function DemoProvider({ children }: { children: ReactNode }) {
  const [statuses, setStatuses] = useState<Record<string, RecStatus>>(() =>
    Object.fromEntries(PROBLEMS.map((p) => [p.id, p.status])),
  );
  const [reasons, setReasons] = useState<Record<string, RejectReason>>({});
  const [actions, setActions] = useState<UserAction[]>([]);
  const [whyId, setWhyId] = useState<string | null>(null);

  const setStatus = useCallback((id: string, status: RecStatus, reason?: RejectReason) => {
    setStatuses((s) => ({ ...s, [id]: status }));
    setReasons((r) => {
      const next = { ...r };
      if (status === "rejected" && reason) next[id] = reason;
      else delete next[id];
      return next;
    });
    const p = PROBLEMS.find((x) => x.id === id);
    if (!p) return;
    const at = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    const why = status === "rejected" && reason ? ` (причина: ${reason.toLowerCase()})` : "";
    setActions((a) => [{ id, title: `${STATUS_LABEL[status]}: ${p.recommendation.toLowerCase()}${why}`, status, at }, ...a]);
  }, []);

  // Opening the evidence marks a new recommendation as viewed.
  const openWhy = useCallback((id: string) => {
    setWhyId(id);
    setStatuses((s) => (s[id] === "new" ? { ...s, [id]: "viewed" } : s));
  }, []);

  const value = useMemo<DemoState>(
    () => ({
      problems: PROBLEMS.map((p) => ({ ...p, status: statuses[p.id], rejectReason: reasons[p.id] })),
      setStatus,
      actions,
      whyId,
      openWhy,
      closeWhy: () => setWhyId(null),
    }),
    [statuses, reasons, setStatus, actions, whyId, openWhy],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo(): DemoState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider>");
  return v;
}
