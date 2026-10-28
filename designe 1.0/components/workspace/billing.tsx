'use client';
import {useEffect,useRef,useState,type FormEvent} from 'react';
import {checkoutUrl,isCheckoutAttempt,type BillingCatalog,type CheckoutAttempt} from '@/lib/billing-contract';

export function BillingCheckout({workspace,catalog,paid,recovered}:{workspace:string;catalog:BillingCatalog;paid:boolean;recovered:CheckoutAttempt|null}) {
 const [sku,setSku]=useState(catalog.items[0].id),[attempt,setAttempt]=useState<CheckoutAttempt|null>(recovered),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const active=useRef(false),key='inrou.checkout.'+workspace;
 useEffect(()=>{try{const value:unknown=JSON.parse(sessionStorage.getItem(key)??'null');
  // eslint-disable-next-line react-hooks/set-state-in-effect -- Restore the non-secret payment operation after browser hydration.
  setAttempt(recovered??(isCheckoutAttempt(value)?value:null));
 }catch{/* Storage may be disabled. A new payment must not begin without saving its operation ID. */}},[key,recovered]);
 function remember(value:CheckoutAttempt){sessionStorage.setItem(key,JSON.stringify(value));setAttempt(value);}
 async function post(path:string,body:Record<string,unknown>={}){
  const response=await fetch(`/api/workspaces/${workspace}/billing/orders${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  if(!response.ok){
   if(response.status===409){const problem=await response.json().catch(()=>null);
    if(problem?.error?.code==='billing_terms_changed'&&!path){sessionStorage.removeItem(key);setAttempt(null);throw new Error('Условия оплаты изменились. Обновите страницу, прочитайте и примите актуальную оферту. Заказ не создан.');}
    if(problem?.error?.code==='billing_order_pending'){window.location.reload();throw new Error('Восстанавливаем существующий заказ.');}
   }
   throw new Error(response.status===409?'Оплата требует проверки оператором. Не создавайте новый платёж.':response.status===403?'Оплата доступна владельцу и администратору.':response.status===503?'Платёжный сервис пока недоступен. Сохранённую операцию можно проверить повторно.':'Запрос не завершён. Повторите проверку сохранённой операции.');
  }
  const value:unknown=await response.json();if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Не удалось проверить ответ сервера.');return value as Record<string,unknown>;
 }
 async function run(refresh=false){
  if(active.current)return;active.current=true;setBusy(true);setError('');setMessage('');
  try{
   let current=attempt;
   if(!current){if(!catalog.terms_sha256)throw new Error('Условия оплаты ещё не утверждены.');current={request_id:crypto.randomUUID(),sku,terms_sha256:catalog.terms_sha256};remember(current);}
   if(!current.id){const order=await post('',current);const next={...current,id:order.id};if(!isCheckoutAttempt(next)||order.sku!==current.sku)throw new Error('Ответ операции требует проверки.');current=next;remember(current);}
   const result=await post(`/${current.id}/${refresh?'refresh':'checkout'}`);
   if(result.status==='succeeded'){sessionStorage.removeItem(key);window.location.reload();return;}
   if(result.status==='canceled'){sessionStorage.removeItem(key);setAttempt(null);setMessage('Платёж отменён. Подписка не оформлена.');return;}
   if(result.status==='review_required')throw new Error('Этот платёж требует сверки оператором. Не создавайте новый платёж и сохраните идентификатор заказа: '+current.id);
   const url=checkoutUrl(result.confirmation_url);
   if(!refresh&&url){window.location.assign(url);return;}
   setMessage('Оплата ещё не подтверждена. После завершения на странице ЮKassa нажмите «Проверить оплату». Если деньги списаны, не создавайте новый платёж.');
  }catch(e){setError(e instanceof Error?e.message:'Не удалось проверить оплату.');}finally{active.current=false;setBusy(false);}
 }
 function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();void run();}
 return <section className="ix-card"><h2>Оплата подписки</h2><p>30 дней доступа и 3 дня на продление. Без автосписаний. Тариф действует на одно рабочее пространство.</p>
  {catalog.test&&<p role="status">Тестовый режим ЮKassa: реальная оплата не принимается.</p>}
  {!catalog.checkout_enabled?<p role="status">Приём платежей откроется после настройки провайдера и утверждения документов.</p>:paid&&!attempt?<p>Действует оплаченный доступ. Досрочное продление и смена тарифа пока недоступны.</p>:<form onSubmit={submit} className="workspace-form">
   {!attempt&&<><label>Тариф<select value={sku} onChange={e=>setSku(e.target.value as typeof sku)} disabled={busy}>{catalog.items.map(p=><option key={p.id} value={p.id}>{p.name} · {p.amount_minor/100} ₽ · аккаунтов: {p.accounts}</option>)}</select></label><label className="workspace-checkbox"><input type="checkbox" required disabled={busy}/>Принимаю <a href="/legal/offer" target="_blank" rel="noreferrer">оферту</a> и условия выбранного тарифа. Оплата разовая.</label></>}
   <button className="ix-btn ix-btn--primary" disabled={busy}>{busy?'Проверяем…':attempt?'Продолжить сохранённую оплату':'Перейти к оплате в ЮKassa'}</button>
   {attempt&&<button className="ix-btn" type="button" disabled={busy} onClick={()=>void run(true)}>Проверить оплату</button>}
   {attempt&&<p className="ix-muted ix-mini">Заказ сохраняется сервером и восстанавливается при открытии тарифов. Повтор использует тот же идентификатор. Статус доступа подтверждает сервер после сверки с провайдером.</p>}
  </form>}{error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}</section>;
}
