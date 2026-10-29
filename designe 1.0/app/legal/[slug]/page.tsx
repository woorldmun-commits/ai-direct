import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PublicFrame } from "@/components/ix/public/chrome";
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

export default async function LegalPage({ params, searchParams }: PageProps<"/legal/[slug]">) {
  const { slug } = await params;
  const doc = LEGAL_DOCS.find((d) => d.slug === slug);
  if (!doc) notFound();
  const key = LEGAL_KEYS[slug as keyof typeof LEGAL_KEYS];
  const query = await searchParams;
  const version = typeof query.version === 'string' ? query.version : undefined;
  const published = key && !Array.isArray(query.version) ? await legalDocument(key, version) : null;

  return (
    <PublicFrame>
      <article className="ix-legal">
        <div className="ix-eyebrow">INROU / Документы</div>
        <h1>{doc.title}</h1>
        <div className="ix-card" style={{marginTop: 24}}>
          {published?.approved ? <>
            <p className="font-semibold">Утверждён · редакция {published.version} · {published.locale}</p>
            <pre className="ix-legal-text">{published.text}</pre>
            <p className="ix-muted ix-mini" style={{overflowWrap: 'anywhere'}}>SHA256: {published.sha256}</p>
          </> : <><p className="font-semibold">Документ не утверждён или временно недоступен.</p>
          {query.version && <p>Запрошенная редакция не доступна для согласия. Обновите страницу регистрации, чтобы проверить действующие документы.</p>}
          <p className="ix-muted">
            {slug === "requisites"
              ? "Данные оператора и исполнителя ещё не подтверждены. Реквизиты будут размещены после проверки владельцем и юристом."
              : "Действующий юридический текст пока не опубликован. После утверждения здесь будут размещены точный текст, версия и контрольная сумма документа."}
          </p>
          </>}
          <Link href="/legal" className="mt-4 inline-block text-sm underline underline-offset-2">Правовая информация</Link>
        </div>
      </article>
    </PublicFrame>
  );
}
