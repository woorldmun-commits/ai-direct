// ponytail: placeholder domain until the real one is bought
export const SITE_URL = "https://adpilot.ru";

const rubFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

/** 42750 → "42 750 ₽" */
export function rub(n: number): string {
  return `${rubFmt.format(Math.round(n))} ₽`;
}

/** Percent change from prev to cur, rounded: 3120 → 3919 gives 26. */
export function pctChange(prev: number, cur: number): number {
  return Math.round(((cur - prev) / prev) * 100);
}

export function signed(n: number): string {
  return n > 0 ? `+${n}` : `${n}`.replace("-", "−");
}

export const LEGAL_DOCS = [
  { slug: "offer", title: "Договор-оферта" },
  { slug: "privacy", title: "Политика обработки персональных данных" },
  { slug: "pd-consent", title: "Согласие на обработку персональных данных" },
  { slug: "marketing-consent", title: "Согласие на получение рекламных рассылок" },
  { slug: "cookies", title: "Согласие на обработку данных cookie" },
  { slug: "requisites", title: "Реквизиты" },
] as const;

export type LegalSlug = (typeof LEGAL_DOCS)[number]["slug"];
