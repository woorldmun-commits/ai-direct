"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { PROBLEMS, type Problem, type RecStatus } from "@/lib/demo";

export interface UserAction {
  id: string;
  title: string;
  status: RecStatus;
  at: string;
}

interface DemoState {
  problems: Problem[];
  decide: (id: string, status: RecStatus) => void;
  actions: UserAction[];
  /** Last decision made in this session: its stamp lands with the animation once. */
  lastStamped: string | null;
  whyId: string | null;
  openWhy: (id: string) => void;
  closeWhy: () => void;
  askOpen: boolean;
  setAskOpen: (open: boolean) => void;
}

const Ctx = createContext<DemoState | null>(null);

const VERB: Partial<Record<RecStatus, string>> = {
  applied: "Применено",
  checked: "Проверено",
  postponed: "Отложено",
  rejected: "Отклонено",
  needs_decision: "Возвращено к решению",
};

// Demo only: decisions live in memory and reset on reload. Nothing is sent anywhere.
export function DemoProvider({ children }: { children: ReactNode }) {
  const [statuses, setStatuses] = useState<Record<string, RecStatus>>(() =>
    Object.fromEntries(PROBLEMS.map((p) => [p.id, p.status])),
  );
  const [actions, setActions] = useState<UserAction[]>([]);
  const [lastStamped, setLastStamped] = useState<string | null>(null);
  const [whyId, setWhyId] = useState<string | null>(null);
  const [askOpen, setAskOpen] = useState(false);

  const decide = useCallback((id: string, status: RecStatus) => {
    const p = PROBLEMS.find((x) => x.id === id);
    if (!p) return;
    setStatuses((s) => ({ ...s, [id]: status }));
    setLastStamped(status === "applied" || status === "checked" ? id : null);
    const at = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    const title = `${VERB[status] ?? "Изменено"}: ${p.recommendation.charAt(0).toLowerCase()}${p.recommendation.slice(1)}`;
    setActions((a) => [{ id, title, status, at }, ...a]);
  }, []);

  const value = useMemo<DemoState>(
    () => ({
      problems: PROBLEMS.map((p) => ({ ...p, status: statuses[p.id] })),
      decide,
      actions,
      lastStamped,
      whyId,
      openWhy: setWhyId,
      closeWhy: () => setWhyId(null),
      askOpen,
      setAskOpen,
    }),
    [statuses, decide, actions, lastStamped, whyId, askOpen],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo(): DemoState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider>");
  return v;
}
