import { AlertTriangle, CheckCircle2, Plug } from "lucide-react";
import Link from "next/link";
import { RULE_CHECK_TEXT, RULE_TITLE, ruleName, type ApiError, type AuditScope } from "@/lib/contract";
import { formatMoment, formatPeriod, formatRuleVersion } from "@/lib/value";

/**
 * Four states of every screen (PRODUCT_SPEC §4.6): loading, empty («Подключите Директ» / «Проблем не найдено —
 * вот что проверено»), error (what happened, what to do, `request_id`), data. The demo switches with `?state=`.
 */
export type ScreenState = "data" | "loading" | "empty" | "no_data" | "error";
const STATES: { key: ScreenState; label: string }[] = [
  { key: "data", label: "Данные" },
  { key: "loading", label: "Загрузка" },
  { key: "empty", label: "Проблем нет" },
  { key: "no_data", label: "Нет подключения" },
  { key: "error", label: "Ошибка" },
];

export function parseScreenState(v: string | string[] | undefined): ScreenState {
  const s = Array.isArray(v) ? v[0] : v;
  return STATES.some((x) => x.key === s) ? (s as ScreenState) : "data";
}

export function DemoStateSwitch({ current, path }: { current: ScreenState; path: string }) {
  return (
    <nav aria-label="Состояние экрана (демо)" className="mb-4 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted">Демо-состояние:</span>
      {STATES.map((s) => (
        <Link
          key={s.key}
          href={s.key === "data" ? path : `${path}?state=${s.key}`}
          aria-current={current === s.key ? "page" : undefined}
          className={`rounded-full border px-2.5 py-1 ${current === s.key ? "border-brand bg-brand-soft text-brand" : "border-line text-muted hover:text-text"}`}
        >
          {s.label}
        </Link>
      ))}
    </nav>
  );
}

export function LoadingState({ cards = 4 }: { cards?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Загружаем данные…</span>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {Array.from({ length: cards }, (_, i) => (
          <div key={i} className="card space-y-3 p-5">
            <div className="skeleton h-4 w-24" />
            <div className="skeleton h-8 w-32" />
            <div className="skeleton h-3 w-40" />
          </div>
        ))}
      </div>
      <div className="card mt-4 space-y-3 p-6">
        <div className="skeleton h-5 w-56" />
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-2/3" />
      </div>
    </div>
  );
}

export function ErrorState({ error, retryHref }: { error: ApiError; retryHref: string }) {
  return (
    <div role="alert" className="card flex items-start gap-4 p-6">
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-danger-bg text-danger">
        <AlertTriangle size={18} />
      </span>
      <div className="min-w-0">
        <p className="font-bold">{error.error.message}</p>
        <p className="mt-1 text-sm text-muted">
          Ваши данные и решения не потеряны. Обновите страницу через минуту; если ошибка повторится — напишите в поддержку и укажите код
          запроса.
        </p>
        <p className="mt-3 text-xs text-muted">
          Код запроса (request_id): <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-text select-all">{error.error.request_id}</code>
        </p>
        <Link href={retryHref} className="btn btn-secondary btn-sm mt-4">
          Повторить
        </Link>
      </div>
    </div>
  );
}

/** «Проблем не найдено» is evidence too: show which rules ran on which period. */
export function NothingFound({
  scope,
  lastAuditAt,
  title = "Проблем не найдено — вот что проверено",
}: {
  scope: AuditScope;
  lastAuditAt: string | null;
  title?: string;
}) {
  return (
    <section className="card p-6" aria-labelledby="nothing-found">
      <h2 id="nothing-found" className="flex items-center gap-2 text-lg font-bold">
        <CheckCircle2 size={20} className="text-success" /> {title}
      </h2>
      <p className="mt-1 text-sm text-muted">
        Период: {formatPeriod(scope.period)} · кабинетов: {scope.ad_accounts.checked}
        {scope.ad_accounts.excluded > 0 && ` (не вошли: ${scope.ad_accounts.excluded})`} · кампаний проверено: {scope.campaigns}
        {lastAuditAt && ` · аудит ${formatMoment(lastAuditAt)} МСК`}
      </p>
      <ul className="mt-4 space-y-2">
        {scope.rules.map((rv) => (
          <li key={rv} className="flex items-start gap-2 text-sm">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" />
            <span>
              {RULE_CHECK_TEXT[ruleName(rv)] ?? RULE_TITLE[ruleName(rv)] ?? ruleName(rv)}{" "}
              <span className="font-mono text-xs text-muted">({formatRuleVersion(rv)})</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-muted">Следующий аудит — после утренней синхронизации. Если что-то найдётся, придёт уведомление.</p>
    </section>
  );
}

export function ConnectDirect() {
  return (
    <section className="card flex flex-col items-start gap-3 p-6" aria-labelledby="connect-direct">
      <span className="grid size-10 place-items-center rounded-full bg-brand-soft text-brand">
        <Plug size={18} />
      </span>
      <h2 id="connect-direct" className="text-lg font-bold">
        Подключите Яндекс Директ
      </h2>
      <p className="text-sm text-muted">
        Аудита ещё не было, поэтому цифр нет — ни нулей, ни примеров. После подключения AdPilot загрузит статистику, проверит кабинет по трём
        правилам и покажет результат здесь. Доступ только на чтение.
      </p>
      <Link href="/demo/integrations" className="btn btn-primary">
        Подключить Яндекс Директ
      </Link>
    </section>
  );
}
