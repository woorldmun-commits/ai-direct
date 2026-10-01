"use client";

import { BarChart3, Check, Eye, EyeOff, Info, Loader2, Megaphone } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { Logo } from "@/components/ui";

// Prototype: there is no auth API yet. Forms validate locally and send nothing anywhere.

export function AuthLayout({ title, sub, children, footer }: { title: string; sub?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <div className="w-full max-w-[460px]">
        <Link href="/" aria-label="На главную">
          <Logo />
        </Link>
        <div className="card mt-6 p-6 md:p-8">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
          {children}
        </div>
        {footer && <p className="mt-4 text-center text-sm text-muted">{footer}</p>}
        <p className="mt-6 flex items-start justify-center gap-2 text-center text-xs text-muted">
          <Info size={14} className="mt-0.5 shrink-0" /> Прототип: регистрация ещё не подключена к серверу, данные никуда не отправляются.
        </p>
      </div>
    </main>
  );
}

const inputCls = "h-11 w-full rounded-xl border border-line bg-surface px-3 outline-none focus:border-brand aria-[invalid=true]:border-danger";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD = 10;

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="mt-1">{children}</div>
      {error && (
        <p id={`${id}-err`} className="mt-1 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

function PasswordInput({ id, value, onChange, error, autoComplete }: { id: string; value: string; onChange: (v: string) => void; error?: string; autoComplete: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        maxLength={128}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-err` : undefined}
        className={`${inputCls} pr-11`}
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        aria-label={show ? "Скрыть пароль" : "Показать пароль"}
        className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted hover:text-text"
      >
        {show ? <EyeOff size={17} /> : <Eye size={17} />}
      </button>
    </div>
  );
}

function CheckRow({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex cursor-pointer gap-3 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 size-4 shrink-0 accent-[var(--brand)]" />
      <span>{children}</span>
    </label>
  );
}

const docLink = (href: string, text: string) => (
  <Link href={href} className="text-brand underline underline-offset-2">
    {text}
  </Link>
);

export function SignupForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [offer, setOffer] = useState(false);
  const [pd, setPd] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!EMAIL_RE.test(email.trim())) next.email = "Введите корректный email.";
    if (password.length < MIN_PASSWORD) next.password = `Минимум ${MIN_PASSWORD} символов.`;
    if (confirm !== password) next.confirm = "Пароли не совпадают.";
    if (!offer || !pd) next.consent = "Чтобы создать аккаунт, примите оферту и дайте согласие на обработку данных.";
    setErrors(next);
    if (Object.keys(next).length === 0) router.push("/verify-email");
  }

  return (
    <form onSubmit={submit} noValidate className="mt-6 space-y-4">
      <Field id="email" label="Email" error={errors.email}>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          maxLength={254}
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "email-err" : undefined}
          className={inputCls}
        />
      </Field>
      <Field id="password" label="Пароль" error={errors.password}>
        <PasswordInput id="password" value={password} onChange={setPassword} error={errors.password} autoComplete="new-password" />
      </Field>
      <Field id="confirm" label="Подтвердите пароль" error={errors.confirm}>
        <PasswordInput id="confirm" value={confirm} onChange={setConfirm} error={errors.confirm} autoComplete="new-password" />
      </Field>
      <div className="space-y-3 pt-1">
        <CheckRow checked={offer} onChange={setOffer}>
          Принимаю условия {docLink("/legal/offer", "Договора-оферты")} <span className="text-muted">(обязательно)</span>
        </CheckRow>
        <CheckRow checked={pd} onChange={setPd}>
          Даю {docLink("/legal/pd-consent", "согласие на обработку персональных данных")} <span className="text-muted">(обязательно)</span>
        </CheckRow>
        <CheckRow checked={marketing} onChange={setMarketing}>
          Согласен получать новости и рекламные материалы AdPilot ({docLink("/legal/marketing-consent", "согласие на рассылку")})
        </CheckRow>
        {errors.consent && <p className="text-xs text-danger">{errors.consent}</p>}
      </div>
      <button type="submit" className="btn btn-primary h-12 w-full">
        Создать аккаунт
      </button>
      <p className="text-xs text-muted">Как мы обрабатываем данные — в {docLink("/legal/privacy", "Политике обработки персональных данных")}.</p>
    </form>
  );
}

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim()) || !password) {
      setError("Введите email и пароль.");
      return;
    }
    router.push("/demo");
  }

  return (
    <form onSubmit={submit} noValidate className="mt-6 space-y-4">
      <Field id="email" label="Email">
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={254} className={inputCls} />
      </Field>
      <Field id="password" label="Пароль">
        <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
      </Field>
      <div className="flex justify-end">
        <Link href="/reset-password" className="text-sm font-semibold text-brand">
          Забыли пароль?
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <button type="submit" className="btn btn-primary h-12 w-full">
        Войти
      </button>
    </form>
  );
}

export function ResetForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  if (sent)
    return (
      <p role="status" className="mt-6 rounded-xl bg-success-bg p-4 text-sm text-success">
        Если аккаунт с таким email существует, мы отправим на него ссылку для смены пароля.
      </p>
    );
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (EMAIL_RE.test(email.trim())) setSent(true);
      }}
      className="mt-6 space-y-4"
    >
      <Field id="email" label="Email">
        <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={254} className={inputCls} />
      </Field>
      <button type="submit" className="btn btn-primary h-12 w-full">
        Отправить ссылку
      </button>
    </form>
  );
}

type SourceState = "idle" | "connecting" | "choose" | "connected";

const GOALS = ["Заявка", "Звонок", "Покупка"];

function SourceCard({
  icon: Icon,
  name,
  scope,
  state,
  onConnect,
  choose,
  details,
}: {
  icon: typeof Megaphone;
  name: string;
  scope: string;
  state: SourceState;
  onConnect: () => void;
  choose: ReactNode;
  details: ReactNode;
}) {
  return (
    <article className="card p-5">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand">
          <Icon size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-bold">{name}</h2>
            {state === "connected" && (
              <span className="badge bg-success-bg text-success">
                <span className="size-1.5 rounded-full bg-success" /> Подключено
              </span>
            )}
          </div>
          <p className="text-sm text-muted">{scope}</p>
        </div>
      </div>
      <div className="mt-4">
        {state === "idle" && (
          <>
            <button className="btn btn-primary w-full sm:w-auto" onClick={onConnect}>
              Подключить
            </button>
            <p className="mt-2 text-xs text-muted">Откроется окно Яндекса: разрешите AdPilot доступ к статистике.</p>
          </>
        )}
        {state === "connecting" && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted">
            <Loader2 size={16} className="animate-spin" /> Ждём разрешения в Яндексе…
          </p>
        )}
        {state === "choose" && choose}
        {state === "connected" && details}
      </div>
    </article>
  );
}

export function ConnectSources() {
  const [direct, setDirect] = useState<SourceState>("idle");
  const [metrika, setMetrika] = useState<SourceState>("idle");
  const [goals, setGoals] = useState<string[]>(GOALS);

  const connect = (set: (s: SourceState) => void) => () => {
    set("connecting");
    // Simulates the user coming back from the Yandex OAuth window.
    setTimeout(() => set("choose"), 900);
  };

  const row = (k: string, v: string) => (
    <div className="flex justify-between gap-4 text-sm">
      <dt className="text-muted">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );

  return (
    <div className="mt-6 space-y-4">
      <SourceCard
        icon={Megaphone}
        name="Яндекс Директ"
        scope="Расходы · кампании · CPA"
        state={direct}
        onConnect={connect(setDirect)}
        choose={
          <div className="space-y-3">
            <label htmlFor="account" className="text-sm font-medium">
              Рекламный аккаунт
            </label>
            <select id="account" className={inputCls} defaultValue="demo">
              <option value="demo">Демо-аккаунт</option>
            </select>
            <button className="btn btn-primary" onClick={() => setDirect("connected")}>
              Готово
            </button>
          </div>
        }
        details={
          <dl className="space-y-1.5">
            {row("Аккаунт", "Демо-аккаунт")}
            {row("Последняя синхронизация", "только что")}
          </dl>
        }
      />
      <SourceCard
        icon={BarChart3}
        name="Яндекс Метрика"
        scope="Цели · конверсии · диагностика"
        state={metrika}
        onConnect={connect(setMetrika)}
        choose={
          <div className="space-y-3">
            <label htmlFor="counter" className="text-sm font-medium">
              Счётчик
            </label>
            <select id="counter" className={inputCls} defaultValue="1">
              <option value="1">12345678 · демо-сайт</option>
            </select>
            <fieldset>
              <legend className="text-sm font-medium">Цели для расчёта CPA</legend>
              <div className="mt-2 space-y-2">
                {GOALS.map((g) => (
                  <CheckRow key={g} checked={goals.includes(g)} onChange={(on) => setGoals((s) => (on ? [...s, g] : s.filter((x) => x !== g)))}>
                    {g}
                  </CheckRow>
                ))}
              </div>
            </fieldset>
            <button className="btn btn-primary" disabled={goals.length === 0} onClick={() => setMetrika("connected")}>
              Готово
            </button>
          </div>
        }
        details={
          <dl className="space-y-1.5">
            {row("Счётчик", "12345678")}
            {row("Цели", String(goals.length))}
            {row("Последняя синхронизация", "только что")}
          </dl>
        }
      />
      <div className="pt-2">
        {direct === "connected" ? (
          <Link href="/demo" className="btn btn-primary h-12 w-full">
            <Check size={18} /> Запустить бесплатный аудит
          </Link>
        ) : (
          <button className="btn btn-primary h-12 w-full" disabled>
            Запустить бесплатный аудит
          </button>
        )}
        <p className="mt-2 text-center text-xs text-muted">
          {direct !== "connected"
            ? "Для аудита нужен хотя бы Яндекс Директ."
            : metrika === "connected"
              ? "Всё готово. В прототипе аудит откроется на демо-данных."
              : "Можно начать без Метрики, но часть диагностик будет ограничена."}
        </p>
      </div>
    </div>
  );
}
