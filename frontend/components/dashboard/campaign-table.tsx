"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { DemoBadge, PageHeader } from "@/components/ui/misc";
import { EmptyState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { num, pct, rub } from "@/lib/formatters";
import type { Campaign, CampaignStatus } from "@/lib/types/domain";
import { campaignsCsv, downloadCsv } from "./analytics";

type Key = "name" | "spend" | "impressions" | "clicks" | "ctr" | "conversions" | "cpa" | "problems";
const COLS: { key: Key; label: string; num?: boolean }[] = [
  { key: "name", label: "Кампания" },
  { key: "spend", label: "Расход", num: true },
  { key: "impressions", label: "Показы", num: true },
  { key: "clicks", label: "Клики", num: true },
  { key: "ctr", label: "CTR", num: true },
  { key: "conversions", label: "Конверсии", num: true },
  { key: "cpa", label: "CPA", num: true },
];
export const CAMPAIGN_STATUS: Record<CampaignStatus, [string, Tone]> = { active: ["Активна", "success"], limited: ["Ограничена бюджетом", "warning"], paused: ["Остановлена", "neutral"] };
const PAGE = 8;

export function CampaignTable({ initialClient }: { initialClient: string }) {
  const router = useRouter();
  const clients = api.clients();
  const [q, setQ] = useState("");
  const [client, setClient] = useState(initialClient);
  const [status, setStatus] = useState<"all" | CampaignStatus>("all");
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "spend", dir: -1 });
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    const val = (c: Campaign) => (sort.key === "cpa" ? (c.cpa ?? -1) : c[sort.key]);
    return api
      .campaigns()
      .filter((c) => (client === "all" || c.client_id === client) && (status === "all" || c.status === status) && (!s || c.name.toLowerCase().includes(s)))
      .sort((a, b) => {
        const x = val(a);
        const y = val(b);
        return (typeof x === "string" ? x.localeCompare(y as string, "ru") : x - (y as number)) * sort.dir;
      });
  }, [q, client, status, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const current = Math.min(page, pages - 1);
  const visible = rows.slice(current * PAGE, current * PAGE + PAGE);
  const clientName = (id: string) => clients.find((c) => c.id === id)?.name ?? "";
  const reset = () => setPage(0);

  return (
    <>
      <PageHeader
        title="Кампании"
        sub="Все кампании подключённых кабинетов за последние 30 дней"
        actions={
          <Button variant="secondary" size="sm" icon={<Download size={15} />} onClick={() => downloadCsv("adpilot-campaigns.csv", campaignsCsv(rows))}>
            Экспорт CSV
          </Button>
        }
      />
      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <span className="relative min-w-[200px] flex-1 sm:max-w-[280px]">
            <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" aria-hidden />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                reset();
              }}
              placeholder="Поиск кампании"
              aria-label="Поиск кампании"
              className="input h-9 pl-8 text-[13px]"
            />
          </span>
          <Select
            aria-label="Клиент"
            value={client}
            onChange={(e) => {
              setClient(e.target.value);
              reset();
            }}
          >
            <option value="all">Все клиенты</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Статус"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as typeof status);
              reset();
            }}
          >
            <option value="all">Все статусы</option>
            <option value="active">Активные</option>
            <option value="limited">Ограничены бюджетом</option>
            <option value="paused">Остановлены</option>
          </Select>
          <span className="ml-auto hidden sm:block">
            <DemoBadge />
          </span>
        </div>

        {visible.length === 0 ? (
          <EmptyState title="Кампании не найдены" text="Измените фильтры или строку поиска." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-[13px]">
              <thead>
                <tr className="border-b border-line bg-bg text-left text-[12px] text-muted">
                  {COLS.map((c) => {
                    const active = sort.key === c.key;
                    return (
                      <th key={c.key} scope="col" aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"} className={`px-4 py-2.5 font-medium ${c.num ? "text-right" : ""}`}>
                        <button
                          type="button"
                          onClick={() => setSort({ key: c.key, dir: active ? (sort.dir === 1 ? -1 : 1) : c.num ? -1 : 1 })}
                          className={`inline-flex items-center gap-1 hover:text-text ${active ? "text-text" : ""}`}
                        >
                          {c.label}
                          {active && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                        </button>
                      </th>
                    );
                  })}
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    Статус
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">
                    Проблемы
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visible.map((c) => (
                  <tr key={c.id} onClick={() => router.push(`/campaigns/${c.id}`)} className="cursor-pointer transition-colors hover:bg-bg">
                    <td className="px-4 py-3">
                      <a href={`/campaigns/${c.id}`} onClick={(e) => e.preventDefault()} className="font-semibold hover:text-brand">
                        {c.name}
                      </a>
                      <span className="block text-[12px] text-muted">{clientName(c.client_id)}</span>
                    </td>
                    <td className="num px-4 py-3 text-right font-medium">{rub(c.spend)}</td>
                    <td className="num px-4 py-3 text-right">{num(c.impressions)}</td>
                    <td className="num px-4 py-3 text-right">{num(c.clicks)}</td>
                    <td className="num px-4 py-3 text-right">{pct(c.ctr)}</td>
                    <td className="num px-4 py-3 text-right">{num(c.conversions)}</td>
                    <td className="num px-4 py-3 text-right">{c.cpa === null ? <span className="text-[12px] text-warning-ink" title="Меньше 10 конверсий за период">мало данных</span> : rub(c.cpa)}</td>
                    <td className="px-4 py-3">
                      <Badge tone={CAMPAIGN_STATUS[c.status][1]} dot>
                        {CAMPAIGN_STATUS[c.status][0]}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right">{c.problems ? <Badge tone="danger">{c.problems}</Badge> : <span className="text-subtle">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-[13px] text-muted">
          <span>
            {rows.length ? `${current * PAGE + 1}–${Math.min(rows.length, current * PAGE + PAGE)} из ${rows.length}` : "0 кампаний"}
          </span>
          <div className="flex items-center gap-1">
            <button type="button" className="btn btn-secondary btn-sm size-8 p-0" aria-label="Предыдущая страница" disabled={current === 0} onClick={() => setPage(current - 1)}>
              <ChevronLeft size={16} />
            </button>
            <span className="num px-2">
              {current + 1} / {pages}
            </span>
            <button type="button" className="btn btn-secondary btn-sm size-8 p-0" aria-label="Следующая страница" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
