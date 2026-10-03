"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

// Bump when the banner/consent text changes: old choices are asked again.
const VERSION = "v1";
const COOKIE = "adpilot-consent";
export const OPEN_EVENT = "adpilot:cookie-settings";

type Choice = "all" | "necessary";

function readChoice(): Choice | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${COOKIE}=${VERSION}:(all|necessary)`));
  return (m?.[1] as Choice) ?? null;
}

function saveChoice(c: Choice) {
  const maxAge = 60 * 60 * 24 * 365;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${COOKIE}=${VERSION}:${c}; Max-Age=${maxAge}; Path=/; SameSite=Lax${secure}`;
}

type Ym = ((...args: unknown[]) => void) & { a?: unknown[]; l?: number };

// Метрика грузится только после согласия на аналитику (152-ФЗ, docs/LEGAL.md п. 8).
function loadMetrika() {
  const id = Number(process.env.NEXT_PUBLIC_YM_ID);
  if (!id || document.getElementById("ym-tag")) return;
  const w = window as unknown as { ym?: Ym };
  const ym: Ym = function (...args: unknown[]) {
    (ym.a = ym.a || []).push(args);
  };
  ym.l = Date.now();
  w.ym = ym;
  const s = document.createElement("script");
  s.id = "ym-tag";
  s.async = true;
  s.src = "https://mc.yandex.ru/metrika/tag.js";
  document.head.appendChild(s);
  ym(id, "init", { clickmap: true, trackLinks: true, accurateTrackBounce: true, webvisor: false });
}

export function CookieSettingsButton({ className = "" }: { className?: string }) {
  return (
    <button type="button" className={className} onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}>
      Настройки cookie
    </button>
  );
}

export function CookieBanner() {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);
  const [analytics, setAnalytics] = useState(false);

  useEffect(() => {
    const c = readChoice();
    if (c === "all") loadMetrika();
    // The cookie is only readable after mount, so this syncs state from the browser.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!c) setOpen(true);
    const reopen = () => {
      setAnalytics(readChoice() === "all");
      setCustom(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_EVENT, reopen);
    return () => window.removeEventListener(OPEN_EVENT, reopen);
  }, []);

  function decide(c: Choice) {
    const before = readChoice();
    saveChoice(c);
    setOpen(false);
    if (c === "all") loadMetrika();
    // Revoking consent: drop the counter's cookies and reload so it stops running.
    else if (before === "all") {
      const host = location.hostname;
      const parent = host.split(".").slice(-2).join(".");
      for (const name of ["_ym_uid", "_ym_d", "_ym_isad", "_ym_visorc"])
        for (const domain of ["", `; Domain=${host}`, `; Domain=.${parent}`])
          document.cookie = `${name}=; Max-Age=0; Path=/${domain}`;
      location.reload();
    }
  }

  if (!open) return null;

  return (
    <div role="dialog" aria-label="Настройки cookie" className="fixed inset-x-4 bottom-20 z-[60] mx-auto max-w-[720px] md:bottom-6">
      <div className="glass anim-fade p-5 text-sm text-text">
        <p>
          Мы используем cookie. Необходимые нужны для работы сайта. Аналитические (Яндекс Метрика) помогают улучшать сервис, и мы
          включим их только с вашего согласия. Подробнее в{" "}
          <Link className="text-brand underline underline-offset-2" href="/legal/privacy">
            Политике обработки персональных данных
          </Link>{" "}
          и{" "}
          <Link className="text-brand underline underline-offset-2" href="/legal/cookies">
            Согласии на обработку данных cookie
          </Link>
          .
        </p>
        {custom && (
          <div className="mt-4 space-y-2 border border-line bg-surface p-3">
            <label className="flex items-center gap-3 opacity-70">
              <input type="checkbox" checked disabled className="size-4 accent-[var(--brand)]" />
              Необходимые — всегда включены
            </label>
            <label className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={analytics}
                onChange={(e) => setAnalytics(e.target.checked)}
                className="size-4 accent-[var(--brand)]"
              />
              Аналитические — Яндекс Метрика
            </label>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {custom ? (
            <>
              <button className="btn btn-primary btn-sm" onClick={() => decide(analytics ? "all" : "necessary")}>
                Сохранить выбор
              </button>
              {readChoice() && (
                <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
                  Закрыть
                </button>
              )}
            </>
          ) : (
            <>
              <button className="btn btn-secondary btn-sm" onClick={() => decide("all")}>
                Принять все
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => decide("necessary")}>
                Только необходимые
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setCustom(true)}>
                Настроить
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
