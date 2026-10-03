"use client";

import { ArrowRight, Check, Clock, RotateCcw, X } from "lucide-react";
import { useState } from "react";
import { Amount, PlatformIcon, PriorityBadge, Stamp, StatusMark } from "@/components/ui";
import { isOpen, PERIOD, SNAPSHOT, type Problem } from "@/lib/demo";
import { useDemo } from "./store";

const STAMP_TIME = () => new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

/** «Было → Станет»: the exact version of the change a human approves (PRD §5, применение через API). */
export function ChangePreview({ change }: { change: NonNullable<Problem["change"]> }) {
  return (
    <dl className="grid grid-cols-[1fr_auto_1fr] items-end gap-x-3 border border-rule bg-surface px-4 py-3">
      <dt className="caption col-span-3 mb-1">{change.what}</dt>
      <dd>
        <span className="caption block">Было</span>
        <span className="money text-[17px] text-muted line-through decoration-1">{change.before}</span>
      </dd>
      <dd aria-hidden className="pb-1 text-muted">
        <ArrowRight size={16} />
      </dd>
      <dd>
        <span className="caption block">Станет</span>
        <span className="money text-[17px]">{change.after}</span>
      </dd>
    </dl>
  );
}

/** Human decision. The product never changes the ad account on its own. */
export function RecActions({ p, compact = false }: { p: Problem; compact?: boolean }) {
  const { decide, lastStamped } = useDemo();
  const [preview, setPreview] = useState(false);
  const sm = compact ? "btn-sm" : "";

  if (p.status === "applied" || p.status === "checked") {
    const applied = p.status === "applied";
    return (
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <Stamp text={applied ? "Применено" : "Проверено"} sub={`${STAMP_TIME()} · Алексей`} animate={lastStamped === p.id} tone={applied ? "brand" : "success"} />
        <p className="caption max-w-[44ch]">
          {applied
            ? "Через 7 дней сравним расход до и после и покажем «Сэкономлено ≈»."
            : "Проблема проверена. Изменений в рекламе не зафиксировано. Продолжаем наблюдение."}
        </p>
        {applied && (
          <button className="btn btn-ghost btn-sm" onClick={() => decide(p.id, "needs_decision")}>
            <RotateCcw size={14} /> Вернуть назад
          </button>
        )}
      </div>
    );
  }

  if (p.status === "postponed" || p.status === "rejected") {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <StatusMark status={p.status} />
        <button className="btn btn-ghost btn-sm" onClick={() => decide(p.id, "needs_decision")}>
          Вернуть к решению
        </button>
      </div>
    );
  }

  if (p.kind === "check") {
    return (
      <div className="flex flex-wrap gap-2">
        <button className={`btn btn-ink ${sm}`} onClick={() => decide(p.id, "checked")}>
          <Check size={16} /> Проверил
        </button>
        <button className={`btn btn-secondary ${sm}`} onClick={() => decide(p.id, "postponed")}>
          <Clock size={15} /> Позже
        </button>
      </div>
    );
  }

  if (preview && p.change) {
    return (
      <div className="anim-fade w-full max-w-[460px] space-y-3">
        <ChangePreview change={p.change} />
        <p className="caption">
          Причина: {p.reason}. Источник: Яндекс Директ, снимок #{SNAPSHOT.id}. В демо изменение никуда не отправляется.
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            className={`btn btn-primary ${sm}`}
            onClick={() => {
              decide(p.id, "applied");
              setPreview(false);
            }}
          >
            <Check size={16} /> Применить
          </button>
          <button className={`btn btn-secondary ${sm}`} onClick={() => setPreview(false)}>
            Отмена
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <button className={`btn btn-ink ${sm}`} onClick={() => setPreview(true)}>
        {p.action} <ArrowRight size={15} />
      </button>
      <button className={`btn btn-secondary ${sm}`} onClick={() => decide(p.id, "postponed")}>
        Отложить
      </button>
      <button className={`btn btn-ghost ${sm}`} onClick={() => decide(p.id, "rejected")} aria-label={`Отклонить: ${p.recommendation}`}>
        <X size={15} /> Отклонить
      </button>
    </div>
  );
}

/** Entries to close the discrepancy: compact table for «Сегодня». */
export function EntryTable({ problems }: { problems: Problem[] }) {
  const { openWhy } = useDemo();
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="caption border-b border-rule">
          <th className="w-8 py-2 font-normal">№</th>
          <th className="py-2 font-normal">Содержание</th>
          <th className="py-2 text-right font-normal">Потери ≈</th>
          <th className="hidden w-[1%] py-2 pl-4 font-normal sm:table-cell" />
        </tr>
      </thead>
      <tbody>
        {problems.map((p, i) => (
          <tr key={p.id} className="border-b border-line align-top">
            <td className="reqs py-3">{i + 1}</td>
            <td className="py-3 pr-3">
              <button onClick={() => openWhy(p.id)} className="text-left font-semibold hover:text-brand hover:underline">
                {p.recommendation}
              </button>
              <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-muted">
                <PlatformIcon platform={p.platform} /> {p.campaign} · {p.title.toLowerCase()}
              </p>
            </td>
            <td className="py-3 text-right text-[16px]">
              <Amount value={p.loss} kind="loss" bare />
            </td>
            <td className="hidden py-3 pl-4 sm:table-cell">
              <button className="btn btn-secondary btn-sm" onClick={() => openWhy(p.id)}>
                Решить
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Full entry for «Рекомендации»: what, why, how much, decision. */
export function RecEntry({ p, n }: { p: Problem; n: number }) {
  const { openWhy } = useDemo();
  const open = isOpen(p.status);
  return (
    <article className={`grid gap-4 border-b border-line py-5 md:grid-cols-[2.5rem_1fr_auto] ${open ? "" : "opacity-90"}`}>
      <span className="reqs pt-1">{String(n).padStart(2, "0")}</span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <PriorityBadge priority={p.priority} />
          <StatusMark status={p.status} />
          {p.kind === "check" && <span className="badge text-muted">Проверить вручную</span>}
        </div>
        <h3 className="mt-2 text-[19px] leading-snug font-bold">{p.recommendation}</h3>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-sm text-muted">
          <PlatformIcon platform={p.platform} /> {p.campaign} · {p.reason}
        </p>
        <p className="reqs mt-2">
          Яндекс Директ · {PERIOD} · снимок #{SNAPSHOT.id} · {p.rule} · уверенность: {p.quality.toLowerCase()}
        </p>
        <button className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline" onClick={() => openWhy(p.id)}>
          Почему? Расчёт и основание <ArrowRight size={14} />
        </button>
        <div className="mt-4">
          <RecActions p={p} />
        </div>
      </div>
      <dl className="flex gap-6 md:block md:min-w-[170px] md:space-y-3 md:text-right">
        <div>
          <dt className="caption">Потери ≈</dt>
          <dd className="text-[20px]">
            <Amount value={p.loss} kind="loss" bare />
          </dd>
        </div>
        <div>
          <dt className="caption">Можно сэкономить ≈</dt>
          <dd className="text-[17px]">{p.saveable ? <Amount value={p.saveable} kind="saveable" bare /> : <span className="text-sm text-muted">после проверки</span>}</dd>
        </div>
      </dl>
    </article>
  );
}
