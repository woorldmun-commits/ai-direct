"use client";

import { ChevronDown, Eye, EyeOff } from "lucide-react";
import { useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

export function Field({ id, label, hint, error, children, className = "" }: { id: string; label: ReactNode; hint?: ReactNode; error?: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-err`} className="mt-1.5 text-[12px] text-danger-ink" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1.5 text-[12px] text-muted">{hint}</p>
      )}
    </div>
  );
}

export function Input({ error, className = "", ...rest }: InputHTMLAttributes<HTMLInputElement> & { error?: string }) {
  return <input className={`input ${className}`} aria-invalid={error ? true : undefined} aria-describedby={error && rest.id ? `${rest.id}-err` : undefined} {...rest} />;
}

export function PasswordInput({ error, ...rest }: InputHTMLAttributes<HTMLInputElement> & { error?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input type={show ? "text" : "password"} error={error} className="pr-11" {...rest} />
      <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Скрыть пароль" : "Показать пароль"} className="absolute top-1/2 right-1.5 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-subtle hover:text-text">
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}

export function Select({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={`relative inline-flex ${className}`}>
      <select className="input h-9 cursor-pointer appearance-none pr-9 text-[13px] font-medium" {...rest}>
        {children}
      </select>
      <ChevronDown size={15} className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-subtle" aria-hidden />
    </span>
  );
}

export function Checkbox({ label, className = "", ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className={`flex cursor-pointer items-start gap-2.5 text-[13px] ${rest.disabled ? "cursor-not-allowed opacity-50" : ""} ${className}`}>
      <input type="checkbox" className="mt-0.5 size-4 shrink-0 cursor-pointer rounded accent-[var(--brand)]" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export function Switch({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${checked ? "bg-brand" : "bg-[#d0d5dd]"}`}
    >
      <span className={`size-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
    </button>
  );
}
