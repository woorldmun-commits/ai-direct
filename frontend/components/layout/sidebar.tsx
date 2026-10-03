"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { Avatar, Logo } from "@/components/ui/misc";
import { Popover } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/permissions";
import { isOpenRec, useApp } from "./app-state";
import { HELP_ICON, isActive, MAIN_NAV, SECONDARY_NAV, type NavItem } from "./nav";

function NavLink({ item, path, count, onNavigate }: { item: NavItem; path: string; count?: number; onNavigate?: () => void }) {
  const active = isActive(path, item.href);
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`group flex h-9 items-center gap-3 rounded-[10px] px-3 text-[13.5px] transition-colors ${active ? "bg-brand-soft font-semibold text-brand" : "font-medium text-[#475467] hover:bg-surface-2 hover:text-text"}`}
    >
      <item.icon size={18} strokeWidth={active ? 2.2 : 1.9} className={active ? "text-brand" : "text-subtle group-hover:text-muted"} aria-hidden />
      {item.label}
      {!!count && <span className="num ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1.5 text-[11px] font-semibold text-white">{count}</span>}
    </Link>
  );
}

function Help() {
  return (
    <Popover
      label="Помощь"
      align="left"
      width={248}
      trigger={({ open, toggle }) => (
        <button type="button" onClick={toggle} aria-expanded={open} className="flex h-9 w-full items-center gap-3 rounded-[10px] px-3 text-[13.5px] font-medium text-[#475467] hover:bg-surface-2 hover:text-text">
          <HELP_ICON size={18} strokeWidth={1.9} className="text-subtle" aria-hidden /> Помощь
        </button>
      )}
    >
      <div className="p-1.5 text-[13px]">
        <Link href="/agents" className="block rounded-lg px-3 py-2 hover:bg-surface-2">
          Как AdPilot делает выводы
        </Link>
        <Link href="/assistant" className="block rounded-lg px-3 py-2 hover:bg-surface-2">
          Спросить AI-аналитика
        </Link>
        <a href="mailto:support@adpilot.ru" className="block rounded-lg px-3 py-2 hover:bg-surface-2">
          Написать в поддержку
        </a>
      </div>
    </Popover>
  );
}

export function SidebarContent({ path, onNavigate }: { path: string; onNavigate?: () => void }) {
  const { recs } = useApp();
  const user = api.user();
  const open = recs.filter(isOpenRec).length;
  return (
    <div className="flex h-full flex-col">
      <Link href="/today" onClick={onNavigate} className="flex h-16 shrink-0 items-center px-5" aria-label="AdPilot — Сегодня">
        <Logo size={26} />
      </Link>
      <nav aria-label="Основные разделы" className="flex-1 overflow-y-auto px-3 pt-2">
        <ul className="space-y-0.5">
          {MAIN_NAV.map((n) => (
            <li key={n.href}>
              <NavLink item={n} path={path} count={n.href === "/recommendations" ? open : undefined} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </nav>
      <div className="space-y-0.5 px-3 pb-2">
        {SECONDARY_NAV.map((n) => (
          <NavLink key={n.href} item={n} path={path} onNavigate={onNavigate} />
        ))}
        <Help />
      </div>
      <Link href="/settings" onClick={onNavigate} className="m-3 mt-1 flex items-center gap-3 rounded-xl border border-line p-2.5 hover:bg-surface-2">
        <Avatar initials={user.initials} size={34} />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[13px] font-semibold">{user.fullName}</span>
          <span className="block truncate text-[12px] text-muted">{ROLE_LABEL[user.role]}</span>
        </span>
        <ChevronRight size={16} className="text-subtle" aria-hidden />
      </Link>
    </div>
  );
}

export function Sidebar({ path }: { path: string }) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-[240px] shrink-0 border-r border-line bg-surface lg:block">
      <SidebarContent path={path} />
    </aside>
  );
}
