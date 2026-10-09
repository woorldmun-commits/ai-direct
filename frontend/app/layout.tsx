import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Manrope } from "next/font/google";
import { headers } from "next/headers";
import { CookieBanner } from "@/components/cookie-banner";
import { METADATA_BASE } from "@/lib/site";
import "./globals.css";

const manrope = Manrope({
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

const TITLE = "AdPilot — контроль кабинетов Яндекс Директа для агентств и директологов";
const DESCRIPTION =
  "AdPilot проверяет кабинеты Яндекс Директа и Метрики и показывает расход с признаками неэффективности в рублях — с доказательством на данных. Решение и изменения — за специалистом. Закрытый пилот для агентств и директологов.";

export const metadata: Metadata = {
  metadataBase: new URL(METADATA_BASE),
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
const themeScript = `try{var t=localStorage.getItem("adpilot-theme");if(t==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`;

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
        {children}
        <CookieBanner />
      </body>
    </html>
  );
}
