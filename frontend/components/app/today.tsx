"use client";

import { ArrowRight, History, ListChecks } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { DeltaBadge, ValueView } from "@/components/value-view";
import { LineChart } from "@/components/charts";
import type { TodayResponse } from "@/lib/contract";
import { DEMO_ERROR, DEMO_NOW, integrations, type SourcesScenario } from "@/lib/demo-backend";
import { TODAY_DATE, USER, WEEK } from "@/lib/demo";
import { EXPOSURE, EXPOSURE_NOTE } from "@/lib/site";
import { formatMoment, formatPeriod } from "@/lib/value";
import { StaleNotice } from "./freshness";
import { LevelBadge } from "./problem";
import { ActionText, EVENT_LABEL, HeldNote, OverlapNote, SAVED_NOTE } from "./rec-parts";
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
      <PageHeader title="Сегодня" sub={`${USER.name}, вот что требует вашего внимания. Демонстрационные данные, каждая оценка — с источником.`} />
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
      <div className="overview-grid">
        <div className="overview-focus"><p>{EXPOSURE}</p><div className="mt-3"><ValueView v={today.exposure.total}/></div><small>{EXPOSURE_NOTE}{missing ? ` Без суммы в итог не вошли: ${missing}.` : ""}</small></div>
        <div className="overview-stat"><p>Потрачено за период</p><div className="mt-3"><ValueView v={today.spent}/></div><small>{formatPeriod(today.spent.period)} · Яндекс Директ</small><div className="mt-5 border-t border-line pt-3"><p className="text-xs text-muted">Открытых рекомендаций</p><p className="mt-1 text-xl font-semibold">{counts.active}</p>{byStatus && <small className="text-[10px] text-muted">Требуют решения: {(counts.new ?? 0) + (counts.requires_decision ?? 0)}</small>}</div></div>
        <div className="overview-stat"><p>Результат решений</p><div className="mt-3">{today.saved ? <ValueView v={today.saved} className="text-success"/> : <p className="text-sm text-muted">Недостаточно данных</p>}</div><small>{SAVED_NOTE}</small><Link href="/demo/history" className="mt-5 inline-flex items-center gap-2 text-xs font-semibold text-brand">История решений <ArrowRight size={14}/></Link></div>
      </div>
      <section className="overview-chart" aria-labelledby="pulse-title"><div><h2 id="pulse-title">Пульс бюджета</h2><p>Расход и признаки неэффективности за 7 дней.</p><p>Демо · {formatPeriod(today.spent.period)}</p></div><div><LineChart series={[{name:"Расход",values:WEEK.spend,color:"var(--brand)"},{name:"Неэффективный расход ≈",values:WEEK.exposure,color:"var(--danger)",dashed:true}]} labels={["25 сен","26","27","28","29","30","1 окт"]} height={145} format={v=>new Intl.NumberFormat("ru-RU",{notation:"compact"}).format(v)}/></div></section>

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
                  <p className="text-sm">
                    <ActionText r={r} />
                  </p>
                  <p className="text-xs text-muted">
                    кабинет {r.ad_account.login} · {formatPeriod(r.period)}
                  </p>
                </div>
                <span className="self-start sm:self-auto">
                  <LevelBadge level={r.action_level} />
                </span>
                <span className="sm:max-w-[200px] sm:text-right">
                  <ValueView v={r.exposure} className="text-lg text-danger" />
                  <OverlapNote r={r} className="block text-[11px] text-muted" />
                  <HeldNote r={r} className="block text-[11px] text-muted" />
                </span>
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
