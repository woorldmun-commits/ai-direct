import type { Metadata } from "next";
import Link from "next/link";
import { PublicFrame } from "@/components/ix/public/chrome";
import { LEGAL_DOCS } from "@/lib/site";

export const metadata: Metadata = { title: "Правовая информация", robots: {index:false,follow:false} };

export default function LegalCenter() {
  return <PublicFrame>
    <div className="ix-legal">
      <div className="ix-eyebrow">INROU / Документы</div>
      <h1>Правовая информация</h1>
      <div className="ix-card" style={{marginTop: 24}}>
        <p><b>Документы и данные оператора требуют утверждения</b></p>
        <p>Здесь собраны ссылки на документы inrou. Утверждённый документ содержит точный текст, редакцию и контрольную сумму. Страница списка не заменяет политику обработки персональных данных, согласие или публичную оферту.</p>
        <p>Регистрация новых клиентов доступна только после утверждения и публикации точных текстов оферты и согласия. Статус и редакция отображаются на странице каждого документа.</p>
        <p>inrou не гарантирует экономию или рекламный результат. Условия платной подписки пока не опубликованы; списания не выполняются. Изменения в рекламе выполняет специалист вручную.</p>
      </div>
      <nav aria-label="Статусы юридических документов" className="ix-pub-cols ix-pub-cols--2" style={{marginTop: 24}}>
        {LEGAL_DOCS.map(doc => <Link key={doc.slug} href={`/legal/${doc.slug}`} className="ix-card">{doc.title}<span className="ix-muted ix-mini" style={{display: 'block', marginTop: 8}}>Открыть документ и проверить статус</span></Link>)}
      </nav>
    </div>
  </PublicFrame>;
}
