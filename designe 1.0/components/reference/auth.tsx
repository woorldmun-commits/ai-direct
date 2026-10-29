"use client";
import Link from "next/link";
import Image from "next/image";
import {BrandMark} from "@/components/brand-mark";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { ThemeControl } from "@/components/theme-control";
import { useState, type FormEvent } from "react";
import "../ix/ix.css";
import "../ix/public/public.css";
import {EmailForm,type EmailMode} from './email-form';
import type {AcceptedDocuments} from '@/lib/legal-document';
import './signup-art.css';

export function ReferenceAuth({ callbackError = false, acceptedDocuments = null, mode = 'login', emailEnabled = false, localPreview = false, legacyLogin = false }: { callbackError?: boolean; acceptedDocuments?:AcceptedDocuments|null; mode?:EmailMode; emailEnabled?:boolean; localPreview?:boolean; legacyLogin?:boolean }) {
  const registrationReady = acceptedDocuments !== null;
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
        body: JSON.stringify({ accepted: registrationReady && accepted && pdConsent ? acceptedDocuments : {}, locale: 'ru-RU' }),
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
  return <div className="ix ix-auth" lang="ru"><a className="ix-skip" href="#main-content">Перейти к содержимому</a><main id="main-content" className="ix-auth-shell" tabIndex={-1}>
    <section className="ix-card ix-auth-form ref-auth-form-panel">
      <Link className="ix-logo" href="/" title="INROU — на главную" style={{padding: 0}}><BrandMark/>INROU<small>INTELLIGENCE ATELIER</small></Link>
      <div className="ref-auth-heading"><h1>{mode==='signup'?'Создайте аккаунт INROU':mode==='verify'?'Подтвердите почту':mode==='forgot'?'Восстановите доступ':mode==='reset'?'Новый пароль':'Вход в INROU'}</h1><p>{mode==='signup'?'Создайте аккаунт по почте и подтвердите адрес.':mode==='verify'?'Повторите выбранный пароль, чтобы завершить регистрацию.':mode==='forgot'?'Получите ссылку для смены пароля.':mode==='reset'?'Выберите новый уникальный пароль.':'Введите email и пароль, чтобы открыть свой кабинет.'}</p></div>
      <EmailForm mode={mode} enabled={emailEnabled} acceptedDocuments={acceptedDocuments} localPreview={localPreview}/>
      {callbackError&&!legacyLogin&&<p role="alert" className="ref-auth-error">{error}</p>}
      {legacyLogin&&(mode==='login'||mode==='signup')&&<details className="ref-auth-alternative"><summary>Вход в ранее созданный аккаунт через Яндекс ID</summary><form onSubmit={signIn} className="ref-auth-signin">
        <p className="ref-auth-note">{registrationReady ? mode==='signup'?'Для создания аккаунта примите оба документа.':'Уже есть аккаунт? Войдите без повторного согласия. Для создания нового аккаунта примите оба документа.' : 'Регистрация откроется после утверждения и публикации документов. Вход доступен для существующих аккаунтов.'}</p>
        {registrationReady && <>
        <label><input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)} /><span>Принимаю условия <Link href={`/legal/offer?version=${acceptedDocuments!.offer}`} target="_blank" rel="noopener">договора-оферты</Link> (редакция {acceptedDocuments!.offer}).</span></label>
        <label><input type="checkbox" checked={pdConsent} onChange={e => setPdConsent(e.target.checked)} /><span>Даю <Link href={`/legal/pd-consent?version=${acceptedDocuments!.pd_consent}`} target="_blank" rel="noopener">согласие на обработку персональных данных</Link> (редакция {acceptedDocuments!.pd_consent}).</span></label>
        </>}
        <button type="submit" disabled={accepted !== pdConsent || busy || (mode==='signup'&&(!registrationReady||!accepted||!pdConsent))} className="ref-button ref-primary ref-auth-submit">{busy ? 'Переходим в Яндекс…' : mode==='signup'?'Создать аккаунт через Яндекс ID':'Войти через Яндекс ID'} <ArrowRight size={17} /></button>
        {error && <p role="alert" className="ref-auth-error">{error}</p>}
      </form></details>}

      <p className="ref-auth-note">Рекламные источники подключаются отдельно от входа. Доступ к аккаунту не предоставляет доступ к рекламным кабинетам автоматически.</p>
      <ThemeControl />
      <div className="ref-auth-registration"><Link href="/legal">Правовая информация</Link></div>
      <Link href="/" className="ref-auth-back"><ArrowLeft size={14} />На главную</Link>
    </section>
    <section className={'ix-auth-art' + (mode === 'signup' ? ' ix-auth-art--signup' : '')} aria-hidden="true">{mode === 'signup' && <Image src="/reference/inrou-signup-workspace-v1.webp" fill sizes="(max-width: 767px) 1px, 50vw" alt=""/>}</section>
  </main></div>;
}
