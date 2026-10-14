import Link from "next/link";
import { Menu } from "lucide-react";
import { Logo } from "@/components/ui";

const links = [["#features","Преимущества"],["#product","Возможности"],["#pricing","Тарифы"],["#faq","FAQ"],["/login","Войти"]];
export function Header() {
  return <header className="liquid-header">
    <Link href="/" aria-label="AdPilot — на главную"><Logo size={23}/></Link>
    <nav aria-label="Основная навигация">{links.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav>
    <Link href="/signup" className="liquid-start">Начать бесплатно</Link>
    <details className="liquid-mobile-menu"><summary aria-label="Открыть меню"><Menu size={22}/></summary><nav aria-label="Мобильная навигация">{links.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></details>
  </header>;
}
