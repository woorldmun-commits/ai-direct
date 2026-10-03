import type { Metadata } from "next";
import { RecList } from "@/components/recommendations/rec-list";

export const metadata: Metadata = { title: "Рекомендации" };

export default async function RecommendationsPage({ searchParams }: PageProps<"/recommendations">) {
  const { open } = await searchParams;
  return <RecList openId={typeof open === "string" ? open : null} />;
}
