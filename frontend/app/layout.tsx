import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { CookieBanner } from "@/components/cookie-banner";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "cyrillic"],
  display: "swap",
});

const TITLE = "AdPilot — находим, где реклама теряет деньги";
const DESCRIPTION =
  "AdPilot анализирует рекламные кампании, находит проблемы, показывает причины и предлагает конкретные действия на основе данных. Изменения — только после вашего подтверждения.";

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
  themeColor: "#07111f",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${inter.variable} h-full`}>
      <body className="min-h-full">
        {children}
        <CookieBanner />
      </body>
    </html>
  );
}
