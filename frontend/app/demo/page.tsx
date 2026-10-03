"use client";

import Link from "next/link";
import { EntryTable } from "@/components/app/rec";
import { useDemo } from "@/components/app/store";
import { Amount, Delta, LedgerLine, Section, StateBox } from "@/components/ui";
import { isOpen, KPI, MEASURES, PERIOD, PREV_KPI, PREV_PERIOD, SAVED, SNAPSHOT, SYNC, SYSTEM_LOG, USER } from "@/lib/demo";
import { pctChange, rub } from "@/lib/site";

const CHANGES = [
  { name: "Расход", prev: rub(PREV_KPI.spend), cur: rub(KPI.spend), d: pctChange(PREV_KPI.spend, KPI.spend), down: true },
  { name: "Конверсии", prev: String(PREV_KPI.conversions), cur: String(KPI.conversions), d: pctChange(PREV_KPI.conversions, KPI.conversions), down: false },
  { name: "CPA", prev: rub(PREV_KPI.cpa), cur: rub(KPI.cpa), d: pctChange(PREV_KPI.cpa, KPI.cpa), down: true },
  { name: "Потери ≈", prev: rub(PREV_KPI.losses), cur: rub(KPI.losses), d: pctChange(PREV_KPI.losses, KPI.losses), down: true },
];

function ActHeader() {
  return (
    <header className="mb-8 grid gap-4 border-b-2 border-text pb-4 md:grid-cols-[1fr_auto] md:items-end">
      <div>
        <h1 className="text-[34px] leading-none font-bold tracking-[-0.025em] md:text-[44px]">Сегодня</h1>
        <p className="mt-2 text-muted">
          Сверка рекламы <b className="font-semibold text-text">{USER.workspace}</b> с Яндекс Директом за {PERIOD}
        </p>
      </div>
      <dl className="reqs grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 md:text-right">
        <dt>Снимок</dt>
        <dd className="text-text">
          #{SNAPSHOT.id} · {SYNC.date}
        </dd>
        <dt>Директ</dt>
        <dd className="text-text">● обновлён {SYNC.direct}</dd>
        <dt>Метрика</dt>
        <dd className="text-text">● обновлена {SYNC.metrika}</dd>
      </dl>
    </header>
  );
}

export default function Today() {
  const { problems, actions } = useDemo();
  const open = problems.filter((p) => isOpen(p.status));
  const openLoss = open.reduce((s, p) => s + p.loss, 0);
  const saveable = open.reduce((s, p) => s + p.saveable, 0);

  return (
    <>
      <ActHeader />

      <div className="grid gap-10 lg:grid-cols-[1fr_1.05fr] lg:gap-14">
        <Section title="Сальдо за 7 дней" aside={<span className="caption">к {PREV_PERIOD}</span>}>
          <div className="divide-y divide-line">
            <LedgerLine size="lg" label="Потрачено" note={<>факт · Яндекс Директ · <Delta value={pctChange(PREV_KPI.spend, KPI.spend)} goodWhenDown /></>}>
              <Amount value={KPI.spend} kind="fact" />
            </LedgerLine>
            <LedgerLine size="lg" label="Потери ≈" note={<>оценка неэффективного расхода по правилам · <Delta value={pctChange(PREV_KPI.losses, KPI.losses)} goodWhenDown /></>}>
              <Amount value={KPI.losses} kind="loss" bare />
            </LedgerLine>
            <LedgerLine size="lg" label="Можно сэкономить ≈" note="прогноз по открытым рекомендациям, которые можно применить">
              {saveable ? <Amount value={saveable} kind="saveable" bare /> : <span className="text-[17px] text-muted">открытых нет</span>}
            </LedgerLine>
            <LedgerLine size="lg" label="Сэкономлено ≈" note={`измерено через 7 дней после ${MEASURES.length} решений в сентябре`}>
              <Amount value={SAVED} kind="saved" bare />
            </LedgerLine>
            <LedgerLine label="Конверсии" note={<>Яндекс Метрика · CPA {rub(KPI.cpa)}</>}>
              <span className="money">{KPI.conversions}</span>
            </LedgerLine>
          </div>
        </Section>

        <Section
          title={open.length ? `Требуют решения: ${open.length}` : "Все проводки закрыты"}
          aside={
            <Link href="/demo/recommendations" className="font-semibold text-brand hover:underline">
              Все рекомендации
            </Link>
          }
        >
          {open.length ? (
            <>
              <EntryTable problems={open} />
              <p className="mt-4 flex flex-wrap items-baseline justify-between gap-2 text-sm">
                <span className="text-muted">Расхождение по открытым проводкам</span>
                <Amount value={openLoss} kind="loss" className="text-[20px]" />
              </p>
            </>
          ) : (
            <div className="mt-4">
              <StateBox kind="empty" title="Решения приняты" text="Новые проблемы появятся после следующей сверки. Эффект решений замерим через 7 дней." />
            </div>
          )}
        </Section>
      </div>

      <div className="mt-14 grid gap-10 lg:grid-cols-3 lg:gap-12">
        <Section title="Что изменилось" aside={<span className="caption">неделя к неделе</span>}>
          <table className="w-full text-sm">
            <thead>
              <tr className="caption border-b border-line text-right">
                <th className="py-1.5 text-left font-normal">Показатель</th>
                <th className="py-1.5 font-normal">Было</th>
                <th className="py-1.5 font-normal">Стало</th>
                <th className="py-1.5 font-normal">
                  <span className="sr-only">Изменение</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {CHANGES.map((c) => (
                <tr key={c.name} className="border-b border-line text-right">
                  <td className="py-2 text-left">{c.name}</td>
                  <td className="money py-2 font-normal text-muted">{c.prev}</td>
                  <td className="money py-2">{c.cur}</td>
                  <td className="py-2 pl-2">
                    <Delta value={c.d} goodWhenDown={c.down} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Link href="/demo/analytics" className="mt-3 inline-block text-sm font-semibold text-brand hover:underline">
            Разбор в аналитике
          </Link>
        </Section>

        <Section title="Последние действия">
          <ul className="text-sm">
            {actions.map((a) => (
              <li key={a.id + a.at + a.status} className="anim-fade grid grid-cols-[3.5rem_1fr] gap-2 border-b border-line py-2">
                <span className="reqs">{a.at}</span>
                <span className="font-semibold">{a.title}</span>
              </li>
            ))}
            {SYSTEM_LOG.slice(0, 4 - Math.min(actions.length, 2)).map((l) => (
              <li key={l.date + l.text} className="grid grid-cols-[3.5rem_1fr] gap-2 border-b border-line py-2">
                <span className="reqs">{l.date.slice(6)}</span>
                <span className="text-muted">{l.text}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Результат решений" aside={<Amount value={SAVED} kind="saved" className="text-[15px]" />}>
          <ul className="text-sm">
            {MEASURES.map((m) => (
              <li key={m.id} className="flex items-baseline justify-between gap-3 border-b border-line py-2">
                <span>
                  <span className="block font-semibold">{m.title}</span>
                  <span className="caption">
                    {m.campaign} · замер {m.window}
                  </span>
                </span>
                <Amount value={m.value} kind="saved" />
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <footer className="mt-14 grid gap-6 border-t-2 border-text pt-4 text-sm sm:grid-cols-2">
        <div>
          <p className="caption">Сверку провёл</p>
          <p className="font-semibold">AdPilot · правила {SNAPSHOT.engine}</p>
          <p className="reqs">Цифры считает код, AI только объясняет</p>
        </div>
        <div>
          <p className="caption">Решения принимает</p>
          <p className="flex items-end gap-3 font-semibold">
            {USER.name}
            <span className="mb-1 h-px w-28 bg-rule" aria-hidden />
          </p>
          <p className="reqs">Без вашего одобрения в кабинете ничего не меняется</p>
        </div>
      </footer>
    </>
  );
}
