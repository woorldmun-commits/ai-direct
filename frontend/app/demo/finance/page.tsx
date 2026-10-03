import type { ReactNode } from "react";
import { canSaveNote, SAVED_NOTE } from "@/components/app/rec-parts";
import { Bars, Donut } from "@/components/charts";
import { PageHeader } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { CAMPAIGN_SHARES, MONTH, MONTH_VALUES, P7, RECOMMENDATIONS } from "@/lib/demo";
import { buildToday } from "@/lib/demo-backend";
import { PAST_RECOMMENDATIONS } from "@/lib/demo-history";
import { EXPOSURE, EXPOSURE_SHORT } from "@/lib/site";
import { formatPeriod, type Value } from "@/lib/value";

const COLORS = ["var(--brand)", "var(--info)", "var(--warning)", "var(--muted)"];

function Tile({ label, v, tone = "", bar, note }: { label: string; v: Value; tone?: string; bar: string; note?: ReactNode }) {
  return (
    <div className="card relative overflow-hidden p-5">
      <span aria-hidden className={`absolute inset-x-0 top-0 h-1 ${bar}`} />
      <p className="text-sm text-muted">{label}</p>
      <div className="mt-2">
        <ValueView v={v} caption className={`text-[28px] ${tone}`} />
      </div>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

export default function Finance() {
  // Demo data source: the same contract response the screens get from GET /today.
  const today = buildToday([...RECOMMENDATIONS, ...PAST_RECOMMENDATIONS]);
  const savings = PAST_RECOMMENDATIONS.filter((r) => r.measurement?.saved);
  return (
    <>
      <PageHeader title="Финансы" sub="Сентябрь 2026. Потраченное, расход с признаками неэффективности и сэкономленное — разные деньги, мы их не смешиваем." />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Потрачено" v={MONTH_VALUES.spend} bar="bg-text/20" />
        <Tile label={EXPOSURE} v={MONTH_VALUES.exposure} tone="text-danger" bar="bg-danger" note="без двойного учёта" />
        <Tile label="Можно сэкономить" v={today.can_save.total} tone="text-warning" bar="bg-warning" note={`По открытым рекомендациям. ${canSaveNote(today.can_save)}`} />
        <Tile label="Сэкономлено" v={today.saved} tone="text-success" bar="bg-success" note={SAVED_NOTE} />
      </div>
      <div className="mt-4">
        <Tile label="Выручка и ROAS" v={MONTH_VALUES.revenue} bar="bg-line" note="ROAS и ДРР не считаем, чтобы не выдумывать цифры" />
      </div>

      <section className="card mt-4 p-5" aria-labelledby="trend">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="trend" className="font-bold">
            Расход и неэффективный расход по дням
          </h2>
          <p className="flex gap-4 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-brand" /> Остальной расход
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-danger" /> {EXPOSURE_SHORT} ≈
            </span>
          </p>
        </div>
        <div className="mt-4">
          <Bars
            a={MONTH.map((d) => d.spend - d.exposure)}
            b={MONTH.map((d) => d.exposure)}
            labels={MONTH.map((d) => ([1, 8, 15, 22, 29].includes(d.day) ? `${d.day} сен` : ""))}
            height={200}
          />
        </div>
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="card p-5" aria-labelledby="struct">
          <h2 id="struct" className="font-bold">
            Структура расходов
          </h2>
          <p className="text-xs text-muted">{formatPeriod(P7)}</p>
          <div className="mt-4 flex flex-wrap items-center gap-6">
            <Donut parts={CAMPAIGN_SHARES.map((c, i) => ({ label: c.name, value: c.spend, color: COLORS[i] }))} />
            <ul className="min-w-0 flex-1 space-y-3 text-sm">
              {CAMPAIGN_SHARES.map((c, i) => (
                <li key={c.name} className="flex items-center gap-3">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: COLORS[i] }} />
                  <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  <ValueView v={c.spendValue} />
                  <span className="w-14 text-right text-muted">
                    <ValueView v={c.share} hint={false} className="font-normal" />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="card p-5" aria-labelledby="savings">
          <h2 id="savings" className="flex flex-wrap items-baseline gap-2 font-bold">
            Сэкономлено <ValueView v={today.saved} className="text-success" />
          </h2>
          <p className="text-xs text-muted">{SAVED_NOTE}. Только выполнения, подтверждённые по данным Директа.</p>
          <ul className="mt-4 divide-y divide-line">
            {savings.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-semibold">{r.title}</p>
                  <p className="text-xs text-muted">
                    замер {formatPeriod(r.measurement!.windows.after)}
                    {!r.measurement!.counts_in_saved_total && " · не входит в итог"}
                  </p>
                </div>
                <ValueView v={r.measurement!.saved!} className="text-success" />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
