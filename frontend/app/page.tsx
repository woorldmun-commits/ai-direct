import type { Metadata } from "next";
import { BudgetInput } from "@/components/landing/budget";
import { Faq, FAQ, FinalCta, Footer, Pricing } from "@/components/landing/bottom";
import { Header, Hero } from "@/components/landing/hero";
import { DemoCta, HowItWorks, Pains, Transparency } from "@/components/landing/sections";
import { SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

// No ratings, reviews or prices: we don't have real ones yet.
const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", "@id": `${SITE_URL ?? ""}/#org`, name: "AdPilot", ...(SITE_URL && { url: SITE_URL }) },
    {
      "@type": "SoftwareApplication",
      name: "AdPilot",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      inLanguage: "ru",
      description: "Доказательный контроль кабинетов Яндекс Директа и Метрики для малых агентств и директологов",
      publisher: { "@id": `${SITE_URL ?? ""}/#org` },
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    },
  ],
};

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <Header />
      <main>
        <Hero />
        <BudgetInput />
        <Pains />
        <HowItWorks />
        <Transparency />
        <DemoCta />
        <Pricing />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
