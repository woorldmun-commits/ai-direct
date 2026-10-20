"use client";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { ThemeControl } from "@/components/theme-control";
import { useState, type FormEvent } from "react";
import { ReferenceLogo } from "./shared";
import "./reference.css";
import "./auth.css";
import {EmailForm,type EmailMode} from './email-form';

export function ReferenceAuth({ callbackError = false, registrationReady = false, mode = 'login', emailEnabled = false, localPreview = false }: { callbackError?: boolean; registrationReady?: boolean; mode?:EmailMode; emailEnabled?:boolean; localPreview?:boolean }) {
  const [accepted, setAccepted] = useState(false);
  const [pdConsent, setPdConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(callbackError ? "Вход не завершён. Повторите попытку. Если ошибка повторится, обратитесь к администратору." : "");
  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (busy || accepted !== pdConsent || (mode==='signup' && (!registrationReady || !accepted || !pdConsent))) return;
    setBusy(true); setError("");
    try {
      const response = await fetch('/api/auth/yandex/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted: registrationReady && accepted && pdConsent ? { offer: '2026-10-01', pd_consent: '2026-10-01' } : {}, locale: 'ru-RU' }),
      });
      if (!response.ok) throw new Error();
      const result: unknown = await response.json();
      if (!result || typeof result !== 'object' || !('authorize_url' in result) || typeof result.authorize_url !== 'string') throw new Error();
      const url = new URL(result.authorize_url);
      if (url.origin !== 'https://oauth.yandex.ru' || url.pathname !== '/authorize' || url.username || url.password) throw new Error();
      window.location.assign(url.href);
    } catch {
      setError('Вход временно недоступен. Попробуйте позже. Аккаунт не создан, доступ к рекламным данным не предоставлен.');
      setBusy(false);
    }
  }
  return <main id="main-content" className="ref-ui ref-auth-page"><div className="ref-auth-glow" aria-hidden="true" /><div className="ref-auth-shell">
    <section className="ref-auth-form-panel">
      <Link href="/" aria-label="inrou — главная"><ReferenceLogo /></Link>
      <div className="ref-auth-heading"><h1>{mode==='signup'?'Создайте аккаунт inrou':mode==='verify'?'Подтвердите почту':mode==='forgot'?'Восстановите доступ':mode==='reset'?'Новый пароль':'Вход в inrou'}</h1><p>{mode==='signup'?(emailEnabled?'Зарегистрируйтесь по email или через Яндекс ID.':'Зарегистрируйтесь через Яндекс ID.'):mode==='verify'?'Повторите выбранный пароль, чтобы завершить регистрацию.':mode==='forgot'?'Получите ссылку для смены пароля.':mode==='reset'?'Выберите новый уникальный пароль.':emailEnabled?'Войдите по email или через Яндекс ID, чтобы открыть свой кабинет.':'Войдите через Яндекс ID, чтобы открыть свой кабинет.'}</p></div>
      {(emailEnabled || (mode!=='login' && mode!=='signup'))&&<EmailForm mode={mode} enabled={emailEnabled} registrationReady={registrationReady} localPreview={localPreview}/>}
      {(mode==='login'||mode==='signup')&&<details open={!emailEnabled||mode==='signup'} className="ref-auth-alternative"><summary>{mode==='signup'?'Регистрация через Яндекс ID':emailEnabled?'Или войти через Яндекс ID':'Вход через Яндекс ID'}</summary><form onSubmit={signIn} className="ref-auth-signin">
        <p className="ref-auth-note">{registrationReady ? mode==='signup'?'Для создания аккаунта примите оба документа.':'Уже есть аккаунт? Войдите без повторного согласия. Для создания нового аккаунта примите оба документа.' : 'Регистрация откроется после утверждения и публикации документов. Вход доступен для существующих аккаунтов.'}</p>
        {registrationReady && <>
        <label><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} /><span>Принимаю условия <Link href="/legal/offer" target="_blank" rel="noopener">договора-оферты</Link> (редакция 01.10.2026).</span></label>
        <label><input type="checkbox" checked={pdConsent} onChange={e => setPdConsent(e.target.checked)} /><span>Даю <Link href="/legal/pd-consent" target="_blank" rel="noopener">согласие на обработку персональных данных</Link> (редакция 01.10.2026).</span></label>
        </>}
        <button type="submit" disabled={accepted !== pdConsent || busy || (mode==='signup'&&(!registrationReady||!accepted||!pdConsent))} className="ref-button ref-primary ref-auth-submit">{busy ? 'Переходим в Яндекс…' : mode==='signup'?'Создать аккаунт через Яндекс ID':'Войти через Яндекс ID'} <ArrowRight size={17} /></button>
        {error && <p role="alert" className="ref-auth-error">{error}</p>}
      </form></details>}
      {!emailEnabled&&(mode==='login'||mode==='signup')&&<div className="ref-email-links"><Link href={mode==='signup'?'/login':'/signup'}>{mode==='signup'?'Уже есть аккаунт? Войти':'Создать аккаунт'}</Link></div>}
      <p className="ref-auth-note">Рекламные источники подключаются отдельно от входа. Доступ к аккаунту не предоставляет доступ к рекламным кабинетам автоматически.</p>
      <ThemeControl />
      <div className="ref-auth-registration"><Link href="/legal">Правовая информация</Link></div>
      <Link href="/" className="ref-auth-back"><ArrowLeft size={14} />На главную</Link>
    </section>
    <section className="ref-auth-art-panel" aria-label="Ваша реклама под контролем"><div className="ref-auth-glass ref-auth-glass-left" /><div className="ref-auth-glass ref-auth-glass-right" /><Image src="/reference/glass-orb.png" className="ref-auth-orbit" alt="Переливающаяся стеклянная скульптура" width={1536} height={1024} priority /><div className="ref-auth-tagline"><h2>Ваша реклама<br />под контролем</h2><p>Показатели. Источники.<br />Обоснованные решения.</p></div></section>
  </div></main>;
}
