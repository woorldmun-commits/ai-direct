"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { CheckRow, docLink, Field, inputCls } from "@/components/form";
import { Logo } from "@/components/ui";

// Prototype of sign-in by phone (P0 D2): number +7 → SMS code → (new number) consents → session.
// There is no auth API yet: no SMS is sent and nothing leaves the browser.

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
          <Info size={14} className="mt-0.5 shrink-0" /> Прототип: вход ещё не подключён к серверу, SMS не отправляется, данные никуда не уходят.
        </p>
      </div>
    </main>
  );
}

const CODE_LEN = 6;
const RESEND_S = 60;
const CODE_TTL_MS = 5 * 60_000;
const MAX_ATTEMPTS = 5;
const MAX_SENDS_PER_HOUR = 5;
const DEMO_CODE = "123456";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Earlier demo builds kept entered numbers here (personal data, 152-FZ). Nothing is stored now; the key is only removed.
const LEGACY_PHONES_KEY = "adpilot-demo-phones";

/** "8 (912) 345-67-89" → "9123456789" (10 digits of a Russian mobile number) or null. */
function normalizePhone(raw: string): string | null {
  let d = raw.replace(/\D/g, "");
  if (d.length === 11 && (d[0] === "7" || d[0] === "8")) d = d.slice(1);
  return d.length === 10 && d[0] === "9" ? d : null;
}

const formatPhone = (d: string) => `+7 ${d.slice(0, 3)} ${d.slice(3, 6)}-${d.slice(6, 8)}-${d.slice(8, 10)}`;

type Step = "phone" | "code" | "consent" | "profile";

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export function PhoneAuth() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("phone");
  const [raw, setRaw] = useState("");
  const [phone, setPhone] = useState("");
  const [sends, setSends] = useState<number[]>([]);
  const [code, setCode] = useState("");
  const [attempts, setAttempts] = useState(0);
  const [error, setError] = useState("");
  const now = useNow(step === "code");

  useEffect(() => {
    try {
      localStorage.removeItem(LEGACY_PHONES_KEY);
    } catch {
      // Storage unavailable: nothing to remove.
    }
  }, []);

  const sentAt = sends[sends.length - 1] ?? 0;
  const wait = Math.min(RESEND_S, Math.max(0, RESEND_S - Math.floor((now - sentAt) / 1000)));

  function requestCode(d: string) {
    const t = Date.now();
    const recent = sends.filter((s) => t - s < 3_600_000);
    if (recent.length >= MAX_SENDS_PER_HOUR) {
      const mins = Math.ceil((recent[0] + 3_600_000 - t) / 60_000);
      setError(`Слишком много запросов кода для этого номера. Попробуйте через ${mins} мин.`);
      return;
    }
    setSends([...recent, t]);
    setPhone(d);
    setCode("");
    setAttempts(0);
    setError("");
    setStep("code");
  }

  function submitPhone(e: FormEvent) {
    e.preventDefault();
    const d = normalizePhone(raw);
    if (!d) return setError("Введите российский мобильный номер: +7 и 10 цифр, начиная с 9.");
    requestCode(d);
  }

  function submitCode(e: FormEvent) {
    e.preventDefault();
    if (attempts >= MAX_ATTEMPTS) return setError("Превышено число попыток. Запросите новый код.");
    if (Date.now() - sentAt > CODE_TTL_MS) return setError("Срок действия кода истёк (5 минут). Запросите новый код.");
    if (code.length !== CODE_LEN) return setError(`Код состоит из ${CODE_LEN} цифр.`);
    if (code !== DEMO_CODE) {
      const left = MAX_ATTEMPTS - attempts - 1;
      setAttempts(attempts + 1);
      return setError(left > 0 ? `Неверный код. Осталось попыток: ${left}.` : "Неверный код. Попытки закончились — запросите новый код.");
    }
    setError("");
    // Whether the number is already registered is the server's answer; the demo keeps no list and asks for consents.
    setStep("consent");
  }

  if (step === "consent") return <ConsentStep onDone={() => setStep("profile")} />;
  if (step === "profile") return <ProfileStep onDone={() => router.push("/onboarding")} />;

  if (step === "phone")
    return (
      <form onSubmit={submitPhone} noValidate className="mt-6 space-y-4">
        <Field id="phone" label="Номер мобильного телефона" error={error} hint="Пришлём SMS с кодом. Номер нужен только для входа.">
          <input
            id="phone"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="+7 900 000-00-00"
            value={raw}
            onChange={(e) => setRaw(e.target.value.slice(0, 20))}
            aria-invalid={!!error}
            aria-describedby={error ? "phone-err" : undefined}
            className={inputCls}
            autoFocus
          />
        </Field>
        <button type="submit" className="btn btn-primary h-12 w-full">
          Получить код
        </button>
        <p className="text-xs text-muted">Новый номер — после кода попросим принять оферту и дать согласие на обработку данных.</p>
      </form>
    );

  return (
    <form onSubmit={submitCode} noValidate className="mt-6 space-y-4">
      <p role="status" className="rounded-xl bg-brand-soft p-3 text-sm text-brand">
        Если номер {formatPhone(phone)} верный, на него придёт SMS с кодом. Код действует 5 минут.
      </p>
      <Field id="code" label="Код из SMS" error={error} hint={`Демо: SMS не отправляется, введите ${DEMO_CODE}.`}>
        <input
          id="code"
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={CODE_LEN}
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, CODE_LEN))}
          aria-invalid={!!error}
          aria-describedby={error ? "code-err" : undefined}
          className={`${inputCls} money text-center text-lg tracking-[0.5em]`}
          autoFocus
        />
      </Field>
      <button type="submit" className="btn btn-primary h-12 w-full" disabled={code.length !== CODE_LEN}>
        Войти
      </button>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <button type="button" className="font-semibold text-brand" onClick={() => (setStep("phone"), setError(""))}>
          Изменить номер
        </button>
        {wait > 0 ? (
          <span className="text-muted" aria-live="polite">
            Отправить повторно через 0:{String(wait).padStart(2, "0")}
          </span>
        ) : (
          <button type="button" className="font-semibold text-brand" onClick={() => requestCode(phone)}>
            Отправить код повторно
          </button>
        )}
      </div>
    </form>
  );
}

function ConsentStep({ onDone }: { onDone: () => void }) {
  const [offer, setOffer] = useState(false);
  const [pd, setPd] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!offer || !pd) return setError("Чтобы создать аккаунт, примите оферту и дайте согласие на обработку персональных данных.");
    onDone();
  }

  return (
    <form onSubmit={submit} noValidate className="mt-6 space-y-4">
      <p className="text-sm">Номер подтверждён. Это новый аккаунт — осталось принять условия.</p>
      <div className="space-y-3">
        <CheckRow checked={offer} onChange={setOffer}>
          Принимаю условия {docLink("/legal/offer", "Договора-оферты")} <span className="text-muted">(обязательно)</span>
        </CheckRow>
        <CheckRow checked={pd} onChange={setPd}>
          Даю {docLink("/legal/pd-consent", "согласие на обработку персональных данных")} <span className="text-muted">(обязательно)</span>
        </CheckRow>
        <CheckRow checked={marketing} onChange={setMarketing}>
          Согласен получать новости и рекламные материалы AdPilot ({docLink("/legal/marketing-consent", "согласие на рассылку")}){" "}
          <span className="text-muted">(необязательно)</span>
        </CheckRow>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
      </div>
      <button type="submit" className="btn btn-primary h-12 w-full">
        Создать аккаунт и войти
      </button>
      <p className="text-xs text-muted">Как мы обрабатываем данные — в {docLink("/legal/privacy", "Политике обработки персональных данных")}.</p>
    </form>
  );
}

function ProfileStep({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (email.trim() && !EMAIL_RE.test(email.trim())) return setError("Проверьте email или оставьте поле пустым.");
    onDone();
  }

  return (
    <form onSubmit={submit} noValidate className="mt-6 space-y-4">
      <p className="text-sm">Вы вошли. Расскажите о себе — это необязательно, можно заполнить позже в настройках.</p>
      <Field id="name" label="Имя">
        <input id="name" autoComplete="given-name" maxLength={80} className={inputCls} />
      </Field>
      <Field id="company" label="Компания">
        <input id="company" autoComplete="organization" maxLength={120} className={inputCls} />
      </Field>
      <Field id="email" label="Email для чеков и счетов" error={error} hint="Не для входа — входите по номеру телефона.">
        <input
          id="email"
          type="email"
          autoComplete="email"
          maxLength={254}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "email-err" : undefined}
          className={inputCls}
        />
      </Field>
      <div className="flex flex-col gap-2 sm:flex-row">
        <button type="submit" className="btn btn-primary h-12 flex-1">
          Продолжить
        </button>
        <button type="button" className="btn btn-secondary h-12 flex-1" onClick={onDone}>
          Пропустить
        </button>
      </div>
    </form>
  );
}
