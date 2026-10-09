"use client";

import {
  Bell,
  CalendarDays,
  GitCompareArrows,
  History,
  LayoutDashboard,
  Lightbulb,
  Menu,
  Moon,
  Plug,
  Search,
  Settings,
  Sun,
  TrendingDown,
  Wallet,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { DemoBadge, Logo } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { DEMO_NOW, LAST_AUDIT_AT, P7, RECOMMENDATIONS, TODAY_DATE, USER } from "@/lib/demo";
import { integrations, parseSources } from "@/lib/demo-backend";
import { formatMoment, formatPeriod } from "@/lib/value";
import { CommandPalette } from "./command-palette";
import { FreshnessBar } from "./freshness";
import { WhyDrawer } from "./why-drawer";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/demo", label: "Сегодня", icon: LayoutDashboard },
  { href: "/demo/losses", label: "Неэффективный расход", icon: TrendingDown },
  { href: "/demo/recommendations", label: "Рекомендации", icon: Lightbulb },
  { href: "/demo/changes", label: "Что изменилось", icon: GitCompareArrows },
  { href: "/demo/finance", label: "Финансы", icon: Wallet },
  { href: "/demo/history", label: "История решений", icon: History },
  { href: "/demo/integrations", label: "Интеграции", icon: Plug },
  { href: "/demo/settings", label: "Настройки", icon: Settings },
];
const MOBILE_NAV = [NAV[0], NAV[1], NAV[2], { ...NAV[5], label: "История" }];

function useTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    // The theme was applied by the inline script in <head>; mirror it into state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);
  function toggle() {
    const next = !dark;
    setDark(next);
    if (next) document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem("adpilot-theme", next ? "dark" : "light");
    } catch {}
  }
  return { dark, toggle };
}

type Theme = ReturnType<typeof useTheme>;

function isActive(path: string, href: string) {
  return href === "/demo" ? path === href : path.startsWith(href);
}

function Sidebar({ path }: { path: string }) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[248px] shrink-0 flex-col border-r border-line bg-surface p-4 lg:flex">
      <Link href="/" className="px-2 py-1" aria-label="AdPilot — на сайт">
        <Logo />
      </Link>
      <nav className="mt-6 flex-1 space-y-0.5" aria-label="Разделы">
        {NAV.map((n) => {
          const active = isActive(path, n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active ? "page" : undefined}
              className={`flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors ${
                active ? "bg-brand-soft text-brand" : "text-muted hover:bg-surface-2 hover:text-text"
              }`}
            >
              <n.icon size={18} />
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="rounded-2xl border border-dashed border-line p-4 opacity-80" aria-disabled>
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Zap size={16} className="text-muted" /> Применение через API после одобрения — в планах
        </p>
        <p className="mt-1 text-xs text-muted">Сейчас изменения в Директе вносите вы, а AdPilot сверяет их по данным и измеряет эффект.</p>
      </div>
      <Link href="/signup" className="btn btn-primary mt-3">
        Заявка на пилот
      </Link>
    </aside>
  );
}

/** «Данные актуальны на …» + per-source status (PRODUCT_SPEC §4.2). Demo: `?sources=stale|no_access`. */
function Freshness({ className = "" }: { className?: string }) {
  const sources = parseSources(useSearchParams().get("sources"));
  return <FreshnessBar lastAuditAt={LAST_AUDIT_AT} items={integrations(sources)} today={TODAY_DATE} now={DEMO_NOW} className={className} />;
}

function Notifications() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button className="btn btn-ghost size-10 p-0" aria-label="Уведомления" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Bell size={18} />
        <span className="absolute top-2 right-2.5 size-2 rounded-full bg-danger" />
      </button>
      {open && (
        <div className="glass anim-fade absolute right-0 z-40 mt-2 w-[300px] rounded-2xl p-2">
          {[
            { t: `Новая проблема: ${RECOMMENDATIONS[0].title}`, v: RECOMMENDATIONS[0].exposure, s: formatMoment(LAST_AUDIT_AT) },
            { t: "Синхронизация завершена", v: null, s: `Директ и Метрика · ${formatMoment(LAST_AUDIT_AT)}` },
          ].map(({ t, v, s }) => (
            <Link key={t} href="/demo/losses" className="block rounded-xl p-3 hover:bg-surface/70" onClick={() => setOpen(false)}>
              <p className="text-sm font-semibold">{t}</p>
              {v && (
                <p className="text-xs text-muted">
                  Расход с признаками неэффективности <ValueView v={v} hint={false} className="font-semibold" />
                </p>
              )}
              <p className="text-xs text-muted">{s}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Topbar({ onPalette, onMenu, theme }: { onPalette: () => void; onMenu: () => void; theme: Theme }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur-xl md:px-6">
      <button className="btn btn-ghost size-10 p-0 lg:hidden" aria-label="Меню" onClick={onMenu}>
        <Menu size={20} />
      </button>
      <button
        onClick={onPalette}
        className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm text-muted md:max-w-[340px]"
      >
        <Search size={16} />
        <span className="truncate">Поиск и команды</span>
        <kbd className="ml-auto hidden rounded-md border border-line px-1.5 font-mono text-[11px] sm:inline">Ctrl K</kbd>
      </button>
      <div className="ml-auto flex items-center gap-1 md:gap-2">
        <DemoBadge className="hidden sm:inline-flex" />
        <span className="hidden items-center gap-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-xs md:inline-flex">
          <CalendarDays size={14} className="text-muted" /> {formatPeriod(P7)}
        </span>
        <button className="btn btn-ghost size-10 p-0" aria-label={theme.dark ? "Светлая тема" : "Тёмная тема"} onClick={theme.toggle}>
          {theme.dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <Notifications />
        <span className="hidden items-center gap-2 pl-2 md:flex">
          <span className="grid size-9 place-items-center rounded-full bg-brand-soft text-sm font-bold text-brand">А</span>
          <span className="text-sm leading-tight">
            <b>{USER.name}</b>
            <span className="block text-xs text-muted">{USER.account}</span>
          </span>
        </span>
      </div>
    </header>
  );
}

function MobileMenu({ path, onClose }: { path: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[65] bg-black/30 lg:hidden" onClick={onClose}>
      <div className="anim-fade absolute inset-x-0 bottom-0 rounded-t-3xl bg-surface p-4 pb-8" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <Logo />
          <button className="btn btn-ghost size-10 p-0" aria-label="Закрыть" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <nav className="grid grid-cols-2 gap-2" aria-label="Все разделы">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              onClick={onClose}
              className={`flex items-center gap-2 rounded-xl border border-line p-3 text-sm ${isActive(path, n.href) ? "bg-brand-soft text-brand" : ""}`}
            >
              <n.icon size={16} /> {n.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}

function BottomNav({ path, onMore }: { path: string; onMore: () => void }) {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      aria-label="Нижняя навигация"
    >
      {MOBILE_NAV.map((n) => (
        <Link
          key={n.href}
          href={n.href}
          className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] ${isActive(path, n.href) ? "text-brand" : "text-muted"}`}
        >
          <n.icon size={20} /> {n.label}
        </Link>
      ))}
      <button onClick={onMore} className="flex h-16 flex-col items-center justify-center gap-1 text-[11px] text-muted">
        <Menu size={20} /> Ещё
      </button>
    </nav>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const theme = useTheme();
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.code === "KeyK") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex min-h-dvh">
      <Sidebar path={path} />
      <div className="min-w-0 flex-1">
        <Topbar onPalette={() => setPalette(true)} onMenu={() => setMenu(true)} theme={theme} />
        <div className="flex items-center justify-center gap-2 bg-warning-bg px-4 py-1.5 text-xs font-semibold text-warning sm:hidden">
          ДЕМО-ДАННЫЕ · {formatPeriod(P7)}
        </div>
        <Suspense fallback={null}>
          <Freshness className="border-b border-line bg-bg/80 px-4 py-2 md:px-6" />
        </Suspense>
        <main className="mx-auto max-w-[1360px] px-4 pt-6 pb-28 md:px-6 lg:pb-12">{children}</main>
      </div>
      <BottomNav path={path} onMore={() => setMenu(true)} />
      {menu && <MobileMenu path={path} onClose={() => setMenu(false)} />}
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
      <WhyDrawer />
    </div>
  );
}
