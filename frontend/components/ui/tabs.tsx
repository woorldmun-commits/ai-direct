"use client";

type Option<T extends string> = { value: T; label: string; count?: number };

/** Compact switch, e.g. «7 дней / 30 дней / 90 дней». */
export function Segmented<T extends string>({ options, value, onChange, label }: { options: Option<T>[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-[10px] bg-surface-2 p-0.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`h-7 rounded-lg px-3 text-[12px] font-medium transition-colors ${on ? "bg-surface text-brand shadow-[0_1px_2px_rgba(16,24,40,0.08)]" : "text-muted hover:text-text"}`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Filter row with counts, e.g. «Все (12) · Высокий приоритет (4)». */
export function FilterTabs<T extends string>({ options, value, onChange, label }: { options: Option<T>[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.value)}
            className={`h-8 shrink-0 rounded-lg px-3 text-[13px] font-medium transition-colors ${on ? "bg-brand text-white" : "text-muted hover:bg-surface-2 hover:text-text"}`}
          >
            {o.label}
            {o.count !== undefined && <span className={on ? "ml-1 opacity-80" : "ml-1 text-subtle"}>({o.count})</span>}
          </button>
        );
      })}
    </div>
  );
}
