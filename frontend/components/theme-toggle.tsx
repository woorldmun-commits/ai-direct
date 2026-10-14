"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

const subscribe = (callback: () => void) => {
  window.addEventListener("adpilot:theme", callback);
  window.addEventListener("storage", callback);
  return () => { window.removeEventListener("adpilot:theme", callback); window.removeEventListener("storage", callback); };
};
export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, () => document.documentElement.dataset.theme ?? "dark", () => "dark");
  const light = theme === "light";
  function toggle() {
    const next = light ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("adpilot-theme", next); } catch { /* Theme still works without storage. */ }
    window.dispatchEvent(new Event("adpilot:theme"));
  }
  return <button type="button" className={`btn btn-ghost size-10 p-0 ${className}`} onClick={toggle} aria-label={light ? "Включить тёмную тему" : "Включить светлую тему"}>{light ? <Moon size={18}/> : <Sun size={18}/>}</button>;
}
