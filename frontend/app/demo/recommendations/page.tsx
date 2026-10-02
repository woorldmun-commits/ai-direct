import { parseRecFilter } from "@/components/app/rec-filter";
import { RecommendationsScreen } from "@/components/app/recommendations";
import { parseScreenState } from "@/components/app/screen-state";

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const RULES = ["zero_conv_campaign", "zero_conv_placements", "high_cpa"];

export default async function RecommendationsPage({ searchParams }: PageProps<"/demo/recommendations">) {
  const sp = await searchParams;
  const rule = one(sp.rule);
  const campaign = one(sp.campaign);
  return (
    <RecommendationsScreen
      // A new key resets the tab when Ctrl+K opens another ready-made selection.
      key={`${one(sp.filter)}|${rule}|${campaign}`}
      state={parseScreenState(sp.state)}
      filter={parseRecFilter(one(sp.filter))}
      rule={rule && RULES.includes(rule) ? rule : undefined}
      campaign={campaign && /^\d{1,20}$/.test(campaign) ? campaign : undefined}
    />
  );
}
