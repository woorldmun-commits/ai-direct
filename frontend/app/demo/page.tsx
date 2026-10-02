import { parseScreenState } from "@/components/app/screen-state";
import { TodayScreen } from "@/components/app/today";
import { parseSources } from "@/lib/demo-backend";

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default async function TodayPage({ searchParams }: PageProps<"/demo">) {
  const sp = await searchParams;
  return <TodayScreen state={parseScreenState(sp.state)} sources={parseSources(one(sp.sources))} />;
}
