"use client";

import { useEffect, useId, useState } from "react";
import { applyTheme, readTheme, type ThemePreference } from "@/lib/theme";
import "./theme-control.css";

export function ThemeControl() {
  const id = useId();
  const [preference, setPreference] = useState<ThemePreference>("system");
  useEffect(() => {
    const refresh = () => { const value = readTheme(); setPreference(value); applyTheme(value); };
    const media = matchMedia("(prefers-color-scheme: dark)");
    const timer = setTimeout(refresh, 0);
    media.addEventListener("change", refresh);
    window.addEventListener("storage", refresh);
    window.addEventListener("inrou-theme-change", refresh);
    return () => {
      clearTimeout(timer);
      media.removeEventListener("change", refresh);
      window.removeEventListener("storage", refresh);
      window.removeEventListener("inrou-theme-change", refresh);
    };
  }, []);
  return <label className="theme-control" htmlFor={id}><span>Тема</span><select aria-label="Тема" id={id} value={preference} onChange={event => {
    const value = event.target.value as ThemePreference;
    setPreference(value);
    applyTheme(value);
    try {
      localStorage.setItem("inrou-theme", value);
      window.dispatchEvent(new Event("inrou-theme-change"));
    } catch { /* Preference applies for this visit. */ }
  }}><option value="light">Светлая</option><option value="dark">Тёмная</option><option value="system">Системная</option></select></label>;
}
