"use client";

import { Bell, BookOpenCheck, ChartColumn, ListChecks, MessageSquareText, Moon, Search, Settings, Sun, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { DemoBadge, Logo } from "@/components/ui";
import { CAMPAIGNS, isOpen, PERIOD, SYNC, USER } from "@/lib/demo";
import { AskAi } from "./ask-ai";
import { useDemo } from "./store";
import { WhyDrawer } from "./why-drawer";

type NavItem = { href: string; label: string; hint: string; icon: LucideIcon };

// v1.0 IA (PRD §5): four sections, AI is a button, not a section.
const NAV: NavItem[] = [
  { href: "/demo", label: "Сегодня", hint: "что происходит", icon: BookOpenCheck },
  { href: "/demo/recommendations", label: "Рекомендации", hint: "что сделать", icon: ListChecks },
  { href: "/demo/analytics", label: "Аналитика", hint: "почему так", icon: ChartColumn },
  { href: "/demo/settings", label: "Настройки", hint: "подключения и доступ", icon: Settings },
];

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

function Sidebar({ path, openCount }: { path: string; openCount: number }) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[236px] shrink-0 flex-col border-r border-rule bg-bg lg:flex">
      <Link href="/" className="flex h-16 items-center border-b border-rule px-5" aria-label="AdPilot — на сайт">
        <Logo />
      </Link>
      <div className="border-b border-line px-5 py-3">
        <p className="caption">Рабочее пространство</p>
        <p className="truncate text-sm font-semibold">{USER.workspace}</p>
        <p className="reqs truncate">{USER.account}</p>
      </div>
      <nav className="flex-1 py-3" aria-label="Разделы">
        <ul>
          {NAV.map((n) => {
            const active = isActive(path, n.href);
            const count = n.href === "/demo/recommendations" ? openCount : null;
            return (
              <li key={n.href}>
                <Link
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-baseline gap-2 border-y px-5 py-2.5 ${
                    active ? "border-rule bg-surface text-text" : "border-transparent text-muted hover:text-text"
                  }`}
                >
                  <span className="min-w-0">
                    <span className={`block text-[15px] ${active ? "font-bold" : "font-semibold"}`}>{n.label}</span>
                    <span className="caption block">{n.hint}</span>
                  </span>
                  {count !== null && count > 0 && <span className="money ml-auto text-sm text-danger">{count}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="space-y-3 border-t border-rule p-5">
        <p className="caption">Изменения в рекламе вносятся только после вашего одобрения.</p>
        <Link href="/signup" className="btn btn-ink w-full">
          Запустить свой аудит
        </Link>
      </div>
    </aside>
  );
}

function Freshness() {
  return (
    <p className="reqs hidden items-center gap-3 xl:flex">
      {[
        ["Директ", SYNC.direct],
        ["Метрика", SYNC.metrika],
      ].map(([name, t]) => (
        <span key={name} className="inline-flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-success" aria-hidden /> {name} {t}
        </span>
      ))}
    </p>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button className="btn btn-ghost relative size-10 p-0" aria-label="Уведомления" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Bell size={18} />
        <span className="absolute top-2.5 right-2.5 size-1.5 rounded-full bg-danger" aria-hidden />
      </button>
      {open && (
        <div className="glass anim-fade absolute right-0 z-40 mt-2 w-[300px]">
          {[
            ["Новая проблема: CPA выше цели", `потери ≈ 42 750 ₽ · ${SYNC.date}`, "/demo/recommendations"],
            ["Синхронизация завершена", `Директ ${SYNC.direct} · Метрика ${SYNC.metrika}`, "/demo/settings#integrations"],
          ].map(([t, s, href]) => (
            <Link key={t} href={href} className="block border-b border-line px-4 py-3 last:border-0 hover:bg-surface-2" onClick={() => setOpen(false)}>
              <p className="text-sm font-semibold">{t}</p>
              <p className="caption">{s}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Topbar({ onPalette, theme }: { onPalette: () => void; theme: Theme }) {
  const { setAskOpen } = useDemo();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-rule bg-bg px-4 md:px-6">
      <Link href="/" className="lg:hidden" aria-label="AdPilot — на сайт">
        <Logo size={24} />
      </Link>
      <button onClick={onPalette} className="hidden h-9 min-w-0 items-center gap-2 border-b border-rule px-1 text-sm text-muted hover:text-text md:flex md:w-[260px]">
        <Search size={15} />
        <span className="truncate">Поиск и команды</span>
        <kbd className="reqs ml-auto">Ctrl K</kbd>
      </button>
      <Freshness />
      <div className="ml-auto flex items-center gap-1 md:gap-2">
        <DemoBadge className="hidden sm:inline-flex" />
        <span className="reqs hidden md:inline">{PERIOD}</span>
        <button className="btn btn-primary btn-sm hidden sm:inline-flex" onClick={() => setAskOpen(true)}>
          <MessageSquareText size={15} /> Спросить AI
        </button>
        <button className="btn btn-ghost size-10 p-0" aria-label={theme.dark ? "Светлая тема" : "Тёмная тема"} onClick={theme.toggle}>
          {theme.dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <Notifications />
        <span className="hidden items-center gap-2 border-l border-line pl-3 md:flex">
          <span className="text-sm leading-tight">
            <b>{USER.name}</b>
            <span className="caption block">владелец</span>
          </span>
        </span>
      </div>
    </header>
  );
}

function CommandPalette({ onClose, theme }: { onClose: () => void; theme: Theme }) {
  const router = useRouter();
  const { setAskOpen } = useDemo();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const items = useMemo(() => {
    const go = (href: string) => () => router.push(href);
    const all = [
      ...NAV.map((n) => ({ label: n.label, hint: "Раздел", run: go(n.href) })),
      ...CAMPAIGNS.map((c) => ({ label: c.name, hint: "Кампания", run: go("/demo/analytics") })),
      { label: "Спросить AI", hint: "AI", run: () => setAskOpen(true) },
      { label: "История решений", hint: "Рекомендации", run: go("/demo/recommendations?tab=history") },
      { label: "Интеграции", hint: "Настройки", run: go("/demo/settings#integrations") },
      { label: theme.dark ? "Светлая тема" : "Тёмная тема", hint: "Вид", run: theme.toggle },
    ];
    return all.filter((i) => i.label.toLowerCase().includes(q.toLowerCase()));
  }, [q, router, theme, setAskOpen]);

  useEffect(() => input.current?.focus(), []);

  function run(i: number) {
    items[i]?.run();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-[70] bg-[rgba(23,25,28,0.32)] p-4 pt-[12vh]" onClick={onClose}>
      <div role="dialog" aria-label="Поиск и команды" className="glass anim-fade mx-auto max-w-[560px]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-rule px-4">
          <Search size={18} className="text-muted" />
          <input
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, items.length - 1));
              if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
              if (e.key === "Enter") run(sel);
              if (e.key === "Escape") onClose();
            }}
            placeholder="Раздел, кампания или команда…"
            className="h-14 flex-1 bg-transparent outline-none placeholder:text-muted"
            aria-label="Поиск"
          />
        </div>
        <ul className="max-h-[360px] overflow-auto py-1" role="listbox">
          {items.length === 0 && <li className="p-4 text-sm text-muted">Ничего не найдено</li>}
          {items.map((it, i) => (
            <li key={it.label} role="option" aria-selected={i === sel}>
              <button
                onMouseEnter={() => setSel(i)}
                onClick={() => run(i)}
                className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm ${i === sel ? "bg-surface-2 font-semibold" : ""}`}
              >
                {it.label}
                <span className="caption">{it.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function BottomNav({ path }: { path: string }) {
  const { setAskOpen } = useDemo();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-rule bg-bg pb-[env(safe-area-inset-bottom)] lg:hidden" aria-label="Разделы">
      {NAV.map((n) => {
        const active = isActive(path, n.href);
        return (
          <Link
            key={n.href}
            href={n.href}
            aria-current={active ? "page" : undefined}
            className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] ${active ? "font-bold text-text" : "text-muted"}`}
          >
            <n.icon size={19} strokeWidth={active ? 2.4 : 1.8} /> {n.label}
          </Link>
        );
      })}
      <button onClick={() => setAskOpen(true)} className="flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-semibold text-brand">
        <MessageSquareText size={19} /> Спросить AI
      </button>
    </nav>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const theme = useTheme();
  const { problems } = useDemo();
  const [palette, setPalette] = useState(false);
  const openCount = problems.filter((p) => isOpen(p.status)).length;

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
      <Sidebar path={path} openCount={openCount} />
      <div className="min-w-0 flex-1">
        <Topbar onPalette={() => setPalette(true)} theme={theme} />
        <p className="reqs border-b border-line px-4 py-1.5 text-center text-warning sm:hidden">ДЕМО-ДАННЫЕ · {PERIOD}</p>
        <main className="mx-auto max-w-[1280px] px-4 pt-8 pb-28 md:px-8 lg:pb-16">{children}</main>
      </div>
      <BottomNav path={path} />
      {palette && <CommandPalette onClose={() => setPalette(false)} theme={theme} />}
      <WhyDrawer />
      <AskAi />
    </div>
  );
}
