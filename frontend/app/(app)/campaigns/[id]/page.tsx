import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CampaignDetail } from "@/components/dashboard/campaign-detail";
import { api } from "@/lib/api";

export async function generateMetadata({ params }: PageProps<"/campaigns/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: api.campaign(id)?.name ?? "Кампания" };
}

export default async function CampaignPage({ params }: PageProps<"/campaigns/[id]">) {
  const { id } = await params;
  if (!api.campaign(id)) notFound();
  return <CampaignDetail id={id} />;
}
