import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline-dark";
export type ButtonSize = "sm" | "md" | "lg";

/** Class string for links that look like buttons. */
export function buttonCls(variant: ButtonVariant = "primary", size: ButtonSize = "md", extra = "") {
  return `btn btn-${variant} ${size === "md" ? "" : `btn-${size}`} ${extra}`.trim();
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
};

export function Button({ variant = "primary", size = "md", loading = false, icon, className = "", children, disabled, type = "button", ...rest }: Props) {
  return (
    <button type={type} className={buttonCls(variant, size, className)} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, children, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" aria-label={label} title={label} className={`btn btn-ghost size-9 p-0 ${className}`} {...rest}>
      {children}
    </button>
  );
}
