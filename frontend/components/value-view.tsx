import { Info, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { useId } from "react";
import {
  CALCULATION_LABEL,
  formatAmount,
  formatPeriod,
  formatRuleVersion,
  formatValue,
  isNegative,
  isPositive,
  PARTIAL_NOTE,
  sourceLabel,
  type DecimalString,
  type Unit,
  type Value,
} from "@/lib/value";

/**
 * The only way to show a number (PRODUCT_SPEC §4.1). `actual` — plain, `estimated` — «≈» with «Как посчитано»
 * (formula, period, source, rule@version), `unavailable` — «Недостаточно данных» and a reason, never 0 or a dash.
 * `data_status = partial` gets a «уточняется» mark. Rendering `.amount` anywhere else is a lint error.
 *
 * «Как посчитано» uses the native `popover` attribute: no script, top layer (not clipped by cards).
 */
export function ValueView({
  v,
  className = "",
  caption = false,
  signed = false,
  reason,
  hint = true,
}: {
  v: Value;
  /** Classes for the number itself (size, tone). */
  className?: string;
  /** A line below: «Факт · Яндекс Директ · 1–30 сентября», plus the partial note in words. */
  caption?: boolean;
  /** Show «+» for positive values (deltas). */
  signed?: boolean;
  /** Why the value is unavailable and what to connect; the contract has no field for it. */
  reason?: string;
  /** `false` only for decorative previews (landing): hides the «Как посчитано» button. */
  hint?: boolean;
}) {
  const id = useId();
  const popId = `how-${id.replace(/:/g, "")}`;

  if (v.calculation_type === "unavailable") {
    return (
      <span className={caption ? "flex flex-col" : "inline"}>
        <span className={`font-semibold text-muted ${caption ? "" : "text-sm"}`} data-value="unavailable">
          {CALCULATION_LABEL.unavailable}
        </span>
        <span className={`text-xs text-muted ${caption ? "mt-0.5" : "ml-1"}`}>
          {caption ? "" : "· "}
          {reason ?? "Данных за период не хватает для расчёта"}
        </span>
      </span>
    );
  }

  const text = formatValue(v, { signed });
  const partial = v.data_status === "partial";
  const explain = hint && (v.calculation_type === "estimated" || v.formula);

  const number = (
    <span className="inline-flex items-baseline gap-1">
      <span className={`money whitespace-nowrap ${className}`} data-value={v.calculation_type}>
        {text ?? "Ошибка формата данных"}
      </span>
      {partial && !caption && (
        <span title={PARTIAL_NOTE} aria-label={PARTIAL_NOTE} className="inline-flex translate-y-[-1px] items-center text-warning">
          <RefreshCw size={11} aria-hidden />
        </span>
      )}
      {explain && !caption && (
        <button
          type="button"
          popoverTarget={popId}
          className="inline-flex translate-y-[-1px] items-center rounded text-muted hover:text-brand"
          aria-label="Как посчитано"
          title="Как посчитано"
        >
          <Info size={13} aria-hidden />
        </button>
      )}
    </span>
  );

  return (
    <>
      {caption ? (
        <span className="flex flex-col">
          {number}
          <span className="mt-0.5 text-xs text-muted">
            {CALCULATION_LABEL[v.calculation_type]} · {sourceLabel(v.source)} · {formatPeriod(v.period)}
            {explain && (
              <>
                {" · "}
                <button type="button" popoverTarget={popId} className="font-semibold text-brand underline-offset-2 hover:underline">
                  как посчитано
                </button>
              </>
            )}
          </span>
          {partial && <span className="mt-0.5 text-xs text-warning">{PARTIAL_NOTE}</span>}
        </span>
      ) : (
        number
      )}
      {explain && <HowCalculated id={popId} v={v} />}
    </>
  );
}

function HowCalculated({ id, v }: { id: string; v: Value }) {
  const rows: [string, string][] = [
    ["Тип", CALCULATION_LABEL[v.calculation_type]],
    ["Формула", v.formula ?? "значение из источника без пересчёта"],
    ["Период", formatPeriod(v.period)],
    ["Источник", sourceLabel(v.source)],
    ["Правило", v.rule_version ? formatRuleVersion(v.rule_version) : "без правила"],
    ["Данные", v.data_status === "partial" ? PARTIAL_NOTE.toLowerCase() : "полные за период"],
  ];
  return (
    <span
      id={id}
      popover="auto"
      role="dialog"
      aria-label="Как посчитано"
      className="m-auto w-[min(92vw,380px)] border border-line bg-surface shadow-[var(--shadow-lg)] rounded-2xl p-4 text-left text-sm text-text"
    >
      <span className="block font-semibold">Как посчитано</span>
      <span className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        {rows.map(([k, val]) => (
          <span key={k} className="contents">
            <span className="text-muted">{k}</span>
            <span className={k === "Формула" || k === "Правило" ? "font-mono text-xs leading-5" : ""}>{val}</span>
          </span>
        ))}
      </span>
      <button type="button" popoverTarget={id} popoverTargetAction="hide" className="btn btn-secondary btn-sm mt-3">
        Понятно
      </button>
    </span>
  );
}

/** Change badge for a `pct` Value. Color follows the sign of the string; `goodWhenDown` for costs. */
export function DeltaBadge({ v, goodWhenDown = false }: { v: Value; goodWhenDown?: boolean }) {
  if (v.amount === null) return <ValueView v={v} reason="нет данных для сравнения" />;
  const up = isPositive(v.amount);
  const down = isNegative(v.amount);
  const good = goodWhenDown ? down : up;
  const tone = !up && !down ? "bg-surface-2 text-muted" : good ? "bg-success-bg text-success" : "bg-danger-bg text-danger";
  const Icon = down ? TrendingDown : TrendingUp;
  return (
    <span className={`badge ${tone}`}>
      <Icon size={12} aria-hidden />
      <ValueView v={v} signed className="text-xs font-semibold" />
    </span>
  );
}

/**
 * A raw decimal parameter of an action (e.g. `action.change_pct = "-15.00"`), which the contract sends as a
 * plain string, not a `Value`. Same string formatting, no float.
 */
export function ParamView({ amount, unit, signed = false }: { amount: DecimalString; unit: Unit; signed?: boolean }) {
  return <span className="money">{formatAmount(amount, unit, { signed }) ?? "Ошибка формата данных"}</span>;
}
