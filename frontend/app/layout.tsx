import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import { headers } from "next/headers";
import { NonceProvider } from "@/components/nonce";
import { CookieBanner } from "@/components/cookie-banner";
import { PageMotion } from "@/components/page-motion";
import { SITE_URL } from "@/lib/site";
import "./globals.css";
import "./design.css";
import "./figma.css";

const manrope = Inter({
  variable: "--font-manrope",
  subsets: ["latin", "cyrillic"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin", "cyrillic"],
  weight: ["400", "500"],
  display: "swap",
});

const TITLE = "AdPilot — анализ рекламы для владельцев бизнеса";
const DESCRIPTION =
  "AdPilot каждый день проверяет кабинеты Яндекс Директа и Метрики и показывает расход с признаками неэффективности в рублях — с доказательством на данных. Решение и изменения — за вами. Первый аудит бесплатно, без карты.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s — AdPilot" },
  description: DESCRIPTION,
  applicationName: "AdPilot",
  ...(process.env.NEXT_PUBLIC_YANDEX_VERIFICATION && {
    verification: { yandex: process.env.NEXT_PUBLIC_YANDEX_VERIFICATION },
  }),
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: "AdPilot",
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f8f6" },
    { media: "(prefers-color-scheme: dark)", color: "#07110f" },
  ],
};

// Runs before paint so a saved dark theme doesn't flash light.
const themeScript = `try{document.documentElement.dataset.theme=localStorage.getItem("adpilot-theme")==="light"?"light":"dark"}catch(e){document.documentElement.dataset.theme="dark"}`;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Per-request CSP nonce from proxy.ts; reading headers() also makes rendering dynamic, which nonces require.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="ru"
      className={`${manrope.variable} ${plexMono.variable} h-full`}
      suppressHydrationWarning
    >
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full">
        <a href="#main-content" className="skip-link">Перейти к содержанию</a>
        <PageMotion />
        <NonceProvider nonce={nonce}>{children}</NonceProvider>
        <CookieBanner />
      </body>
    </html>
  );
}
