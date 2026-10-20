'use client';
import {createContext,useCallback,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {applyRecommendation,initialState,recs,scoped,restoreState,type DemoState} from './model';
type Context = {state:DemoState;setState:React.Dispatch<React.SetStateAction<DemoState>>;days:number;setDays:(v:number)=>void;account:string;setAccount:(v:string)=>void;rows:ReturnType<typeof scoped>;toast:string;notify:(s:string)=>void;log:(title:string,detail:string,type:string)=>void;apply:(id:number)=>void};
const DemoContext=createContext<Context|null>(null);
const storage='adpilot-reference-v2';
export function ReferenceProvider({children}:{children:ReactNode}) {
 const [state,setReactState]=useState(initialState),[days,setDays]=useState(31),[account,setAccount]=useState('Все аккаунты'),[toast,setToast]=useState('');
 const stateRef=useRef(state),storageFailed=useRef(false);
 const setState=useCallback<React.Dispatch<React.SetStateAction<DemoState>>>(update=>{
  let current=stateRef.current;
  if(!storageFailed.current)try{current=restoreState(JSON.parse(localStorage.getItem(storage)||'null'));}catch{}
  const next=typeof update==='function'?update(current):update;
  stateRef.current=next;
  // shortcut: localStorage has no cross-tab transaction; use a server for simultaneous collaborative edits.
  try{localStorage.setItem(storage,JSON.stringify(next));storageFailed.current=false;}catch{storageFailed.current=true;setToast('Сохранение в браузере недоступно. Изменения действуют до перезагрузки.');}
  setReactState(next);
 },[]);
 useEffect(()=>{
  const restore=()=>{try{const next=restoreState(JSON.parse(localStorage.getItem(storage)||'null'));stateRef.current=next;setReactState(next);}catch{}};
  const receive=(event:StorageEvent)=>{if(event.key===storage||event.key===null)restore();};
  const timer=setTimeout(restore,0);window.addEventListener('storage',receive);
  return()=>{clearTimeout(timer);window.removeEventListener('storage',receive);};
 },[]);
 useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),4500);return()=>clearTimeout(timer);},[toast]);
 const log=(title:string,detail:string,type:string)=>setState(s=>({...s,events:[{id:crypto.randomUUID(),title,detail,date:new Date().toISOString(),type},...s.events]}));
 const apply=(id:number)=>{setState(s=>{const next=applyRecommendation(s,id);if(next===s)return s;return {...next,events:[{id:crypto.randomUUID(),title:'Применена рекомендация',detail:recs.find(r=>r.id===id)!.title,date:new Date().toISOString(),type:'Рекомендации'},...s.events]};});setToast('Рекомендация применена в демо. История обновлена.');};
 return <DemoContext.Provider value={{state,setState,days,setDays,account,setAccount,rows:scoped(state.campaigns,days,account),toast,notify:setToast,log,apply}}>{children}</DemoContext.Provider>;
}
export function useReference(){const value=useContext(DemoContext);if(!value)throw new Error('ReferenceProvider required');return value;}
