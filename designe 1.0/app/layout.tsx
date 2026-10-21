import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { CookieBanner } from "@/components/cookie-banner";
import { SITE_URL, PUBLIC_SITE_CONFIGURED } from "@/lib/site";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";
import "./palette.css";
import "./fonts.css";
import "./inter.css";
import "./responsive.css";
import "@/components/reference/midnight.css";
import "@/components/reference/launch-reference.css";

const TITLE = "inrou — контроль кабинетов Яндекс Директа для агентств и директологов";
const DESCRIPTION =
  "inrou — аналитика Яндекс Директа и Метрики для директологов и агентств. Поймите, куда уходит рекламный бюджет: расходы, CPA и рекомендации с основаниями. Подписка от 1 990 ₽ в месяц.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s — inrou" },
  description: DESCRIPTION,
  applicationName: "inrou",
  robots: { index: PUBLIC_SITE_CONFIGURED, follow: PUBLIC_SITE_CONFIGURED },
  ...(process.env.NEXT_PUBLIC_YANDEX_VERIFICATION && {
    verification: { yandex: process.env.NEXT_PUBLIC_YANDEX_VERIFICATION },
  }),
  openGraph: {
    type: "website",
    locale: "ru_RU",
    siteName: "inrou",
    title: TITLE,
    description: DESCRIPTION,
  },
  twitter: { card: "summary", title: TITLE, description: DESCRIPTION },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f1ec" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

// Runs before paint so a saved dark theme doesn't flash light.
const themeScript = THEME_SCRIPT;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Per-request CSP nonce from proxy.ts; reading headers() also makes rendering dynamic, which nonces require.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="ru"
      className="h-full"
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

