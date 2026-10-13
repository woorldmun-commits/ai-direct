import Image from "next/image";
import Link from "next/link";
import { Logo } from "@/components/ui";
export { Header } from "./navigation";

export function Hero() {
  return <section className="liquid-hero" aria-labelledby="hero-title" data-node-id="6:40562">
    <Image className="liquid-sculpture" src="/figma/liquid/6-40562-img.png" alt="" width={330} height={451} unoptimized priority />
    <div className="liquid-copy">
      <h1 id="hero-title">AI-директор<br /><span>вашей рекламы</span></h1>
      <p>AdPilot анализирует ваш бюджет. Находит точки роста. Даёт понятные рекомендации. Контролирует ваш бюджет.</p>
      <div className="liquid-platforms"><span>◈ <b>Яндекс Директ</b></span><span>◈ <b>VK Реклама</b></span><span>◈ <b>Telegram Ads</b></span><span>◈ <b>Avito</b></span></div>
      <div className="liquid-actions"><Link href="/signup">Попробовать бесплатно →</Link><Link href="/demo/analytics">▶　Смотреть как это работает</Link></div>
    </div>
    <div className="liquid-assistant"><Logo size={23} /><Link className="liquid-advice" href="/demo/recommendations" title="Пример рекомендации на демонстрационных данных"><strong>🔴　Вчера потеряно ≈ 23 000 ₽</strong><span>Причина: кампания «РСЯ — Новая»</span><small>Рекомендация: снизить ставку на 15%　→</small></Link></div>
    <Link className="liquid-effect" href="/demo/effect" title="Иллюстрация эффекта из макета"><p>◈　CTR вырос на 32%</p><small>После применения рекомендаций</small><Image src="/figma/liquid/6-40562-img1.svg" alt="" width={145.377} height={35.7748} unoptimized /></Link>
    <div className="liquid-stats" aria-label="Иллюстративные показатели из макета">{[["12","Активных кампаний"],["98%","Успешность рекомендаций"],["+24,11%","Рост конверсий"],["08","Подключённые сервисы"]].map(([value,label])=><div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
  </section>;
}
