"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { CHART_COLORS, TrendChart } from "@/components/charts/charts";
import { useApp } from "@/components/layout/app-state";
import { RecCard } from "@/components/recommendations/rec-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { DemoBadge } from "@/components/ui/misc";
import { EmptyState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { compact, rub, shortDay } from "@/lib/formatters";
import { CAMPAIGN_STATUS } from "./campaign-table";
import { KpiGrid } from "./widgets";

export function CampaignDetail({ id }: { id: string }) {
  const c = api.campaign(id)!;
  const client = api.client(c.client_id);
  const { recs } = useApp();
  const related = recs.filter((r) => r.campaign_id === id);
  return (
    <div className="space-y-6">
      <div>
        <Link href="/campaigns" className="inline-flex items-center gap-1 text-[13px] font-medium text-muted hover:text-text">
          <ChevronLeft size={16} /> Кампании
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[24px] leading-8 font-semibold tracking-[-0.02em]">{c.name}</h1>
            <p className="mt-1 text-[14px] text-muted">
              {client?.name} · кабинет <span className="font-mono text-[13px]">{c.account}</span> · Яндекс Директ
            </p>
          </div>
          <div className="flex items-center gap-2">
            <DemoBadge />
            <Badge tone={CAMPAIGN_STATUS[c.status][1]} dot>
              {CAMPAIGN_STATUS[c.status][0]}
            </Badge>
          </div>
        </div>
      </div>

      <KpiGrid kpis={api.campaignKpis(id)} />

      <Card className="p-5">
        <CardHeader title="Расход по дням" sub="Факт · Яндекс Директ · последние 30 дней" />
        <div className="mt-4">
          <TrendChart ariaLabel={`Расход кампании ${c.name} по дням`} data={api.campaignSeries(id)} xKey="date" xFmt={shortDay} fmt={rub} axisFmt={compact} height={240} series={[{ key: "spend", name: "Расход", color: CHART_COLORS.brand, area: true }]} />
        </div>
      </Card>

      <section aria-labelledby="camp-recs">
        <h2 id="camp-recs" className="mb-3 text-[16px] font-semibold">
          Проблемы и рекомендации
        </h2>
        {related.length ? (
          <div className="space-y-4">
            {related.map((r) => (
              <RecCard key={r.id} rec={r} />
            ))}
          </div>
        ) : (
          <div className="card">
            <EmptyState title="Проблем не найдено" text="Аудит не нашёл отклонений в этой кампании за последние 7 дней." />
          </div>
        )}
      </section>
    </div>
  );
}
