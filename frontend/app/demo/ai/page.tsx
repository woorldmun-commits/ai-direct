"use client";

import { ArrowUp, Bot, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useDemo } from "@/components/app/store";
import { Approx, PriorityIcon } from "@/components/ui";
import { exposureTotal, KPI, PREV_KPI, RECOVERABLE, type Problem } from "@/lib/demo";
import { EXPOSURE_SHORT, pctChange, rub, signed } from "@/lib/site";

type Msg = { role: "user" | "ai"; text: string };

// Answers are templates over computed account data — the assistant never invents numbers.
function answer(q: string, problems: Problem[]): string {
  const open = problems.filter((p) => p.status !== "done" && p.status !== "rejected");
  switch (q) {
    case "Почему вырос CPA?":
      return `CPA вырос с ${rub(PREV_KPI.cpa)} до ${rub(KPI.cpa)} (${signed(pctChange(PREV_KPI.cpa, KPI.cpa))}%). Расход изменился на ${signed(pctChange(PREV_KPI.spend, KPI.spend))}%, а конверсий стало ${KPI.conversions} вместо ${PREV_KPI.conversions}. Сильнее всего влияет «${problems[0].campaign}»: ${problems[0].reason}.`;
    case "Где больше всего неэффективного расхода?":
      return `${problems.map((p, i) => `${i + 1}. ${p.campaign} — ${p.title.toLowerCase()}, ≈ ${rub(p.loss)}`).join("\n")}\nРасход с признаками неэффективности ≈ ${rub(exposureTotal(problems).total)} за 7 дней (оценка, одна сумма учтена один раз).`;
    case "Что изменилось за неделю?":
      return `К прошлой неделе: расход ${signed(pctChange(PREV_KPI.spend, KPI.spend))}%, конверсии ${signed(pctChange(PREV_KPI.conversions, KPI.conversions))}%, CPA ${signed(pctChange(PREV_KPI.cpa, KPI.cpa))}%, неэффективный расход ≈ ${signed(pctChange(PREV_KPI.losses, KPI.losses))}%.`;
    case "Что сделать сегодня?":
      return open.length
        ? `${open
            .slice(0, 2)
            .map((p, i) => `${i + 1}. ${p.recommendation} — ${p.campaign} (≈ ${rub(p.loss)})`)
            .join("\n")}\nИзменения в Яндекс Директе вносите вы, затем отметьте решение — через 7 дней я замерю эффект.`
        : "Открытых рекомендаций нет. Я сообщу, когда найду новые проблемы.";
    default:
      return "В демо я отвечаю на быстрые вопросы ниже. В рабочей версии отвечу на любой вопрос по данным вашего аккаунта.";
  }
}

const QUICK = ["Почему вырос CPA?", "Где больше всего неэффективного расхода?", "Что изменилось за неделю?", "Что сделать сегодня?"];

export default function AiDirector() {
  const { problems, openWhy } = useDemo();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const waiting = problems.filter((p) => p.status === "new" || p.status === "in_progress").length;

  function ask(q: string) {
    const text = q.trim().slice(0, 500);
    if (!text) return;
    setMsgs((m) => [...m, { role: "user", text }, { role: "ai", text: answer(text, problems) }]);
    setInput("");
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    ask(input);
  }

  return (
    <div className="mx-auto max-w-[880px]">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-premium text-[#39BFA0]">
          <Bot size={24} />
        </span>
        <div>
          <h1 className="text-[28px] leading-tight font-bold tracking-tight md:text-[32px]">Сегодня я нашёл {problems.length} проблемы.</h1>
          <p className="text-muted">И могу помочь решить их. Отвечаю только по данным аккаунта; цифры считает код.</p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-3 gap-3">
        <div className="card p-4">
          <p className="label">{EXPOSURE_SHORT}</p>
          <Approx className="text-lg text-danger md:text-2xl">{rub(KPI.losses)}</Approx>
        </div>
        <div className="card p-4">
          <p className="label">Можно сэкономить</p>
          <Approx className="text-lg text-warning md:text-2xl">{rub(RECOVERABLE)}</Approx>
        </div>
        <div className="card p-4">
          <p className="label">Ожидают решения</p>
          <p className="money text-lg md:text-2xl">{waiting}</p>
        </div>
      </div>

      <ul className="mt-4 space-y-2">
        {problems.map((p) => (
          <li key={p.id}>
            <button
              onClick={() => openWhy(p.id)}
              className="card flex w-full items-center gap-3 p-4 text-left transition-shadow hover:shadow-[var(--shadow-md)]"
            >
              <PriorityIcon priority={p.priority} size={34} />
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{p.recommendation}</span>
                <span className="block truncate text-xs text-muted">{p.reason}</span>
              </span>
              <Approx className="whitespace-nowrap text-danger">{rub(p.loss)}</Approx>
            </button>
          </li>
        ))}
      </ul>

      <section className="card mt-6 p-5" aria-label="Диалог с AI-Директором">
        {msgs.length > 0 && (
          <div className="mb-4 space-y-3" aria-live="polite">
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <p key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand px-4 py-2 text-sm text-on-brand">
                  {m.text}
                </p>
              ) : (
                <div key={i} className="anim-fade max-w-[90%] rounded-2xl rounded-bl-md bg-surface-2 px-4 py-3 text-sm">
                  <p className="whitespace-pre-line">{m.text}</p>
                  <p className="mt-2 text-xs text-muted">Ответ сгенерирован AI на основе данных аккаунта. Проверьте перед применением.</p>
                </div>
              ),
            )}
          </div>
        )}
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles size={15} className="text-brand" /> Рекомендуемые вопросы
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {QUICK.map((q) => (
            <button key={q} className="chip" onClick={() => ask(q)}>
              {q}
            </button>
          ))}
        </div>
        <form onSubmit={submit} className="mt-4 flex items-center gap-2 rounded-2xl border border-line bg-surface p-1.5 pl-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={500}
            placeholder="Напишите ваш вопрос…"
            aria-label="Вопрос AI-Директору"
            className="h-10 min-w-0 flex-1 bg-transparent outline-none"
          />
          <button className="btn btn-primary size-10 rounded-xl p-0" aria-label="Отправить" disabled={!input.trim()}>
            <ArrowUp size={18} />
          </button>
        </form>
      </section>
    </div>
  );
}
