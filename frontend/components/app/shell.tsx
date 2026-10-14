"use client";

import {
  Bell,
  BarChart3,
  FileText,
  Bot,
  Megaphone,
  CalendarDays,
  GitCompareArrows,
  History,
  LayoutDashboard,
  Lightbulb,
  Menu,
  Plug,
  Search,
  Settings,
  TrendingDown,
  TrendingUp,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
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
  { href: "/demo/campaigns", label: "Кампании", icon: Megaphone },
  { href: "/demo/analytics", label: "Аналитика", icon: BarChart3 },
  { href: "/demo/assistant", label: "AI-помощник", icon: Bot },
  { href: "/demo/effect", label: "Эффект", icon: TrendingUp },
  { href: "/demo/reports", label: "Отчёты", icon: FileText },
  { href: "/demo/plans", label: "Тарифы", icon: Wallet },
];
const CORE_NAV = [NAV[9], NAV[2], NAV[11], NAV[6], NAV[7]];
const EXTRA_NAV = NAV.filter((n) => !CORE_NAV.includes(n));
const MOBILE_NAV = [{ ...NAV[9], label: "Анализ" }, NAV[2], NAV[11], { ...NAV[6], label: "Источники" }];

function isActive(path: string, href: string) {
  return href === "/demo" ? path === href : path.startsWith(href);
}

function Sidebar({ path }: { path: string }) {
  const navLink = (n: NavItem) => <Link key={n.href} href={n.href} aria-current={isActive(path, n.href) ? "page" : undefined} className={`app-nav-link flex h-11 items-center gap-3 rounded-xl px-3 text-[13px] font-medium transition-colors ${isActive(path, n.href) ? "bg-brand-soft text-brand" : "text-muted hover:bg-surface-2 hover:text-text"}`}><n.icon size={18}/>{n.href === "/demo/analytics" ? "Анализ" : n.href === "/demo/integrations" ? "Подключения" : n.label}</Link>;
  return (
    <aside className="app-sidebar sticky top-0 hidden h-dvh w-[248px] shrink-0 flex-col border-r border-line p-4 lg:flex">
      <nav className="flex-1 space-y-1 pb-3" aria-label="Разделы">
        {CORE_NAV.map(navLink)}
        <details key={path} open={EXTRA_NAV.some(n => isActive(path,n.href))} className="sidebar-more"><summary>Все инструменты</summary><div className="mt-2 space-y-1">{EXTRA_NAV.map(navLink)}</div></details>
      </nav>
      <div className="sidebar-meta px-3"><span>Тариф</span><strong className="block my-2 text-text">Контроль · демо</strong><small>Вы принимаете решения</small></div>
      <Link href="/signup" className="btn btn-primary mt-3">
        Запустить свой аудит
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

function Topbar({ onPalette, onMenu }: { onPalette: () => void; onMenu: () => void }) {
  return (
    <header className="app-topbar sticky top-0 z-30 flex h-[76px] items-center gap-3 border-b border-line px-4 md:px-6">
      <Link href="/" className="cabinet-brand" aria-label="AdPilot — на сайт"><Logo size={23}/></Link>
      <button className="btn btn-ghost size-10 p-0 lg:hidden" aria-label="Меню" onClick={onMenu}>
        <Menu size={20} />
      </button>
      <button
        onClick={onPalette}
        aria-label="Поиск и команды"
        className="cabinet-command flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-sm text-muted md:max-w-[340px]"
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
        <Link href="/demo/assistant" className="cabinet-ai" aria-label="AI-помощник">AI ◉</Link>
        <Notifications />
        <Link href="/demo/settings#profile" aria-label="Открыть профиль" className="hidden items-center gap-2 pl-2 md:flex">
          <span className="cabinet-avatar"><Image src="/figma/liquid/6-40708-img1.png" alt="" width={1600} height={1200} unoptimized /></span>
          <span className="text-sm leading-tight">
            <b>{USER.name}</b>
            <span className="block text-xs text-muted">{USER.account}</span>
          </span>
        </Link>
      </div>
    </header>
  );
}

function MobileMenu({ path, onClose }: { path: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog ref={dialog} className="app-mobile-menu glass fixed inset-x-0 top-auto bottom-0 m-0 w-full max-w-none rounded-t-3xl p-0 text-text" aria-label="Все разделы" onCancel={onClose} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="anim-fade p-4 pb-8">
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
              aria-current={isActive(path, n.href) ? "page" : undefined}
              className={`flex items-center gap-2 rounded-xl border border-line p-3 text-sm ${isActive(path, n.href) ? "bg-brand-soft text-brand" : ""}`}
            >
              <n.icon size={16} /> {n.label}
            </Link>
          ))}
        </nav>
      </div>
    </dialog>
  );
}

function BottomNav({ path, onMore }: { path: string; onMore: () => void }) {
  return (
    <nav
      className="app-bottom-nav glass fixed inset-x-3 bottom-3 z-30 grid grid-cols-5 rounded-[22px] pb-[env(safe-area-inset-bottom)] lg:hidden"
      aria-label="Нижняя навигация"
    >
      {MOBILE_NAV.map((n) => (
        <Link
          key={n.href}
          href={n.href}
          aria-current={isActive(path, n.href) ? "page" : undefined}
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
    <div className="app-shell flex min-h-dvh">
      <Topbar onPalette={() => setPalette(true)} onMenu={() => setMenu(true)} />
      <Sidebar path={path} />
      <div className="app-workspace">
        <div className="flex items-center justify-center gap-2 bg-warning-bg px-4 py-1.5 text-xs font-semibold text-warning sm:hidden">
          ДЕМО-ДАННЫЕ · {formatPeriod(P7)}
        </div>
        <details className="cabinet-freshness"><summary>Данные аудита</summary><Suspense fallback={null}><Freshness className="p-3" /></Suspense></details>
        <main id="main-content" key={path} className="app-content mx-auto max-w-[1360px] px-4 pt-8 pb-28 md:px-8 lg:pb-12">{children}</main>
      </div>
      <BottomNav path={path} onMore={() => setMenu(true)} />
      {menu && <MobileMenu path={path} onClose={() => setMenu(false)} />}
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
      <WhyDrawer />
    </div>
  );
}
