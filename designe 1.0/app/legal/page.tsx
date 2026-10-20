import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/landing/bottom";
import { Logo } from "@/components/ui";
import { LEGAL_DOCS } from "@/lib/site";

export const metadata: Metadata = { title: "Правовая информация", robots: {index:false,follow:false} };

export default function LegalCenter() {
  return <>
    <header className="mx-auto max-w-[860px] px-4 py-6"><Link href="/" aria-label="На главную"><Logo /></Link></header>
    <main className="mx-auto max-w-[860px] px-4 pb-20">
      <h1 className="text-[32px] font-bold tracking-tight">Правовая информация</h1>
      <div className="card mt-6 space-y-4 p-6">
        <p className="font-semibold">Документы и данные оператора требуют утверждения</p>
        <p>Здесь собраны ссылки на документы inrou. Утверждённый документ содержит точный текст, редакцию и контрольную сумму. Страница списка не заменяет политику обработки персональных данных, согласие или публичную оферту.</p>
        <p>Регистрация новых клиентов доступна только после утверждения и публикации точных текстов оферты и согласия. Статус и редакция отображаются на странице каждого документа.</p>
        <p>inrou не гарантирует экономию или рекламный результат. Условия платной подписки пока не опубликованы; списания не выполняются. Изменения в рекламе выполняет специалист вручную.</p>
      </div>
      <nav aria-label="Статусы юридических документов" className="mt-6 grid gap-3 sm:grid-cols-2">
        {LEGAL_DOCS.map(doc => <Link key={doc.slug} href={`/legal/${doc.slug}`} className="card p-4 underline underline-offset-2">{doc.title}<span className="mt-2 block text-xs text-muted">Открыть документ и проверить статус</span></Link>)}
      </nav>
    </main>
    <Footer />
  </>;
}
