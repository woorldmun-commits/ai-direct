// The real public origin, e.g. https://example.ru (no trailing slash). Unset = domain not bought yet: sitemap, robots sitemap
// line and JSON-LD urls are omitted instead of pointing at a domain we do not own. A deploy sets REQUIRE_SITE_URL=1
// to fail the build when it is missing.
export const SITE_URL: string | undefined = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/+$/, "") || undefined;
if (process.env.REQUIRE_SITE_URL === "1" && !SITE_URL) throw new Error("NEXT_PUBLIC_SITE_URL is required for this build");
/** Only for Next's metadataBase (relative canonical/OG); never published as a real address when SITE_URL is unset. */
export const METADATA_BASE = SITE_URL ?? "http://localhost:3000";

const rubFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

/** 42750 → "42 750 ₽". Landing only (budget slider input); business numbers go through <ValueView>. */
export function rub(n: number): string {
  return `${rubFmt.format(Math.round(n))} ₽`;
}

// Wording (P0 D9/D10): an estimate of spend with signs of inefficiency, never "lost money".
export const EXPOSURE = "Расход с признаками неэффективности";
export const EXPOSURE_SHORT = "Неэффективный расход";
export const EXPOSURE_NOTE =
  "Оценка расходов, по которым система обнаружила признаки неэффективности. Одна и та же сумма учитывается в итоге только один раз.";
export const SAVED_NOTE = "Расчётный эффект · сравнение 7 дней до и после без контрольной группы";

export const LEGAL_DOCS = [
  { slug: "offer", title: "Договор-оферта" },
  { slug: "privacy", title: "Политика обработки персональных данных" },
  { slug: "pd-consent", title: "Согласие на обработку персональных данных" },
  { slug: "marketing-consent", title: "Согласие на получение рекламных рассылок" },
  { slug: "cookies", title: "Согласие на обработку данных cookie" },
  { slug: "requisites", title: "Реквизиты" },
] as const;

export type LegalSlug = (typeof LEGAL_DOCS)[number]["slug"];
