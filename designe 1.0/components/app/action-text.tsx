import { ParamView } from "@/components/value-view";
import type { CpaLever, InvestigateCheck, InvestigateTopic, PlacementRef, Recommendation } from "@/lib/contract";

// What the human does by hand in Direct (`action`, API_CONTRACT §5, backend/app/audit/present.py). The server sends
// codes only; every text is this dictionary.

const pct = (changePct: string) => <ParamView amount={changePct.replace(/^-/, "")} unit="pct" />;

const TOPIC_TITLE: Record<InvestigateTopic, string> = {
  high_cpa: "Проверить причину высокого CPA",
  zero_conv_campaign: "Проверить, почему нет конверсий",
  zero_conv_placements: "Проверить площадки без конверсий",
};

const CHECK_LABEL: Record<InvestigateCheck, string> = {
  conversion_goals: "цели и учёт конверсий",
  strategy: "стратегию и цель CPA",
  search_queries_negative_keywords: "поисковые запросы и минус-фразы",
  network_placements: "площадки РСЯ и их аудиторию",
};

/** «site-1, site-2, site-3 и ещё N»: N counts from `total`, not from the names we have. */
export function placementList(placements: PlacementRef[], total: number = placements.length): string {
  const shown = placements.flatMap((p) => (p.name ? [p.name] : [])).slice(0, 3);
  if (!shown.length) return "";
  const rest = total - shown.length;
  return shown.join(", ") + (rest > 0 ? ` и ещё ${rest}` : "");
}

const LEVER_TEXT: Record<CpaLever["lever"], string> = {
  decrease_bid: "снизить ставку на",
  lower_target_cpa: "снизить целевую цену конверсии",
  check_conversion_goals: "проверить цели конверсий",
};
const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Lever text from its code: «снизить ставку на N%», «снизить целевую цену конверсии», «проверить цели конверсий». */
function LeverText({ l, cap }: { l: CpaLever; cap: boolean }) {
  const text = LEVER_TEXT[l.lever] ?? l.lever;
  return (
    <>
      {cap ? capitalize(text) : text}
      {l.lever === "decrease_bid" && <> {pct(l.change_pct)}</>}
    </>
  );
}

function joinLevers(levers: CpaLever[], cap = false) {
  return levers.map((l, i) => (
    <span key={l.lever}>
      {i > 0 && " или "}
      <LeverText l={l} cap={cap && i === 0} />
    </span>
  ));
}

/** `lower_cpa`: levers grouped by strategy; with the strategy unknown both ways are named, the human picks. */
function Levers({ levers }: { levers: CpaLever[] }) {
  const manual = levers.filter((l) => l.strategy === "manual");
  const auto = levers.filter((l) => l.strategy === "auto");
  if (!levers.length) return <>Действие недоступно, см. доказательства</>;
  if (!manual.length || !auto.length) return <>{joinLevers(levers, true)}</>;
  return (
    <>
      Если ручные ставки — {joinLevers(manual)}; если автостратегия — {joinLevers(auto)}
    </>
  );
}

/**
 * The action in line with the policy level: `inspect_only` is always «Проверить …» (never a settings change, even
 * if a server sent one); `lower_cpa` names the levers; `action = null` (a shape the server could not present)
 * sends to the evidence.
 */
export function ActionText({ r }: { r: Pick<Recommendation, "action" | "action_level"> }) {
  const { action } = r;
  if (!action) return <>Действие недоступно, см. доказательства</>;
  const inspect = r.action_level === "inspect_only";
  switch (action.type) {
    case "investigate": {
      const list = action.placements ? placementList(action.placements) : "";
      // The placements topic already says «площадки»: its `network_placements` check would only repeat the title.
      const checks = action.checks.filter((c) => !(action.topic === "zero_conv_placements" && c === "network_placements"));
      return (
        <>
          {TOPIC_TITLE[action.topic] ?? "Проверить"}
          {action.placements && ` (${action.placements.length})`}
          {list && `: ${list}`}
          {checks.length > 0 && `${list ? "; проверьте " : ": "}${checks.map((c) => CHECK_LABEL[c] ?? c).join(", ")}`}
          {action.suggest === "set_target_cpa" && "; укажите целевой CPA"}
        </>
      );
    }
    case "lower_cpa":
      if (inspect) return <>{TOPIC_TITLE.high_cpa} — ставку до проверки не меняйте</>;
      return <Levers levers={action.levers} />;
    case "decrease_bid":
      if (inspect) return <>{TOPIC_TITLE.high_cpa} — ставку до проверки не меняйте</>;
      return <>Снизить ставку на {pct(action.change_pct)}</>;
    case "exclude_placements": {
      const list = placementList(action.placements, action.placements_count);
      return (
        <>
          {inspect ? TOPIC_TITLE.zero_conv_placements : "Проверить и исключить площадки без конверсий"} ({action.placements_count})
          {list && `: ${list}`}
        </>
      );
    }
    default:
      return <>Действие недоступно, см. доказательства</>;
  }
}
