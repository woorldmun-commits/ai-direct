import type { Metadata } from "next";
import { ReferenceLanding } from "@/components/reference/landing";
export const metadata: Metadata = { title: { absolute: "inrou — контроль бюджета Яндекс Директа" }, description: "Поймите, какие расходы Яндекс Директа требуют проверки. Контроль расходов и плана, проверка источников и рекомендации с основаниями — в одном кабинете inrou. Планируемая подписка от 1 990 ₽ в месяц.", alternates: { canonical: "/" } };
export default function Home() { return <ReferenceLanding />; }
