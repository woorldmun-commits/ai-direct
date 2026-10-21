'use client';

import {useEffect,useState,type FormEvent} from 'react';

type State={enabled:boolean;manager:boolean;connected:boolean;analysis_access:boolean;run:null|{id:number;status:string;error_code:string|null}};
const labels:Record<string,string>={queued:'В очереди',running:'Загрузка данных',waiting_report:'Яндекс формирует отчёт',succeeded:'Данные загружены',failed:'Загрузка не удалась',skipped:'Запуск пропущен'};

export function DirectConnect({workspace}:{workspace:string}){
 const [state,setState]=useState<State|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const base=`/api/workspaces/${encodeURIComponent(workspace)}/direct`;
 useEffect(()=>{
  let active=true;
  const load=async()=>{
   try{
    const r=await fetch(base,{cache:'no-store'});
    if(!r.ok)throw new Error();
    const value=await r.json();
    if(active)setState(value);
   }catch{if(active)setMessage('Статус подключения недоступен. Обновите страницу.');}
  };
  void load();const timer=setInterval(load,10000);
  return()=>{active=false;clearInterval(timer);};
 },[base]);
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();setMessage('');setBusy(true);
  const data=new FormData(e.currentTarget);
  const goals=String(data.get('goals')||'').trim();
  const counter=String(data.get('counter')||'').trim();
  const payload={login:String(data.get('login')||'').trim(),counter_id:counter?Number(counter):null,
   goal_ids:goals?goals.split(',').map(v=>Number(v.trim())):[],target_cpa:String(data.get('cpa')||'').trim()||null};
  if((!!counter!==!!goals)||payload.goal_ids.some(v=>!Number.isSafeInteger(v)||v<=0)){
   setMessage('Укажите счётчик и ID целей вместе. Цели — положительные числа через запятую.');setBusy(false);return;
  }
  try{
   const r=await fetch(base+'/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   const value=await r.json();if(!r.ok)throw new Error(value.error?.message||'Подключение недоступно.');
   const url=new URL(value.authorize_url);
   if(url.origin!=='https://oauth.yandex.ru'||url.pathname!=='/authorize')throw new Error('Некорректный адрес авторизации.');
   window.location.assign(url.href);
  }catch(error){setMessage(error instanceof Error?error.message:'Подключение не выполнено.');setBusy(false);}
 }
 async function sync(){
  setBusy(true);setMessage('');
  try{
   const r=await fetch(base+'/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
   const value=await r.json();if(!r.ok)throw new Error(value.error?.message||'Запуск недоступен.');
   setMessage('Анализ поставлен в очередь. После загрузки обновите страницу, чтобы увидеть результаты.');
  }catch(error){setMessage(error instanceof Error?error.message:'Ошибка запуска.');}finally{setBusy(false);}
 }
 return <section className="pilot-card"><h2>Подключить Яндекс Директ</h2>
  <p>Вы перейдёте на сайт Яндекса и разрешите доступ к статистике. inrou не меняет объявления, ставки и бюджеты.</p>
  <p>Яндекс выдаёт приложению право API, которое технически позволяет управлять рекламой. В этом сервисе используются только запросы чтения.</p>
  {message&&<p role="status">{message}</p>}
  {!state?<p>Проверяем доступ…</p>:!state.manager?<p>Подключение доступно владельцу или администратору.</p>:
   !state.enabled?<p>Администратор ещё не настроил OAuth-приложение Директа.</p>:
   !state.analysis_access?<p>Администратор должен выдать вашему рабочему пространству доступ к пилоту.</p>:<>
   {state.run&&<p role="status">Последняя загрузка: {labels[state.run.status]||'Статус неизвестен'}. {state.run.error_code&&'Код: '+state.run.error_code+'. '}После загрузки обновите страницу: аудит может занять дополнительное время.</p>}
   {state.connected&&<button type="button" className="ref-button" onClick={sync} disabled={busy||!!state.run&&['queued','running','waiting_report'].includes(state.run.status)}>Обновить данные и анализ</button>}
   <form className="ap-form" onSubmit={submit}>
    <label>Логин рекламного кабинета<input name="login" required maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]*" autoComplete="off"/></label>
    <label>Номер счётчика Метрики<input name="counter" inputMode="numeric" pattern="[0-9]+"/></label>
    <label>ID целей через запятую<input name="goals" placeholder="12345, 67890"/></label>
    <label>Целевая стоимость конверсии, ₽<input name="cpa" type="number" min="0.01" step="0.01"/></label>
    <p>Без счётчика и целей анализ конверсий будет недоступен. Используйте цели из вашего счётчика Метрики.</p>
    <button className="ref-button ref-primary" disabled={busy}>{busy?'Подключаем…':'Разрешить доступ через Яндекс'}</button>
   </form></>}
 </section>;
}
