"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { CheckRow, docLink, Field, inputCls } from "@/components/form";
import { SmartCaptcha } from "@/components/smart-captcha";
import { Logo } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { api, ApiError, errorText } from "@/lib/api";

export function AuthLayout({ title, sub, children, footer }: { title: string; sub?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return <main id="main-content" className="auth-page relative grid min-h-dvh place-items-center px-4 py-12"><ThemeToggle className="absolute top-5 right-5"/><div className="auth-frame grid w-full max-w-[1060px] items-center gap-12 lg:grid-cols-2 lg:gap-24">
    <aside className="hidden lg:block">
      <Image src="/figma/liquid/6-33531-img.png" alt="" fill unoptimized className="auth-promo-image" />
      <div className="auth-promo-copy"><h2>Ваш рост —<br />под контролем</h2><p>Умная аналитика.<br />Точные рекомендации.<br />Результаты без лишних усилий.</p></div>
    </aside>
    <div className="w-full max-w-[480px] justify-self-center">
    <Link href="/" aria-label="На главную"><Logo size={23} /></Link>
    <div className="card mt-6 p-6 md:p-8"><h1 className="text-2xl font-bold">{title}</h1>{sub && <p className="mt-2 text-sm text-muted">{sub}</p>}{children}</div>
    {footer && <p className="mt-4 text-center text-sm text-muted">{footer}</p>}
    <p className="mt-6 text-center text-xs text-muted">Доступ к рекламе подключается отдельно. AdPilot читает статистику и предлагает решения; изменения вы вносите вручную.</p>
  </div></div></main>;
}
export function normalizePhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, "");
  if (digits.length === 11 && (digits[0] === "7" || digits[0] === "8")) digits = digits.slice(1);
  return digits.length === 10 && digits[0] === "9" ? "+7" + digits : null;
}
export function PhoneAuth() {
  const router = useRouter();
  const [raw, setRaw] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code" | "consent">("phone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [offer, setOffer] = useState(false);
  const [pd, setPd] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaRevision, setCaptchaRevision] = useState(0);
  async function requestCode() {
    const normalized = normalizePhone(raw);
    if (!normalized) return setError("Введите российский мобильный номер: +7 и 10 цифр, начиная с 9.");
    setBusy(true); setError("");
    try {
      await api("/auth/code/request", { method: "POST", body: JSON.stringify({ phone: normalized, ...(captchaToken ? { captcha_token: captchaToken } : {}) }) });
      setPhone(normalized); setCode(""); setStep("code"); setCaptchaToken(""); setCaptchaRevision((v) => v + 1);
    } catch (e) {
      if (e instanceof ApiError && (e.code === "captcha_required" || e.reason === "captcha_required")) { setCaptchaRequired(true); setCaptchaToken(""); setError("Для повторного SMS пройдите проверку от роботов."); }
      else setError(errorText(e));
    } finally { setBusy(false); if (captchaToken) { setCaptchaToken(""); setCaptchaRevision((v) => v + 1); } }
  }
  async function verify() {
    setBusy(true); setError("");
    try {
      await api("/auth/code/verify", { method: "POST", body: JSON.stringify({
        phone, code, ...(step === "consent" ? { accepted: { offer: "2026-10-01", pd_consent: "2026-10-01", ...(marketing ? { marketing: "2026-10-01" } : {}) } } : {}),
      }) });
      router.replace("/app");
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === "acceptance_required") setStep("consent");
      else setError(errorText(e));
    } finally { setBusy(false); }
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (step === "phone") void requestCode(); else void verify();
  }
  return <form onSubmit={submit} className="mt-6 space-y-4">
    {step === "phone" ? <Field id="phone" label="Номер мобильного телефона">
      <input id="phone" type="tel" autoComplete="tel" className={inputCls} value={raw} onChange={(e) => setRaw(e.target.value.slice(0, 20))} required placeholder="+7 900 000-00-00" />
    </Field> : <><p className="text-sm">Код отправлен на {phone}. Если он не пришёл, проверьте номер.</p>
      <Field id="code" label="Код из SMS"><input id="code" inputMode="numeric" autoComplete="one-time-code" className={inputCls}
        value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} minLength={6} maxLength={6} required /></Field></>}
    {step === "consent" && <div className="space-y-3">
      <CheckRow checked={offer} onChange={setOffer}>Принимаю {docLink("/legal/offer", "оферту")}</CheckRow>
      <CheckRow checked={pd} onChange={setPd}>Даю {docLink("/legal/pd-consent", "согласие на обработку персональных данных")}</CheckRow>
      <CheckRow checked={marketing} onChange={setMarketing}>Согласен на {docLink("/legal/marketing-consent", "необязательную рассылку")}</CheckRow>
    </div>}
    {captchaRequired && <SmartCaptcha key={captchaRevision} onToken={setCaptchaToken} />}
    {error && <p role="alert" className="rounded-xl bg-danger-bg p-3 text-sm text-danger">{error}</p>}
    <button className="btn btn-primary h-12 w-full" disabled={busy || (step === "phone" && captchaRequired && !captchaToken) || (step !== "phone" && code.length !== 6) || (step === "consent" && (!offer || !pd))}>
      {busy ? "Подождите…" : step === "phone" ? "Получить код" : step === "consent" ? "Принять условия и войти" : "Войти"}
    </button>
    {step !== "phone" && <div className="flex justify-between gap-2 text-sm">
      <button type="button" disabled={busy} className="text-brand" onClick={() => { setStep("phone"); setCode(""); setError(""); }}>Изменить номер</button>
      <button type="button" disabled={busy || (captchaRequired && !captchaToken)} className="text-brand" onClick={() => void requestCode()}>Отправить код повторно</button>
    </div>}
    <p className="text-xs text-muted">SMS отправляет подключённый провайдер. Если отправка недоступна, вы увидите причину; демонстрационный код не используется.</p>
  </form>;
}
