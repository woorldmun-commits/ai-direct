'use client';
import {useState,type FormEvent} from 'react';
import {PricingPlans} from '@/components/midnight/pricing-plans';

export function DemoAgency() {
  const [clients,setClients]=useState(['Основное пространство','Клиент · Магазин']),[name,setName]=useState(''),[selected,setSelected]=useState(0);
  function add(e:FormEvent<HTMLFormElement>){e.preventDefault();const text=name.trim();if(!text||clients.length>=5)return;setClients([...clients,text]);setName('');}
  return <><section className="ix-card" aria-label="Демонстрация агентского пакета"><span className="ix-eyebrow">АГЕНТСТВО · СИНТЕТИЧЕСКИЙ ПРИМЕР</span><h2>Клиенты отдельно. Подписка общая.</h2><p>Создайте до 5 демонстрационных пространств, включая основное, и переключайтесь между ними. Данные и права настоящих клиентов не используются.</p>
    <div className="ix-actions" role="group" aria-label="Демонстрационные клиенты">{clients.map((client,i)=><button key={i} type="button" className="ix-btn" aria-pressed={selected===i} onClick={()=>setSelected(i)}>{client}</button>)}</div>
    <div className="ix-card" style={{marginBlock:18}} aria-live="polite"><h3>{clients[selected]}</h3><p>{selected===0?'Основное пространство оплачивает пакет.':'У этого клиента — отдельная организация и свои участники.'}</p><p className="ix-muted ix-mini">Пространств: {clients.length} / 5 · лимит аккаунтов: 15 суммарно. Приглашения участников в рабочем сервисе — через оператора.</p></div>
    <form onSubmit={add} className="workspace-form"><label>Название демоклиента<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} required disabled={clients.length>=5}/></label><button className="ix-btn ix-btn--primary" disabled={clients.length>=5}>{clients.length>=5?'Лимит 5 пространств достигнут':'Добавить демоклиента'}</button></form><p className="ix-muted ix-mini">Изменения только в памяти страницы. При перезагрузке пример сбрасывается; подписка и платёж не создаются.</p>
  </section><PricingPlans/></>;
}
