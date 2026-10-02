"use client";

import { ArrowLeft, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CAMPAIGNS } from "@/lib/demo";
import { WORKSPACES } from "@/lib/demo-backend";

/**
 * Ctrl+K — the entry into the product (PRODUCT_SPEC §4.5). v1.0 commands are navigation and ready-made
 * selections only: no free-text questions to AI (that is «Спросить AI», v1.1).
 */
type Mode = "root" | "campaign" | "client";
type Item = { label: string; hint: string; href?: string; mode?: Mode; keep?: boolean };

const ROOT: Item[] = [
  { label: "Расход с признаками неэффективности за 7 дней", hint: "Выборка", href: "/demo/losses" },
  { label: "Рекомендации, требующие решения", hint: "Выборка", href: "/demo/recommendations?filter=requires_decision" },
  { label: "Кампании без конверсий", hint: "Выборка", href: "/demo/recommendations?rule=zero_conv_campaign" },
  { label: "Площадки РСЯ без конверсий", hint: "Выборка", href: "/demo/recommendations?rule=zero_conv_placements" },
  { label: "Что изменилось за сутки", hint: "Выборка", href: "/demo/changes#day" },
  { label: "История решений", hint: "Раздел", href: "/demo/history" },
  { label: "Найти кампанию…", hint: "Поиск", mode: "campaign", keep: true },
  { label: "Переключить клиента…", hint: "Агентство", mode: "client", keep: true },
  { label: "Подключить Яндекс Директ", hint: "Интеграции", href: "/demo/integrations" },
  { label: "Сегодня", hint: "Раздел", href: "/demo" },
  { label: "Финансы", hint: "Раздел", href: "/demo/finance" },
  { label: "Настройки", hint: "Раздел", href: "/demo/settings" },
];

const CAMPAIGN_ITEMS: Item[] = CAMPAIGNS.map((c) => ({ label: c.name, hint: "Кампания", href: `/demo/recommendations?campaign=${c.id}` }));
const CLIENT_ITEMS: Item[] = WORKSPACES.map((w) => ({ label: w.name, hint: w.note, href: w.href }));

const PLACEHOLDER: Record<Mode, string> = {
  root: "Команда, раздел или кампания…",
  campaign: "Название кампании…",
  client: "Клиент агентства…",
};

export function CommandPalette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("root");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const pool = mode === "campaign" ? CAMPAIGN_ITEMS : mode === "client" ? CLIENT_ITEMS : needle ? [...ROOT, ...CAMPAIGN_ITEMS] : ROOT;
    return pool.filter((i) => i.label.toLowerCase().includes(needle));
  }, [q, mode]);

  useEffect(() => input.current?.focus(), [mode]);

  function run(i: number) {
    const it = items[i];
    if (!it) return;
    if (it.mode) {
      setMode(it.mode);
      setQ("");
      setSel(0);
      return;
    }
    if (it.href) router.push(it.href);
    onClose();
  }

  function back() {
    setMode("root");
    setQ("");
    setSel(0);
  }

  return (
    <div className="fixed inset-0 z-[70] bg-black/30 p-4 pt-[12vh]" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Поиск и команды"
        className="glass anim-fade mx-auto max-w-[560px] overflow-hidden rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-line px-4">
          {mode === "root" ? (
            <Search size={18} className="text-muted" />
          ) : (
            <button className="text-muted hover:text-text" aria-label="Назад к командам" onClick={back}>
              <ArrowLeft size={18} />
            </button>
          )}
          <input
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel((s) => Math.min(s + 1, items.length - 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel((s) => Math.max(s - 1, 0));
              }
              if (e.key === "Enter") run(sel);
              if (e.key === "Escape") (mode === "root" ? onClose : back)();
              if (e.key === "Backspace" && !q && mode !== "root") back();
            }}
            placeholder={PLACEHOLDER[mode]}
            className="h-14 flex-1 bg-transparent outline-none"
            aria-label="Поиск"
            role="combobox"
            aria-expanded
            aria-controls="palette-list"
            aria-activedescendant={items[sel] ? `palette-${sel}` : undefined}
          />
        </div>
        <ul id="palette-list" className="max-h-[380px] overflow-auto p-2" role="listbox">
          {items.length === 0 && <li className="p-4 text-sm text-muted">Ничего не найдено</li>}
          {items.map((it, i) => (
            <li key={it.label + it.hint} id={`palette-${i}`} role="option" aria-selected={i === sel}>
              <button
                onMouseEnter={() => setSel(i)}
                onClick={() => run(i)}
                className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${i === sel ? "bg-surface" : ""}`}
              >
                <span>{it.label}</span>
                <span className="shrink-0 text-xs text-muted">{it.hint}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="border-t border-line px-4 py-2 text-[11px] text-muted">↑↓ — выбрать · Enter — открыть · Esc — закрыть</p>
      </div>
    </div>
  );
}
