export type ThemePreference = "light" | "dark" | "system";

export const THEME_SCRIPT = `try{var t=localStorage.getItem("inrou-theme");document.documentElement.dataset.theme=t==="light"||t==="dark"?t:t==="system"&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}catch(e){document.documentElement.dataset.theme="light"}`;

export function readTheme(): ThemePreference {
  try {
    const saved = localStorage.getItem("inrou-theme");
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch { /* System preference still works without browser storage. */ }
  return "light";
}

export function applyTheme(preference: ThemePreference) {
  document.documentElement.dataset.theme = preference === "system"
    ? matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
    : preference;
}
