import type { MetricValue, Source, Unit } from "@/lib/types/domain";

const int = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const dec1 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });
const dec2 = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 2482000 → "2 482 000 ₽" */
export const rub = (n: number) => `${int.format(Math.round(n))} ₽`;
export const rub2 = (n: number) => `${dec2.format(n)} ₽`;
export const num = (n: number) => int.format(n);
export const pct = (n: number) => `${dec1.format(n)}%`;

/** 12 → "+12", −8 → "−8" with a real minus sign. */
export const signed = (n: number, digits = 0) => {
  const s = n.toFixed(digits).replace(".", ",");
  return n > 0 ? `+${s}` : s.replace("-", "−");
};

/** Compact axis label: 412000 → "412 тыс." */
export function compact(n: number) {
  if (Math.abs(n) >= 1_000_000) return `${dec1.format(n / 1_000_000)} млн`;
  if (Math.abs(n) >= 1_000) return `${int.format(n / 1_000)} тыс.`;
  return int.format(n);
}

export function formatAmount(amount: number, unit: Unit) {
  if (unit === "rub") return rub(amount);
  if (unit === "pct") return pct(amount);
  if (unit === "ratio") return dec2.format(amount);
  return num(amount);
}

/** Display text for a Value per API_CONTRACT §2. Unavailable never renders a number. */
export function formatValue(v: MetricValue) {
  if (v.calculation_type === "unavailable") return "Недостаточно данных";
  const text = formatAmount(v.amount, v.unit);
  return v.calculation_type === "estimated" ? `≈ ${text}` : text;
}

export const SOURCE_LABEL: Record<Source, string> = {
  yandex_direct: "Яндекс Директ",
  yandex_metrika: "Яндекс Метрика",
  user_input: "Настройки",
};
export const sources = (s: Source[]) => s.map((x) => SOURCE_LABEL[x]).join(" + ");

export const CALC_LABEL = { actual: "Факт", estimated: "≈ Оценка", unavailable: "Недостаточно данных" } as const;

const months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
/** "2026-09-25" → "25 сентября" */
export function day(iso: string) {
  const d = new Date(iso);
  return `${d.getDate()} ${months[d.getMonth()]}`;
}
/** "2026-09-25T14:32" → "25 сентября, 14:32" */
export function dateTime(iso: string) {
  const d = new Date(iso);
  return `${day(iso)}, ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}
export const shortDay = (iso: string) => {
  const d = new Date(iso);
  return `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, "0")}`;
};
