"use client";

import { Download, PlugZap } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { BarsChart, CHART_COLORS, ComparisonChart, DonutChart, TrendChart } from "@/components/charts/charts";
import { Badge } from "@/components/ui/badge";
import { Button, buttonCls } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/misc";
import { NoData } from "@/components/ui/states";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";
import { compact, num, pct, rub, shortDay } from "@/lib/formatters";
import type { Campaign } from "@/lib/types/domain";
import { KpiGrid } from "./widgets";

export function downloadCsv(name: string, rows: (string | number)[][]) {
  const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(";")).join("\n");
  const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function campaignsCsv(list: Campaign[]) {
  return [["Кампания", "Расход, ₽", "Показы", "Клики", "CTR, %", "Конверсии", "CPA, ₽"], ...list.map((c) => [c.name, c.spend, c.impressions, c.clicks, c.ctr, c.conversions, c.cpa ?? "недостаточно данных"])];
}

function Platforms() {
  const total = api.money().spend;
  const soon = ["VK Реклама", "Telegram Ads", "Ozon Performance"];
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div className="card p-4">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-[#fff1e6] text-[13px] font-bold text-[#e04f16]">Я</span>
          <span className="text-[13px] font-semibold">Яндекс Директ</span>
          <Badge tone="success" dot className="ml-auto">
            Подключено
          </Badge>
        </div>
        <p className="mt-3 text-[22px] font-semibold">
          <ValueText value={total} />
        </p>
        <p className="text-[12px] text-muted">9 кабинетов · 15 кампаний</p>
      </div>
      {soon.map((p) => (
        <div key={p} className="card flex flex-col p-4">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-surface-2 text-subtle">
              <PlugZap size={15} />
            </span>
            <span className="text-[13px] font-semibold text-muted">{p}</span>
            <Badge className="ml-auto">Скоро</Badge>
          </div>
          <p className="mt-auto pt-3 text-[12px] text-muted">Интеграция в разработке — данных нет.</p>
        </div>
      ))}
    </div>
  );
}

export function Analytics() {
  const series = api.series().slice(-30);
  const campaigns = api.campaigns();
  const [client, setClient] = useState("all");
  const scoped = useMemo(() => campaigns.filter((c) => client === "all" || c.client_id === client), [campaigns, client]);
  const withCpa = scoped.filter((c) => c.cpa !== null).sort((a, b) => b.cpa! - a.cpa!);
  const avgCpa = api.todayKpis()[2].value;
  const top = [...scoped].sort((a, b) => b.spend - a.spend).slice(0, 5);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Аналитика"
        sub="Глубокий анализ рекламных кампаний за 2 сентября — 1 октября 2026"
        actions={
          <Button variant="secondary" size="sm" icon={<Download size={15} />} onClick={() => downloadCsv("adpilot-campaigns.csv", campaignsCsv(campaigns))}>
            Экспорт CSV
          </Button>
        }
      />
      <Platforms />
      <KpiGrid kpis={api.analyticsKpis()} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="p-5 xl:col-span-2">
          <CardHeader title="Расходы по дням" sub="Факт · Яндекс Директ · последние 30 дней" />
          <div className="mt-4">
            <BarsChart ariaLabel="Расход по дням за 30 дней в сравнении с предыдущим периодом" data={series} xKey="date" xFmt={shortDay} fmt={rub} axisFmt={compact} series={[{ key: "spend", name: "Расход", color: CHART_COLORS.brand }, { key: "prevSpend", name: "Прошлый период", color: "#C7C9FB" }]} />
          </div>
        </Card>
        <Card className="p-5">
          <CardHeader title="Структура расхода" sub="По типам кампаний" />
          <div className="mt-5">
            <DonutChart ariaLabel="Доля расхода по типам кампаний" data={api.spendByType()} fmt={rub} center={{ label: "Всего", value: compact(api.money().spend.amount ?? 0) }} />
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5">
          <CardHeader title="CPA по дням" sub="Пунктир — цель CPA по аккаунту" />
          <div className="mt-4">
            <TrendChart ariaLabel="CPA по дням за 30 дней" data={series} xKey="date" xFmt={shortDay} fmt={rub} axisFmt={(n) => `${num(n)} ₽`} height={240} target={{ value: api.targetCpa(), label: "цель" }} series={[{ key: "cpa", name: "CPA", color: CHART_COLORS.violet, area: true }]} />
          </div>
        </Card>
        <Card className="p-5">
          <CardHeader title="Конверсии по дням" sub="Факт · Яндекс Метрика" />
          <div className="mt-4">
            <BarsChart ariaLabel="Конверсии по дням за 30 дней" data={series} xKey="date" xFmt={shortDay} fmt={num} height={240} series={[{ key: "conversions", name: "Конверсии", color: CHART_COLORS.sky }, { key: "prevConversions", name: "Прошлый период", color: "#BFDBFE" }]} />
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <CardHeader
          title="Эффективность по кампаниям"
          sub="CPA за 30 дней. Красным — выше среднего по аккаунту."
          action={
            <Select aria-label="Клиент" value={client} onChange={(e) => setClient(e.target.value)}>
              <option value="all">Все клиенты</option>
              {api.clients().map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          }
        />
        <div className="mt-5 grid gap-8 xl:grid-cols-[1.3fr_1fr]">
          <div>
            {withCpa.length ? <ComparisonChart ariaLabel="CPA по кампаниям против среднего" data={withCpa.map((c) => ({ name: c.name, value: c.cpa! }))} target={avgCpa.amount ?? 0} targetLabel="средний" fmt={rub} /> : <NoData why="У кампаний клиента меньше 10 конверсий за период — CPA не рассчитывается." />}
            {scoped.some((c) => c.cpa === null) && <p className="mt-3 text-[12px] text-muted">Без CPA: {scoped.filter((c) => c.cpa === null).map((c) => c.name).join(", ")} — меньше 10 конверсий за период.</p>}
          </div>
          <div>
            <p className="mb-2 text-[13px] font-semibold">Топ кампаний по расходу</p>
            <ul className="divide-y divide-line">
              {top.map((c) => (
                <li key={c.id}>
                  <Link href={`/campaigns/${c.id}`} className="flex items-center gap-3 py-2.5 hover:text-brand">
                    <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{c.name}</span>
                    <span className="num w-24 text-right text-[13px]">{rub(c.spend)}</span>
                    <span className="num w-20 text-right text-[12px] text-muted">{c.cpa === null ? "—" : `CPA ${num(c.cpa)}`}</span>
                    <span className="num w-14 text-right text-[12px] text-muted">CTR {pct(c.ctr)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>

      <Card className="p-5" id="finance">
        <CardHeader title="Финансы" sub="Выручка и ROI показываются только при наличии данных о доходе" />
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Расход", value: api.money().spend },
            { label: "CPA", value: avgCpa },
            { label: "Измеренный эффект", value: api.measuredTotal() },
          ].map((m) => (
            <div key={m.label} className="rounded-xl border border-line p-4">
              <p className="text-[12px] text-muted">{m.label}</p>
              <p className="mt-1 text-[20px] font-semibold">
                <ValueText value={m.value} />
              </p>
              <ValueMeta value={m.value} className="mt-1" />
            </div>
          ))}
          <div className="rounded-xl border border-line p-4">
            <p className="text-[12px] text-muted">Выручка и ROI</p>
            <NoData
              className="mt-2"
              why="AdPilot не получает доход по заказам. Передайте ценность конверсий в цели Метрики или подключите CRM — тогда появятся выручка, ROI и ROMI."
              action={
                <Link href="/integrations" className={buttonCls("secondary", "sm")}>
                  Подключить источник
                </Link>
              }
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
