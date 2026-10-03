"use client";

import { ArrowRight } from "lucide-react";
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
    <section aria-labelledby="budget-title" className="mx-auto max-w-[1280px] px-4 pt-16 md:px-8">
      <div className="grid gap-8 border-b border-rule pb-12 lg:grid-cols-[1.2fr_1fr] lg:gap-16">
        <div>
          <h2 id="budget-title" className="text-[22px] font-bold">
            Сумма к сверке
          </h2>
          <p className="mt-1 text-sm text-muted">Ваш рекламный бюджет в месяц — чтобы понять масштаб проверки.</p>
          <output htmlFor="budget" className="mt-6 block leading-none">
            <span className="money u-fact text-[36px] md:text-[44px]">{rub(budget)}</span>
            <span className="ml-2 text-[16px] text-muted">/ месяц</span>
          </output>
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
            className="mt-6 h-1 w-full cursor-pointer appearance-none accent-[var(--brand)]"
            style={{ background: `linear-gradient(to right, var(--text) ${pct}%, var(--border) ${pct}%)` }}
          />
          <div className="reqs mt-2 flex justify-between">
            <span>{rub(MIN)}</span>
            <span>{rub(MAX)}</span>
          </div>
        </div>
        <div className="self-end">
          <p className="max-w-[52ch]">
            Мы не обещаем конкретный процент потерь и не знаем вашу цифру, пока не проверим кабинет. Бесплатный аудит покажет реальные расхождения при бюджете{" "}
            <b className="money">{rub(budget)}</b> в месяц — с формулой и источником каждой суммы.
          </p>
          <Link href="/signup" className="btn btn-ink mt-5">
            Проверить реальные потери <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </section>
  );
}
