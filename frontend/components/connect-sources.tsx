"use client";

import { BarChart3, Check, Loader2, Megaphone } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { CheckRow, inputCls } from "@/components/form";

// Prototype: simulates the Yandex OAuth round trip; nothing is sent anywhere.

type SourceState = "idle" | "connecting" | "choose" | "connected";

const GOALS = ["Заявка", "Звонок", "Покупка"];

function SourceCard({
  icon: Icon,
  name,
  scope,
  state,
  onConnect,
  choose,
  details,
}: {
  icon: typeof Megaphone;
  name: string;
  scope: string;
  state: SourceState;
  onConnect: () => void;
  choose: ReactNode;
  details: ReactNode;
}) {
  return (
    <article className="card p-5">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand">
          <Icon size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-bold">{name}</h2>
            {state === "connected" && (
              <span className="badge bg-success-bg text-success">
                <span className="size-1.5 rounded-full bg-success" /> Подключено
              </span>
            )}
          </div>
          <p className="text-sm text-muted">{scope}</p>
        </div>
      </div>
      <div className="mt-4">
        {state === "idle" && (
          <>
            <button className="btn btn-primary w-full sm:w-auto" onClick={onConnect}>
              Подключить
            </button>
            <p className="mt-2 text-xs text-muted">Откроется окно Яндекса: разрешите AdPilot доступ к статистике.</p>
          </>
        )}
        {state === "connecting" && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted">
            <Loader2 size={16} className="animate-spin" /> Ждём разрешения в Яндексе…
          </p>
        )}
        {state === "choose" && choose}
        {state === "connected" && details}
      </div>
    </article>
  );
}

export function ConnectSources() {
  const [direct, setDirect] = useState<SourceState>("idle");
  const [metrika, setMetrika] = useState<SourceState>("idle");
  const [goals, setGoals] = useState<string[]>(GOALS);

  const connect = (set: (s: SourceState) => void) => () => {
    set("connecting");
    // Simulates the user coming back from the Yandex OAuth window.
    setTimeout(() => set("choose"), 900);
  };

  const row = (k: string, v: string) => (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );

  return (
    <div className="mt-6 space-y-4">
      <SourceCard
        icon={Megaphone}
        name="Яндекс Директ"
        scope="Расходы · кампании · CPA"
        state={direct}
        onConnect={connect(setDirect)}
        choose={
          <div className="space-y-3">
            <label htmlFor="account" className="text-sm font-medium">
              Рекламный аккаунт
            </label>
            <select id="account" className={inputCls} defaultValue="demo">
              <option value="demo">Демо-аккаунт</option>
            </select>
            <button className="btn btn-primary" onClick={() => setDirect("connected")}>
              Готово
            </button>
          </div>
        }
        details={
          <dl className="space-y-1.5">
            {row("Аккаунт", "Демо-аккаунт")}
            {row("Последняя синхронизация", "только что")}
          </dl>
        }
      />
      <SourceCard
        icon={BarChart3}
        name="Яндекс Метрика"
        scope="Цели · конверсии · диагностика"
        state={metrika}
        onConnect={connect(setMetrika)}
        choose={
          <div className="space-y-3">
            <label htmlFor="counter" className="text-sm font-medium">
              Счётчик
            </label>
            <select id="counter" className={inputCls} defaultValue="1">
              <option value="1">12345678 · демо-сайт</option>
            </select>
            <fieldset>
              <legend className="text-sm font-medium">Цели для расчёта CPA</legend>
              <div className="mt-2 space-y-2">
                {GOALS.map((g) => (
                  <CheckRow key={g} checked={goals.includes(g)} onChange={(on) => setGoals((s) => (on ? [...s, g] : s.filter((x) => x !== g)))}>
                    {g}
                  </CheckRow>
                ))}
              </div>
            </fieldset>
            <button className="btn btn-primary" disabled={goals.length === 0} onClick={() => setMetrika("connected")}>
              Готово
            </button>
          </div>
        }
        details={
          <dl className="space-y-1.5">
            {row("Счётчик", "12345678")}
            {row("Цели", String(goals.length))}
            {row("Последняя синхронизация", "только что")}
          </dl>
        }
      />
      <div className="pt-2">
        {direct === "connected" ? (
          <Link href="/demo" className="btn btn-primary h-12 w-full">
            <Check size={18} /> Запустить бесплатный аудит
          </Link>
        ) : (
          <button className="btn btn-primary h-12 w-full" disabled>
            Запустить бесплатный аудит
          </button>
        )}
        <p className="mt-2 text-center text-xs text-muted">
          {direct !== "connected"
            ? "Для аудита нужен хотя бы Яндекс Директ."
            : metrika === "connected"
              ? "Всё готово. В прототипе аудит откроется на демо-данных."
              : "Можно начать без Метрики, но часть диагностик будет ограничена."}
        </p>
      </div>
    </div>
  );
}
