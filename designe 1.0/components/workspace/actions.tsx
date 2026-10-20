'use client';
import {useRef,useState,type FormEvent} from 'react';

function useMutation(path:string,returnTo:string){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const attempt=useRef<{payload:string;key:string}|null>(null);
 async function submit(body:Record<string,unknown>,idempotent=false){
  if(busy)return;setBusy(true);setError('');
  const payload=JSON.stringify(body);
  if(attempt.current?.payload!==payload)attempt.current={payload,key:crypto.randomUUID()};
  try{
   const response=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,...(idempotent?{idempotency_key:attempt.current.key}:{})})});
   if(!response.ok)throw new Error(response.status===409?'Данные изменились. Обновите страницу и проверьте актуальную версию.':response.status===403?'Для этого действия недостаточно прав.':response.status===400?'Проверьте поля и формат данных. Изменения не приняты.':response.status===503?'Функция временно недоступна. Изменение не подтверждено.':'Запрос не завершён. Повторите его или проверьте состояние кабинета.');
   const result:unknown=await response.json();if(!result||typeof result!=='object')throw new Error('Ответ сервера требует проверки.');
   window.history.replaceState(null,'',returnTo);
   window.location.reload();
  }catch(e){setError(e instanceof Error?e.message:'Запрос не завершён.');setBusy(false);}
 }
 return {busy,error,submit};
}

export function BudgetForm({workspace,period}:{workspace:string;period:{from:string;to:string}}){
 const mutation=useMutation(`/workspaces/${workspace}/budget-plan`,`/workspace?workspace=${workspace}#insights`);
 function save(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);void mutation.submit({period_from:data.get('from'),period_to:data.get('to'),amount:String(data.get('amount')).replace(',','.')});}
 return <form onSubmit={save} className="workspace-form"><label>Начало периода<input name="from" type="date" required defaultValue={period.from}/></label><label>Конец периода<input name="to" type="date" required defaultValue={period.to}/></label><label>План расходов, ₽<input name="amount" inputMode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" required placeholder="Сумма на весь период" maxLength={15}/></label><p>План не меняет рекламные бюджеты. Сравнение доступно только с сопоставимыми данными за тот же период.</p><button className="ref-button ref-primary" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Сохранить план'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>;
}

const csvHeader='external_id,created_on,status,updated_on,direct_account_id,acquired_on,campaign_id,amount,currency,refund_amount\n';
export function LeadImportForm({workspace,period,accounts}:{workspace:string;period:{from:string;to:string};accounts:string[]}){
 const mutation=useMutation(`/workspaces/${workspace}/lead-import`,`/workspace?workspace=${workspace}#lead-quality`),[localError,setLocalError]=useState('');
 function template(){const url=URL.createObjectURL(new Blob([csvHeader],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='rekvero-leads-template.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function upload(event:FormEvent<HTMLFormElement>){event.preventDefault();setLocalError('');const data=new FormData(event.currentTarget),file=data.get('file');if(!(file instanceof File)||!file.size||file.size>48000){setLocalError('Выберите непустой CSV размером до 48 КБ.');return;}const csv=await file.text();void mutation.submit({csv,period_from:data.get('from'),period_to:data.get('to'),cohort_complete:data.get('complete')==='on'});}
 return <form onSubmit={upload} className="workspace-form"><p>Загружайте только ID, даты, статусы и суммы. Имена, телефоны, email и комментарии менеджеров не принимаются. UUID заявки должен оставаться одинаковым при обновлении статуса.</p><button type="button" className="ref-button" onClick={template}>Скачать пустой CSV-шаблон</button><p>Аккаунты этого пространства: {accounts.length?accounts.join(', '):'Не подключены'}. Статусы: new, qualified, rejected, won, lost, refunded. Дата привлечения acquired_on нужна для сопоставимой когорты qCPL.</p><label>CSV-файл<input name="file" type="file" accept=".csv,text/csv" required/></label><label>Когорта: с<input name="from" type="date" defaultValue={period.from} required/></label><label>По<input name="to" type="date" defaultValue={period.to} required/></label><label className="workspace-checkbox"><input name="complete" type="checkbox"/>Подтверждаю: файл содержит полную когорту заявок за указанный период привлечения и аккаунты из файла. Это моя оценка полноты, а не проверка CRM сервисом.</label><p>При недостаточных или несопоставимых данных qCPL останется недоступным. Повторный импорт обновляет ту же заявку, а не создаёт дубль.</p><button className="ref-button ref-primary" disabled={mutation.busy}>{mutation.busy?'Проверяем и импортируем…':'Проверить и импортировать'}</button>{(localError||mutation.error)&&<p role="alert">{localError||mutation.error}</p>}</form>;
}

export function DecisionForm({workspace,rec,version,state,allowed}:{workspace:string;rec:string;version:string;state:string;allowed:string[]}){
 const mutation=useMutation(`/workspaces/${workspace}/recommendations/${rec}/decisions`,`/workspace/recommendations/${rec}?workspace=${workspace}`);
 const [action,setAction]=useState(allowed.includes('check')?'check':allowed.includes('postpone')?'postpone':'reject');
 function save(event:FormEvent<HTMLFormElement>){event.preventDefault();const data=new FormData(event.currentTarget);void mutation.submit({action,expected_version_id:version,expected_state_version:state,...(action==='postpone'?{until:data.get('until')}:action==='reject'?{reason:data.get('reason')}:{})},true);}
 const choices=[['check','Проверил, изменение не требуется'],['postpone','Вернуться позже'],['reject','Отклонить рекомендацию']].filter(([key])=>allowed.includes(key));
 return <>{choices.length>0&&<form onSubmit={save} className="workspace-form"><label>Решение<select value={action} onChange={e=>setAction(e.target.value)}>{choices.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>{action==='reject'&&<label>Причина<select name="reason" required><option value="wrong_data">Некорректные данные</option><option value="irrelevant_rule">Правило не подходит</option><option value="not_enough_context">Недостаточно контекста</option><option value="too_risky">Слишком высокий риск</option></select></label>}{action==='postpone'&&<label>Вернуться к рекомендации<input name="until" type="date" required/></label>}<button className="ref-button ref-primary" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Сохранить решение'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>}{allowed.includes('mark_done_manually')&&<ManualForm workspace={workspace} rec={rec} version={version} state={state}/>}</>;
}
function ManualForm({workspace,rec,version,state}:{workspace:string;rec:string;version:string;state:string}){
 const mutation=useMutation(`/workspaces/${workspace}/recommendations/${rec}/manual-execution`,`/workspace/recommendations/${rec}?workspace=${workspace}`);
 return <form className="workspace-form" onSubmit={e=>{e.preventDefault();void mutation.submit({expected_version_id:version,expected_state_version:state},true);}}><label className="workspace-checkbox"><input type="checkbox" required/>Подтверждаю, что самостоятельно внёс изменение в Директе. Эта отметка не подтверждает сверку или экономию.</label><button className="ref-button" disabled={mutation.busy}>{mutation.busy?'Сохраняем…':'Отметить ручное выполнение'}</button>{mutation.error&&<p role="alert">{mutation.error}</p>}</form>;
}
