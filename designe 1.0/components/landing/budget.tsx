"use client";
import { ArrowUpRight } from "lucide-react";
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
    <section
      aria-labelledby="budget-title"
      className="premium-section budget-section"
    >
      <div>
        <h2 id="budget-title">
          Каждый бюджет
          <br />
          заслуживает внимания.
        </h2>
        <p>
          Расход без конверсий, CPA выше цели и площадки РСЯ.
          <br />
          Три проверки, с которых начинается порядок.
        </p>
      </div>
      <div className="budget-control">
        <label htmlFor="budget">Ваш рекламный бюджет в месяц</label>
        <output htmlFor="budget" className="budget-value">
          {rub(budget)}
        </output>
        <input
          id="budget"
          type="range"
          min={MIN}
          max={MAX}
          step={STEP}
          value={budget}
          onChange={(e) => setBudget(Number(e.target.value))}
          aria-label="Рекламный бюджет в месяц"
          aria-valuetext={`${rub(budget)} в месяц`}
          style={{
            background: `linear-gradient(to right, var(--brand) ${pct}%, var(--border) ${pct}%)`,
          }}
        />
        <div className="budget-scale">
          <span>{rub(MIN)}</span>
          <span>{rub(MAX)}</span>
        </div>
        <p>
          Точную оценку можно получить после проверки аккаунта. Возможная
          экономия зависит от ваших данных.
        </p>
        <Link href="/signup" className="text-link">
          Проверить аккаунт <ArrowUpRight size={17} />
        </Link>
      </div>
    </section>
  );
}
