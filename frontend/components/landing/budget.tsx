"use client";

import { ArrowRight, Lightbulb } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { rub } from "@/lib/site";

const MIN = 100_000;
const MAX = 5_000_000;
const STEP = 50_000;

export function BudgetInput() {
  const [budget, setBudget] = useState(500_000);
  const pct = ((budget - MIN) / (MAX - MIN)) * 100;
  return (
    <section aria-labelledby="budget-title" className="relative mx-auto -mt-10 max-w-[1360px] px-4 md:px-8">
      <div className="card grid gap-8 p-6 shadow-[var(--shadow-md)] md:p-8 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <h2 id="budget-title" className="text-xl font-bold">
            Укажите свой рекламный бюджет
          </h2>
          <p className="mt-1 text-sm text-muted">и узнайте, что AdPilot проверит в вашем аккаунте.</p>
          <label htmlFor="budget" className="mt-5 flex h-12 max-w-[320px] items-center rounded-xl border border-line px-4">
            <span className="money text-xl">{rub(budget)}</span>
            <span className="ml-2 text-sm text-muted">/ месяц</span>
          </label>
          <input
            id="budget"
            type="range"
            min={MIN}
            max={MAX}
            step={STEP}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            aria-labelledby="budget-title"
            aria-valuetext={`${rub(budget)} в месяц`}
            className="mt-5 h-1.5 w-full cursor-pointer appearance-none rounded-full accent-[var(--brand)]"
            style={{ background: `linear-gradient(to right, var(--brand) ${pct}%, var(--border) ${pct}%)` }}
          />
          <div className="mt-2 flex justify-between text-xs text-muted">
            <span>{rub(MIN)}</span>
            <span>{rub(MAX)}</span>
          </div>
        </div>
        <div className="flex gap-4 rounded-2xl bg-surface-2 p-5">
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-brand-soft text-brand">
            <Lightbulb size={20} />
          </span>
          <div>
            <p className="text-sm">
              Мы не обещаем конкретный процент экономии и не знаем вашу цифру, пока не проверим аккаунт. Бесплатный аудит покажет
              реальные проблемы при бюджете <b className="money">{rub(budget)}</b> в месяц — с формулой и источником каждой цифры.
            </p>
            <Link href="/signup" className="btn btn-primary mt-4">
              Проверить свой аккаунт <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
