import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { ParamView, ValueView } from "@/components/value-view";
import {
  objectLabel,
  type BidLever,
  type ExcludePlacementsAction,
  type ExposureSummary,
  type InvestigateTopic,
  type Measurement,
  type Recommendation,
  type ZeroConversionCheck,
} from "@/lib/contract";
import { formatMoment, formatPeriod, formatRuleVersion, isPositive, PARTIAL_NOTE, sourceLabel, type Value } from "@/lib/value";

// Shared pieces of a recommendation: action text, fact labels, «Откуда это число?», measurement.

export const FACT_LABEL: Record<string, string> = {
  cost: "Расход",
  conversions: "Конверсии",
  cpa: "CPA",
  cpc: "Цена клика",
  cvr: "Конверсия",
  clicks: "Клики",
  target_cpa: "Целевой CPA",
  deviation_pct: "Отклонение от цели",
  placements: "Площадок",
};

export const LIMITATION_LABEL: Record<string, string> = {
  strategy_unknown: "Стратегия кампании неизвестна — проверьте, управляется ли ставка вручную",
};

export const POLICY_REASON_LABEL: Record<string, string> = {
  data_partial: "данные за последние дни ещё уточняются",
  data_sufficiency_low: "мало данных",
  data_sufficiency_medium: "данных впритык — проверьте вручную",
  strategy_unknown: "стратегия неизвестна",
};

const pct = (changePct: string) => <ParamView amount={changePct.replace(/^-/, "")} unit="pct" />;

/** «site-1, site-2, site-3 и ещё N»: N counts from `placements_count`, not from the names we have. */
function placementList(a: ExcludePlacementsAction): string {
  const shown = a.placements.flatMap((p) => (p.name ? [p.name] : [])).slice(0, 3);
  const rest = a.placements_count - shown.length;
  if (!shown.length) return "";
  return shown.join(", ") + (rest > 0 ? ` и ещё ${rest}` : "");
}

const TOPIC_TITLE: Record<InvestigateTopic, string> = {
  high_cpa: "Проверить причину высокого CPA",
  zero_conv_campaign: "Проверить, почему нет конверсий",
  zero_conv_placements: "Проверить площадки без конверсий",
};

/**
 * What the human does by hand in Direct (`action`, API_CONTRACT §5), in line with the policy level:
 * `inspect_only` is always «Проверить …» (never a settings change, even if an older server sent one);
 * `review` with `levers` names both ways; `action = null` (an unknown shape) sends to the evidence.
 */
export function ActionText({ r }: { r: Pick<Recommendation, "action" | "action_level"> }) {
  const { action } = r;
  if (!action) return <>Действие недоступно, см. доказательства</>;
  const inspect = r.action_level === "inspect_only";
  switch (action.type) {
    case "investigate":
      return (
        <>
          {TOPIC_TITLE[action.topic] ?? "Проверить"}
          {action.checks.length > 0 && `: ${action.checks.map((c) => CHECK_LABEL[c] ?? c).join(", ")}`}
        </>
      );
    case "decrease_bid":
      if (inspect) return <>{TOPIC_TITLE.high_cpa} — ставку до проверки не меняйте</>;
      return action.levers?.length ? <Levers levers={action.levers} /> : <>Снизить ставку на {pct(action.change_pct)}</>;
    case "exclude_placements": {
      const list = placementList(action);
      return (
        <>
          {inspect ? TOPIC_TITLE.zero_conv_placements : "Проверить и исключить площадки без конверсий"} ({action.placements_count})
          {list && `: ${list}`}
        </>
      );
    }
    case "investigate_zero_conversions":
      return (
        <>
          Проверить: {action.checks.map((c) => CHECK_LABEL[c] ?? c).join(", ")}
          {action.suggest === "set_target_cpa" && "; укажите целевой CPA"}
        </>
      );
    case "investigate_cpa_growth":
      return <>Проверить причину роста CPA{action.suggest === "set_target_cpa" && "; укажите целевой CPA"}</>;
  }
}

/** Both levers of `decrease_bid` when the campaign's strategy is unknown: the human picks the one that fits. */
function Levers({ levers }: { levers: BidLever[] }) {
  const manual = levers.find((l) => l.strategy === "manual");
  const auto = levers.find((l) => l.strategy === "auto");
  return (
    <>
      {manual && (
        <>Если ручные ставки — {manual.change_pct ? <>снизить ставку на {pct(manual.change_pct)}</> : manual.text}</>
      )}
      {manual && auto && "; "}
      {auto && <>{manual ? "если" : "Если"} автостратегия — {auto.text}</>}
    </>
  );
}

const CHECK_LABEL: Record<ZeroConversionCheck | string, string> = {
  conversion_goals: "цели и учёт конверсий",
  strategy: "стратегию и цель CPA",
  search_queries_negative_keywords: "поисковые запросы и минус-фразы",
  placements_audience: "что это за площадки и подходит ли их аудитория",
};

/** «часть суммы уже учтена в другой карточке» — from `exposure_overlap` (> 0), with the amount. */
export function OverlapNote({ r, className = "" }: { r: Pick<Recommendation, "exposure" | "exposure_overlap">; className?: string }) {
  const o = r.exposure_overlap;
  if (o.amount === null || !isPositive(o.amount)) return null;
  const whole = r.exposure.amount !== null && o.amount === r.exposure.amount;
  return (
    <span className={className}>
      {whole ? "Вся сумма уже учтена в другой карточке" : "Часть суммы уже учтена в другой карточке"}: <ValueView v={o} hint={false} />
      {" "}— в итог входит один раз
    </span>
  );
}

/** Caption of the «Можно сэкономить» total (ECONOMICS §3.6): an honest sum, and how many cards have an estimate. */
export function canSaveNote(s: Pick<ExposureSummary, "coverage">): string {
  const { included, unavailable } = s.coverage;
  const base = "Сумма оценок по карточкам, где оценка есть; по одной кампании — без двойного учёта.";
  return unavailable > 0 ? `${base} Оценка есть не для всех карточек (${included} из ${included + unavailable}).` : base;
}

/** A held problem (`data_sufficiency = insufficient`): shown, but its sum is not in the total. */
export function HeldNote({ r, className = "" }: { r: Pick<Recommendation, "data_sufficiency">; className?: string }) {
  if (r.data_sufficiency !== "insufficient") return null;
  return <span className={className}>Мало данных для оценки — в итог не входит, продолжаем наблюдать</span>;
}

/** Time of the calculation of the current version (`computed_at`, API_CONTRACT §5). */
export const calculatedAt = (r: Pick<Recommendation, "computed_at">): string => r.computed_at;

/** «Откуда это число?» — period, campaign, spend, conversions, rule and version, calculation time, data used. */
export function Origin({ r, v }: { r: Recommendation; v: Value }) {
  const { cost, conversions } = r.evidence.facts;
  const rows: [string, ReactNode][] = [
    ["Период", formatPeriod(v.period)],
    ["Кампании", objectLabel(r.object)],
    ["Кабинет", r.ad_account.login],
    ["Расход", cost ? <ValueView v={cost} /> : "не используется в расчёте"],
    ["Конверсии", conversions ? <ValueView v={conversions} /> : "не используются в расчёте"],
    ["Правило и версия", formatRuleVersion(v.rule_version ?? r.evidence.rule_version)],
    ["Формула", v.formula ?? "значение из источника без пересчёта"],
    ["Время расчёта", `${formatMoment(calculatedAt(r))} МСК`],
    ["Какие данные были", `${sourceLabel(v.source)} · ${v.data_status === "partial" ? PARTIAL_NOTE.toLowerCase() : "полные за период"}`],
  ];
  return (
    <details className="group mt-2 rounded-xl border border-line">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-semibold text-brand">
        Откуда это число?
        <ChevronDown size={14} className="text-muted transition-transform group-open:rotate-180" />
      </summary>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 px-3 pb-3 text-xs">
        {rows.map(([k, val]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd className={k === "Формула" || k === "Правило и версия" ? "font-mono" : ""}>{val}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

const VERDICT: Record<NonNullable<Measurement["verdict"]>, string> = {
  effect: "Эффект есть",
  no_effect: "Эффекта нет",
  not_confirmed: "Не подтверждено: CPA снизился, но конверсий стало меньше",
  insufficient: "Недостаточно данных для замера",
};

export const EVENT_LABEL: Record<string, string> = {
  created: "AdPilot нашёл проблему",
  seen_again: "Аудит подтвердил проблему",
  viewed: "Вы открыли рекомендацию",
  delivered: "Уведомление доставлено",
  accepted: "Вы приняли к выполнению",
  postponed: "Вы отложили",
  rejected: "Вы отклонили",
  recommendation_checked: "Вы проверили",
  manual_claimed: "Вы отметили «выполнено вручную»",
  verification_confirmed: "Сверка: изменение подтверждено по данным Директа",
  verification_not_confirmed: "Сверка: изменение в Директе не найдено",
  measured: "Замер через 7 дней завершён",
  measurement_skipped: "Замер пропущен",
};

export const SAVED_NOTE ="Расчётный эффект · сравнение 7 дней до и после без контрольной группы";

/** Result of the 7-day check (API_CONTRACT §7). */
export function MeasurementView({ m }: { m: Measurement }) {
  if (m.status === "pending") {
    return <p className="text-sm">Замер идёт: окно «после» — {formatPeriod(m.windows.after)}. Результат появится после его окончания.</p>;
  }
  if (m.status === "skipped") return <p className="text-sm text-muted">Замер пропущен: подписка или подключение были неактивны.</p>;
  const keys = Object.keys(m.before).filter((k) => m.after[k]);
  return (
    <div className="space-y-2 text-sm">
      <p className="font-semibold">{m.verdict ? VERDICT[m.verdict] : "Замер завершён"}</p>
      <ul className="space-y-1">
        {keys.map((k) => (
          <li key={k} className="flex flex-wrap items-center gap-x-2">
            <span className="text-muted">{FACT_LABEL[k] ?? k}:</span>
            <ValueView v={m.before[k]} /> <span className="text-muted">→</span> <ValueView v={m.after[k]} />
          </li>
        ))}
      </ul>
      {m.saved && (
        <p className="flex flex-wrap items-center gap-x-2">
          <span className="text-muted">Сэкономлено:</span>
          <ValueView v={m.saved} className="text-success" />
          {!m.counts_in_saved_total && <span className="text-xs text-muted">не входит в «Сэкономлено»: выполнение не подтверждено</span>}
        </p>
      )}
      <p className="text-xs text-muted">{SAVED_NOTE}.</p>
    </div>
  );
}
