'use client';
import {useEffect, useState} from 'react';
import {readTheme, type ThemePreference} from '@/lib/theme';
import {cycleTheme} from '../theme';

const NAME: Record<ThemePreference, string> = {light: 'светлая', dark: 'тёмная', system: 'системная'};

export function ThemeRow() {
  const [pref, setPref] = useState<ThemePreference>('light');
  useEffect(() => { const t = setTimeout(() => setPref(readTheme()), 0); return () => clearTimeout(t); }, []);
  return <div className="ix-rowline"><span>Цветовая тема: {NAME[pref]}</span>
    <button type="button" className="ix-btn" onClick={() => setPref(cycleTheme())}>Переключить</button></div>;
}
