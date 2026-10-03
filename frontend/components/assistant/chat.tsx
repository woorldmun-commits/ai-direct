"use client";

import { ArrowRight, ArrowUp, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Avatar, PageHeader } from "@/components/ui/misc";
import { Skeleton } from "@/components/ui/states";
import { ValueMeta, ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";
import type { AssistantAnswer } from "@/lib/types/domain";

type Msg = { id: number; role: "user" } & { text: string } | { id: number; role: "ai"; answer: AssistantAnswer };

function AnswerCard({ a }: { a: AssistantAnswer }) {
  const ok = a.sufficiency === "sufficient";
  return (
    <div className="card anim-fade max-w-[720px] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={ok ? "success" : "warning"} dot>
          {ok ? "Данных достаточно" : "Недостаточно данных"}
        </Badge>
        <span className="text-[12px] text-muted">Снимок данных от 1 октября, 10:42</span>
      </div>
      <p className="mt-3 text-[14px] leading-relaxed">{a.answer}</p>
      <div className="mt-4">
        <p className="mb-2 text-[12px] font-semibold tracking-wide text-muted uppercase">Факты</p>
        <ul className="space-y-2">
          {a.facts.map((f) => (
            <li key={f.label} className="rounded-xl border border-line px-3.5 py-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-[13px] text-muted">{f.label}</span>
                <span className="text-[15px] font-semibold">
                  <ValueText value={f.value} />
                </span>
              </div>
              <ValueMeta value={f.value} className="mt-1" />
              {f.value.calculation_type === "unavailable" && <p className="mt-1 text-[12px] text-warning-ink">{f.value.missing}</p>}
            </li>
          ))}
        </ul>
      </div>
      {a.links.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {a.links.map((l) => (
            <Link key={l.href} href={l.href} className="inline-flex items-center gap-1 rounded-lg bg-brand-soft px-3 py-1.5 text-[13px] font-medium text-brand hover:bg-[#e2e5ff]">
              {l.label} <ArrowRight size={13} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const user = api.user();

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [msgs, thinking]);

  function ask(q: string) {
    const question = q.trim();
    if (!question || thinking) return;
    setMsgs((m) => [...m, { id: Date.now(), role: "user", text: question }]);
    setText("");
    setThinking(true);
    setTimeout(() => {
      setMsgs((m) => [...m, { id: Date.now(), role: "ai", answer: api.ask(question) }]);
      setThinking(false);
    }, 800);
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(text);
  };

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[1fr_320px]">
      <div className="flex min-h-[calc(100dvh-180px)] flex-col">
        <PageHeader title="AI-аналитик" sub="Задавайте вопросы по данным вашего рекламного кабинета." />
        <div className="flex-1 space-y-5" aria-live="polite">
          {msgs.length === 0 && (
            <div className="card flex flex-col items-center px-6 py-12 text-center">
              <span className="grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-[#7c5cff] to-[#3b82f6] text-white">
                <Sparkles size={22} />
              </span>
              <p className="mt-4 text-[16px] font-semibold">Спросите о своей рекламе</p>
              <p className="mt-1 max-w-[52ch] text-[13px] text-muted">Ответ строится по снимку данных подключённых кабинетов. Каждый ответ показывает факты, источник, период и достаточность данных.</p>
              <div className="mt-6 grid w-full max-w-[640px] gap-2 sm:grid-cols-2">
                {api.suggestedQuestions().map((q) => (
                  <button key={q} type="button" onClick={() => ask(q)} className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-[13px] font-medium transition-colors hover:border-[#c7c9fb] hover:bg-[#fafaff]">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex justify-end gap-3">
                <p className="max-w-[560px] rounded-2xl rounded-tr-md bg-brand px-4 py-2.5 text-[14px] text-white">{m.text}</p>
                <Avatar initials={user.initials} size={32} />
              </div>
            ) : (
              <div key={m.id} className="flex gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#7c5cff] to-[#3b82f6] text-white" aria-hidden>
                  <Sparkles size={15} />
                </span>
                <AnswerCard a={m.answer} />
              </div>
            ),
          )}
          {thinking && (
            <div className="flex gap-3" role="status" aria-label="AI-аналитик готовит ответ">
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
                <Sparkles size={15} />
              </span>
              <div className="card w-full max-w-[720px] space-y-2.5 p-5">
                <Skeleton className="h-3 w-1/3" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            </div>
          )}
          <div ref={end} />
        </div>
        <form onSubmit={submit} className="sticky bottom-20 mt-6 lg:bottom-4">
          <div className="card flex items-end gap-2 p-2 focus-within:border-brand focus-within:shadow-[0_0_0_4px_rgba(91,91,247,0.12)]">
            <label htmlFor="ask" className="sr-only">
              Вопрос AI-аналитику
            </label>
            <textarea
              id="ask"
              rows={1}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(text);
                }
              }}
              placeholder="Например: почему вырос CPA в «Поиск — Москва»?"
              maxLength={500}
              className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[14px] outline-none placeholder:text-subtle"
            />
            <Button type="submit" aria-label="Отправить" className="size-10 p-0" disabled={!text.trim() || thinking}>
              <ArrowUp size={18} />
            </Button>
          </div>
          <p className="mt-2 text-center text-[12px] text-subtle">AI-аналитик не придумывает числа: если данных нет, он так и скажет.</p>
        </form>
      </div>

      <aside className="space-y-6 xl:sticky xl:top-24">
        <Card className="p-5">
          <CardHeader title="Примеры вопросов" />
          <ul className="mt-3 space-y-1">
            {api.suggestedQuestions().map((q) => (
              <li key={q}>
                <button type="button" onClick={() => ask(q)} className="w-full rounded-lg px-2 py-2 text-left text-[13px] text-[#475467] hover:bg-bg hover:text-text">
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-5">
          <CardHeader title="Как отвечает AI" />
          <ul className="mt-3 list-disc space-y-1.5 pl-4 text-[13px] text-muted">
            <li>Числа берёт только из снимка данных — их считает код, не модель.</li>
            <li>В модель уходят обезличенные агрегаты, без ПД и токенов.</li>
            <li>Нет данных — ответ «Недостаточно данных» и что подключить.</li>
            <li>Ничего не меняет в кабинете: действия — через рекомендации.</li>
          </ul>
        </Card>
      </aside>
    </div>
  );
}
