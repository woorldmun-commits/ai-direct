'use client';
import './ix.css';
import Link from 'next/link';
import {BrandMark} from '@/components/brand-mark';
import {usePathname} from 'next/navigation';
import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';
import {Menu, PanelLeftClose, PanelLeftOpen, X} from 'lucide-react';
import {readTheme, type ThemePreference} from '@/lib/theme';
import {NAV, CONTEXT_NAV} from './nav';
import {cycleTheme} from './theme';
import {useDialog} from './use-dialog';
import {Info, Gap} from './ui';

export type IxMode = 'live' | 'demo';
type Workspace = {id: string; name: string};

const SearchContext = createContext('');
/** Строка поиска из верхней панели: списки на странице фильтруются по ней. */
export const useIxSearch = () => useContext(SearchContext);

const THEME_NAME: Record<ThemePreference, string> = {light: 'светлая', dark: 'тёмная', system: 'системная'};

function ThemeButton() {
  const [pref, setPref] = useState<ThemePreference>('light');
  useEffect(() => {
    const t = setTimeout(() => setPref(readTheme()), 0);
    return () => clearTimeout(t);
  }, []);
  const next = () => setPref(cycleTheme());
  return <button type="button" className="ix-pill" onClick={next} aria-label={`Тема: ${THEME_NAME[pref]}. Переключить тему`} title={`Тема: ${THEME_NAME[pref]}`}><span aria-hidden>◐ </span>Тема</button>;
}

export function IxShell({base, mode, workspace, workspaces = [], periodLabel, children}: {base: '/workspace' | '/demo'; mode: IxMode; workspace?: string; workspaces?: Workspace[]; periodLabel?: string; children: ReactNode}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState('');
  const panel = useRef<HTMLElement>(null);
  const close = () => setOpen(false);
  useDialog(open, panel, close);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) { setLastPath(pathname); setOpen(false); }
  useEffect(() => {
    const media = matchMedia('(min-width:1024px)');
    const restore = setTimeout(() => { try { setCollapsed(localStorage.getItem('inrou-sidebar-collapsed') === '1'); } catch {} }, 0);
    const sync = () => { if (media.matches) setOpen(false); };
    media.addEventListener('change', sync);
    return () => { clearTimeout(restore); media.removeEventListener('change', sync); };
  }, []);
  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem('inrou-sidebar-collapsed', next ? '1' : '0'); } catch {}
  };
  const active = pathname.startsWith(base + '/') ? pathname.slice(base.length + 1).split('/')[0] : '';
  const href = (slug: string) => `${base}/${slug}${mode === 'live' && workspace ? '?workspace=' + encodeURIComponent(workspace) : ''}`;
  const current = workspaces.find(w => w.id === workspace);
  const bottom = ['overview', 'analysis', 'recommendations', 'ai'].map(s => [...NAV, ...CONTEXT_NAV].find(n => n.slug === s)!);

  return <div className="ix" lang="ru">
    <a className="ix-skip" href="#main-content">Перейти к содержимому</a>
    <div className={'ix-shell' + (collapsed ? ' is-collapsed' : '')}>
      <aside ref={panel} id="ix-sidebar" className={'ix-sidebar' + (open ? ' is-open' : '')} role={open ? 'dialog' : undefined} aria-modal={open || undefined} aria-label="Разделы кабинета"><div className="ix-sidebar-in">
        <Link className="ix-logo" href="/" title="INROU — на главную" aria-label="INROU — на главную"><BrandMark/><span className="ix-brand-text">INROU<small>INTELLIGENCE ATELIER</small></span></Link>
        <button type="button" className="ix-collapse" aria-label={collapsed ? 'Развернуть панель' : 'Свернуть панель'} aria-expanded={!collapsed} aria-controls="ix-primary-nav" onClick={toggleSidebar}>{collapsed ? <PanelLeftOpen size={18} aria-hidden/> : <PanelLeftClose size={18} aria-hidden/>}<span>{collapsed ? 'Развернуть' : 'Свернуть панель'}</span></button>
        <button type="button" className="ix-pill ix-menu" style={{alignSelf: 'flex-end', display: open ? 'inline-block' : 'none'}} aria-label="Закрыть меню" onClick={close}><X size={18} aria-hidden /></button>
        <nav id="ix-primary-nav" className="ix-nav" aria-label="Основная навигация">
          {NAV.map(({slug, label, Icon}) => <Link key={slug} href={href(slug)} aria-label={label} title={label} aria-current={active === slug ? 'page' : undefined} data-autofocus={active === slug ? '' : undefined}><Icon aria-hidden /><span className="ix-nav-label">{label}</span></Link>)}
        </nav>
        <div className="ix-sidefoot">{mode === 'demo'
          ? <>● Демонстрационный режим<br />Данные синтетические. Никаких изменений в рекламных кабинетах.</>
          : <>● Решение за вами<br />Доступ к рекламным данным — только чтение. Изменения вы вносите вручную.</>}</div>
      </div></aside>
      {open && <button type="button" className="ix-scrim" aria-label="Закрыть меню" tabIndex={-1} onClick={close} />}
      <main className="ix-main" id="main-content" tabIndex={-1} inert={open}>
        <div className="ix-top">
          <button type="button" className="ix-pill ix-menu" aria-label="Открыть меню" aria-expanded={open} aria-controls="ix-sidebar" onClick={() => setOpen(true)}><Menu size={18} aria-hidden /></button>
          <input className="ix-search" type="search" aria-label="Поиск" placeholder="Поиск кампаний, рекомендаций, данных…" value={query} onChange={e => setQuery(e.target.value)} />
          <div className="ix-topright">
            <ThemeButton />
            <span className="ix-pill">{periodLabel ?? (mode === 'demo' ? 'Демо · 01–31 марта' : 'Период аудита')}</span>
            {mode === 'live' ? <details className="ix-user">
              <summary className="ix-pill">{current?.name ?? 'Пространство'} ▾</summary>
              <div className="ix-usermenu">
                {workspaces.map(w => <Link key={w.id} href={`${base}/${active || 'overview'}?workspace=${encodeURIComponent(w.id)}`} aria-current={w.id === workspace ? 'true' : undefined}>{w.name}</Link>)}
                <form action="/api/auth/logout" method="post"><button type="submit">Выйти</button></form>
              </div>
            </details> : <span className="ix-pill">Александра ▾</span>}
          </div>
        </div>
        <SearchContext.Provider value={query.trim().toLowerCase()}><div className="ix-page" key={pathname}>{mode==='demo'&&<><Info>Демо-кабинет · синтетические данные. Это пример интерфейса, не данные вашего Директа.</Info><Gap h={12}/></>}{children}<nav className="ix-context-links" aria-label="Инструменты рабочего пространства">{(mode === 'live' ? [['overview','Обзор'],['decisions','Центр решений'],['agency','Клиенты'],['data-catalog','Показатели'],['business-profile','Бизнес-профиль'],['help','Помощь']] : [['overview','Обзор'],['business-profile','Бизнес-профиль']]).map(([slug,label]) => <Link key={slug} className="ix-pill" href={href(slug)}>{label}</Link>)}</nav></div></SearchContext.Provider>
      </main>
    </div>
    <nav className="ix-mobilebottom" aria-label="Быстрая навигация" inert={open}>
      {bottom.map(({slug, label, short, Icon}) => <Link key={slug} href={href(slug)} className="ix-bottom-item" aria-current={active === slug ? 'page' : undefined}><Icon aria-hidden />{short ?? label}</Link>)}
      <button type="button" className="ix-bottom-item" onClick={() => setOpen(true)} aria-label="Открыть меню"><Menu aria-hidden />Меню</button>
    </nav>
  </div>;
}
