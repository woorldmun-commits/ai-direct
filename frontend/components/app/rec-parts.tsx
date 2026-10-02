import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { ParamView, ValueView } from "@/components/value-view";
import type { Measurement, Recommendation, RecommendationAction, ZeroConversionCheck } from "@/lib/contract";
import { formatMoment, formatPeriod, formatRuleVersion, PARTIAL_NOTE, sourceLabel, type Value } from "@/lib/value";

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

/** What the human changes by hand in Direct (`action`, API_CONTRACT §5): one text per action type. */
export function ActionText({ action }: { action: RecommendationAction }) {
  switch (action.type) {
    case "decrease_bid":
      return (
        <>
          Снизить ставку на <ParamView amount={action.change_pct.replace(/^-/, "")} unit="pct" />
        </>
      );
    case "exclude_placements": {
      const named = action.placements.filter((p) => p.name).map((p) => p.name);
      const list = named.slice(0, 3).join(", ") + (named.length > 3 ? ` и ещё ${action.placements_count - 3}` : "");
      return (
        <>
          Исключить площадки без конверсий ({action.placements_count}){list && `: ${list}`}
        </>
      );
    }
    case "investigate_zero_conversions":
      return (
        <>
          Проверить: {action.checks.map((c) => CHECK_LABEL[c]).join(", ")}
          {action.suggest === "set_target_cpa" && "; укажите целевой CPA"}
        </>
      );
    case "investigate_cpa_growth":
      return <>Проверить причину роста CPA{action.suggest === "set_target_cpa" && "; укажите целевой CPA"}</>;
  }
}

const CHECK_LABEL: Record<ZeroConversionCheck, string> = {
  conversion_goals: "цели и учёт конверсий",
  strategy: "стратегию и цель CPA",
  search_queries_negative_keywords: "поисковые запросы и минус-фразы",
};

/** Time of the calculation of the current version (`computed_at`, API_CONTRACT §5). */
export const calculatedAt = (r: Pick<Recommendation, "computed_at">): string => r.computed_at;

/** «Откуда это число?» — period, campaign, spend, conversions, rule and version, calculation time, data used. */
export function Origin({ r, v }: { r: Recommendation; v: Value }) {
  const { cost, conversions } = r.evidence.facts;
  const rows: [string, ReactNode][] = [
    ["Период", formatPeriod(v.period)],
    ["Кампании", r.object.name],
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
