'use client';
import {useRef,useState,type FormEvent} from 'react';

const importErrors:Record<string,string>={csv_columns:'Проверьте названия столбцов по шаблону. Лишние столбцы не принимаются.',duplicate_or_invalid_id:'ID должен быть UUID; повторов внутри файла быть не должно.',date_order:'Проверьте порядок дат и отсутствие будущих дат.',status_enum:'Используйте статусы new, qualified, rejected, won, lost, refunded.',account_not_selected:'В файле есть аккаунт, который не выбран в этом пространстве.',row_outside_period:'Дата привлечения заявки находится вне выбранного периода.',acquisition_date_required:'Для полной когорты заполните acquired_on в каждой строке.',conflicting_or_stale_update:'Обновление устарело или меняет исходные данные заявки. Проверьте даты и постоянный ID.',cohort_period_not_closed:'Период должен закончиться до сегодняшнего дня.',cohort_period_required:'Укажите обе границы периода.',csv_size:'Файл должен быть не больше 48 КБ.',csv_rows:'Проверьте число столбцов и ограничение в 500 строк.',external_id_uuid:'Используйте UUID в качестве ID заявки.',account_format:'Аккаунт указывается как acc_123.',currency_rub:'Для сумм укажите валюту RUB.',refund_amount:'Возврат не может превышать сумму заказа.',date_format:'Используйте существующие даты в формате ГГГГ-ММ-ДД.',amount_format:'Сумма должна быть неотрицательной, с точкой и не более двух знаков после неё.'};
async function importError(response:Response){try{const body=await response.json();return importErrors[body?.error?.reason]??'Проверьте формат файла, даты и аккаунты. Изменения не приняты.';}catch{return 'Не удалось проверить файл. Повторите запрос.';}}

function useMutation(path:string,returnTo:string){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const attempt=useRef<{payload:string;key:string}|null>(null);
 async function submit(body:Record<string,unknown>,idempotent=false){
  if(busy)return;setBusy(true);setError('');
  const payload=JSON.stringify(body);
  if(attempt.current?.payload!==payload)attempt.current={payload,key:crypto.randomUUID()};
  try{
   const response=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,...(idempotent?{idempotency_key:attempt.current.key}:{})})});
   if(response.status===400&&path.includes('lead-import'))throw new Error(await importError(response));
   if(!response.ok)throw new Error(response.status===409?'Данные изменились. Обновите страницу и проверьте актуальную версию.':response.status===403?'Для этого действия недостаточно прав.':response.status===400?'Проверьте поля и формат данных. Изменения не приняты.':response.status===503?'Функция временно недоступна. Изменение не подтверждено.':'Запрос не завершён. Повторите его или проверьте состояние кабинета.');
   const result:unknown=await response.json();if(!result||typeof result!=='object')throw new Error('Ответ сервера требует проверки.');
   {const target=new URL(returnTo,window.location.href);
   // Тот же адрес с якорем не перезагружает страницу: данные нужно получить заново, чтобы увидеть сохранённое.
   if(target.pathname+target.search===window.location.pathname+window.location.search){window.location.hash=target.hash;window.location.reload();}else window.location.replace(target.href);}
  }catch(e){setError(e instanceof Error?e.message:'Запрос не завершён.');setBusy(false);}
 }
 return {busy,error,submit};
}

export function BudgetForm({workspace,period}:{workspace:string;period:{from:string;to:string}}){
 const mutation=useMutation(`/workspaces/${workspace}/budget-plan`,`/workspace/analysis?workspace=${workspace}#insights`);
 function save(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);void mutation.submit({period_from:data.get('from'),period_to:data.get('to'),amount:String(data.get('amount')).replace(',','.')});}
 return <form onSubmit={save} className="workspace-form"><label>Начало периода<input name="from" type="date" required defaultValue={period.from}/></label><label>Конец периода<input name="to" type="date" required defaultValue={period.to}/></label><label>План расходов, ₽<input name="amount" inputMode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" required placeholder="Сумма на весь период" maxLength={15}/></label><p>План не меняет рекламные бюджеты. Сравнение доступно только с сопоставимыми данными за тот же период.</p><button className="ref-button ref-primary" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Сохранить план'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>;
}

const csvHeader='external_id,created_on,status,updated_on,direct_account_id,acquired_on,campaign_id,amount,currency,refund_amount\n';
export function LeadImportForm({workspace,period,accounts}:{workspace:string;period:{from:string;to:string};accounts:string[]}){
 const path=`/workspaces/${workspace}/lead-import`;
 const mutation=useMutation(path,`/workspace/analysis?workspace=${workspace}#lead-quality`);
 const [localError,setLocalError]=useState(''),[busy,setBusy]=useState(false);
 const [preview,setPreview]=useState<{payload:Record<string,unknown>;rows:number;counts:Record<string,number>}|null>(null);
 function template(){const url=URL.createObjectURL(new Blob([csvHeader],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='inrou-leads-template.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function upload(event:FormEvent<HTMLFormElement>){
  event.preventDefault();if(busy)return;setLocalError('');setPreview(null);
  const data=new FormData(event.currentTarget),file=data.get('file');
  if(!(file instanceof File)||!file.size||file.size>48000){setLocalError('Выберите непустой CSV размером до 48 КБ.');return;}
  setBusy(true);
  try{
   const payload={csv:await file.text(),period_from:data.get('from'),period_to:data.get('to'),cohort_complete:data.get('complete')==='on'};
   const response=await fetch('/api'+path+'/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   if(!response.ok)throw new Error(response.status===400?await importError(response):'Не удалось проверить файл. Проверьте доступ и повторите.');
   const result=await response.json();
   if(result.status!=='preview'||!Number.isSafeInteger(result.accepted_rows)||result.accepted_rows<1||result.accepted_rows>500||!result.counts||typeof result.counts!=='object'||!Object.values(result.counts).every(n=>Number.isSafeInteger(n)&&Number(n)>=0))throw new Error('Ответ проверки требует уточнения.');
   setPreview({payload,rows:result.accepted_rows,counts:result.counts});
  }catch(error){setLocalError(error instanceof Error?error.message:'Не удалось проверить файл.');}finally{setBusy(false);}
 }
 return <form onSubmit={upload} onChange={()=>{setPreview(null);setLocalError('');}} className="workspace-form"><p>Загружайте только ID, даты, статусы и суммы. Имена, телефоны, email и комментарии не принимаются. UUID должен оставаться одинаковым при обновлении заявки.</p><button type="button" className="ref-button" onClick={template}>Скачать пустой CSV-шаблон</button><p>Аккаунты пространства: {accounts.length?accounts.join(', '):'Не подключены'}. Статусы: new, qualified, rejected, won, lost, refunded.</p><p>Для qCPL квалифицированными считаются qualified, won, lost и refunded: проигрыш сделки или возврат не отменяет первоначальную квалификацию. Источник кампании задан в импортируемом файле; это ручное сопоставление.</p><label>CSV-файл<input name="file" type="file" accept=".csv,text/csv" required disabled={busy||mutation.busy}/></label><label>Когорта: с<input name="from" type="date" defaultValue={period.from} required disabled={busy||mutation.busy}/></label><label>По<input name="to" type="date" defaultValue={period.to} required disabled={busy||mutation.busy}/></label><label className="workspace-checkbox"><input name="complete" type="checkbox" disabled={busy||mutation.busy}/>Подтверждаю полноту когорты за период привлечения и аккаунты из файла. Это моя оценка; полнота CRM сервисом не проверяется.</label><p>acquired_on — дата привлечения. qCPL рассчитывается по расходу аккаунтов из файла за тот же период; он не подтверждает атрибуцию каждого лида.</p><button className="ref-button" disabled={busy||mutation.busy}>{busy?'Проверяем…':'Предпросмотр импорта'}</button>{preview&&<section role="status"><h3>Проверка пройдена: {preview.rows} строк</h3><ul>{Object.entries(preview.counts).map(([status,count])=><li key={status}>{status}: {count}</li>)}</ul><p>Данные ещё не сохранены. Повторный импорт обновит заявки с тем же UUID. Перед записью сервер повторит проверку.</p><button type="button" className="ref-button ref-primary" disabled={mutation.busy} onClick={()=>void mutation.submit(preview.payload)}>{mutation.busy?'Импортируем…':'Подтвердить импорт'}</button></section>}{(localError||mutation.error)&&<p role="alert">{localError||mutation.error}</p>}</form>;
}

export function DecisionForm({workspace,rec,version,state,allowed}:{workspace:string;rec:string;version:string;state:string;allowed:string[]}){
 const mutation=useMutation(`/workspaces/${workspace}/recommendations/${rec}/decisions`,`/workspace/recommendations?workspace=${workspace}&rec=${rec}`);
 const [action,setAction]=useState(allowed.includes('check')?'check':allowed.includes('postpone')?'postpone':'reject');
 function save(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);void mutation.submit({action,expected_version_id:version,expected_state_version:state,...(action==='postpone'?{until:data.get('until')}:action==='reject'?{reason:data.get('reason')}:{})},true);}
 const choices=[['check','Проверил, изменение не требуется'],['postpone','Вернуться позже'],['reject','Отклонить рекомендацию']].filter(([key])=>allowed.includes(key));
 return <>{choices.length>0&&<form onSubmit={save} className="workspace-form"><label>Решение<select value={action} onChange={e=>setAction(e.target.value)}>{choices.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>{action==='reject'&&<label>Причина<select name="reason" required><option value="wrong_data">Некорректные данные</option><option value="irrelevant_rule">Правило не подходит</option><option value="not_enough_context">Недостаточно контекста</option><option value="too_risky">Слишком высокий риск</option></select></label>}{action==='postpone'&&<label>Вернуться к рекомендации<input name="until" type="date" required/></label>}<button className="ref-button ref-primary" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Сохранить решение'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>}{allowed.includes('mark_done_manually')&&<ManualForm workspace={workspace} rec={rec} version={version} state={state}/>}</>;
}
function ManualForm({workspace,rec,version,state}:{workspace:string;rec:string;version:string;state:string}){
 const mutation=useMutation(`/workspaces/${workspace}/recommendations/${rec}/manual-execution`,`/workspace/recommendations?workspace=${workspace}&rec=${rec}`);
 return <form className="workspace-form" onSubmit={e=>{e.preventDefault();void mutation.submit({expected_version_id:version,expected_state_version:state},true);}}><label className="workspace-checkbox"><input type="checkbox" required/>Подтверждаю, что самостоятельно внёс изменение в Директе. Эта отметка не подтверждает сверку или экономию.</label><button className="ref-button" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Отметить ручное выполнение'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>;
}

export function VerificationForm({workspace,rec,version,state,returnTo}:{workspace:string;rec:string;version:string;state:string;returnTo:string}){
 const mutation=useMutation(`/workspaces/${workspace}/recommendations/${rec}/verification`,returnTo);
 return <form className="workspace-form" onSubmit={e=>{e.preventDefault();void mutation.submit({expected_version_id:version,expected_state_version:state},true);}}><p>Сервис прочитает исключения площадок в Директе. Сверка показывает состояние на момент чтения; она не доказывает автора изменения или экономию.</p><button className="ix-btn" disabled={mutation.busy}>{mutation.busy?'Ставим сверку в очередь…':'Проверить исключения в Директе'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>;
}
