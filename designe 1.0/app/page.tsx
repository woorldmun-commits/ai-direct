import type { Metadata } from "next";
import { PublicPage } from "@/components/ix/public/pages";
import {headers} from 'next/headers';
import {SITE_URL, PUBLIC_SITE_CONFIGURED} from '@/lib/site';
import {publicMetadata} from '@/lib/public-metadata';
export const metadata: Metadata = { title: { absolute: "INROU — контроль бюджета Яндекс Директа" }, description: "Поймите, какие расходы Яндекс Директа требуют проверки. Контроль расходов и плана, проверка источников и рекомендации с основаниями — в одном кабинете INROU. Планируемая подписка от 2 990 ₽ в месяц.", alternates: { canonical: "/" } };
metadata.openGraph = publicMetadata('/', 'Контроль бюджета Яндекс Директа', metadata.description as string).openGraph;
metadata.twitter = publicMetadata('/', 'Контроль бюджета Яндекс Директа', metadata.description as string).twitter;
export default async function Home() {
  const nonce = (await headers()).get('x-nonce') ?? undefined;
  return <>{PUBLIC_SITE_CONFIGURED && <script nonce={nonce} type="application/ld+json" dangerouslySetInnerHTML={{__html: JSON.stringify({'@context': 'https://schema.org', '@type': 'WebSite', name: 'INROU', url: SITE_URL, inLanguage: 'ru-RU'}).replace(/</g, '\\u003c')}} />}<PublicPage page="home" /></>;
}
