import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Footer } from "@/components/landing/bottom";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";
import { legalDocument, LEGAL_KEYS } from "@/lib/legal-document";

export const dynamicParams = false;
export const dynamic = 'force-dynamic';

export function generateStaticParams() {
  return LEGAL_DOCS.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: PageProps<"/legal/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const doc = LEGAL_DOCS.find((d) => d.slug === slug);
  return doc ? { title: doc.title, alternates: { canonical: `/legal/${slug}` }, robots: {index:false,follow:false} } : {};
}

export default async function LegalPage({ params }: PageProps<"/legal/[slug]">) {
  const { slug } = await params;
  const doc = LEGAL_DOCS.find((d) => d.slug === slug);
  if (!doc) notFound();
  const key = LEGAL_KEYS[slug as keyof typeof LEGAL_KEYS];
  const published = key ? await legalDocument(key) : null;

  return (
    <>
      <header className="mx-auto max-w-[860px] px-4 py-6">
        <Link href="/" aria-label="На главную">
          <Logo />
        </Link>
      </header>
      <main className="mx-auto max-w-[860px] px-4 pb-20">
        <h1 className="text-[32px] leading-tight font-bold tracking-tight">{doc.title}</h1>
        <div className="card mt-6 p-6">
          {published?.approved ? <>
            <p className="font-semibold">Утверждён · редакция {published.version} · {published.locale}</p>
            <pre className="mt-5 whitespace-pre-wrap break-words font-sans text-sm leading-7">{published.text}</pre>
            <p className="mt-6 break-all text-xs text-muted">SHA256: {published.sha256}</p>
          </> : <><p className="font-semibold">Документ не утверждён или временно недоступен.</p>
          <p className="mt-2 text-sm text-muted">
            {slug === "requisites"
              ? "Данные оператора и исполнителя ещё не подтверждены. Реквизиты будут размещены после проверки владельцем и юристом."
              : "Действующий юридический текст пока не опубликован. После утверждения здесь будут размещены точный текст, версия и контрольная сумма документа."}
          </p>
          </>}
          <Link href="/legal" className="mt-4 inline-block text-sm underline underline-offset-2">Правовая информация</Link>
        </div>
      </main>
      <Footer />
    </>
  );
}
