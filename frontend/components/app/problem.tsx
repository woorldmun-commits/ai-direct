"use client";

import { ArrowRight, Database, X } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Approx, PlatformIcon, PriorityBadge, PriorityIcon } from "@/components/ui";
import { exposureTotal, PERIOD, type Problem } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_SHORT, rub } from "@/lib/site";
import { RecActions, StatusBadge } from "./rec-actions";
import { useDemo } from "./store";

export { RecActions, StatusBadge };

export function MetricCard({
  label,
  value,
  approx = false,
  tone = "",
  extra,
  note,
}: {
  label: string;
  value: string;
  approx?: boolean;
  tone?: string;
  extra?: ReactNode;
  note?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">{label}</p>
        {extra}
      </div>
      {approx ? (
        <Approx className={`mt-2 block text-[28px] leading-tight md:text-[32px] ${tone}`}>{value}</Approx>
      ) : (
        <p className={`money mt-2 text-[28px] leading-tight md:text-[32px] ${tone}`}>{value}</p>
      )}
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

export function MainFocus({ p }: { p: Problem }) {
  const { openWhy } = useDemo();
  return (
    <section className="card relative overflow-hidden p-6" aria-labelledby="focus-title">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1 bg-danger" />
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge bg-danger-bg text-danger">Сегодня важнее всего</span>
        <StatusBadge status={p.status} />
      </div>
      <div className="mt-4 flex gap-4">
        <PriorityIcon priority={p.priority} size={44} />
        <div className="min-w-0 flex-1">
          <h2 id="focus-title" className="text-xl font-bold md:text-2xl">
            {p.title}
          </h2>
          <p className="text-sm text-muted">Кампания: {p.campaign}</p>
        </div>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-[auto_1fr] md:items-end">
        <div>
          <p className="label">{EXPOSURE}</p>
          <Approx className="text-[36px] leading-tight text-danger">{rub(p.loss)}</Approx>
          <p className="text-xs text-muted">оценка за {PERIOD}</p>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm md:justify-end">
          {p.facts.map((f) => (
            <div key={f.label}>
              <dt className="label">{f.label}</dt>
              <dd className="money">{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="mt-5 flex flex-col gap-4 rounded-2xl bg-surface-2 p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="label">Рекомендация</p>
          <p className="text-lg font-bold">{p.recommendation}</p>
          <button className="mt-1 inline-flex items-center gap-1 text-sm font-semibold text-brand" onClick={() => openWhy(p.id)}>
            Почему? Расчёт и источник <ArrowRight size={14} />
          </button>
        </div>
        <RecActions id={p.id} status={p.status} />
      </div>
    </section>
  );
}

export function RecommendationCard({ p }: { p: Problem }) {
  const { openWhy } = useDemo();
  return (
    <article className="card anim-fade flex flex-col p-5">
      <div className="flex flex-wrap items-center gap-2">
        <PriorityBadge priority={p.priority} />
        <StatusBadge status={p.status} />
      </div>
      <h3 className="mt-3 text-lg font-bold">{p.recommendation}</h3>
      <p className="text-sm text-muted">
        {p.title} · {p.campaign}
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <div>
          <dt className="label">{EXPOSURE_SHORT}</dt>
          <dd className="money text-danger">≈ {rub(p.loss)}</dd>
        </div>
        <div>
          <dt className="label">Причина</dt>
          <dd>{p.reason}</dd>
        </div>
        <div>
          <dt className="label">Достаточность</dt>
          <dd>{p.checks[1]}</dd>
        </div>
        <div>
          <dt className="label">Качество данных</dt>
          <dd>{p.quality}</dd>
        </div>
      </dl>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
        <Database size={13} /> Яндекс Директ · {PERIOD}
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <button className="text-sm font-semibold text-brand" onClick={() => openWhy(p.id)}>
          Почему?
        </button>
        <RecActions id={p.id} status={p.status} compact />
      </div>
    </article>
  );
}

export function LossesList({ problems, selectable = true }: { problems: Problem[]; selectable?: boolean }) {
  const { openWhy } = useDemo();
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const all = problems.length > 0 && selected.length === problems.length;
  const { covered } = exposureTotal(problems);
  const coveredNote = (id: string) =>
    covered.has(id) && <span className="block text-[11px] font-normal text-muted">уже учтено в другой карточке</span>;

  return (
    <div className="relative">
      <div className="card hidden overflow-hidden md:block">
        <table className="w-full text-sm">
          <thead className="border-b border-line text-left text-xs text-muted">
            <tr>
              {selectable && (
                <th className="w-12 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label="Выбрать все"
                    checked={all}
                    onChange={() => setSelected(all ? [] : problems.map((p) => p.id))}
                    className="size-4 accent-[var(--brand)]"
                  />
                </th>
              )}
              <th className="px-4 py-3 font-medium">Приоритет</th>
              <th className="px-4 py-3 font-medium">Кампания / Площадка</th>
              <th className="px-4 py-3 font-medium">Проблема</th>
              <th className="px-4 py-3 text-right font-medium">{EXPOSURE_SHORT}, оценка</th>
              <th className="px-4 py-3 text-right font-medium">Действие</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {problems.map((p) => (
              <tr key={p.id} className={`transition-colors hover:bg-surface-2/60 ${selected.includes(p.id) ? "bg-brand-soft/50" : ""}`}>
                {selectable && (
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      aria-label={`Выбрать: ${p.campaign}`}
                      checked={selected.includes(p.id)}
                      onChange={() => toggle(p.id)}
                      className="size-4 accent-[var(--brand)]"
                    />
                  </td>
                )}
                <td className="px-4 py-4">
                  <PriorityBadge priority={p.priority} />
                </td>
                <td className="px-4 py-4">
                  <div className="flex items-center gap-3">
                    <PlatformIcon platform={p.platform} />
                    <div>
                      <p className="font-semibold">{p.campaign}</p>
                      <p className="text-xs text-muted">Яндекс Директ · {p.platform === "search" ? "Поиск" : "РСЯ"}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-4">
                  <p className="font-medium">{p.title}</p>
                  <p className="text-xs text-muted">{p.reason}</p>
                </td>
                <td className="money px-4 py-4 text-right whitespace-nowrap text-danger">
                  ≈ {rub(p.loss)}
                  {coveredNote(p.id)}
                </td>
                <td className="px-4 py-4 text-right">
                  <button className="btn btn-secondary btn-sm" onClick={() => openWhy(p.id)}>
                    {p.action}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 md:hidden">
        {problems.map((p) => (
          <li key={p.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <PriorityBadge priority={p.priority} />
              {selectable && (
                <input
                  type="checkbox"
                  aria-label={`Выбрать: ${p.campaign}`}
                  checked={selected.includes(p.id)}
                  onChange={() => toggle(p.id)}
                  className="size-5 accent-[var(--brand)]"
                />
              )}
            </div>
            <p className="mt-3 font-bold">{p.title}</p>
            <p className="text-xs text-muted">{p.campaign}</p>
            <div className="mt-3 flex items-center justify-between">
              <div>
                <Approx className="text-xl text-danger">{rub(p.loss)}</Approx>
                {coveredNote(p.id)}
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => openWhy(p.id)}>
                {p.action}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {selectable && selected.length > 0 && (
        <div className="anim-fade sticky bottom-20 z-20 mt-4 flex items-center justify-between gap-3 rounded-2xl bg-premium px-5 py-3 text-white shadow-[var(--shadow-lg)] lg:bottom-4">
          <span className="text-sm">Выбрано: {selected.length}</span>
          <div className="flex items-center gap-2">
            <Link href="/demo/recommendations" className="btn btn-sm bg-[#39BFA0] text-[#04130f] hover:bg-[#52cfb2]">
              Просмотреть решения ({selected.length})
            </Link>
            <button className="btn btn-sm size-8 p-0 text-white/70 hover:text-white" aria-label="Снять выбор" onClick={() => setSelected([])}>
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
