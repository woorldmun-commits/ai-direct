"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Recommendation, TodayResponse, UserAction } from "@/lib/contract";
import { RECOMMENDATIONS } from "@/lib/demo";
import { applyAction, buildToday, sortForList, withAllowed, type ActionPayload, type SourcesScenario } from "@/lib/demo-backend";
import { PAST_RECOMMENDATIONS } from "@/lib/demo-history";

/**
 * Demo data source. With the real API, `recs` comes from `GET /recommendations` and `today` from `GET /today`,
 * and `act` becomes `POST /recommendations/{id}/actions` — the screens keep the same contract shapes.
 * Decisions live in memory and reset on reload; nothing is ever changed in an ad account.
 */
interface DemoState {
  /** Current recommendations of the last audit (backend order). */
  active: Recommendation[];
  /** Every recommendation, including finished cycles (for «История решений»). */
  all: Recommendation[];
  get: (id: string) => Recommendation | undefined;
  act: (id: string, action: UserAction, payload?: ActionPayload) => void;
  /** Demo only: put a recommendation back to its initial state. */
  reset: (id: string) => void;
  today: (sources: SourcesScenario) => TodayResponse;
  whyId: string | null;
  openWhy: (id: string) => void;
  closeWhy: () => void;
}

const Ctx = createContext<DemoState | null>(null);
const INITIAL = [...RECOMMENDATIONS, ...PAST_RECOMMENDATIONS];
const ACTIVE_IDS = new Set(RECOMMENDATIONS.map((r) => r.id));

export function DemoProvider({ children }: { children: ReactNode }) {
  const [recs, setRecs] = useState<Record<string, Recommendation>>(() => Object.fromEntries(INITIAL.map((r) => [r.id, r])));
  const [whyId, setWhyId] = useState<string | null>(null);

  const act = useCallback((id: string, action: UserAction, payload?: ActionPayload) => {
    setRecs((s) => (s[id] ? { ...s, [id]: applyAction(s[id], action, payload) } : s));
  }, []);

  const reset = useCallback((id: string) => {
    const initial = INITIAL.find((r) => r.id === id);
    if (initial) setRecs((s) => ({ ...s, [id]: initial }));
  }, []);

  // Opening the passport sends `view`: new → requires_decision.
  const openWhy = useCallback(
    (id: string) => {
      setWhyId(id);
      act(id, "view");
    },
    [act],
  );

  const value = useMemo<DemoState>(() => {
    const all = Object.values(recs).map(withAllowed);
    const active = sortForList(all.filter((r) => ACTIVE_IDS.has(r.id)));
    return {
      active,
      all,
      get: (id) => all.find((r) => r.id === id),
      act,
      reset,
      today: (sources) => buildToday(all, sources),
      whyId,
      openWhy,
      closeWhy: () => setWhyId(null),
    };
  }, [recs, act, reset, whyId, openWhy]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo(): DemoState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider>");
  return v;
}
