"use client";

import { Bell, Building2, Check, ChevronDown, Menu, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { buttonCls } from "@/components/ui/button";
import { Avatar, DemoBadge } from "@/components/ui/misc";
import { Popover } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/permissions";
import { useApp } from "./app-state";
import { MAIN_NAV, SECONDARY_NAV } from "./nav";

type Hit = { label: string; hint: string; href: string };

function SearchBox() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const hits = useMemo<Hit[]>(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const all: Hit[] = [
      ...[...MAIN_NAV, ...SECONDARY_NAV].map((n) => ({ label: n.label, hint: "Раздел", href: n.href })),
      ...api.campaigns().map((c) => ({ label: c.name, hint: "Кампания", href: `/campaigns/${c.id}` })),
      ...api.clients().map((c) => ({ label: c.name, hint: "Клиент", href: `/campaigns?client=${c.id}` })),
    ];
    return all.filter((h) => h.label.toLowerCase().includes(s)).slice(0, 8);
  }, [q]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.code === "KeyK") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function go(h: Hit | undefined) {
    if (!h) return;
    router.push(h.href);
    setQ("");
    setOpen(false);
    input.current?.blur();
  }

  return (
    <div className="relative hidden w-full max-w-[420px] md:block">
      <Search size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" aria-hidden />
      <input
        ref={input}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setSel(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, hits.length - 1));
          if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
          if (e.key === "Enter") go(hits[sel]);
          if (e.key === "Escape") input.current?.blur();
        }}
        placeholder="Поиск по проектам, кампаниям, клиентам…"
        aria-label="Поиск"
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls="search-results"
        className="input h-10 rounded-[10px] bg-surface pr-14 pl-9 text-[13px]"
      />
      <kbd className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded-md border border-line px-1.5 text-[11px] text-subtle">Ctrl K</kbd>
      {open && q && (
        <ul id="search-results" role="listbox" className="glass anim-fade absolute top-12 left-0 z-50 w-full py-1.5">
          {hits.length === 0 && <li className="px-4 py-3 text-[13px] text-muted">Ничего не найдено</li>}
          {hits.map((h, i) => (
            <li key={h.href + h.label} role="option" aria-selected={i === sel}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => go(h)} onMouseEnter={() => setSel(i)} className={`flex w-full items-center justify-between px-4 py-2 text-left text-[13px] ${i === sel ? "bg-surface-2" : ""}`}>
                {h.label}
                <span className="text-[12px] text-subtle">{h.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Notifications() {
  const items = [
    { t: "Новая проблема: расход без конверсий", s: "РСЯ — Акции · сегодня, 09:12", href: "/recommendations?open=r-promo-zero" },
    { t: "Рекомендация не сформирована: недостаточно данных", s: "РСЯ — Охват · сегодня, 09:12", href: "/recommendations?open=r-reach-blocked" },
    { t: "Не удалось получить данные из Яндекс Директ", s: "Кабинет planeta-spb · 10:42", href: "/integrations" },
  ];
  return (
    <Popover
      label="Уведомления"
      width={340}
      trigger={({ open, toggle }) => (
        <button type="button" onClick={toggle} aria-expanded={open} aria-label="Уведомления, 3 новых" className="btn btn-ghost relative size-10 p-0">
          <Bell size={19} />
          <span className="absolute top-2 right-2.5 size-2 rounded-full border-2 border-bg bg-danger" aria-hidden />
        </button>
      )}
    >
      {(close) => (
        <div className="py-1.5">
          <p className="px-4 py-2 text-[13px] font-semibold">Уведомления</p>
          {items.map((n) => (
            <Link key={n.t} href={n.href} onClick={close} className="block px-4 py-2.5 hover:bg-surface-2">
              <p className="text-[13px] font-medium">{n.t}</p>
              <p className="text-[12px] text-muted">{n.s}</p>
            </Link>
          ))}
        </div>
      )}
    </Popover>
  );
}

function WorkspaceSelect() {
  const { workspace, setWorkspace, notify } = useApp();
  const list = api.workspaces();
  const current = list.find((w) => w.id === workspace) ?? list[0];
  return (
    <Popover
      label="Рабочее пространство"
      width={260}
      trigger={({ open, toggle }) => (
        <button type="button" onClick={toggle} aria-expanded={open} className="hidden h-10 items-center gap-2 rounded-[10px] border border-line bg-surface px-3 text-[13px] font-medium hover:bg-surface-2 xl:flex">
          <Building2 size={15} className="text-subtle" aria-hidden />
          {current.name}
          <ChevronDown size={14} className="text-subtle" aria-hidden />
        </button>
      )}
    >
      {(close) => (
        <div className="p-1.5">
          <p className="px-3 pt-1.5 pb-1 text-[12px] text-muted">Рабочее пространство</p>
          {list.map((w) => (
            <button
              key={w.id}
              type="button"
              onClick={() => {
                setWorkspace(w.id);
                notify(`Открыто пространство «${w.name}»`);
                close();
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] hover:bg-surface-2"
            >
              <span className="flex-1">
                {w.name}
                <span className="block text-[12px] text-muted">{w.kind === "agency" ? "Агентство" : "Собственный бизнес"}</span>
              </span>
              {w.id === current.id && <Check size={15} className="text-brand" />}
            </button>
          ))}
        </div>
      )}
    </Popover>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const user = api.user();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-bg/85 px-4 backdrop-blur-md md:px-6">
      <button type="button" onClick={onMenu} className="btn btn-ghost size-10 p-0 lg:hidden" aria-label="Открыть меню">
        <Menu size={20} />
      </button>
      <SearchBox />
      <div className="ml-auto flex items-center gap-1.5 md:gap-2">
        <span className="hidden sm:block">
          <DemoBadge />
        </span>
        <Link href="/assistant" className={buttonCls("secondary", "sm", "hidden md:inline-flex")}>
          <Sparkles size={15} className="text-brand" /> Спросить AI
        </Link>
        <WorkspaceSelect />
        <Notifications />
        <Link href="/settings" className="flex items-center gap-2.5 rounded-[10px] py-1 pr-1 pl-1 hover:bg-surface-2 md:pr-2">
          <Avatar initials={user.initials} size={34} />
          <span className="hidden leading-tight md:block">
            <span className="block text-[13px] font-semibold">{user.fullName}</span>
            <span className="block text-[12px] text-muted">{ROLE_LABEL[user.role]}</span>
          </span>
        </Link>
      </div>
    </header>
  );
}
