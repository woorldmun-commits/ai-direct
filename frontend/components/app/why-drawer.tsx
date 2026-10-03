"use client";

import { Check, ChevronDown, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Amount, PriorityBadge, StatusMark } from "@/components/ui";
import { PERIOD, SNAPSHOT, SYNC } from "@/lib/demo";
import { RecActions } from "./rec";
import { useDemo } from "./store";

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-3 border-b border-line py-2.5 text-sm">
      <dt className="text-muted">{k}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Паспорт рекомендации (PRD §5): decision and basis first, formula for the marketer below. */
export function WhyDrawer() {
  const { problems, whyId, closeWhy } = useDemo();
  const p = problems.find((x) => x.id === whyId);

  useEffect(() => {
    if (!p) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeWhy();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [p, closeWhy]);

  if (!p) return null;
  const sources = p.id === "cpa" ? "Яндекс Директ + Яндекс Метрика" : "Яндекс Директ";

  return (
    <div className="fixed inset-0 z-[60] bg-[rgba(23,25,28,0.32)]" onClick={closeWhy}>
      <aside
        role="dialog"
        aria-modal
        aria-labelledby="why-title"
        onClick={(e) => e.stopPropagation()}
        className="anim-slide absolute inset-0 overflow-y-auto border-rule bg-bg p-5 md:inset-y-0 md:right-0 md:left-auto md:w-[520px] md:border-l md:p-7"
      >
        <div className="flex items-start justify-between gap-4 border-b-2 border-text pb-3">
          <div>
            <p className="reqs">Паспорт рекомендации · снимок #{SNAPSHOT.id}</p>
            <h2 id="why-title" className="mt-1 text-[22px] leading-snug font-bold text-balance">
              {p.recommendation}
            </h2>
            <div className="mt-2 flex flex-wrap gap-2">
              <PriorityBadge priority={p.priority} />
              <StatusMark status={p.status} />
            </div>
          </div>
          <button className="btn btn-ghost size-10 shrink-0 p-0" aria-label="Закрыть" onClick={closeWhy} autoFocus>
            <X size={20} />
          </button>
        </div>

        <dl className="mt-1">
          <Row k="Проблема">
            <b>{p.title}</b> · {p.campaign}
          </Row>
          <Row k="Основание">{p.reason}</Row>
          <Row k="Период">
            {PERIOD}, {p.days} дней
          </Row>
          <Row k="Источник">
            {sources} · {SYNC.date}, {SYNC.direct}
          </Row>
          <Row k="Качество данных">{p.quality}</Row>
          <Row k="Потери ≈">
            <Amount value={p.loss} kind="loss" className="text-[18px]" bare />
          </Row>
          <Row k="Можно сэкономить ≈">
            {p.saveable ? <Amount value={p.saveable} kind="saveable" className="text-[18px]" bare /> : <span className="text-muted">оценим после проверки</span>}
          </Row>
          <Row k="Ограничения">{p.limits}</Row>
        </dl>

        <section className="mt-5">
          <h3 className="text-[15px] font-bold">Фактические данные</h3>
          <dl className="mt-2 grid grid-cols-3 border-t border-l border-line">
            {p.facts.map((f) => (
              <div key={f.label} className="border-r border-b border-line px-3 py-2">
                <dt className="caption">{f.label}</dt>
                <dd className="money mt-0.5 text-[16px]">{f.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-5">
          <h3 className="text-[15px] font-bold">Проверка безопасности</h3>
          <ul className="mt-2 space-y-1.5 text-sm">
            {p.checks.map((c) => (
              <li key={c} className="flex items-start gap-2">
                <Check size={15} className="mt-0.5 shrink-0 text-success" /> {c}
              </li>
            ))}
            <li className="flex items-start gap-2">
              <Check size={15} className="mt-0.5 shrink-0 text-success" />
              {p.kind === "apply" ? "Данные полные — применение через API разрешено" : "Данные неполные — только ручная проверка"}
            </li>
          </ul>
        </section>

        <section className="mt-5 bg-surface-2 px-4 py-3">
          <h3 className="text-sm font-bold">Пояснение AI</h3>
          <p className="mt-1 text-sm">{p.ai}</p>
          <p className="caption mt-2">AI объясняет расчёт и не вводит новых чисел. Проверьте перед применением.</p>
        </section>

        <details className="group mt-5 border-y border-rule">
          <summary className="flex cursor-pointer list-none items-center justify-between py-3 text-sm font-bold">
            Для маркетолога: формула и версия правила
            <ChevronDown size={16} className="text-muted group-open:rotate-180" />
          </summary>
          <p className="reqs border border-line bg-surface px-3 py-2 text-[13px] text-text">{p.calc}</p>
          <dl className="reqs grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 py-3">
            <dt>rule_version</dt>
            <dd className="text-text">{p.rule}</dd>
            <dt>snapshot</dt>
            <dd className="text-text">
              #{SNAPSHOT.id} · {SYNC.date}
            </dd>
            <dt>engine</dt>
            <dd className="text-text">{SNAPSHOT.engine}</dd>
            <dt>evidence</dt>
            <dd className="text-text">ev_{p.id}_0930</dd>
          </dl>
        </details>

        <section className="mt-6">
          <h3 className="mb-3 text-[15px] font-bold">Решение</h3>
          <RecActions p={p} />
        </section>
      </aside>
    </div>
  );
}
