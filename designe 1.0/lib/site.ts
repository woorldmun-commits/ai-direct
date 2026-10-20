const configuredSite = process.env.NEXT_PUBLIC_SITE_URL;
const site = new URL(configuredSite || 'http://127.0.0.1:3120');
if ((site.protocol !== 'https:' && !(site.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(site.hostname)))
  || site.username || site.password || site.search || site.hash || site.pathname !== '/') throw new Error('NEXT_PUBLIC_SITE_URL must be an HTTPS origin or a local preview origin');
export const SITE_URL = site.origin;
const previewHost = /^(localhost|127\..*|\[::1\])$/.test(site.hostname) || site.hostname.endsWith('.localhost') || site.hostname.endsWith('.local');
export const PUBLIC_SITE_CONFIGURED = !!configuredSite && site.protocol === 'https:' && !previewHost;

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
  { slug: "terms", title: "Условия использования" },
  { slug: "consents", title: "Согласия и их отзыв" },
  { slug: "offer", title: "Договор-оферта" },
  { slug: "privacy", title: "Политика обработки персональных данных" },
  { slug: "pd-consent", title: "Согласие на обработку персональных данных" },
  { slug: "marketing-consent", title: "Согласие на получение рекламных рассылок" },
  { slug: "cookies", title: "Согласие на обработку данных cookie" },
  { slug: "requisites", title: "Реквизиты" },
] as const;

export type LegalSlug = (typeof LEGAL_DOCS)[number]["slug"];
