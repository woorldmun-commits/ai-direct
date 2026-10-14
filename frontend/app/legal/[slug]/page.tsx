import type { Metadata } from "next";
import { ArrowLeft, FileCheck2 } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Footer } from "@/components/landing/bottom";
import { Logo } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { LEGAL_DOCS } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return LEGAL_DOCS.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: PageProps<"/legal/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const doc = LEGAL_DOCS.find((d) => d.slug === slug);
  return doc ? { title: doc.title, alternates: { canonical: `/legal/${slug}` } } : {};
}

export default async function LegalPage({ params }: PageProps<"/legal/[slug]">) {
  const { slug } = await params;
  const doc = LEGAL_DOCS.find((d) => d.slug === slug);
  if (!doc) notFound();

  return (
    <div className="legal-container">
      <header className="mx-auto flex max-w-[860px] items-center justify-between px-4 py-6">
        <Link href="/" aria-label="На главную">
          <Logo />
        </Link>
        <ThemeToggle/>
      </header>
      <main id="main-content" className="legal-page legal-layout">
        <aside><Link href="/" className="mb-8 inline-flex items-center gap-2 text-xs text-muted"><ArrowLeft size={14}/> На главную</Link><nav aria-label="Юридические документы">{LEGAL_DOCS.map(d => <Link href={`/legal/${d.slug}`} key={d.slug} aria-current={d.slug === slug ? "page" : undefined}>{d.title}</Link>)}</nav></aside>
        <article><FileCheck2 size={28} className="mb-6 text-brand"/><h1 className="text-[32px] leading-tight font-semibold tracking-tight">{doc.title}</h1>
        {slug === "requisites" ? (
          <dl className="card mt-6 grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 p-6 text-sm">
            {[
              ["Наименование", "Реквизиты ещё не опубликованы"],
              ["ИНН", "Будет указан после утверждения"],
              ["ОГРН / ОГРНИП", "Будет указан после утверждения"],
              ["Адрес", "Будет указан после утверждения"],
              ["E-mail", "Будет указан после утверждения"],
            ].map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <div className="card mt-6 p-6">
            <p className="font-semibold">Редакция документа готовится.</p>
            <p className="mt-2 text-sm text-muted">
              Текст утверждает юрист. Документ будет опубликован здесь до начала приёма пользователей; версия и дата редакции будут
              указаны в начале документа.
            </p>
          </div>
        )}
        </article>
      </main>
      <Footer />
    </div>
  );
}
