"use client";

import { ChevronRight } from "lucide-react";
import { isOpenRec, useApp } from "@/components/layout/app-state";
import { Badge, RecStatusBadge, SeverityIcon } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { formatValue } from "@/lib/formatters";
import type { MetricValue, Recommendation } from "@/lib/types/domain";

export function relativeDay(iso: string) {
  const d = new Date(iso).toDateString();
  const today = new Date("2026-10-02").toDateString();
  const y = new Date("2026-10-01").toDateString();
  return d === today ? "Сегодня" : d === y ? "Вчера" : new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

const signedValue = (v: MetricValue) => `${v.amount && v.amount > 0 ? "+" : ""}${formatValue(v)}`.replace("-", "−");

function headline(rec: Recommendation) {
  const dev = rec.facts.find((f) => f.label === "Отклонение" || f.label === "Изменение");
  return dev && dev.value.calculation_type !== "unavailable" ? dev.value : null;
}

function PrimaryAction({ rec }: { rec: Recommendation }) {
  const { openApproval, openEvidence, decide } = useApp();
  if (rec.safety.verdict === "blocked" || !isOpenRec(rec)) {
    return (
      <Button size="sm" variant="secondary" onClick={() => openEvidence(rec.id)}>
        Посмотреть
      </Button>
    );
  }
  if (rec.action_level === "review") {
    return (
      <Button size="sm" variant="secondary" onClick={() => decide(rec.id, "checked")}>
        Отметить проверенным
      </Button>
    );
  }
  return (
    <Button size="sm" onClick={() => openApproval(rec.id)}>
      Применить
    </Button>
  );
}

/** Full card: problem → cause → facts → action → effect → evidence. */
export function RecCard({ rec }: { rec: Recommendation }) {
  const { openEvidence } = useApp();
  const dev = headline(rec);
  const blocked = rec.safety.verdict === "blocked";
  return (
    <article className="card p-5 transition-shadow hover:shadow-[0_8px_30px_rgba(15,23,42,0.08)]">
      <div className="flex gap-4">
        <SeverityIcon severity={rec.severity} blocked={blocked} done={rec.status === "applied"} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 text-[15px] leading-6 font-semibold">
                {rec.title}
                {dev && <span className="num text-[13px] font-semibold text-danger">{signedValue(dev)}</span>}
              </h3>
              <p className="mt-0.5 text-[12px] text-muted">
                {rec.client} · {rec.campaign}
              </p>
            </div>
            <RecStatusBadge rec={rec} />
          </div>

          <p className="mt-3 text-[13px] text-[#475467]">
            <span className="font-medium text-text">Причина: </span>
            {rec.cause}
          </p>

          <ul className="mt-3 flex flex-wrap gap-2">
            {rec.facts.map((f) => (
              <li key={f.label} className="rounded-lg bg-bg px-2.5 py-1.5 text-[12px]">
                <span className="text-muted">{f.label} </span>
                <ValueText value={f.value} className="font-semibold" />
              </li>
            ))}
          </ul>
          <ValueMeta value={rec.facts[0].value} className="mt-2" />

          <div className="mt-4 flex flex-wrap items-end justify-between gap-4 border-t border-line pt-4">
            <div className="grid gap-x-8 gap-y-2 text-[13px] sm:grid-cols-2">
              <div>
                <p className="text-[12px] text-muted">Рекомендованное действие</p>
                <p className="font-semibold">{rec.action ?? (blocked ? "Рекомендация не сформирована: недостаточно данных" : "—")}</p>
              </div>
              <div>
                <p className="text-[12px] text-muted">{rec.effect.label}</p>
                <p className="font-semibold">
                  <ValueText value={rec.effect.value} />
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="mr-1 text-[12px] text-subtle">{relativeDay(rec.created_at)}</span>
              <Button size="sm" variant="ghost" onClick={() => openEvidence(rec.id)}>
                Почему?
              </Button>
              <PrimaryAction rec={rec} />
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

/** Compact row for «Сегодня». */
export function RecRow({ rec }: { rec: Recommendation }) {
  const { openEvidence } = useApp();
  const dev = headline(rec);
  const blocked = rec.safety.verdict === "blocked";
  return (
    <li>
      <button type="button" onClick={() => openEvidence(rec.id)} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors hover:bg-bg">
        <SeverityIcon severity={rec.severity} blocked={blocked} done={rec.status === "applied"} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-[13.5px] font-semibold">
            <span className="truncate">{rec.title}</span>
            {dev && <span className="num shrink-0 text-[12px] text-danger">{signedValue(dev)}</span>}
          </span>
          <span className="block truncate text-[12px] text-muted">{blocked ? "Рекомендация не сформирована: недостаточно данных" : `Рекомендация: ${rec.action}`}</span>
        </span>
        <span className="hidden shrink-0 text-right sm:block">
          {rec.effect.value.calculation_type !== "unavailable" ? (
            <span className="num block text-[13px] font-semibold">{formatValue(rec.effect.value)}</span>
          ) : (
            <Badge tone="neutral">нет оценки</Badge>
          )}
          <span className="block text-[11px] text-subtle">{relativeDay(rec.created_at)}</span>
        </span>
        <ChevronRight size={16} className="shrink-0 text-subtle" aria-hidden />
      </button>
    </li>
  );
}
