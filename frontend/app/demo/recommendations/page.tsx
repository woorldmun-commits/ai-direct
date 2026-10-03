"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { RecEntry } from "@/components/app/rec";
import { useDemo } from "@/components/app/store";
import { Amount, PageHeader, Section, StateBox } from "@/components/ui";
import { HISTORY, isOpen, MEASURES, SAVED, SYSTEM_LOG, type HistoryKind, type Problem } from "@/lib/demo";

type Tab = "all" | "new" | "needs_decision" | "done" | "postponed" | "rejected" | "history";

const TABS: { key: Tab; label: string; match?: (p: Problem) => boolean }[] = [
  { key: "all", label: "Все", match: () => true },
  { key: "new", label: "Новые", match: (p) => p.status === "new" },
  { key: "needs_decision", label: "Требуют решения", match: (p) => p.status === "needs_decision" },
  { key: "done", label: "Выполненные", match: (p) => p.status === "applied" || p.status === "checked" },
  { key: "postponed", label: "Отложенные", match: (p) => p.status === "postponed" },
  { key: "rejected", label: "Отклонённые", match: (p) => p.status === "rejected" },
  { key: "history", label: "История решений" },
];

const KIND_LABEL: Record<HistoryKind, string> = {
  found: "Проблема",
  rec: "Рекомендация",
  action: "Ваше решение",
  measure: "Замер",
};

function Measures() {
  return (
    <Section title="Через 7 дней после решения" aside={<Amount value={SAVED} kind="saved" />}>
      {MEASURES.map((m) => (
        <article key={m.id} className="grid gap-3 border-b border-line py-4 md:grid-cols-[1fr_auto]">
          <div>
            <p className="font-bold">{m.title}</p>
            <p className="reqs">
              {m.campaign} · решение {m.decided} · окно {m.window} · {m.rule}
            </p>
            <table className="mt-2 text-sm">
              <tbody>
                {m.rows.map((r) => (
                  <tr key={r.label}>
                    <td className="py-0.5 pr-4 text-muted">{r.label}</td>
                    <td className="money py-0.5 pr-2 font-normal text-muted">{r.before}</td>
                    <td className="py-0.5 pr-2 text-muted">→</td>
                    <td className="money py-0.5">{r.after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="md:text-right">
            <p className="caption">{m.outcome}</p>
            <Amount value={m.value} kind="saved" className="text-[20px]" />
          </div>
        </article>
      ))}
      <p className="caption mt-3 max-w-[70ch]">
        Сэкономлено ≈ — расход за 7 дней до решения минус расход за 7 дней после, если конверсии не упали. Это оценка, а не возврат денег.
      </p>
    </Section>
  );
}

function History() {
  const { actions } = useDemo();
  const events = [
    ...actions.map((a) => ({ date: `сегодня ${a.at}`, kind: "action" as const, title: a.title, detail: "Отмечено в демо", amount: undefined })),
    ...HISTORY,
  ];
  return (
    <div className="space-y-12">
      <Measures />
      <Section title="Журнал решений">
        <ol>
          {events.map((e, i) => (
            <li key={i} className="grid grid-cols-[6.5rem_1fr_auto] gap-3 border-b border-line py-2.5 text-sm">
              <span className="reqs">{e.date}</span>
              <span>
                <span className="caption block">{KIND_LABEL[e.kind]}</span>
                <span className="font-semibold">{e.title}</span>
                <span className="block text-muted">{e.detail}</span>
              </span>
              {e.amount !== undefined && <Amount value={e.amount} kind={e.kind === "measure" ? "saved" : "loss"} />}
            </li>
          ))}
        </ol>
      </Section>
      <Section title="Журнал системы">
        <ul className="reqs">
          {SYSTEM_LOG.map((l) => (
            <li key={l.date + l.text} className="grid grid-cols-[6.5rem_1fr] gap-3 border-b border-line py-2">
              <span>{l.date}</span>
              <span className="text-text">{l.text}</span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Recommendations() {
  const { problems } = useDemo();
  const params = useSearchParams();
  const router = useRouter();
  const tab: Tab = TABS.find((t) => t.key === params.get("tab"))?.key ?? "all";
  const current = TABS.find((t) => t.key === tab)!;
  const shown = current.match ? problems.filter(current.match) : [];
  const open = problems.filter((p) => isOpen(p.status)).length;

  return (
    <>
      <PageHeader title="Рекомендации" sub="Каждое изменение вы одобряете сами. Через 7 дней AdPilot замеряет результат.">
        <span className="reqs">открыто: {open}</span>
      </PageHeader>

      <div className="mb-2 flex gap-5 overflow-x-auto border-b border-line" role="tablist" aria-label="Статус">
        {TABS.map((t) => {
          const n = t.match ? problems.filter(t.match).length : null;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className="chip shrink-0"
              onClick={() => router.replace(t.key === "all" ? "/demo/recommendations" : `/demo/recommendations?tab=${t.key}`, { scroll: false })}
            >
              {t.label}
              {n !== null && <span className="money text-[12px] text-muted">{n}</span>}
            </button>
          );
        })}
      </div>

      <div role="tabpanel">
        {tab === "history" ? (
          <div className="pt-6">
            <History />
          </div>
        ) : shown.length ? (
          shown.map((p, i) => <RecEntry key={p.id} p={p} n={i + 1} />)
        ) : (
          <div className="pt-6">
            <StateBox kind="empty" title="Здесь пока пусто" text="Рекомендации появятся здесь, когда вы примете по ним решение." />
          </div>
        )}
      </div>
    </>
  );
}

export default function RecommendationsPage() {
  return (
    <Suspense>
      <Recommendations />
    </Suspense>
  );
}
