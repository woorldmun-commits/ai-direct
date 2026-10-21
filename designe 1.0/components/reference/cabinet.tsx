'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Layers,Activity,ArrowLeft,ArrowUpRight,ArrowRight,Bell,Bot,ChartColumnIncreasing,ClipboardClock,FolderClosed,CalendarDays,ChevronDown,Flame,LayoutGrid,Menu,Search,Settings,ShieldCheck,Sparkles,SquareChartGantt,X} from 'lucide-react';
import {ThemeControl} from '../theme-control';
import {ReferenceLogo,ReferencePortrait,PlatformBadge,ReferenceModal} from './shared';
import {ReferenceChart,MiniChart,chartMetrics} from './chart';
import {ReferenceProvider,useReference} from './state';
import {colors,num,platforms,recs,rub,signals,sum,seriesFor,comparisonFor,recommendationsFor} from './model';
import './adpilot.css';
import './reference-fidelity-v2.css';
import './reference-panels.css';
export {RecommendationsScreen,CampaignsScreen} from './optimization';
export {EffectScreen,ReportsScreen,PricingScreen} from './results';
export {ConnectionsScreen,HistoryScreen,TeamScreen,SettingsScreen,SignalsScreen,AnalystScreen} from './workspace';
export const navigation=[
 {href:'/demo',label:'Анализ',icon:ChartColumnIncreasing},
 {href:'/demo/recommendations',label:'Рекомендации',icon:FolderClosed},
 {href:'/demo/campaigns',label:'Кампании',icon:SquareChartGantt},
 {href:'/demo/integrations',label:'Подключения',icon:LayoutGrid},
 {href:'/demo/changes',label:'Эффект',icon:Activity},
 {href:'/demo/reports',label:'Отчёты',icon:SquareChartGantt},
 {href:'/demo/signals',label:'Сигналы',icon:Bell},
 {href:'/demo/analyst',label:'AI-аналитик',icon:Bot},
 {href:'/demo/history',label:'История',icon:ClipboardClock},
 {href:'/demo/team',label:'Команда',icon:Layers},
 {href:'/demo/pricing',label:'Тарифы',icon:CalendarDays},
 {href:'/demo/settings',label:'Настройки',icon:Settings},
];
export function ReferenceCabinet({children}:{children:ReactNode}){return <ReferenceProvider><Cabinet>{children}</Cabinet></ReferenceProvider>;}
function Cabinet({children}:{children:ReactNode}){
 const pathname=usePathname(),{state,days,setDays,toast}=useReference();
 const [menu,setMenu]=useState(false),[search,setSearch]=useState(''),[searchOpen,setSearchOpen]=useState(false),[notifications,setNotifications]=useState(false);
 const closeRef=useRef<HTMLButtonElement>(null),menuRef=useRef<HTMLDivElement>(null);
 const menuButtonRef=useRef<HTMLButtonElement>(null);
 useEffect(()=>{if(!menu)return;closeRef.current?.focus();const restoreFocus=menuButtonRef.current,overflow=document.body.style.overflow;document.body.style.overflow='hidden';const handler=(e:KeyboardEvent)=>{if(e.key==='Escape'){setMenu(false);menuButtonRef.current?.focus();}if(e.key==='Tab'){const items=Array.from(menuRef.current?.querySelectorAll<HTMLElement>('a,button,summary')??[]).filter(item=>item.getClientRects().length>0&&(!item.closest('details:not([open])')||item.tagName==='SUMMARY'));if(!items?.length)return;const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};window.addEventListener('keydown',handler);return()=>{document.body.style.overflow=overflow;window.removeEventListener('keydown',handler);if(window.matchMedia('(max-width:767px)').matches)restoreFocus?.focus();};},[menu]);
 useEffect(()=>{const media=window.matchMedia('(max-width:767px)');const closeOnDesktop=()=>{if(!media.matches){setMenu(false);document.getElementById('main-content')?.focus();}};media.addEventListener('change',closeOnDesktop);return()=>media.removeEventListener('change',closeOnDesktop);},[]);
 const unread=signals.filter(s=>!state.readSignals.includes(s.id)).length;
 const matches=navigation.filter(n=>n.label.toLowerCase().includes(search.trim().toLowerCase()));
 const campaignMatches=state.campaigns.filter(c=>(c.name+' '+c.platform).toLowerCase().includes(search.trim().toLowerCase()));
 const recMatches=recs.filter(r=>(r.title+' '+r.description).toLowerCase().includes(search.trim().toLowerCase()));
 const sourceNames=platforms.slice(0,4).concat('Яндекс Метрика'),connectedSources=sourceNames.filter(p=>state.connections.includes(p)).length;
 return <div className="ref-ui ap-app ap-cabinet">
 <a className="ap-skip-link" href="#main-content">Перейти к содержимому</a>
 {menu&&<button className="ap-menu-overlay" aria-label="Закрыть меню" aria-hidden="true" tabIndex={-1} onClick={()=>{setMenu(false);menuButtonRef.current?.focus();}}/>}
 <aside id="cabinet-menu" ref={menuRef} className={'ap-sidebar '+(menu?'is-open':'')} role={menu?'dialog':undefined} aria-modal={menu?true:undefined} aria-label="Навигация"><div className="ap-sidebar-brand"><Link href="/" aria-label="inrou — главная"><ReferenceLogo/></Link><Link className="ap-sidebar-home" href="/" aria-label="На главную"><ArrowLeft size={13}/></Link><button className="ap-close-menu" ref={closeRef} aria-label="Закрыть навигацию" onClick={()=>{setMenu(false);menuButtonRef.current?.focus();}}><X size={18}/></button></div>
 <nav aria-label="Разделы кабинета">{navigation.map(({href,label,icon:Icon})=><Link href={href} key={href} title={label} onClick={()=>setMenu(false)} className={pathname===href?'is-active':''} aria-current={pathname===href?'page':undefined}><Icon size={18}/><span>{label}</span>{label==='Рекомендации'&&<b>{recs.length-state.applied.length}</b>}{label==='Сигналы'&&unread>0&&<b>{unread}</b>}</Link>)}</nav>
 <Link className="ap-health" href="/demo/integrations" onClick={()=>setMenu(false)}><span className={'ap-icon '+(connectedSources===sourceNames.length?'teal':'purple')}><ShieldCheck size={21}/></span><span><strong>Data Health</strong><small>{connectedSources} из {sourceNames.length} демоисточников</small><small>{connectedSources===sourceNames.length?'Источники добавлены':'Есть отключённые источники'}</small></span></Link>
 </aside>
 <div className="ap-workspace" inert={menu}><header className="ap-topbar"><button ref={menuButtonRef} className="ap-menu-button ap-icon-button" aria-label="Открыть меню" aria-expanded={menu} aria-controls="cabinet-menu" onClick={()=>setMenu(true)}><Menu size={21}/></button>
 <form className="ap-global-search" role="search" onSubmit={e=>{e.preventDefault();setSearchOpen(true);}}><Search size={17}/><input placeholder="Поиск по кампаниям, рекомендациям, данным…" aria-label="Поиск по кабинету" maxLength={120} value={search} onChange={e=>setSearch(e.target.value)}/><button type="submit" aria-label="Найти"><ArrowRight size={15}/></button></form>
 <label className="ap-date"><CalendarDays size={16}/><select aria-label="Период данных" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={31}>01 мар — 31 мар 2025</option><option value={7}>25 мар — 31 мар 2025</option><option value={1}>31 марта 2025</option></select></label>
 <button className="ap-icon-button ap-notifications" aria-label="Уведомления" onClick={()=>setNotifications(true)}><Bell size={19}/>{unread>0&&<i/>}</button>
 <ThemeControl/><Link href="/demo/settings" className="ap-profile" aria-label={'Настройки профиля: '+state.profile.name}><ReferencePortrait size={33}/><span>{state.profile.name}<small>Маркетолог</small></span><ChevronDown size={13}/></Link>
 </header><div className="mc-demo-notice"><ShieldCheck size={16}/><span>Демонстрационные данные. Действия изменяют только модель в этом браузере.</span><a href="/login">Войти со своими данными</a></div><main id="main-content" className="ap-content" key={pathname} tabIndex={-1}>{children}</main><footer className="ap-demo-footer"><span className="ap-live"/>Демонстрационный кабинет · март 2025 · модельные сравнения<Link href="/legal">Правовая информация</Link></footer></div>
 {toast&&<div className="ap-toast" role="status"><ShieldCheck size={18}/>{toast}</div>}
 {notifications&&<ReferenceModal title="Уведомления" onClose={()=>setNotifications(false)}><div className="ap-notice-list">{signals.map(s=><Link key={s.id} href="/demo/signals" onClick={()=>setNotifications(false)}><Bell size={18}/><span>{s.title}<small>{state.readSignals.includes(s.id)?'Прочитано':s.severity}</small></span><ArrowRight size={15}/></Link>)}</div></ReferenceModal>}
 {searchOpen&&<ReferenceModal title="Результаты поиска" onClose={()=>setSearchOpen(false)}><p className="ap-muted">По запросу «{search||'Все разделы'}»</p><div className="ap-notice-list">{matches.map(n=><Link href={n.href} key={n.href} onClick={()=>setSearchOpen(false)}>{n.label}<ArrowRight size={16}/></Link>)}{campaignMatches.map(c=><Link key={c.id} href={'/demo/campaigns?q='+encodeURIComponent(c.name)} onClick={()=>setSearchOpen(false)}><PlatformBadge platform={c.platform} size={25}/>{c.name}</Link>)}{recMatches.map(r=><Link key={r.id} href={'/demo/recommendations?rec='+r.id} onClick={()=>setSearchOpen(false)}><Sparkles size={18}/>{r.title}</Link>)}</div>{matches.length+campaignMatches.length+recMatches.length===0&&<Empty text="Ничего не найдено. Попробуйте «Кампании» или «Поиск»."/>}</ReferenceModal>}
 </div>;
}
export function Heading({title,subtitle,badge,children}:{title:string;subtitle?:string;badge?:string;children?:ReactNode}){
 const triangle=['Кампании','AI-аналитик','Подключения'].includes(title),chart=['Рекомендации','Эффект','Отчёты','Тарифы','История'].includes(title);
 const SectionIcon=title==='Отчёты'?SquareChartGantt:title==='История'?ClipboardClock:ChartColumnIncreasing;
 return <div className="ap-page-heading"><div><h1 className="ap-heading-title">{(triangle||chart)&&<span className={'ap-section-mark '+(triangle?'is-logo':'')} aria-hidden="true">{triangle?<ReferenceLogo/>:<SectionIcon/>}</span>}{title}{badge&&<span className="ap-beta">{badge}</span>}</h1>{subtitle&&<p>{subtitle}</p>}</div><div className="ap-heading-actions">{children}</div></div>;
}
export function Tabs({items,value,onChange,counts,platformBadges=false}:{items:string[];value:string;onChange:(v:string)=>void;counts?:Record<string,number>;platformBadges?:boolean}){return <div className="ap-tabs" role="group" aria-label="Варианты просмотра">{items.map(item=><button key={item} className={value===item?'is-active':''} aria-label={counts?item+', '+counts[item]+' элементов':item} data-tab={item} title={counts?counts[item]+' элементов':undefined} aria-pressed={value===item} onClick={()=>onChange(item)}>{platformBadges&&item!=='Все'&&<PlatformBadge platform={item} size={14}/>}<span>{item}</span>{counts&&<b className="ap-tab-count" aria-hidden="true">{counts[item]}</b>}</button>)}</div>;}
export function Empty({text='Ничего не найдено. Измените фильтры.'}:{text?:string}){return <div className="ap-empty" role="status"><Search size={25}/><p>{text}</p></div>;}
export function Accounts(){const {account,setAccount}=useReference();return <select className="ap-account" aria-label="Рекламный аккаунт" value={account} onChange={e=>setAccount(e.target.value)}>{['Все аккаунты','Магазин','Агентство'].map(a=><option key={a}>{a}</option>)}</select>;}
export function AnalysisScreen(){
 const {state,rows,days,setDays,account,notify}=useReference(),total=sum(rows);
 const raw=state.campaigns.filter(c=>account==='Все аккаунты'||c.account===account);
 const series=seriesFor(raw,days);
 const channelRows=platforms.map((name,i)=>({name,color:colors[i],...sum(rows.filter(r=>r.platform===name))})).filter(c=>c.spend>0);
 const gradient=channelRows.map((c,i)=>{const from=channelRows.slice(0,i).reduce((a,r)=>a+r.spend,0)/Math.max(1,total.spend)*100;return c.color+' '+from+'% '+(from+c.spend/Math.max(1,total.spend)*100)+'%';}).join(',');
 const [detail,setDetail]=useState<number|null>(null);
 const changes=comparisonFor(rows).changes,scopedRecs=recommendationsFor(rows);
 return <><Heading title="Анализ" subtitle="Сводные показатели по всем рекламным каналам"><Accounts/></Heading>
 <div className="ap-metrics">{chartMetrics.map(m=>{const change=changes[m.key],good=change!==null&&((m.key==='spend'||m.key==='cpa')?change<=0:change>=0);return <section className={'ap-card ap-metric metric-'+m.key} key={m.key}><div>{m.label}<ArrowUpRight size={16}/></div><div><strong>{m.key==='conversions'?num(total[m.key]):m.key==='cpa'&&!total.conversions?'—':rub(total[m.key])}</strong><b className={change===null?'ap-muted':good?'ap-green':'ap-red'}>{change===null?'—':(change>0?'+':'')+change+'%'}</b></div><small title="Сравнение с модельным прошлым периодом" aria-label="к модельному прошлому периоду">к прошлому периоду</small><MiniChart metric={m.key} values={series[m.key]}/></section>;})}</div>
 <div className="ap-analysis-grid"><div className="ap-analysis-main"><section className="ap-card ap-dynamics"><div className="ap-card-heading"><h2>Динамика ключевых показателей</h2><Tabs items={['День','Неделя','Месяц','Квартал','Год']} value={days===1?'День':days===7?'Неделя':'Месяц'} onChange={v=>{if(v==='Квартал'||v==='Год')notify('В демо доступны данные за март 2025. Для этого периода нужны дополнительные данные.');else setDays(v==='День'?1:v==='Неделя'?7:31);}}/></div><ReferenceChart rows={raw} days={days}/></section>
 <div className="ap-effect-mini"><Link className="ap-card" href="/demo/changes"><span className="ap-icon cyan"><Activity/></span><span><small>Доп. выручка по рекомендациям</small><strong>+{rub(842000*total.revenue/3842000+scopedRecs.filter(r=>r.kind==='revenue'&&state.applied.includes(r.id)).reduce((a,r)=>a+r.effect,0))} <em>Модель</em></strong></span></Link><Link className="ap-card" href="/demo/recommendations"><span className="ap-icon purple"><Flame/></span><span><small>Потенциальный эффект</small><strong>+{rub(scopedRecs.filter(r=>!state.applied.includes(r.id)).reduce((a,r)=>a+r.effect,0))}<em>Прогноз</em></strong></span></Link></div></div>
 <div className="ap-analysis-side"><section className="ap-card ap-distribution"><h2>Распределение расходов</h2>{total.spend>0?<div className="ap-donut-layout"><div className="ap-donut" role="img" aria-label={'Распределение расходов: '+channelRows.map(c=>c.name+' '+Math.round(c.spend/total.spend*100)+'%').join(', ')} style={{background:'conic-gradient('+gradient+')'}}><div><strong>{rub(total.spend)}</strong><small className="ap-green" title="Изменение к модельному прошлому периоду">{changes.spend===null?'—':(changes.spend>0?'+':'')+changes.spend+'%'}</small></div></div><div className="ap-channel-legend">{channelRows.map(c=><div key={c.name}><PlatformBadge platform={c.name} size={13}/><span>{c.name}</span><b>{Math.round(c.spend/total.spend*100)}%</b></div>)}</div></div>:<Empty text="Нет расходов за выбранный период."/>}</section>
 <section className="ap-card ap-alerts"><div className="ap-card-heading"><h2>Сигналы и алерты</h2><Link href="/demo/signals">Все сигналы <ArrowRight size={12}/></Link></div>{signals.map((s,i)=><button className="ap-alert-row" key={s.id} onClick={()=>setDetail(s.id)}><span className={'ap-icon '+['coral','blue','purple'][i]}>{i===0?<Flame size={15}/>:i===1?<ArrowUpRight size={15}/>:<Sparkles size={15}/>}</span><span>{s.title}</span><small className={'ap-status '+['danger','warning','info'][i]}>{s.severity}</small></button>)}</section></div></div>
 {detail!==null&&<ReferenceModal title={signals.find(s=>s.id===detail)!.title} onClose={()=>setDetail(null)}><p>{signals.find(s=>s.id===detail)!.detail}</p><Link className="ref-button ref-primary" href="/demo/signals" onClick={()=>setDetail(null)}>Все сигналы <ArrowRight size={16}/></Link></ReferenceModal>}
 </>;
}
export function AnalysisPreview(){return <div className="ap-card"><h2>Анализ</h2><ReferenceChart compact/></div>;}










