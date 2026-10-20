/**
 * `Value` — the one shape of every business number (docs/API_CONTRACT.md §2, backend `app/contract.py`).
 *
 * The type is a discriminated union on `calculation_type`, so the contract invariants are checked by the
 * compiler: `amount` is a Decimal string only in `actual | estimated`, and is `null` only in `unavailable`
 * (`unavailable` ⇔ `insufficient` ⇔ `amount = null` ⇔ `unavailable_reason` is set; `estimated` ⇒ `formula` is set).
 *
 * The frontend never computes or re-labels a number: it formats the Decimal string as text (no float
 * parsing), and the only component that renders it is `<ValueView>` (components/value-view.tsx).
 */

/** Decimal number as a string, e.g. `"12500.00"`, `"-15.00"`, `"9"`. Never a JSON number. */
export type DecimalString = string;
export type Unit = "rub" | "count" | "pct";
export type CalculationType = "actual" | "estimated" | "unavailable";
export type DataStatus = "complete" | "partial";
export type DataSufficiency = "sufficient" | "insufficient";
export type SourceId = "yandex_direct" | "yandex_metrika" | "user_input";
/** Why there is no number (API_CONTRACT §2) — a closed list; the texts are `UNAVAILABLE_REASON_LABEL`. */
export type UnavailableReason =
  | "source_missing"
  | "no_conversions"
  | "history_insufficient"
  | "volume_insufficient"
  | "no_forecast"
  | "no_data";

/** `YYYY-MM-DD` dates, inclusive. */
export interface Period {
  from: string;
  to: string;
}

interface ValueCommon {
  unit: Unit;
  /** `yandex_direct` · `yandex_metrika` · `user_input`, joined with `+`. */
  source: string;
  period: Period;
  data_status: DataStatus;
  /** `name@N`, e.g. `high_cpa_target@1`. */
  rule_version: string | null;
}

export interface ActualValue extends ValueCommon {
  calculation_type: "actual";
  amount: DecimalString;
  data_sufficiency: "sufficient";
  formula: string | null;
  unavailable_reason: null;
}

export interface EstimatedValue extends ValueCommon {
  calculation_type: "estimated";
  amount: DecimalString;
  data_sufficiency: "sufficient";
  formula: string;
  unavailable_reason: null;
}

export interface UnavailableValue extends ValueCommon {
  calculation_type: "unavailable";
  amount: null;
  data_sufficiency: "insufficient";
  formula: string | null;
  unavailable_reason: UnavailableReason;
}

export type Value = ActualValue | EstimatedValue | UnavailableValue;
export type AvailableValue = ActualValue | EstimatedValue;

export function isAvailable(v: Value): v is AvailableValue {
  return v.calculation_type !== "unavailable";
}

const DECIMAL = /^([+-])?(\d+)(?:\.(\d+))?$/;
const NBSP = " ";
const MINUS = "−";

/** True when the Decimal string is negative and not zero ("-0.00" is zero). */
export function isNegative(amount: DecimalString): boolean {
  const m = DECIMAL.exec(amount.trim());
  return !!m && m[1] === "-" && /[1-9]/.test(m[2] + (m[3] ?? ""));
}

/** True when the Decimal string is positive and not zero. */
export function isPositive(amount: DecimalString): boolean {
  const m = DECIMAL.exec(amount.trim());
  return !!m && m[1] !== "-" && /[1-9]/.test(m[2] + (m[3] ?? ""));
}

/**
 * Formats a Decimal string as Russian text by string operations only — no `parseFloat`, so
 * `"12500.10"` stays exactly `12 500,10`. Money keeps kopecks when they are not zero; percents and
 * counts drop trailing zeros. Returns `null` for a string that is not a decimal number.
 */
export function formatAmount(amount: DecimalString, unit: Unit, opts: { signed?: boolean } = {}): string | null {
  const m = DECIMAL.exec(amount.trim());
  if (!m) return null;
  const [, sign, rawInt, rawFrac = ""] = m;
  const int = rawInt.replace(/^0+(?=\d)/, "");
  let frac = rawFrac.replace(/0+$/, "");
  if (unit === "rub" && frac) frac = frac.padEnd(2, "0");
  const zero = !/[1-9]/.test(int + frac);
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  const body = frac ? `${grouped},${frac}` : grouped;
  const prefix = zero ? "" : sign === "-" ? MINUS : opts.signed ? "+" : "";
  const text = prefix + body;
  if (unit === "rub") return `${text}${NBSP}₽`;
  if (unit === "pct") return `${text}%`;
  return text;
}

/** Text of an available value, e.g. `≈ 12 500 ₽`. Used by `<ValueView>` only (lint rule). */
export function formatValue(v: AvailableValue, opts: { signed?: boolean } = {}): string | null {
  const text = formatAmount(v.amount, v.unit, opts);
  if (text === null) return null;
  return v.calculation_type === "estimated" ? `≈${NBSP}${text}` : text;
}

const SOURCE_LABEL: Record<SourceId, string> = {
  yandex_direct: "Яндекс Директ",
  yandex_metrika: "Яндекс Метрика",
  user_input: "ваши настройки",
};

export function sourceLabel(source: string): string {
  return source
    .split("+")
    .map((s) => SOURCE_LABEL[s.trim() as SourceId] ?? s.trim())
    .join(" + ");
}

export const CALCULATION_LABEL: Record<CalculationType, string> = {
  actual: "Факт",
  estimated: "Оценка",
  unavailable: "Недостаточно данных",
};

/** Why a value is unavailable and what to do — shown next to «Недостаточно данных» (never a number or a dash). */
export const UNAVAILABLE_REASON_LABEL: Record<UnavailableReason, string> = {
  source_missing: "Источник данных не подключён или не отдал данные — подключите его в «Интеграциях»",
  no_conversions: "За период нет конверсий — считать не из чего",
  history_insufficient: "Мало истории для сравнения — нужно больше дней данных",
  volume_insufficient: "Мало расхода, кликов или конверсий для надёжного вывода",
  no_forecast: "Для этого действия нет обоснованной формулы эффекта — оценим по факту после замера",
  no_data: "Нет данных для расчёта за период",
};

export const PARTIAL_NOTE = "Данные за последние дни могут уточниться";

const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];

function parseDate(d: string): { y: number; m: number; day: number } | null {
  const r = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d);
  return r ? { y: +r[1], m: +r[2], day: +r[3] } : null;
}

/** `2026-09-25` → `25 сентября`. */
export function formatDate(d: string): string {
  const p = parseDate(d);
  return p ? `${p.day} ${MONTHS[p.m - 1]}` : d;
}

/** `{2026-09-01, 2026-09-30}` → `1–30 сентября`; across months → `25 сентября – 1 октября`. */
export function formatPeriod(p: Period): string {
  const a = parseDate(p.from);
  const b = parseDate(p.to);
  if (!a || !b) return `${p.from} – ${p.to}`;
  if (p.from === p.to) return formatDate(p.from);
  if (a.y === b.y && a.m === b.m) return `${a.day}–${b.day} ${MONTHS[b.m - 1]}`;
  return `${formatDate(p.from)} – ${formatDate(p.to)}`;
}

const MSK = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** ISO moment with offset → `02.10.2026, 07:01` in Moscow time (same on server and client). */
export function formatMoment(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso : MSK.format(t);
}

/** `high_cpa_target@1` → `high_cpa_target, версия 1`. */
export function formatRuleVersion(rv: string): string {
  const [name, version] = rv.split("@");
  return version ? `${name}, версия ${version}` : rv;
}
