import type { Metadata } from "next";
import Link from "next/link";
import { Bars, LineChart } from "@/components/charts";
import { Amount, Delta, PageHeader, Section, StateBox } from "@/components/ui";
import { CAMPAIGNS, DAYS, KPI, PERIOD, PREV_KPI, PREV_PERIOD, PREV_WEEK, PROBLEMS, SAVEABLE, WEEK } from "@/lib/demo";
import { pctChange, rub } from "@/lib/site";

export const metadata: Metadata = { title: "Аналитика" };

const n = (v: number) => new Intl.NumberFormat("ru-RU").format(v);
const k = (v: number) => (v >= 1000 ? `${Math.round(v / 1000)} тыс.` : String(v));
const prevCpaDaily = PREV_WEEK.spend.map((s, i) => Math.round(s / PREV_WEEK.conversions[i]));

const ROWS = [
  { name: "Расход", prev: rub(PREV_KPI.spend), cur: rub(KPI.spend), d: pctChange(PREV_KPI.spend, KPI.spend), down: true, src: "Директ" },
  { name: "Клики", prev: n(PREV_KPI.clicks), cur: n(KPI.clicks), d: pctChange(PREV_KPI.clicks, KPI.clicks), down: false, src: "Директ" },
  { name: "CTR", prev: `${PREV_KPI.ctr}%`, cur: `${KPI.ctr}%`, d: pctChange(PREV_KPI.ctr, KPI.ctr), down: false, src: "Директ" },
  { name: "Конверсии", prev: n(PREV_KPI.conversions), cur: n(KPI.conversions), d: pctChange(PREV_KPI.conversions, KPI.conversions), down: false, src: "Метрика" },
  { name: "CPA", prev: rub(PREV_KPI.cpa), cur: rub(KPI.cpa), d: pctChange(PREV_KPI.cpa, KPI.cpa), down: true, src: "Директ + Метрика" },
  { name: "Потери ≈", prev: rub(PREV_KPI.losses), cur: rub(KPI.losses), d: pctChange(PREV_KPI.losses, KPI.losses), down: true, src: "правила AdPilot" },
];

const BY_CAMPAIGN = CAMPAIGNS.map((c) => ({
  ...c,
  cpa: Math.round(c.spend / c.conversions),
  loss: PROBLEMS.filter((p) => p.campaign === c.name).reduce((s, p) => s + p.loss, 0),
})).sort((a, b) => b.loss - a.loss);

const FORTNIGHT_LOSSES = [...PREV_WEEK.losses, ...WEEK.losses];
const FORTNIGHT = {
  useful: [...PREV_WEEK.spend, ...WEEK.spend].map((s, i) => s - FORTNIGHT_LOSSES[i]),
  losses: FORTNIGHT_LOSSES,
  labels: ["16", "", "", "19", "", "", "22", "23", "", "", "26", "", "", "29"],
};

export default function Analytics() {
  return (
    <>
      <PageHeader title="Аналитика" sub="Куда ушли деньги, где появились потери и где стало лучше — без захода в рекламный кабинет.">
        <span className="reqs">
          {PERIOD} к {PREV_PERIOD}
        </span>
      </PageHeader>

      <div className="grid gap-12 lg:grid-cols-[1fr_1.2fr]">
        <Section title="Ведомость показателей">
          <table className="w-full text-sm">
            <thead>
              <tr className="caption border-b border-line text-right">
                <th className="py-1.5 text-left font-normal">Показатель</th>
                <th className="py-1.5 font-normal">Прошлая неделя</th>
                <th className="py-1.5 font-normal">Эта неделя</th>
                <th className="py-1.5 font-normal">
                  <span className="sr-only">Изменение</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((r) => (
                <tr key={r.name} className="border-b border-line text-right">
                  <td className="py-2.5 text-left">
                    {r.name}
                    <span className="caption block">{r.src}</span>
                  </td>
                  <td className="money py-2.5 font-normal text-muted">{r.prev}</td>
                  <td className="money py-2.5 text-[16px]">{r.cur}</td>
                  <td className="py-2.5 pl-3">
                    <Delta value={r.d} goodWhenDown={r.down} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Расход и потери по дням" aside={<span className="caption">16–29 сентября</span>}>
          <div className="mt-4">
            <Bars a={FORTNIGHT.useful} b={FORTNIGHT.losses} labels={FORTNIGHT.labels} split={7} height={210} label="Полезный расход и потери по дням за две недели" />
          </div>
          <p className="caption mt-2 flex flex-wrap gap-x-5 gap-y-1">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 bg-text opacity-80" aria-hidden /> Полезный расход
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 bg-danger" aria-hidden /> Потери ≈
            </span>
            <span>пунктир — начало текущей недели</span>
          </p>
        </Section>
      </div>

      <div className="mt-14">
        <Section title="Деньги по кампаниям" aside={<span className="caption">{PERIOD} · сортировка по потерям</span>}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="caption border-b border-line text-right">
                  <th className="py-1.5 text-left font-normal">Кампания</th>
                  <th className="py-1.5 font-normal">Потрачено</th>
                  <th className="py-1.5 font-normal">Клики</th>
                  <th className="py-1.5 font-normal">Конверсии</th>
                  <th className="py-1.5 font-normal">CPA</th>
                  <th className="py-1.5 font-normal">Потери ≈</th>
                  <th className="py-1.5 font-normal">Доля потерь</th>
                </tr>
              </thead>
              <tbody>
                {BY_CAMPAIGN.map((c) => (
                  <tr key={c.name} className="border-b border-line text-right">
                    <td className="py-3 text-left font-semibold">{c.name}</td>
                    <td className="py-3">
                      <Amount value={c.spend} kind="fact" />
                    </td>
                    <td className="money py-3 font-normal">{n(c.clicks)}</td>
                    <td className="money py-3 font-normal">{c.conversions}</td>
                    <td className="money py-3 font-normal">{rub(c.cpa)}</td>
                    <td className="py-3">{c.loss ? <Amount value={c.loss} kind="loss" bare /> : <span className="text-muted">—</span>}</td>
                    <td className="money py-3 font-normal text-muted">{Math.round((c.loss / c.spend) * 100)}%</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="text-right font-bold">
                  <td className="py-3 text-left">Итого</td>
                  <td className="py-3">
                    <span className="money u-total">{rub(KPI.spend)}</span>
                  </td>
                  <td className="money py-3">{n(KPI.clicks)}</td>
                  <td className="money py-3">{KPI.conversions}</td>
                  <td className="money py-3">{rub(KPI.cpa)}</td>
                  <td className="py-3">
                    <Amount value={BY_CAMPAIGN.reduce((s, c) => s + c.loss, 0)} kind="loss" bare />
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="caption mt-2">
            Потери по кампаниям — сумма найденных проблем. Общие потери недели в ведомости шире: они включают дни без явной причины.
          </p>
        </Section>
      </div>

      <div className="mt-14 grid gap-12 lg:grid-cols-2">
        <Section title="CPA по дням">
          <div className="mt-4">
            <LineChart
              height={150}
              labels={DAYS}
              format={k}
              label="CPA по дням: эта неделя и прошлая"
              series={[
                { name: `Эта неделя, ${PERIOD}`, values: KPI.cpaDaily, color: "var(--text)" },
                { name: `Прошлая, ${PREV_PERIOD}`, values: prevCpaDaily, color: "var(--muted)", dashed: true },
              ]}
            />
          </div>
        </Section>

        <Section title="Финансовые показатели">
          <div className="mt-4 space-y-4">
            <StateBox
              kind="insufficient"
              title="Недостаточно данных для ROI, ROAS и ДРР"
              text="Они считаются только по фактической выручке. Подключите источник выручки — до этого мы их не показываем."
              action={
                <Link href="/demo/settings#integrations" className="btn btn-secondary btn-sm">
                  Подключения
                </Link>
              }
            />
            <p className="flex items-baseline justify-between gap-3 border-b border-line pb-2 text-sm">
              <span>Можно сэкономить ≈ по открытым рекомендациям</span>
              <Amount value={SAVEABLE} kind="saveable" className="text-[17px]" bare />
            </p>
          </div>
        </Section>
      </div>
    </>
  );
}
