"use client";

import { ArrowRight, CheckCircle2, ListChecks, PiggyBank } from "lucide-react";
import Link from "next/link";
import { Sparkline } from "@/components/charts";
import { MainFocus, MetricCard, StatusBadge } from "@/components/app/problem";
import { useDemo } from "@/components/app/store";
import { Approx, Delta, PageHeader, PriorityIcon } from "@/components/ui";
import { KPI, PREV_KPI, SAVED, SYNC, USER, WEEK } from "@/lib/demo";
import { EXPOSURE_SHORT, pctChange, rub, SAVED_NOTE } from "@/lib/site";

export default function Overview() {
  const { problems, openWhy } = useDemo();
  const [main, ...others] = problems;

  return (
    <>
      <PageHeader title={`Доброе утро, ${USER.name}`} sub="Вот что происходит с вашей рекламой за последние 7 дней." />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <MetricCard label="Потрачено" value={rub(KPI.spend)} extra={<Delta value={pctChange(PREV_KPI.spend, KPI.spend)} goodWhenDown />} />
        <MetricCard
          label={EXPOSURE_SHORT}
          value={rub(KPI.losses)}
          approx
          tone="text-danger"
          note="оценка, без двойного счёта"
          extra={<Delta value={pctChange(PREV_KPI.losses, KPI.losses)} goodWhenDown />}
        />
        <MetricCard label="CPA" value={rub(KPI.cpa)} extra={<Delta value={pctChange(PREV_KPI.cpa, KPI.cpa)} goodWhenDown />} />
        <MetricCard label="Конверсии" value={String(KPI.conversions)} extra={<Delta value={pctChange(PREV_KPI.conversions, KPI.conversions)} />} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[2fr_1fr]">
        <MainFocus p={main} />
        <Link href="/demo/recommendations" className="card group flex flex-col justify-between bg-premium p-6 text-white">
          <div>
            <p className="flex items-center gap-2 text-sm font-semibold text-white/80">
              <ListChecks size={18} className="text-[#39BFA0]" /> Сводка дня
            </p>
            <p className="mt-4 text-xl font-bold">Найдено проблем: {problems.length}.</p>
            <p className="mt-2 text-sm text-white/70">
              Главная — CPA выше цели: это {Math.round((main.loss / KPI.losses) * 100)}% расхода с признаками неэффективности. Решение
              и изменение в Директе — за вами.
            </p>
          </div>
          <span className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-[#39BFA0]">
            К рекомендациям <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
          </span>
        </Link>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
        <section className="card p-5 xl:col-span-2" aria-labelledby="others">
          <div className="flex items-center justify-between">
            <h2 id="others" className="font-bold">
              Другие проблемы
            </h2>
            <Link href="/demo/losses" className="text-sm font-semibold text-brand">
              Все проблемы
            </Link>
          </div>
          <ul className="mt-3 divide-y divide-line">
            {others.map((p) => (
              <li key={p.id}>
                <button onClick={() => openWhy(p.id)} className="flex w-full items-center gap-3 py-3 text-left">
                  <PriorityIcon priority={p.priority} size={32} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{p.title}</span>
                    <span className="block truncate text-xs text-muted">{p.campaign}</span>
                  </span>
                  <span className="hidden sm:inline">
                    <StatusBadge status={p.status} />
                  </span>
                  <Approx className="whitespace-nowrap text-danger">{rub(p.loss)}</Approx>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-5" aria-labelledby="changed">
          <h2 id="changed" className="font-bold">
            Что изменилось
          </h2>
          <p className="text-xs text-muted">к прошлой неделе</p>
          <div className="mt-3 space-y-3">
            {[
              { l: "CPA", v: pctChange(PREV_KPI.cpa, KPI.cpa), s: KPI.cpaDaily },
              { l: "Расход", v: pctChange(PREV_KPI.spend, KPI.spend), s: WEEK.spend },
            ].map((m) => (
              <div key={m.l} className="flex items-center gap-3">
                <span className="w-14 text-sm">{m.l}</span>
                <div className="flex-1">
                  <Sparkline values={m.s} color={m.v > 0 ? "var(--danger)" : "var(--success)"} height={28} />
                </div>
                <Delta value={m.v} goodWhenDown />
              </div>
            ))}
          </div>
          <Link href="/demo/changes" className="mt-3 inline-block text-sm font-semibold text-brand">
            Подробнее
          </Link>
        </section>

        <div className="grid gap-4">
          <section className="card p-5" aria-labelledby="saved">
            <h2 id="saved" className="flex items-center gap-2 text-sm text-muted">
              <PiggyBank size={16} className="text-success" /> Сэкономлено
            </h2>
            <Approx className="mt-1 block text-[28px] text-success">{rub(SAVED)}</Approx>
            <p className="text-xs text-muted">{SAVED_NOTE} · 2 решения в сентябре</p>
          </section>
          <section className="card p-5" aria-labelledby="data">
            <h2 id="data" className="text-sm text-muted">
              Состояние данных
            </h2>
            <ul className="mt-2 space-y-1.5 text-sm">
              <li className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-success" /> Яндекс Директ • {SYNC.direct}
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 size={15} className="text-success" /> Яндекс Метрика • {SYNC.metrika}
              </li>
            </ul>
          </section>
        </div>
      </div>
    </>
  );
}
