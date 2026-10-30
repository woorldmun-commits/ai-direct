'use client';
import {useRef,useState,type FormEvent} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import type {AgencyClients} from '@/lib/agency-contract';
export function AgencyClientPanel({workspace,data,enabled}:{workspace:string;data:AgencyClients;enabled:boolean}) {
  const router=useRouter(),operation=useRef<string|null>(null),active=useRef(false);
  const [busy,setBusy]=useState(false),[problem,setProblem]=useState('');
  async function submit(e:FormEvent<HTMLFormElement>){
    e.preventDefault();if(active.current)return;active.current=true;setBusy(true);setProblem('');
    const name=String(new FormData(e.currentTarget).get('name')??'').trim();
    try{
      operation.current??=crypto.randomUUID();
      const response=await fetch(`/api/workspaces/${workspace}/billing/clients`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,request_id:operation.current}),signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw new Error(response.status===409?'Нужен действующий тариф «Агентство». В пакете не больше 5 пространств, включая основное.':response.status===403?'Создание доступно владельцу основного пространства.':'Запрос не завершён. Повторите с тем же названием — повтор не создаст дубль.');
      operation.current=null;router.refresh();
    }catch(e){setProblem(e instanceof Error?e.message:'Не удалось создать пространство.');}finally{active.current=false;setBusy(false);}
  }
  if(data.managed)return <section className="ix-card"><h2>Подписка агентства</h2><p>Доступ этого клиента оплачивается в основном пространстве агентства. Клиентские данные и участники остаются в отдельной организации.</p></section>;
  return <section className="ix-card" aria-label="Клиенты агентства"><h2>Клиентские пространства</h2><p>До 5 пространств, включая основное, и до 15 аккаунтов Директа суммарно. У каждого клиента — отдельная организация и свои доступы.</p>
    <ul>{data.items.map(client=><li key={client.id}><Link href={`/workspace/overview?workspace=${client.id}`}>{client.name}</Link>{client.id===workspace?' · основное':''}{client.status!=='active'?' · приостановлено':''}</li>)}</ul>
    {enabled&&data.items.length<5?<form onSubmit={submit} className="workspace-form"><label>Название клиента<input name="name" required minLength={1} maxLength={120} disabled={busy}/></label><button className="ix-btn ix-btn--primary" disabled={busy}>{busy?'Создаём…':'Создать отдельное пространство'}</button></form>:<p className="ix-muted">{data.items.length>=5?'Лимит пространств пакета достигнут.':'Создание доступно владельцу после активации тарифа «Агентство».'}</p>}
    <p className="ix-muted ix-mini">Создание не переносит участников из основного пространства. Приглашения клиентов и сотрудников пока оформляет оператор. При завершении подписки новый анализ в клиентских пространствах останавливается.</p>{problem&&<p role="alert">{problem}</p>}
  </section>;
}
