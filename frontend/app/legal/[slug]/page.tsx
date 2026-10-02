import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Footer } from "@/components/landing/bottom";
import { Logo } from "@/components/ui";
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
    <>
      <header className="mx-auto max-w-[860px] px-4 py-6">
        <Link href="/" aria-label="На главную">
          <Logo />
        </Link>
      </header>
      <main className="mx-auto max-w-[860px] px-4 pb-20">
        <h1 className="text-[32px] leading-tight font-bold tracking-tight">{doc.title}</h1>
        {slug === "requisites" ? (
          <dl className="card mt-6 grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 p-6 text-sm">
            {[
              ["Наименование", "[ИП Фамилия И. О. / ООО «Название»]"],
              ["ИНН", "[__________]"],
              ["ОГРН / ОГРНИП", "[_____________]"],
              ["Адрес", "[____]"],
              ["E-mail", "[support@…]"],
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
      </main>
      <Footer />
    </>
  );
}
