"use client";

import { ArrowRight, History, ListChecks } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { DeltaBadge, ValueView } from "@/components/value-view";
import type { TodayResponse } from "@/lib/contract";
import { DEMO_ERROR, DEMO_NOW, integrations, type SourcesScenario } from "@/lib/demo-backend";
import { TODAY_DATE, USER } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_NOTE } from "@/lib/site";
import { formatMoment, formatPeriod } from "@/lib/value";
import { StaleNotice } from "./freshness";
import { LevelBadge, MetricCard } from "./problem";
import { EVENT_LABEL, SAVED_NOTE } from "./rec-parts";
import { ConnectDirect, DemoStateSwitch, ErrorState, LoadingState, NothingFound, type ScreenState } from "./screen-state";
import { useDemo } from "./store";

/**
 * «Сегодня» (PRODUCT_SPEC §5): in 5 seconds — how much ≈ (no double counting), how many problems, 3 actions.
 * Written against `TodayResponse` (API_CONTRACT §8): fields announced for later (`saved`, counts by status,
 * `changes`, `recent_actions`) are shown only when the response has them.
 */
export function TodayScreen({ state, sources }: { state: ScreenState; sources: SourcesScenario }) {
  const demo = useDemo();
  const today = demo.today(sources);

  return (
    <>
      <PageHeader title="Сегодня" sub={`Доброе утро, ${USER.name}. Расход, проблемы и решения по кабинету — с источником каждой цифры.`} />
      <DemoStateSwitch current={state} path="/demo" />
      {state === "loading" && <LoadingState />}
      {state === "error" && <ErrorState error={DEMO_ERROR} retryHref="/demo" />}
      {state === "no_data" && <ConnectDirect />}
      {state === "empty" && (today.audit_scope ? <NothingFound scope={today.audit_scope} lastAuditAt={today.last_audit_at} /> : <ConnectDirect />)}
      {state === "data" && (
        <>
          <StaleNotice items={integrations(sources)} today={TODAY_DATE} now={DEMO_NOW} />
          <TodayData today={today} />
        </>
      )}
    </>
  );
}

function TodayData({ today }: { today: TodayResponse }) {
  const { openWhy } = useDemo();
  const { counts, changes, conversions, recent_actions: recent } = today;
  const byStatus = counts.new !== undefined && counts.requires_decision !== undefined && counts.accepted !== undefined && counts.postponed !== undefined;
  const missing = today.exposure.coverage.unavailable;

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label={EXPOSURE} v={today.exposure.total} tone="text-danger" note={`${EXPOSURE_NOTE}${missing ? ` Без суммы в итог не вошли: ${missing}.` : ""}`} />
        <div className="card p-5">
          <p className="text-sm text-muted">Проблем найдено</p>
          <p className="money mt-2 text-[28px] leading-tight md:text-[32px]">{counts.active}</p>
          {byStatus && (
            <p className="mt-0.5 text-xs text-muted">
              требуют решения: {(counts.new ?? 0) + (counts.requires_decision ?? 0)} · приняты: {counts.accepted} · отложены: {counts.postponed}
            </p>
          )}
        </div>
        <MetricCard label="Потрачено" v={today.spent} />
        {today.saved && <MetricCard label="Сэкономлено" v={today.saved} tone="text-success" note={SAVED_NOTE} />}
      </div>

      <section className="card mt-4 p-5 md:p-6" aria-labelledby="top-actions">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="top-actions" className="flex items-center gap-2 text-lg font-bold">
            <ListChecks size={20} className="text-brand" /> Что сделать сегодня
          </h2>
          <Link href="/demo/recommendations" className="inline-flex items-center gap-1 text-sm font-semibold text-brand">
            Все рекомендации <ArrowRight size={14} />
          </Link>
        </div>
        {today.top.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Открытых рекомендаций нет — все решения приняты.</p>
        ) : (
          <ol className="mt-3 divide-y divide-line">
            {today.top.slice(0, 3).map((r, i) => (
              <li key={r.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
                <span className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold ${i === 0 ? "bg-danger-bg text-danger" : "bg-surface-2 text-muted"}`}>
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{r.title}</p>
                  <p className="text-xs text-muted">
                    {r.object.name} · {formatPeriod(r.period)}
                  </p>
                </div>
                <span className="self-start sm:self-auto">
                  <LevelBadge level={r.action_level} />
                </span>
                <ValueView v={r.exposure} className="text-lg text-danger" />
                <button className="btn btn-secondary btn-sm" onClick={() => openWhy(r.id)}>
                  Почему? Что сделать
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {changes && (
        <section className="card p-5" aria-labelledby="changes-day">
          <h2 id="changes-day" className="font-bold">
            Что изменилось за сутки
          </h2>
          <p className="text-xs text-muted">{formatPeriod(changes.period)}: последний день к предыдущему</p>
          <dl className="mt-3 space-y-2.5 text-sm">
            {[
              { l: "Расход", v: changes.spent_delta_pct, down: true },
              { l: "Конверсии", v: changes.conversions_delta_pct, down: false },
              { l: "CPA", v: changes.cpa_delta_pct, down: true },
            ].map((m) => (
              <div key={m.l} className="flex items-center justify-between gap-3">
                <dt>{m.l}</dt>
                <dd>
                  <DeltaBadge v={m.v} goodWhenDown={m.down} />
                </dd>
              </div>
            ))}
            {conversions && (
              <div className="flex items-center justify-between gap-3 border-t border-line pt-2.5">
                <dt>Конверсии за 7 дней</dt>
                <dd>
                  <ValueView v={conversions} />
                </dd>
              </div>
            )}
          </dl>
          <Link href="/demo/changes" className="mt-3 inline-block text-sm font-semibold text-brand">
            Подробнее
          </Link>
        </section>
        )}

        {recent && (
        <section className="card p-5" aria-labelledby="recent">
          <div className="flex items-center justify-between">
            <h2 id="recent" className="flex items-center gap-2 font-bold">
              <History size={18} className="text-muted" /> Последние решения и проверки
            </h2>
            <Link href="/demo/history" className="text-sm font-semibold text-brand">
              История
            </Link>
          </div>
          <ul className="mt-3 space-y-2.5 text-sm">
            {recent.map((a) => (
              <li key={a.recommendation_id + a.event + a.at} className="flex gap-3">
                <span className="w-[118px] shrink-0 text-xs text-muted">{formatMoment(a.at)}</span>
                <span className="min-w-0">
                  <span className="block font-medium">{EVENT_LABEL[a.event] ?? a.event}</span>
                  <span className="block truncate text-xs text-muted">{a.title}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
        )}
      </div>
    </>
  );
}
