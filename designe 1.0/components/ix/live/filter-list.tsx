'use client';
import {useRouter} from 'next/navigation';
import {useRef,useState, type ReactNode} from 'react';
import {Drawer} from '../drawer';
import {useIxSearch} from '../shell';
import type {Value} from '@/lib/value';

/** Список, который фильтруется строкой поиска из верхней панели. `text` — то, по чему ищем. */
export function FilterList({items, empty = 'По запросу ничего не найдено.'}: {items: {key: string; text: string; node: ReactNode;kind?:string;exposure?:Value;computedAt?:string}[]; empty?: string}) {
  const q = useIxSearch();
  const [kind,setKind]=useState('all'),[sort,setSort]=useState('priority');
  const kinds=[['all','Все'],['change','Изменения вручную'],['review','Проверки'],['inspect_only','Наблюдения']];
  const hasKinds=items.some(i=>i.kind!==undefined);
  const priority=(s:string|undefined)=>s==='change'?0:s==='review'?1:2;
  const amount=(s:string|null|undefined)=>s&&/^\d+(\.\d{1,2})?$/.test(s)?BigInt(s.split('.')[0])*BigInt(100)+BigInt((s.split('.')[1]??'').padEnd(2,'0')):BigInt(-1);
  const shown=items.filter(i=>(!q||i.text.toLowerCase().includes(q))&&(kind==='all'||i.kind===kind)).sort((a,b)=>{
    if(sort==='exposure'){const av=amount(a.exposure?.amount),bv=amount(b.exposure?.amount);return av===bv?0:av>bv?-1:1;}
    if(sort==='recent')return String(b.computedAt??'').localeCompare(a.computedAt??'');
    return priority(a.kind)-priority(b.kind);
  });
  return <>{hasKinds&&<><div className="ix-actions" role="group" aria-label="Тип рекомендаций">{kinds.map(([id,label])=><button key={id} className={'ix-btn'+(kind===id?' ix-btn--primary':'')} type="button" aria-pressed={kind===id} onClick={()=>setKind(id)}>{label} · {items.filter(i=>id==='all'||i.kind===id).length}</button>)}<label className="ix-mini">Порядок <select className="ix-field" aria-label="Порядок рекомендаций" value={sort} onChange={e=>setSort(e.target.value)}><option value="priority">Сначала изменения</option>{items.some(i=>i.exposure)&&<option value="exposure">По затронутым расходам</option>}<option value="recent">По свежести оснований</option></select></label></div><p className="ix-muted ix-mini">Фильтр и порядок относятся к загруженной странице. Затронутые расходы не означают экономию; суммы карточек могут пересекаться.</p></>}{shown.length?shown.map(i=><div key={i.key}>{i.node}</div>):<p className="ix-muted">{empty}</p>}</>;
}

/** Паспорт рекомендации в правой панели; закрытие возвращает на список с сохранением пространства. */
export function PassportDrawer({title, closeHref, children}: {title: string; closeHref: string; children: ReactNode}) {
  const router = useRouter();
  const done = useRef(false);
  const close = () => { if (done.current) return; done.current = true; router.replace(closeHref, {scroll: false}); };
  return <Drawer title={title} onClose={close}>{children}</Drawer>;
}
