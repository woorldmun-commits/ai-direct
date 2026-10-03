// The only module pages read data from. In development it serves the demo mock;
// for production replace each body with a call to the backend (docs/API_CONTRACT.md) — signatures stay.

import * as data from "@/lib/mock/data";
import * as org from "@/lib/mock/org";
import * as recs from "@/lib/mock/recommendations";

export const IS_DEMO = true;

export const api = {
  user: () => org.USER,
  workspaces: () => org.WORKSPACES,
  team: () => org.TEAM,
  todayKpis: () => data.TODAY_KPIS,
  analyticsKpis: () => data.ANALYTICS_KPIS,
  series: () => data.SERIES,
  money: () => data.MONEY,
  targetCpa: () => data.TARGET_CPA,
  spendByType: () => data.SPEND_BY_TYPE,
  campaigns: () => data.CAMPAIGNS,
  campaign: (id: string) => data.CAMPAIGNS.find((c) => c.id === id) ?? null,
  campaignKpis: data.campaignKpis,
  campaignSeries: data.campaignSeries,
  clients: () => data.CLIENTS,
  client: (id: string) => data.CLIENTS.find((c) => c.id === id) ?? null,
  recommendations: () => recs.RECOMMENDATIONS,
  measurements: () => recs.MEASUREMENTS,
  measuredTotal: () => recs.MEASURED_TOTAL,
  agents: () => org.AGENTS,
  integrations: () => org.INTEGRATIONS,
  syncErrors: () => org.SYNC_ERRORS,
  plans: () => org.PLANS,
  subscription: () => org.SUBSCRIPTION,
  usage: () => org.USAGE,
  invoices: () => org.INVOICES,
  reports: () => org.REPORTS,
  suggestedQuestions: () => org.SUGGESTED_QUESTIONS,
  ask: (question: string) => {
    const q = question.trim().toLowerCase();
    const hit = org.ANSWERS.find((a) => a.question.toLowerCase() === q) ?? org.ANSWERS.find((a) => keywords(a.question).some((k) => q.includes(k)));
    return hit ?? org.INSUFFICIENT_ANSWER(question);
  },
};

// ponytail: keyword match stands in for the backend assistant; the real one answers from the snapshot.
function keywords(question: string) {
  const map: Record<string, string[]> = {
    [org.SUGGESTED_QUESTIONS[0]]: ["cpa", "цена заявки", "стоимость конверсии"],
    [org.SUGGESTED_QUESTIONS[1]]: ["теря", "слива", "без конверс"],
    [org.SUGGESTED_QUESTIONS[2]]: ["изменил", "7 дней", "неделю"],
    [org.SUGGESTED_QUESTIONS[3]]: ["рекомендац", "внимани", "решени"],
  };
  return map[question] ?? [];
}
