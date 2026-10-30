'use client';
import {useEffect, useRef, useState, type FormEvent} from 'react';

type Preference = {enabled:boolean;email_verified:boolean;delivery_configured:boolean};
const valid = (v:unknown):v is Preference => !!v&&typeof v==='object'&&['enabled','email_verified','delivery_configured'].every(k=>typeof (v as Record<string,unknown>)[k]==='boolean');

export function EmailPreferences({workspace}:{workspace:string}) {
  const [data,setData]=useState<Preference|null>(null),[enabled,setEnabled]=useState(false),[message,setMessage]=useState('');
  const [busy,setBusy]=useState(false),active=useRef(false);
  const url=`/api/workspaces/${workspace}/email-preference`;
  useEffect(()=>{
    const controller=new AbortController();
    void fetch(url,{signal:controller.signal}).then(async response=>{
      if(!response.ok)throw new Error();
      const value:unknown=await response.json();if(!valid(value))throw new Error();
      setData(value);setEnabled(value.enabled);
    }).catch(()=>{if(!controller.signal.aborted)setMessage('Настройки писем недоступны. Обновите страницу.');});
    return()=>controller.abort();
  },[url]);
  async function save(event:FormEvent) {
    event.preventDefault();if(active.current||!data)return;active.current=true;setBusy(true);setMessage('');
    try {
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled}),signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw new Error();
      const value:unknown=await response.json();if(!valid(value))throw new Error();
      setData(value);setEnabled(value.enabled);setMessage(value.enabled?'Сервисные уведомления включены.':'Сервисные уведомления выключены.');
    }catch{setMessage('Сохранение не подтверждено. Обновите страницу перед повтором.');}
    finally{active.current=false;setBusy(false);}
  }
  return <section aria-label="Сервисные письма"><h3>Письма о новых рекомендациях</h3>
    {!data&&!message&&<p role="status">Загружаем ваши настройки…</p>}
    {data&&<form onSubmit={save}><label className="workspace-checkbox"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)} disabled={busy||(!data.email_verified&&!enabled)}/>Получать сервисные уведомления этого пространства на подтверждённый email</label>
      {!data.email_verified&&<p>Нужен подтверждённый email. Вход через Яндекс сам по себе не подтверждает адрес для этих писем.</p>}
      {!data.delivery_configured&&<p>Отправка ещё не включена оператором; выбранная настройка сохранится.</p>}
      <p>Без названий клиентов, кампаний и рекламных сумм. Это оповещения о новых рекомендациях, без маркетинга и обещания ежедневного дайджеста.</p>
      <button className="ix-btn" disabled={busy}>{busy?'Сохраняем…':'Сохранить настройку писем'}</button></form>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
