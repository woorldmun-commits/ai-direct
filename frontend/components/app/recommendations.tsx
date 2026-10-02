"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader, StateBox } from "@/components/ui";
import { ruleName, RULE_TITLE } from "@/lib/contract";
import { AUDIT_SCOPE, DEMO_ERROR } from "@/lib/demo-backend";
import { LAST_AUDIT_AT } from "@/lib/demo";
import { RecommendationCard } from "./problem";
import { TABS, type RecFilter } from "./rec-filter";
import { ConnectDirect, DemoStateSwitch, ErrorState, LoadingState, NothingFound, type ScreenState } from "./screen-state";
import { useDemo } from "./store";

export function RecommendationsScreen({
  state,
  filter: initial,
  rule,
  campaign,
}: {
  state: ScreenState;
  filter: RecFilter;
  rule?: string;
  campaign?: string;
}) {
  const { active } = useDemo();
  const [tab, setTab] = useState<RecFilter>(initial);
  const scoped = active.filter((r) => (!rule || ruleName(r.evidence.rule_version).startsWith(rule)) && (!campaign || r.object.id === campaign));
  const match = TABS.find((t) => t.key === tab)!.match;
  const shown = scoped.filter((r) => match(r.status));
  const ruleScope = rule ? { ...AUDIT_SCOPE, rules: AUDIT_SCOPE.rules.filter((rv) => rv.startsWith(rule)) } : AUDIT_SCOPE;
  const selection = rule ? RULE_TITLE[rule] ?? rule : campaign ? active.find((r) => r.object.id === campaign)?.object.name ?? "кампания" : null;

  return (
    <>
      <PageHeader
        title="Рекомендации"
        sub="AdPilot не меняет кабинет. Вы принимаете решение и вносите изменение в Яндекс Директе вручную, а AdPilot сверяет его по данным Директа и измеряет эффект."
      />
      <DemoStateSwitch current={state} path="/demo/recommendations" />
      {selection && (
        <p className="mb-3 text-sm">
          Выборка: <b>{selection}</b> ·{" "}
          <Link href="/demo/recommendations" className="font-semibold text-brand">
            показать все
          </Link>
        </p>
      )}
      {state === "loading" && <LoadingState cards={2} />}
      {state === "error" && <ErrorState error={DEMO_ERROR} retryHref="/demo/recommendations" />}
      {state === "no_data" && <ConnectDirect />}
      {(state === "empty" || (state === "data" && scoped.length === 0)) && (
        <NothingFound scope={ruleScope} lastAuditAt={LAST_AUDIT_AT} title={selection ? `${selection}: проблем не найдено — вот что проверено` : undefined} />
      )}
      {state === "data" && scoped.length > 0 && (
        <>
          <div className="mb-4 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Статус">
            {TABS.map((t) => (
              <button key={t.key} className="chip shrink-0" aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
                {t.label} ({scoped.filter((r) => t.match(r.status)).length})
              </button>
            ))}
          </div>
          {shown.length ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {shown.map((r) => (
                <RecommendationCard key={r.id} r={r} />
              ))}
            </div>
          ) : (
            <StateBox
              kind="empty"
              title="С этим статусом рекомендаций нет"
              text={tab === "done" ? "Отметьте «Выполнено вручную» после изменения в Директе. Прошлые замеры — в «Истории решений»." : "Выберите другой фильтр."}
            />
          )}
        </>
      )}
    </>
  );
}
