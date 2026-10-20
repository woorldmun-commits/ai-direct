import { AlertTriangle, CircleX } from "lucide-react";
import Link from "next/link";
import type { IntegrationItem, Provider } from "@/lib/contract";
import { formatMoment } from "@/lib/value";

/**
 * Data freshness (PRODUCT_SPEC §4.2): «Данные актуальны на …» from the last audit, and one status per source —
 * «актуально» / «обновление N мин назад» / «нет доступа — переподключить».
 */

const PROVIDER_LABEL: Record<Provider, string> = { yandex_direct: "Директ", yandex_metrika: "Метрика" };
const NO_ACCESS = new Set(["token_expired", "token_revoked", "permission_missing", "disconnected"]);

export type Freshness = { provider: Provider; name: string; tone: "ok" | "warn" | "bad"; text: string };

function ago(iso: string | null, now: string): string {
  if (!iso) return "давно";
  const min = Math.max(0, Math.round((Date.parse(now) - Date.parse(iso)) / 60_000));
  if (min < 60) return `${min} мин назад`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} ч назад` : `${Math.round(h / 24)} дн назад`;
}

function yesterday(today: string): string {
  const d = new Date(`${today}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

export function freshnessOf(i: IntegrationItem, today: string, now: string): Freshness {
  const name = PROVIDER_LABEL[i.provider];
  if (NO_ACCESS.has(i.status)) return { provider: i.provider, name, tone: "bad", text: "нет доступа — переподключить" };
  const current = i.status === "connected" && i.data_to !== null && i.data_to >= yesterday(today);
  if (current) return { provider: i.provider, name, tone: "ok", text: "актуально" };
  return { provider: i.provider, name, tone: "warn", text: `обновление ${ago(i.last_success_at, now)}` };
}

const DOT = { ok: "bg-success", warn: "bg-warning", bad: "bg-danger" };

function SourceChip({ f }: { f: Freshness }) {
  const inner = (
    <>
      {f.tone === "ok" && <span aria-hidden className="size-1.5 rounded-full bg-success" />}
      {f.tone === "warn" && <AlertTriangle size={12} aria-hidden className="text-warning" />}
      {f.tone === "bad" && <CircleX size={12} aria-hidden className="text-danger" />}
      <span>
        {f.name} · <span className={f.tone === "ok" ? "" : f.tone === "warn" ? "text-warning" : "text-danger"}>{f.text}</span>
      </span>
    </>
  );
  const cls = "inline-flex items-center gap-1.5 whitespace-nowrap";
  return f.tone === "bad" ? (
    <Link href="/demo/integrations" className={`${cls} underline-offset-2 hover:underline`}>
      {inner}
    </Link>
  ) : (
    <span className={cls}>{inner}</span>
  );
}

export function FreshnessBar({
  lastAuditAt,
  items,
  today,
  now,
  className = "",
}: {
  lastAuditAt: string | null;
  items: IntegrationItem[];
  today: string;
  now: string;
  className?: string;
}) {
  const list = items.map((i) => freshnessOf(i, today, now));
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted ${className}`} aria-label="Свежесть данных">
      <span className="whitespace-nowrap">
        {lastAuditAt ? (
          <>
            Данные актуальны на <b className="font-semibold text-text">{formatMoment(lastAuditAt)}</b> МСК
          </>
        ) : (
          "Аудита ещё не было"
        )}
      </span>
      {list.map((f) => (
        <SourceChip key={f.provider} f={f} />
      ))}
    </div>
  );
}

/** On «Сегодня»: stale or missing sources lower the confidence of recommendations — say so. */
export function StaleNotice({ items, today, now }: { items: IntegrationItem[]; today: string; now: string }) {
  const bad = items.map((i) => freshnessOf(i, today, now)).filter((f) => f.tone !== "ok");
  if (!bad.length) return null;
  const hard = bad.some((f) => f.tone === "bad");
  return (
    <div className={`mb-4 flex items-start gap-3 rounded-2xl border p-4 text-sm ${hard ? "border-danger/30 bg-danger-bg" : "border-warning/30 bg-warning-bg"}`} role="status">
      <span className={`mt-0.5 size-2 shrink-0 rounded-full ${hard ? DOT.bad : DOT.warn}`} aria-hidden />
      <div>
        <p className="font-semibold">
          {bad.map((f) => `${f.name}: ${f.text}`).join(" · ")}
        </p>
        <p className="mt-0.5 text-muted">
          Рекомендации, которые опираются на эти данные, менее надёжны: конверсии и CPA могут быть неполными.{" "}
          <Link href="/demo/integrations" className="font-semibold text-brand">
            Проверить подключение
          </Link>
        </p>
      </div>
    </div>
  );
}
