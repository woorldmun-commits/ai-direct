import type { RecStatus } from "@/lib/contract";

/** API_CONTRACT §5 `filter`; the default is new + requires_decision + accepted. Shared by the server page and the screen. */
export type RecFilter = "active" | "all" | "new" | "requires_decision" | "accepted" | "done" | "postponed" | "rejected";

export const TABS: { key: RecFilter; label: string; match: (s: RecStatus) => boolean }[] = [
  { key: "active", label: "Активные", match: (s) => s === "new" || s === "requires_decision" || s === "accepted" },
  { key: "requires_decision", label: "Требуют решения", match: (s) => s === "new" || s === "requires_decision" },
  { key: "accepted", label: "Приняты к выполнению", match: (s) => s === "accepted" },
  { key: "done", label: "Выполнены", match: (s) => s === "applied" },
  { key: "postponed", label: "Отложены", match: (s) => s === "postponed" },
  { key: "rejected", label: "Отклонены", match: (s) => s === "rejected" },
  { key: "all", label: "Все", match: () => true },
];

export const parseRecFilter = (v: unknown): RecFilter => (TABS.some((t) => t.key === v) ? (v as RecFilter) : "active");
