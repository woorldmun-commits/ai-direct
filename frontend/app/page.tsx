import type { Metadata } from "next";
import { Faq, FAQ, FinalCta, Footer, Pricing } from "@/components/landing/bottom";
import { Header, Hero } from "@/components/landing/hero";
import { HowItWorks, Pains, Transparency } from "@/components/landing/sections";
import { ProductPreview } from "@/components/landing/product";
import { SITE_URL } from "@/lib/site";
import "./landing.css";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

// No ratings, reviews or prices: we don't have real ones yet.
const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", "@id": `${SITE_URL}/#org`, name: "AdPilot", url: SITE_URL },
    {
      "@type": "SoftwareApplication",
      name: "AdPilot",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      inLanguage: "ru",
      description: "Доказательный контроль кабинетов Яндекс Директа и Метрики для малых агентств и директологов",
      publisher: { "@id": `${SITE_URL}/#org` },
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQ.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    },
  ],
};

export default function Home() {
  return (
    <div className="landing-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <main id="main-content">
        <div className="liquid-reference"><div className="liquid-canvas"><Header /><Hero /></div></div>
        <Pains />
        <HowItWorks />
        <Transparency />
        <ProductPreview />
        <Pricing />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
