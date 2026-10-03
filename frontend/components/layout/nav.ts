import { BarChart3, Bot, Building2, CircleHelp, FileText, Lightbulb, Megaphone, PlugZap, Settings, Sun, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

export const MAIN_NAV: NavItem[] = [
  { href: "/today", label: "Сегодня", icon: Sun },
  { href: "/analytics", label: "Аналитика", icon: BarChart3 },
  { href: "/recommendations", label: "Рекомендации", icon: Lightbulb },
  { href: "/campaigns", label: "Кампании", icon: Megaphone },
  { href: "/clients", label: "Клиенты", icon: Building2 },
  { href: "/reports", label: "Отчёты", icon: FileText },
  { href: "/agents", label: "AI-агенты", icon: Bot },
];

export const SECONDARY_NAV: NavItem[] = [
  { href: "/integrations", label: "Интеграции", icon: PlugZap },
  { href: "/settings", label: "Настройки", icon: Settings },
];

export const HELP_ICON = CircleHelp;

export const isActive = (path: string, href: string) => path === href || path.startsWith(`${href}/`);
