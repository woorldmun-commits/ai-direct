import type { ReactNode } from "react";

export function Card({ children, className = "", as: Tag = "section", ...rest }: { children: ReactNode; className?: string; as?: "section" | "div" | "article" } & { id?: string; "aria-label"?: string }) {
  return (
    <Tag className={`card ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, sub, action, className = "" }: { title: ReactNode; sub?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-x-4 gap-y-2 sm:flex-nowrap ${className}`}>
      <div className="min-w-0">
        <h2 className="text-[15px] leading-6 font-semibold">{title}</h2>
        {sub && <p className="mt-0.5 text-[13px] text-muted">{sub}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}
