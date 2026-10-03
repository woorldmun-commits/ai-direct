"use client";

import { ArrowRight, CalendarDays, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { AgentFlow } from "@/components/agents/agent-pipeline";
import { SafetyCheckList } from "@/components/evidence/safety-check";
import { isOpenRec, useApp } from "@/components/layout/app-state";
import { RecRow } from "@/components/recommendations/rec-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/states";
import { ValueInfo, ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";
import { num, rub } from "@/lib/formatters";
import type { MetricValue, Verdict } from "@/lib/types/domain";
import { PerformanceCard } from "./performance-card";
import { KpiGrid } from "./widgets";

const linkCls = "inline-flex items-center gap-1 text-[13px] font-medium text-brand hover:underline";

function AgentsCard() {
  const ids = ["collector", "audit", "safety", "explain", "human"];
  const agents = api.agents().filter((a) => ids.includes(a.id));
  return (
    <Card className="p-5">
      <CardHeader title="AI-агенты" sub="Каждый шаг — своя роль. Расчёты и проверки без LLM." action={<Link href="/agents" className={linkCls}>Подробнее</Link>} />
      <div className="mt-5">
        <AgentFlow agents={agents} />
      </div>
    </Card>
  );
}

function SafetyCard() {
  const { recs, openEvidence } = useApp();
  const blocked = recs.find((r) => r.safety.verdict === "blocked");
  const ok = recs.filter((r) => r.safety.verdict !== "blocked").length;
  return (
    <Card className="p-5">
      <CardHeader title="Safety check" sub="Можно ли делать вывод по этим данным" action={<Badge tone="success">{ok} из {recs.length} разрешены</Badge>} />
      {blocked ? (
        <div className="mt-4">
          <div className="flex items-start gap-3 rounded-xl border border-[#fecdca] bg-danger-soft/60 p-3">
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-danger" aria-hidden />
            <div className="min-w-0">
              <p className="text-[13px] font-semibold">{blocked.campaign}</p>
              <p className="text-[12px] text-muted">{blocked.client}</p>
            </div>
          </div>
          <div className="mt-4">
            <SafetyCheckList safety={blocked.safety} dense />
          </div>
          <Button size="sm" variant="secondary" className="mt-4 w-full" onClick={() => openEvidence(blocked.id)}>
            Что подключить, чтобы получить вывод
          </Button>
        </div>
      ) : (
        <EmptyState compact title="Все выводы прошли проверку" />
      )}
    </Card>
  );
}

function MoneyLine({ label, hint, value }: { label: string; hint: string; value: MetricValue }) {
  return (
    <div className="flex items-start justify-between gap-3 py-3">
      <div>
        <p className="text-[13px] font-medium">{label}</p>
        <p className="text-[12px] text-muted">{hint}</p>
      </div>
      <div className="flex items-center gap-1 text-[15px] font-semibold">
        <ValueText value={value} />
        <ValueInfo value={value} />
      </div>
    </div>
  );
}

function MoneyCard() {
  const m = api.money();
  return (
    <Card className="p-5">
      <CardHeader title="Деньги без двойного учёта" sub="Разные виды сумм не складываются" />
      <div className="mt-2 divide-y divide-line">
        <MoneyLine label="Расход" hint="Факт за 30 дней" value={m.spend} />
        <MoneyLine label="Под риском" hint="Оценка по находкам" value={m.at_risk} />
        <MoneyLine label="Потенциал восстановления" hint="Если применить рекомендации" value={m.recoverable} />
        <MoneyLine label="Измеренный эффект" hint="Подтверждено замером до/после" value={api.measuredTotal()} />
      </div>
    </Card>
  );
}

function ProblemsCard() {
  const { recs } = useApp();
  const list = recs.filter((r) => isOpenRec(r) || r.safety.verdict === "blocked").sort((a, b) => ["high", "medium", "low"].indexOf(a.severity) - ["high", "medium", "low"].indexOf(b.severity));
  return (
    <Card className="p-5">
      <CardHeader title="Проблемы и рекомендации" sub="Что произошло, почему и что сделать" action={<Link href="/recommendations" className={linkCls}>Все рекомендации</Link>} />
      {list.length ? (
        <ul className="-mx-3 mt-3 divide-y divide-line">
          {list.slice(0, 5).map((r) => (
            <RecRow key={r.id} rec={r} />
          ))}
        </ul>
      ) : (
        <EmptyState compact title="Нерешённых проблем нет" text="AdPilot проверит кабинеты снова завтра утром." />
      )}
    </Card>
  );
}

const VERDICT: Record<Verdict, [string, "success" | "neutral" | "warning" | "brand"]> = {
  effect: ["Есть эффект", "success"],
  no_effect: ["Нет эффекта", "neutral"],
  not_confirmed: ["Не подтверждено", "warning"],
  insufficient: ["Мало данных", "neutral"],
  pending: ["Идёт замер", "brand"],
};

function ResultsCard() {
  const items = api.measurements().slice(0, 4);
  return (
    <Card className="p-5">
      <CardHeader title="Что произошло после действий" sub="Замер 7 дней до и после изменения" action={<Link href="/history" className={linkCls}>История решений</Link>} />
      <ul className="mt-3 divide-y divide-line">
        {items.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold">{m.recommendation}</p>
              <p className="truncate text-[12px] text-muted">{m.campaign}</p>
            </div>
            <span className="num text-[12px] text-muted">
              {m.rows[0].label}: {m.rows[0].before} <ArrowRight size={11} className="inline" aria-label="→" /> {m.rows[0].after}
            </span>
            <Badge tone={VERDICT[m.verdict][1]}>{VERDICT[m.verdict][0]}</Badge>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AccountsCard() {
  const clients = api.clients();
  return (
    <Card className="p-5">
      <CardHeader title="Подключённые кабинеты" sub="Яндекс Директ · 9 кабинетов" action={<Link href="/integrations" className={linkCls}>+ Добавить</Link>} />
      <ul className="mt-3 space-y-1">
        {clients.map((c) => (
          <li key={c.id}>
            <Link href={`/campaigns?client=${c.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-bg">
              <span className="grid size-8 place-items-center rounded-lg bg-[#fff1e6] text-[12px] font-bold text-[#e04f16]">Я</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">{c.name}</span>
                <span className="block text-[12px] text-muted">
                  {c.accounts} {c.accounts === 1 ? "кабинет" : "кабинета"} · {rub(c.spend)}
                </span>
              </span>
              {c.problems > 0 && <span className="num text-[12px] text-danger">{num(c.problems)} пробл.</span>}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Today() {
  const user = api.user();
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[24px] leading-8 font-semibold tracking-[-0.02em]">
            Добрый день, {user.name}
          </h1>
          <p className="mt-1 text-[14px] text-muted">Вот что происходит с вашей рекламой сегодня.</p>
        </div>
        <span className="inline-flex h-9 items-center gap-2 rounded-[10px] border border-line bg-surface px-3 text-[13px] font-medium" title="Период данных на этом экране">
          <CalendarDays size={15} className="text-subtle" aria-hidden /> 2 сентября — 1 октября 2026
        </span>
      </div>

      <KpiGrid kpis={api.todayKpis()} />

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <PerformanceCard />
        </div>
        <AgentsCard />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <ProblemsCard />
          <ResultsCard />
        </div>
        <div className="space-y-6">
          <SafetyCard />
          <MoneyCard />
          <AccountsCard />
        </div>
      </div>
    </div>
  );
}
