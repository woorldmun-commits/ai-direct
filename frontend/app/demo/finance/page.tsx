import { Bars, Donut } from "@/components/charts";
import { Approx, PageHeader } from "@/components/ui";
import { CAMPAIGNS, MONTH, MONTH_LOSS, MONTH_SPEND, PERIOD, RECOVERABLE, SAVED, SAVINGS } from "@/lib/demo";
import { rub } from "@/lib/site";

const COLORS = ["var(--brand)", "var(--info)", "var(--warning)"];

function Tile({ label, value, tone, bar, note, approx }: { label: string; value: number; tone: string; bar: string; note: string; approx?: boolean }) {
  return (
    <div className="card relative overflow-hidden p-5">
      <span aria-hidden className={`absolute inset-x-0 top-0 h-1 ${bar}`} />
      <p className="text-sm text-muted">{label}</p>
      {approx ? <Approx className={`mt-2 block text-[28px] ${tone}`}>{rub(value)}</Approx> : <p className={`money mt-2 text-[28px] ${tone}`}>{rub(value)}</p>}
      <p className="mt-1 text-xs text-muted">{note}</p>
    </div>
  );
}

export default function Finance() {
  const spend7 = CAMPAIGNS.reduce((s, c) => s + c.spend, 0);
  return (
    <>
      <PageHeader title="Финансы" sub="Сентябрь 2026. Потраченное, потерянное и сэкономленное — разные деньги, мы их не смешиваем." />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Потрачено" value={MONTH_SPEND} tone="" bar="bg-text/20" note="факт по Яндекс Директу" />
        <Tile label="Потери" value={MONTH_LOSS} tone="text-danger" bar="bg-danger" note="расход без результата по правилам" approx />
        <Tile label="Можно вернуть" value={RECOVERABLE} tone="text-warning" bar="bg-warning" note={`открытые рекомендации, ${PERIOD}`} approx />
        <Tile label="Сэкономлено" value={SAVED} tone="text-success" bar="bg-success" note="расчётная оценка после замера" approx />
      </div>

      <section className="card mt-4 p-5" aria-labelledby="trend">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="trend" className="font-bold">
            Динамика расходов и потерь
          </h2>
          <p className="flex gap-4 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-brand" /> Полезный расход
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm bg-danger" /> Потери
            </span>
          </p>
        </div>
        <div className="mt-4">
          <Bars
            a={MONTH.map((d) => d.spend - d.loss)}
            b={MONTH.map((d) => d.loss)}
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
          <p className="text-xs text-muted">{PERIOD}</p>
          <div className="mt-4 flex flex-wrap items-center gap-6">
            <Donut parts={CAMPAIGNS.map((c, i) => ({ label: c.name, value: c.spend, color: COLORS[i] }))} />
            <ul className="min-w-0 flex-1 space-y-3 text-sm">
              {CAMPAIGNS.map((c, i) => (
                <li key={c.name} className="flex items-center gap-3">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: COLORS[i] }} />
                  <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  <span className="money">{rub(c.spend)}</span>
                  <span className="w-10 text-right text-muted">{Math.round((c.spend / spend7) * 100)}%</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="card p-5" aria-labelledby="savings">
          <h2 id="savings" className="font-bold">
            Сэкономлено ≈ {rub(SAVED)}
          </h2>
          <p className="text-xs text-muted">Расчётная оценка: расход до решения минус расход за 7 дней после, при той же цене клика.</p>
          <ul className="mt-4 divide-y divide-line">
            {SAVINGS.map((s) => (
              <li key={s.title} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-semibold">{s.title}</p>
                  <p className="text-xs text-muted">
                    {s.campaign} · замер {s.period}
                  </p>
                </div>
                <Approx className="text-success">{rub(s.value)}</Approx>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
