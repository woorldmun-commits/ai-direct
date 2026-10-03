"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useApp, isOpenRec } from "@/components/layout/app-state";
import { RecStatusBadge, SEVERITY, Badge } from "@/components/ui/badge";
import { Button, buttonCls } from "@/components/ui/button";
import { Drawer } from "@/components/ui/overlay";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { day, sources } from "@/lib/formatters";
import type { Recommendation } from "@/lib/types/domain";
import { SafetyCheckList, SafetyVerdict, VERDICT } from "./safety-check";

function EvidenceGrid({ rec }: { rec: Recommendation }) {
  const e = rec.evidence;
  const rows: [string, React.ReactNode][] = [
    ["Источник", sources(e.sources)],
    ["Период", `${day(e.period.from)} — ${day(e.period.to)}`],
    ["Правило", <code key="r" className="font-mono text-[12px]">{e.rule}</code>],
    ["Данные", e.data_sufficiency === "sufficient" ? <span className="text-success-ink">Достаточно</span> : <span className="text-warning-ink">Недостаточно</span>],
    ["Расчёт", e.formula],
    ["Безопасность", VERDICT[rec.safety.verdict].label],
    ["Снимок данных", <code key="s" className="font-mono text-[12px]">{e.snapshot_id}</code>],
  ];
  return (
    <dl className="divide-y divide-line rounded-xl border border-line">
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[132px_1fr] gap-3 px-4 py-2.5 text-[13px]">
          <dt className="text-muted">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EvidencePanel({ rec }: { rec: Recommendation }) {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={SEVERITY[rec.severity].tone} dot>
            {SEVERITY[rec.severity].label} приоритет
          </Badge>
          <RecStatusBadge rec={rec} />
        </div>
        <h3 className="mt-3 text-[18px] leading-snug font-semibold">{rec.title}</h3>
        <p className="mt-1 text-[13px] text-muted">
          {rec.client} · {rec.campaign}
        </p>
      </div>

      <section aria-labelledby="ev-why">
        <h4 id="ev-why" className="text-[14px] font-semibold">
          Почему AdPilot это рекомендует
        </h4>
        <p className="mt-2 text-[14px] leading-relaxed">{rec.evidence.explanation}</p>
        <p className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-muted">
          <Sparkles size={13} className="text-violet" aria-hidden /> Текст — Explain agent. Числа взяты из доказательств ниже, новых он не вводит.
        </p>
      </section>

      <section aria-labelledby="ev-facts">
        <h4 id="ev-facts" className="mb-2 text-[14px] font-semibold">
          Метрики
        </h4>
        <ul className="grid gap-2 sm:grid-cols-2">
          {rec.evidence.metrics.map((m) => (
            <li key={m.label} className="rounded-xl border border-line px-3.5 py-3">
              <p className="text-[12px] text-muted">{m.label}</p>
              <p className="mt-0.5 text-[18px] font-semibold">
                <ValueText value={m.value} />
              </p>
              <ValueMeta value={m.value} className="mt-1" />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ev-grid">
        <h4 id="ev-grid" className="mb-2 text-[14px] font-semibold">
          Доказательства
        </h4>
        <EvidenceGrid rec={rec} />
      </section>

      <section aria-labelledby="ev-safety">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h4 id="ev-safety" className="text-[14px] font-semibold">
            Safety check
          </h4>
          <SafetyVerdict safety={rec.safety} />
        </div>
        <SafetyCheckList safety={rec.safety} />
        <p className="mt-2 font-mono text-[11px] text-subtle">{rec.safety.policy}</p>
      </section>

      <section aria-labelledby="ev-effect" className="rounded-xl bg-bg p-4">
        <h4 id="ev-effect" className="text-[13px] text-muted">
          {rec.effect.label}
        </h4>
        <p className="mt-0.5 text-[20px] font-semibold">
          <ValueText value={rec.effect.value} />
        </p>
        <ValueMeta value={rec.effect.value} className="mt-1" />
        {rec.action && (
          <p className="mt-3 text-[13px]">
            Рекомендованное действие: <b>{rec.action}</b>
          </p>
        )}
      </section>
    </div>
  );
}

export function EvidenceDrawer() {
  const { recs, evidenceId, openEvidence, openApproval, decide } = useApp();
  const rec = recs.find((r) => r.id === evidenceId);
  const close = () => openEvidence(null);
  const open = !!rec && isOpenRec(rec);

  const footer = rec ? (
    rec.safety.verdict === "blocked" ? (
      <Link href="/integrations" onClick={close} className={buttonCls("primary")}>
        Подключить данные
      </Link>
    ) : open && rec.action_level === "change" ? (
      <>
        <Button
          onClick={() => {
            close();
            openApproval(rec.id);
          }}
        >
          Применить
        </Button>
        <Button variant="secondary" onClick={() => decide(rec.id, "postpone")}>
          Отложить
        </Button>
        <Button variant="ghost" onClick={() => decide(rec.id, "reject")}>
          Не выполнять
        </Button>
      </>
    ) : open ? (
      <>
        <Button onClick={() => decide(rec.id, "checked")}>Отметить проверенным</Button>
        <Button variant="secondary" onClick={() => decide(rec.id, "postpone")}>
          Отложить
        </Button>
      </>
    ) : (
      <Link href="/history" onClick={close} className={buttonCls("secondary")}>
        История решений
      </Link>
    )
  ) : null;

  return (
    <Drawer open={!!rec} onClose={close} title="Почему AdPilot это рекомендует" footer={footer}>
      {rec && <EvidencePanel rec={rec} />}
    </Drawer>
  );
}
