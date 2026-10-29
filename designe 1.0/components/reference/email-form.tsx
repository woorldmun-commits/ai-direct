'use client';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Eye,EyeOff} from 'lucide-react';
import type {AcceptedDocuments} from '@/lib/legal-document';

export type EmailMode='login'|'signup'|'verify'|'forgot'|'reset';
export function EmailForm({mode,enabled,acceptedDocuments=null,localPreview=false}:{mode:EmailMode;enabled:boolean;acceptedDocuments?:AcceptedDocuments|null;localPreview?:boolean}){
 const registrationReady=acceptedDocuments!==null;
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[show,setShow]=useState(false),[token,setToken]=useState('');
 const active=useRef(false);
 useEffect(()=>{
  if(mode!=='verify'&&mode!=='reset')return;
  const params=new URLSearchParams(location.hash.slice(1)),value=params.get('token')??'';
  // The fragment exists only in the browser; consume it after hydration without storing it persistently.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  if(/^[A-Za-z0-9_-]{32,128}$/.test(value))setToken(value);
  history.replaceState(null,'',location.pathname);
 },[mode]);
 const blocked=!enabled||(mode==='signup'&&!registrationReady)||((mode==='verify'||mode==='reset')&&!token);
 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();if(active.current||blocked)return;
  const data=new FormData(event.currentTarget),password=String(data.get('password')??'');
  if((mode==='signup'||mode==='reset')&&password!==String(data.get('confirm'))){setError('Пароли не совпадают.');return;}
  active.current=true;setBusy(true);setError('');
  const operation=mode==='signup'?'register':mode==='forgot'?'reset-request':mode==='reset'?'reset':mode==='verify'?'verify':'login';
  const body=mode==='verify'||mode==='reset'?{token,password}:mode==='forgot'?{email:data.get('email')}:{email:data.get('email'),password,...(mode==='signup'?{accepted:acceptedDocuments,locale:'ru-RU'}:{})};
  try{
   const response=await fetch('/api/auth/email/'+operation,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   if(!response.ok)throw new Error(response.status===401?'Неверный email или пароль.':response.status===429?'Слишком много попыток. Подождите и попробуйте позже.':response.status===400?'Проверьте данные. Ссылка могла устареть или уже использована.':'Сервис входа или отправки писем временно недоступен. Попробуйте позже.');
   if(mode==='login'||mode==='verify'){location.assign(new URL('/workspace',location.href).href);return;}
   setMessage(mode==='reset'?'Пароль изменён. Войдите с новым паролем.':mode==='forgot'?'Если для этого адреса есть аккаунт с паролем, вы получите письмо с инструкцией.':'Проверьте почту. Если регистрация для этого адреса возможна, вы получите ссылку подтверждения.');
  }catch(e){setError(e instanceof Error?e.message:'Не удалось завершить запрос.');}
  finally{active.current=false;setBusy(false);}
 }
 if(message)return <div className="ref-email-result" role="status"><p>{message}</p>{localPreview&&mode!=='reset'&&<a className="ref-button" href="http://127.0.0.1:3121/local-test/mail" target="_blank" rel="noreferrer">Открыть локальный почтовый ящик</a>}<a href={mode==='reset'?'/login':mode==='forgot'?'/forgot-password':'/signup'}>{mode==='reset'?'Войти':mode==='forgot'?'Запросить письмо повторно':'Другой адрес или повторная отправка'}</a></div>;
 return <form className="ref-email-form" onSubmit={submit}>
  {localPreview&&<p className="ref-email-local">Локальная проверка: используйте адрес вида name@example.test. Письма доступны в локальном ящике, во внешнюю почту не отправляются. Документы тестовые.</p>}
  {!enabled&&<p className="ref-auth-note ref-email-unavailable" role="status">Вход и регистрация по почте готовятся к запуску. Отправка писем пока не настроена.</p>}
  {mode==='signup'&&!registrationReady&&<p role="status">Регистрация откроется после утверждения и публикации документов.</p>}
  {(mode==='verify'||mode==='reset')&&!token&&<p role="status">Откройте ссылку из письма. Если она устарела, запросите новое письмо.</p>}
  <fieldset disabled={!enabled||busy}>
  {mode!=='verify'&&mode!=='reset'&&<label>Электронная почта<input name="email" type="email" autoComplete="email" maxLength={254} required placeholder={localPreview?'name@example.test':'you@company.ru'}/></label>}
  {mode!=='forgot'&&<label>{mode==='verify'?'Пароль, указанный при регистрации':mode==='reset'?'Новый пароль':'Пароль'}<span className="ref-email-password"><input name="password" type={show?'text':'password'} autoComplete={mode==='signup'||mode==='reset'?'new-password':'current-password'} minLength={mode==='signup'||mode==='reset'?12:1} maxLength={128} required/><button type="button" aria-label={show?'Скрыть пароль':'Показать пароль'} aria-pressed={show} onClick={()=>setShow(!show)}>{show?<EyeOff size={20}/>:<Eye size={20}/>}</button></span></label>}
  {(mode==='signup'||mode==='reset')&&<><p className="ref-auth-note">От 12 до 128 символов. Используйте уникальный пароль.</p><label>Повторите пароль<input name="confirm" type={show?'text':'password'} autoComplete="new-password" minLength={12} maxLength={128} required/></label></>}
  {mode==='signup'&&<><label className="ref-email-consent"><input name="offer" type="checkbox" required/><span>Принимаю <a href={acceptedDocuments?`/legal/offer?version=${acceptedDocuments.offer}`:'/legal/offer'} target="_blank" rel="noreferrer">договор-оферту</a>{acceptedDocuments&&` (редакция ${acceptedDocuments.offer})`}.</span></label><label className="ref-email-consent"><input name="pd" type="checkbox" required/><span>Даю <a href={acceptedDocuments?`/legal/pd-consent?version=${acceptedDocuments.pd_consent}`:'/legal/pd-consent'} target="_blank" rel="noreferrer">согласие на обработку персональных данных</a>{acceptedDocuments&&` (редакция ${acceptedDocuments.pd_consent})`}.</span></label></>}
  </fieldset>
  {error&&<p className="ref-auth-error" role="alert">{error}</p>}
  <button className="ref-button ref-primary ref-auth-submit" disabled={busy||blocked}>{busy?'Подождите…':mode==='signup'?'Создать аккаунт':mode==='verify'?'Подтвердить email и войти':mode==='forgot'?'Получить ссылку':mode==='reset'?'Сохранить пароль':'Войти по email'}</button>
  <div className="ref-email-links">{mode==='login'?<><a href="/signup">Создать аккаунт</a><a href="/forgot-password">Забыли пароль?</a></>:<a href="/login">Вернуться ко входу</a>}</div>
 </form>;
}
