import type { Metadata } from "next";
import { PublicPage } from "@/components/ix/public/pages";
export const metadata: Metadata = { title: { absolute: "INROU — контроль бюджета Яндекс Директа" }, description: "Поймите, какие расходы Яндекс Директа требуют проверки. Контроль расходов и плана, проверка источников и рекомендации с основаниями — в одном кабинете INROU. Планируемая подписка от 2 990 ₽ в месяц.", alternates: { canonical: "/" } };
export default function Home() { return <PublicPage page="home" />; }
