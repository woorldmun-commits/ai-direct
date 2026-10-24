import {BarChart3, Bell, Bot, Briefcase, Clock, FileText, Gem, Home, Plug, Settings, Sparkles, Table2, TrendingUp, Users, type LucideIcon} from 'lucide-react';

export type NavItem = {slug: string; label: string; short?: string; Icon: LucideIcon};

// Twelve root sections from the final atlas; contextual routes remain addressable.
export const NAV: NavItem[] = [
  {slug: 'analysis', label: 'Анализ', Icon: BarChart3},
  {slug: 'recommendations', label: 'Рекомендации', short: 'Советы', Icon: Sparkles},
  {slug: 'campaigns', label: 'Кампании', Icon: Table2},
  {slug: 'connections', label: 'Подключения', Icon: Plug},
  {slug: 'impact', label: 'Эффект', Icon: TrendingUp},
  {slug: 'reports', label: 'Отчёты', Icon: FileText},
  {slug: 'alerts', label: 'Сигналы', Icon: Bell},
  {slug: 'ai', label: 'AI-аналитик', short: 'AI', Icon: Bot},
  {slug: 'history', label: 'История', Icon: Clock},
  {slug: 'team', label: 'Команда', Icon: Users},
  {slug: 'plans', label: 'Тарифы', Icon: Gem},
  {slug: 'settings', label: 'Настройки', Icon: Settings},
];

export const CONTEXT_NAV: NavItem[] = [
  {slug: 'overview', label: 'Обзор', Icon: Home},
  {slug: 'business-profile', label: 'Бизнес-профиль', Icon: Briefcase},
];
export const SLUGS = [...NAV, ...CONTEXT_NAV].map(n => n.slug);
export const navLabel = (slug: string) => [...NAV, ...CONTEXT_NAV].find(n => n.slug === slug)?.label ?? 'INROU';
