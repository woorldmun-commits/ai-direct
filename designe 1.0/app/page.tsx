import type { Metadata } from "next";
import { ReferenceLanding } from "@/components/reference/landing";
export const metadata: Metadata = { title: { absolute: "inrou — аналитика Директа и Метрики" }, description: "inrou — аналитика Яндекс Директа и Метрики для директологов и агентств. Поймите, куда уходит рекламный бюджет: расходы, CPA и рекомендации с основаниями. Подписка от 1 990 ₽ в месяц.", alternates: { canonical: "/" } };
export default function Home() { return <ReferenceLanding />; }
