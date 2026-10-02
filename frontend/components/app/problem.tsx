"use client";

import { Database, X } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { PlatformIcon } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { ACTION_LEVEL_LABEL, type Recommendation } from "@/lib/contract";
import { EXPOSURE_SHORT } from "@/lib/site";
import { formatPeriod, sourceLabel, type Value } from "@/lib/value";
import { RecActions, StatusBadge } from "./rec-actions";
import { ActionText } from "./rec-parts";
import { useDemo } from "./store";

export { RecActions, StatusBadge };

export function MetricCard({
  label,
  v,
  tone = "",
  extra,
  note,
  reason,
}: {
  label: string;
  v: Value;
  tone?: string;
  extra?: ReactNode;
  note?: string;
  reason?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">{label}</p>
        {extra}
      </div>
      <div className="mt-2">
        <ValueView v={v} caption reason={reason} className={`text-[28px] leading-tight md:text-[32px] ${tone}`} />
      </div>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

const LEVEL_STYLE = { inspect_only: "bg-info-bg text-info", review: "bg-warning-bg text-warning", change: "bg-success-bg text-success" };

export function LevelBadge({ level }: { level: Recommendation["action_level"] }) {
  return <span className={`badge ${LEVEL_STYLE[level]}`}>{ACTION_LEVEL_LABEL[level]}</span>;
}

export function RecommendationCard({ r }: { r: Recommendation }) {
  const { openWhy } = useDemo();
  return (
    <article className="card anim-fade flex flex-col p-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge r={r} />
        <LevelBadge level={r.action_level} />
      </div>
      <h3 className="mt-3 text-lg font-bold">
        <ActionText action={r.action} />
      </h3>
      <p className="text-sm text-muted">
        {r.title} · {r.object.name}
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="label">{EXPOSURE_SHORT}</dt>
          <dd>
            <ValueView v={r.exposure} className="text-danger" />
          </dd>
        </div>
        <div>
          <dt className="label">Можно сэкономить</dt>
          <dd>
            <ValueView v={r.can_save} className="text-warning" reason="нет обоснованной формулы эффекта" />
          </dd>
        </div>
      </dl>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted">
        <Database size={13} /> {sourceLabel(r.exposure.source)} · {formatPeriod(r.exposure.period)} · {r.evidence.rule_version}
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <button className="text-sm font-semibold text-brand" onClick={() => openWhy(r.id)}>
          Почему?
        </button>
        <RecActions r={r} compact />
      </div>
    </article>
  );
}

export function LossesList({ recs, selectable = true }: { recs: Recommendation[]; selectable?: boolean }) {
  const { openWhy } = useDemo();
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const all = recs.length > 0 && selected.length === recs.length;
  const overlapNote = (r: Recommendation) => r.exposure_overlap && <span className="block text-[11px] font-normal text-muted">уже учтено в другой карточке</span>;
  const platform = (r: Recommendation) => (r.object.name.startsWith("РСЯ") ? "network" : "search");

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
                    onChange={() => setSelected(all ? [] : recs.map((r) => r.id))}
                    className="size-4 accent-[var(--brand)]"
                  />
                </th>
              )}
              <th className="px-4 py-3 font-medium">Кампания</th>
              <th className="px-4 py-3 font-medium">Проблема</th>
              <th className="px-4 py-3 text-right font-medium">{EXPOSURE_SHORT}, оценка</th>
              <th className="px-4 py-3 text-right font-medium">Действие</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {recs.map((r) => (
              <tr key={r.id} className={`transition-colors hover:bg-surface-2/60 ${selected.includes(r.id) ? "bg-brand-soft/50" : ""}`}>
                {selectable && (
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      aria-label={`Выбрать: ${r.object.name}`}
                      checked={selected.includes(r.id)}
                      onChange={() => toggle(r.id)}
                      className="size-4 accent-[var(--brand)]"
                    />
                  </td>
                )}
                <td className="px-4 py-4">
                  <div className="flex items-center gap-3">
                    <PlatformIcon platform={platform(r)} />
                    <div>
                      <p className="font-semibold">{r.object.name}</p>
                      <p className="text-xs text-muted">Яндекс Директ · {r.ad_account.login}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-4">
                  <p className="font-medium">{r.title}</p>
                  <p className="text-xs text-muted">
                    {r.evidence.rule_version} · {formatPeriod(r.exposure.period)}
                  </p>
                </td>
                <td className="px-4 py-4 text-right whitespace-nowrap">
                  <ValueView v={r.exposure} className="text-danger" />
                  {overlapNote(r)}
                </td>
                <td className="px-4 py-4 text-right">
                  <button className="btn btn-secondary btn-sm" onClick={() => openWhy(r.id)}>
                    Почему и что сделать
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 md:hidden">
        {recs.map((r) => (
          <li key={r.id} className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <StatusBadge r={r} />
              {selectable && (
                <input
                  type="checkbox"
                  aria-label={`Выбрать: ${r.object.name}`}
                  checked={selected.includes(r.id)}
                  onChange={() => toggle(r.id)}
                  className="size-5 accent-[var(--brand)]"
                />
              )}
            </div>
            <p className="mt-3 font-bold">{r.title}</p>
            <p className="text-xs text-muted">{r.object.name}</p>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div>
                <ValueView v={r.exposure} className="text-xl text-danger" />
                {overlapNote(r)}
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => openWhy(r.id)}>
                Почему?
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
