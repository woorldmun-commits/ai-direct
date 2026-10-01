"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { PROBLEMS, STATUS_LABEL, type Problem, type RecStatus } from "@/lib/demo";

interface UserAction {
  id: string;
  title: string;
  status: RecStatus;
  at: string;
}

interface DemoState {
  problems: Problem[];
  setStatus: (id: string, status: RecStatus) => void;
  actions: UserAction[];
  whyId: string | null;
  openWhy: (id: string) => void;
  closeWhy: () => void;
}

const Ctx = createContext<DemoState | null>(null);

// Demo only: decisions live in memory and reset on reload. Nothing is sent anywhere.
export function DemoProvider({ children }: { children: ReactNode }) {
  const [statuses, setStatuses] = useState<Record<string, RecStatus>>(() =>
    Object.fromEntries(PROBLEMS.map((p) => [p.id, p.status])),
  );
  const [actions, setActions] = useState<UserAction[]>([]);
  const [whyId, setWhyId] = useState<string | null>(null);

  const setStatus = useCallback((id: string, status: RecStatus) => {
    setStatuses((s) => ({ ...s, [id]: status }));
    const p = PROBLEMS.find((x) => x.id === id);
    if (!p) return;
    const at = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    setActions((a) => [{ id, title: `${STATUS_LABEL[status]}: ${p.recommendation.toLowerCase()}`, status, at }, ...a]);
  }, []);

  const value = useMemo<DemoState>(
    () => ({
      problems: PROBLEMS.map((p) => ({ ...p, status: statuses[p.id] })),
      setStatus,
      actions,
      whyId,
      openWhy: setWhyId,
      closeWhy: () => setWhyId(null),
    }),
    [statuses, setStatus, actions, whyId],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo(): DemoState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider>");
  return v;
}
