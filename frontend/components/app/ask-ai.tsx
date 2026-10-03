"use client";

import { ArrowUp, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { isOpen, KPI, PERIOD, PREV_KPI, SNAPSHOT, USER, type Problem } from "@/lib/demo";
import { pctChange, rub, signed } from "@/lib/site";
import { useDemo } from "./store";

type Msg = { role: "user" | "ai"; text: string };

const SCREEN: Record<string, { name: string; quick: string[] }> = {
  "/demo": { name: "Сегодня", quick: ["Почему сегодня выросли потери?", "Что сделать сегодня?", "Где самые большие потери?"] },
  "/demo/recommendations": { name: "Рекомендации", quick: ["Почему AdPilot предлагает снизить ставку?", "Что сделать сегодня?"] },
  "/demo/analytics": { name: "Аналитика", quick: ["Что сильнее всего повлияло на CPA за неделю?", "Что изменилось за неделю?"] },
  "/demo/settings": { name: "Настройки", quick: ["Каких данных не хватает?"] },
};

// Answers are templates over computed account data — the assistant never introduces numbers of its own.
function answer(q: string, problems: Problem[]): string {
  const open = problems.filter((p) => isOpen(p.status));
  const top = [...problems].sort((a, b) => b.loss - a.loss)[0];
  switch (q) {
    case "Почему сегодня выросли потери?":
      return `Потери ≈ ${rub(KPI.losses)} за 7 дней против ≈ ${rub(PREV_KPI.losses)} неделей раньше (${signed(pctChange(PREV_KPI.losses, KPI.losses))}%). Больше всего даёт «${top.campaign}»: ${top.reason}.`;
    case "Что сильнее всего повлияло на CPA за неделю?":
      return `CPA ${rub(PREV_KPI.cpa)} → ${rub(KPI.cpa)} (${signed(pctChange(PREV_KPI.cpa, KPI.cpa))}%). Расход ${signed(pctChange(PREV_KPI.spend, KPI.spend))}%, конверсий ${KPI.conversions} вместо ${PREV_KPI.conversions}. Сильнее всего — «${problems[0].campaign}»: ${problems[0].reason}.`;
    case "Где самые большие потери?":
      return problems.map((p, i) => `${i + 1}. ${p.campaign} — ${p.title.toLowerCase()}, ≈ ${rub(p.loss)}`).join("\n");
    case "Что изменилось за неделю?":
      return `К прошлой неделе: расход ${signed(pctChange(PREV_KPI.spend, KPI.spend))}%, конверсии ${signed(pctChange(PREV_KPI.conversions, KPI.conversions))}%, CPA ${signed(pctChange(PREV_KPI.cpa, KPI.cpa))}%, потери ${signed(pctChange(PREV_KPI.losses, KPI.losses))}%.`;
    case "Почему AdPilot предлагает снизить ставку?":
      return `${problems[0].reason}. Правило ${problems[0].rule}: ${problems[0].calc}. Данных достаточно: ${problems[0].checks.join(", ")}.`;
    case "Что сделать сегодня?":
      return open.length
        ? `${open.map((p, i) => `${i + 1}. ${p.recommendation} — ${p.campaign} (потери ≈ ${rub(p.loss)})`).join("\n")}\nКаждое изменение вы одобряете сами.`
        : "Открытых рекомендаций нет. Новые появятся после следующей сверки.";
    case "Каких данных не хватает?":
      return "Не подключён источник выручки: без него ROI, ROAS и ДРР не считаются. Директ и Метрика подключены.";
    default:
      return "Недостаточно данных для ответа в демо. В рабочей версии отвечу на вопрос по данным вашего аккаунта — только по посчитанным цифрам.";
  }
}

/** «Спросить AI»: a side note, not a menu item (PRD §5). Context = workspace, account, period, screen. */
export function AskAi() {
  const { problems, askOpen, setAskOpen } = useDemo();
  const path = usePathname();
  const screen = SCREEN[path] ?? SCREEN["/demo"];
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!askOpen) return;
    field.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setAskOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [askOpen, setAskOpen]);

  if (!askOpen) return null;

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
    <div className="fixed inset-0 z-[60] bg-[rgba(23,25,28,0.32)]" onClick={() => setAskOpen(false)}>
      <aside
        role="dialog"
        aria-modal
        aria-labelledby="ask-title"
        onClick={(e) => e.stopPropagation()}
        className="anim-slide absolute inset-0 flex flex-col bg-bg md:inset-y-0 md:right-0 md:left-auto md:w-[460px] md:border-l md:border-rule"
      >
        <header className="border-b-2 border-text px-5 pt-5 pb-3">
          <div className="flex items-start justify-between gap-3">
            <h2 id="ask-title" className="text-[22px] font-bold">
              Спросить AI
            </h2>
            <button className="btn btn-ghost size-10 p-0" aria-label="Закрыть" onClick={() => setAskOpen(false)}>
              <X size={20} />
            </button>
          </div>
          <p className="reqs mt-1">
            {USER.workspace} · {USER.account} · {PERIOD} · экран «{screen.name}» · снимок #{SNAPSHOT.id}
          </p>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4" aria-live="polite">
          {msgs.length === 0 && (
            <p className="max-w-[44ch] text-sm text-muted">AI объясняет только посчитанные AdPilot цифры. Если данных не хватает, так и скажет.</p>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <p key={i} className="ml-auto w-fit max-w-[85%] border border-rule bg-surface px-3 py-2 text-sm font-semibold">
                {m.text}
              </p>
            ) : (
              <div key={i} className="anim-fade max-w-[92%] border-l-2 border-brand pl-3 text-sm">
                <p className="whitespace-pre-line">{m.text}</p>
                <p className="caption mt-1.5">Пояснение AI по данным снимка #{SNAPSHOT.id}. Проверьте перед применением.</p>
              </div>
            ),
          )}
        </div>

        <div className="border-t border-rule px-5 pt-3 pb-5">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {screen.quick.map((q) => (
              <button key={q} className="text-left text-sm font-semibold text-brand hover:underline" onClick={() => ask(q)}>
                {q}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="mt-3 flex items-center gap-2 border-b border-rule focus-within:border-brand">
            <input
              ref={field}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Вопрос по данным аккаунта…"
              aria-label="Вопрос AI"
              className="h-11 min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted"
            />
            <button className="btn btn-primary size-9 p-0" aria-label="Отправить" disabled={!input.trim()}>
              <ArrowUp size={17} />
            </button>
          </form>
        </div>
      </aside>
    </div>
  );
}
