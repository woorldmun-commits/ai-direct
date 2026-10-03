"use client";

import { Check, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useApp } from "@/components/layout/app-state";
import { RecRow } from "@/components/recommendations/rec-card";
import { buttonCls } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { DemoBadge, PageHeader } from "@/components/ui/misc";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";

const STAGES = [
  { title: "Сбор данных", text: "Кампании, расходы и цели за 30 дней" },
  { title: "Качество данных", text: "Свежесть, полнота, конверсии, период" },
  { title: "Аудит", text: "Правила: CPA к цели, расход без конверсий, лимиты" },
  { title: "Рекомендации", text: "Действия с доказательствами и Safety check" },
];

export function Audit() {
  const { recs } = useApp();
  const [stage, setStage] = useState(0);
  const done = stage >= STAGES.length;
  useEffect(() => {
    if (done) return;
    const t = setTimeout(() => setStage((s) => s + 1), 1100);
    return () => clearTimeout(t);
  }, [stage, done]);
  const findings = recs.filter((r) => r.status !== "applied");
  const pct = Math.round((Math.min(stage, STAGES.length) / STAGES.length) * 100);

  return (
    <>
      <PageHeader title="Бесплатный аудит" sub="Проверяем рекламный кабинет на реальные проблемы и потенциальные потери бюджета." actions={<DemoBadge />} />
      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <p className="text-[14px] font-semibold">{done ? "Аудит завершён" : `Шаг ${stage + 1} из ${STAGES.length}: ${STAGES[stage].title}`}</p>
          <span className="num text-[13px] text-muted">{pct}%</span>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label="Прогресс аудита" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-gradient-to-r from-[#5b5bf7] to-[#7c5cff] transition-[width] duration-700" style={{ width: `${pct}%` }} />
        </div>
        <ol className="mt-6 grid gap-4 md:grid-cols-4">
          {STAGES.map((s, i) => {
            const state = i < stage ? "done" : i === stage ? "active" : "todo";
            return (
              <li key={s.title} className={`rounded-xl border p-4 ${state === "active" ? "border-[#c7c9fb] bg-[#fafaff]" : "border-line"}`}>
                <span className={`grid size-7 place-items-center rounded-full ${state === "done" ? "bg-success-soft text-success" : state === "active" ? "bg-brand text-white" : "bg-surface-2 text-subtle"}`}>
                  {state === "done" ? <Check size={14} strokeWidth={3} /> : state === "active" ? <Loader2 size={14} className="animate-spin" /> : <span className="num text-[12px]">{i + 1}</span>}
                </span>
                <p className="mt-3 text-[13px] font-semibold">{s.title}</p>
                <p className="text-[12px] text-muted">{s.text}</p>
              </li>
            );
          })}
        </ol>
      </Card>

      {done && (
        <div className="anim-fade mt-6 grid items-start gap-6 xl:grid-cols-3">
          <Card className="p-5">
            <CardHeader title="Итог аудита" sub="Демо-результаты в режиме разработки" />
            <dl className="mt-4 space-y-4">
              <div>
                <dt className="text-[13px] text-muted">Под риском за 30 дней</dt>
                <dd className="text-[24px] font-semibold">
                  <ValueText value={api.money().at_risk} />
                </dd>
                <ValueMeta value={api.money().at_risk} />
              </div>
              <div className="flex justify-between text-[13px]">
                <dt className="text-muted">Находок</dt>
                <dd className="font-semibold">{findings.length}</dd>
              </div>
              <div className="flex justify-between text-[13px]">
                <dt className="text-muted">Заблокировано Safety agent</dt>
                <dd className="font-semibold">{findings.filter((r) => r.safety.verdict === "blocked").length}</dd>
              </div>
            </dl>
            <Link href="/recommendations" className={buttonCls("primary", "md", "mt-6 w-full")}>
              Перейти к рекомендациям
            </Link>
          </Card>
          <Card className="p-5 xl:col-span-2">
            <CardHeader title="Что нашёл аудит" sub="Нажмите, чтобы увидеть доказательства" />
            <ul className="-mx-3 mt-3 divide-y divide-line">
              {findings.map((r) => (
                <RecRow key={r.id} rec={r} />
              ))}
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}
