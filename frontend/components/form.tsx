import Link from "next/link";
import type { ReactNode } from "react";

export const inputCls =
  "h-11 w-full rounded-xl border border-line bg-surface px-3 outline-none focus:border-brand aria-[invalid=true]:border-danger";

export function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && (
        <p id={`${id}-err`} role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function CheckRow({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer gap-3 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 size-4 shrink-0 accent-[var(--brand)]" />
      <span>{children}</span>
    </label>
  );
}

export const docLink = (href: string, text: string) => (
  <Link href={href} className="text-brand underline underline-offset-2">
    {text}
  </Link>
);
