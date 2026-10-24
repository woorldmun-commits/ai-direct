import {applyTheme, readTheme, type ThemePreference} from '@/lib/theme';

const ORDER: ThemePreference[] = ['light', 'dark', 'system'];

/** Светлая → тёмная → системная; выбор сохраняется так же, как в ThemeControl (localStorage `inrou-theme`). */
export function cycleTheme(): ThemePreference {
  const next = ORDER[(ORDER.indexOf(readTheme()) + 1) % ORDER.length];
  applyTheme(next);
  try { localStorage.setItem('inrou-theme', next); window.dispatchEvent(new Event('inrou-theme-change')); } catch { /* тема применена на этот визит */ }
  return next;
}
