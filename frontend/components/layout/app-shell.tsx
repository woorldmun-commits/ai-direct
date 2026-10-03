"use client";

import { BarChart3, Lightbulb, MoreHorizontal, Sparkles, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ApprovalDialog } from "@/components/approval/approval-dialog";
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer";
import { useApp } from "./app-state";
import { isActive } from "./nav";
import { Sidebar, SidebarContent } from "./sidebar";
import { Topbar } from "./topbar";

const BOTTOM = [
  { href: "/today", label: "Сегодня", icon: Sun },
  { href: "/recommendations", label: "Решения", icon: Lightbulb },
  { href: "/analytics", label: "Аналитика", icon: BarChart3 },
  { href: "/assistant", label: "AI", icon: Sparkles },
];

function MobileNav({ open, onClose, path }: { open: boolean; onClose: () => void; path: string }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] lg:hidden">
      <button type="button" aria-label="Закрыть меню" className="absolute inset-0 bg-[rgba(7,17,31,0.42)]" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="Меню" className="anim-slide absolute inset-y-0 left-0 w-[280px] max-w-[85vw] bg-surface shadow-[0_24px_64px_rgba(15,23,42,0.24)]" style={{ animationName: "fade-in" }}>
        <button type="button" onClick={onClose} aria-label="Закрыть меню" className="btn btn-ghost absolute top-3 right-3 size-10 p-0">
          <X size={20} />
        </button>
        <SidebarContent path={path} onNavigate={onClose} />
      </div>
    </div>
  );
}

function BottomNav({ path, onMore }: { path: string; onMore: () => void }) {
  return (
    <nav aria-label="Быстрая навигация" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
      {BOTTOM.map((n) => {
        const active = isActive(path, n.href);
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined} className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium ${active ? "text-brand" : "text-muted"}`}>
            <n.icon size={20} strokeWidth={active ? 2.3 : 1.9} aria-hidden /> {n.label}
          </Link>
        );
      })}
      <button type="button" onClick={onMore} className="flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium text-muted">
        <MoreHorizontal size={20} aria-hidden /> Ещё
      </button>
    </nav>
  );
}

function Toasts() {
  const { toasts } = useApp();
  return (
    <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-20 z-[80] flex flex-col items-end gap-2 lg:bottom-6">
      {toasts.map((t) => (
        <p key={t.id} className="anim-pop rounded-xl bg-navy px-4 py-3 text-[13px] font-medium text-white shadow-[0_12px_32px_rgba(7,17,31,0.3)]">
          {t.text}
        </p>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [menu, setMenu] = useState(false);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- close the mobile menu on navigation
  useEffect(() => setMenu(false), [path]);

  return (
    <div className="flex min-h-dvh bg-bg">
      <Sidebar path={path} />
      <div className="min-w-0 flex-1">
        <Topbar onMenu={() => setMenu(true)} />
        <main id="main" className="mx-auto w-full max-w-[1360px] px-4 pt-6 pb-28 md:px-8 md:pt-8 lg:pb-12">
          {children}
        </main>
      </div>
      <BottomNav path={path} onMore={() => setMenu(true)} />
      <MobileNav open={menu} onClose={() => setMenu(false)} path={path} />
      <EvidenceDrawer />
      <ApprovalDialog />
      <Toasts />
    </div>
  );
}
