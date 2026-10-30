'use client';
import '../ix.css';
import './public.css';
import Link from 'next/link';
import {BrandMark} from '@/components/brand-mark';
import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Menu, X} from 'lucide-react';
import {readTheme, type ThemePreference} from '@/lib/theme';
import {cycleTheme} from '../theme';
import {SectionMotion} from './section-motion';
import {FooterMeta} from './footer-meta';
import {DEFAULT_PUBLIC_START, type PublicStart} from '@/lib/public-start';

export const PUBLIC_NAV: [string, string][] = [['Возможности', '/features'], ['Как работает', '/how-it-works'], ['Агентствам', '/agencies'], ['Бизнесу', '/business'], ['Тарифы', '/pricing'], ['FAQ', '/faq']];
const NAME: Record<ThemePreference, string> = {light: 'светлая', dark: 'тёмная', system: 'системная'};

function Theme() {
  const [pref, setPref] = useState<ThemePreference>('light');
  useEffect(() => { const t = setTimeout(() => setPref(readTheme()), 0); return () => clearTimeout(t); }, []);
  return <button type="button" className="ix-pill" onClick={() => setPref(cycleTheme())} aria-label={`Переключить тему. Сейчас: ${NAME[pref]}`} title={`Тема: ${NAME[pref]}`}>◐</button>;
}

export function PublicHeader({start = DEFAULT_PUBLIC_START}: {start?: PublicStart}) {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); toggle.current?.focus(); } };
    const media = matchMedia('(min-width:1280px)');
    const sync = () => { if (media.matches) setOpen(false); };
    document.addEventListener('keydown', key); media.addEventListener('change', sync);
    return () => { document.removeEventListener('keydown', key); media.removeEventListener('change', sync); };
  }, [open]);
  return <header className="ix-pub-header">
    <Link className="ix-logo" href="/" title="INROU — на главную" style={{padding: 0}}><BrandMark/>INROU<small>INTELLIGENCE ATELIER</small></Link>
    <nav id="ix-pub-nav" aria-label="Главная навигация" className={open ? 'is-open' : ''}>
      {PUBLIC_NAV.map(([label, href]) => <Link key={href} href={href} onClick={() => setOpen(false)}>{label}</Link>)}
    </nav>
    <div className="ix-pub-actions"><Theme /><Link href="/login" className="ix-pill">Войти</Link><Link href={start.href} className="ix-btn ix-btn--primary ix-pub-cta">{start.label}</Link>
      <button ref={toggle} type="button" className="ix-pill ix-pub-menu" aria-label={open ? 'Закрыть меню' : 'Открыть меню'} aria-expanded={open} aria-controls="ix-pub-nav" onClick={() => setOpen(v => !v)}>{open ? <X size={18} aria-hidden /> : <Menu size={18} aria-hidden />}</button></div>
  </header>;
}

export function PublicFooter() {
  return <footer className="ix-pub-footer">
    <div><Link className="ix-logo" href="/" style={{padding: 0}}><BrandMark/>INROU<small>INTELLIGENCE ATELIER</small></Link>
      <p className="ix-muted ix-mini" style={{maxWidth: 420}}>Данные. Основания. Ваше решение. INROU — независимый сервис, не аффилирован с Яндексом.</p></div>
    <nav aria-label="Нижняя навигация">{[
      ['Продукт', [['Возможности', '/features'], ['Источники', '/integrations'], ['Методики', '/methodology'], ['Тарифы', '/pricing']]],
      ['Компания', [['О компании', '/about'], ['Безопасность', '/security'], ['Контакты', '/contact']]],
      ['Документы', [['Правовая информация', '/legal'], ['Конфиденциальность', '/legal/privacy'], ['Оферта', '/legal/offer'], ['Реквизиты', '/legal/requisites']]],
    ].map(([title, links]) => <div className="ix-footer-group" key={String(title)}><strong>{String(title)}</strong>{(links as string[][]).map(([label, href]) => <Link href={href} key={href}>{label}</Link>)}</div>)}</nav>
    <FooterMeta/>
  </footer>;
}

export function PublicFrame({children, start}: {children: ReactNode; start?: PublicStart}) {
  return <div className="ix ix-pub" lang="ru"><SectionMotion /><a className="ix-skip" href="#main-content">Перейти к содержимому</a><PublicHeader start={start}/><main id="main-content" tabIndex={-1}>{children}</main><PublicFooter /></div>;
}
