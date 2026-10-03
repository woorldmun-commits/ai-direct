import type { Metadata } from "next";
import { CampaignTable } from "@/components/dashboard/campaign-table";

export const metadata: Metadata = { title: "Кампании" };

export default async function CampaignsPage({ searchParams }: PageProps<"/campaigns">) {
  const { client } = await searchParams;
  return <CampaignTable initialClient={typeof client === "string" ? client : "all"} />;
}
