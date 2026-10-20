export type Campaign = { id: string; name: string; platform: string; account: string; status: string; spend: number; conversions: number; revenue: number };
export const platforms = ['Яндекс Директ', 'VK Ads', 'Telegram Ads', 'Авито', 'Другое'];
export const colors = ['var(--chart-spend)', 'var(--chart-conversions)', 'var(--chart-cpa)', 'var(--chart-revenue)', 'var(--chart-other)'];
export const campaigns: Campaign[] = [
  { id:'search', name:'Поиск | Бренд', platform:platforms[0], account:'Магазин', status:'Активна', spend:80000, conversions:420, revenue:960000 },
  { id:'rsya', name:'РСЯ | Конверсии', platform:platforms[0], account:'Магазин', status:'Активна', spend:24429, conversions:312, revenue:360000 },
  { id:'vk', name:'VK | Лиды', platform:platforms[1], account:'Магазин', status:'Активна', spend:69619, conversions:284, revenue:1100000 },
  { id:'tg', name:'Telegram | Подписки', platform:platforms[2], account:'Агентство', status:'Активна', spend:37296, conversions:186, revenue:582000 },
  { id:'avito', name:'Авито | Продажи', platform:platforms[3], account:'Агентство', status:'Пауза', spend:24864, conversions:74, revenue:372000 },
  { id:'other', name:'Другие площадки', platform:platforms[4], account:'Агентство', status:'Активна', spend:12432, conversions:8, revenue:468000 },
];
export const rub = (n:number) => `${Math.round(n).toLocaleString('ru-RU')} ₽`;
export const num = (n:number) => Math.round(n).toLocaleString('ru-RU');
export const cpa = (spend:number, conversions:number) => conversions > 0 ? spend / conversions : 0;
export const sum = (rows:Pick<Campaign,'spend'|'conversions'|'revenue'>[]) => {
  const total = rows.reduce((a,r)=>({spend:a.spend+r.spend,conversions:a.conversions+r.conversions,revenue:a.revenue+r.revenue}), {spend:0,conversions:0,revenue:0});
  return {...total,cpa:cpa(total.spend,total.conversions)};
};
export function comparisonFor(rows:Campaign[]) {
 const current=sum(rows),previous={spend:Math.round(current.spend/.88),conversions:Math.round(current.conversions/1.34),revenue:Math.round(current.revenue/1.48)};
 const before={...previous,cpa:cpa(previous.spend,previous.conversions)};
 const change=(key:keyof typeof current)=>before[key]>0&&(key!=='cpa'||current.conversions>0)?Math.round((current[key]/before[key]-1)*100):null;
 return {previous:before,changes:{spend:change('spend'),conversions:change('conversions'),cpa:change('cpa'),revenue:change('revenue')}};
}
export function daily(total:number,seed=0) {
  // Synthetic reference profiles keep the illustrated trend while allocating exact totals.
  const profiles = [
    [0,4,13,26,40,48,51,48,43,39,39,44,56,72,82,83,77,68,62,59,60,64,67,66,67,73,80,87,94,101,110],
    [0,8,18,30,42,51,57,60,61,58,54,51,49,50,55,64,75,80,81,81,84,89,94,95,94,94,97,102,107,112,118],
    [0,11,25,40,49,53,53,47,40,34,30,30,29,28,28,29,31,33,35,38,42,47,52,54,54,55,57,60,63,65,67],
  ];
  const weights = profiles[seed] || profiles[0];
  const weight = weights.reduce((a,b)=>a+b,0);
  let allocated = 0;
  return weights.map((_,i)=>{const cumulative = Math.round(total * weights.slice(0,i+1).reduce((a,b)=>a+b,0)/weight); const v=cumulative-allocated; allocated=cumulative;return v;});
}
export function scoped(rows:Campaign[], days:number, account:string, platform='Все') {
  return rows.filter(r=>(account==='Все аккаунты'||r.account===account)&&(platform==='Все'||r.platform===platform)).map(r=>({...r,spend:daily(r.spend).slice(-days).reduce((a,b)=>a+b,0),conversions:daily(r.conversions,1).slice(-days).reduce((a,b)=>a+b,0),revenue:daily(r.revenue,2).slice(-days).reduce((a,b)=>a+b,0)}));
}
export function seriesFor(rows:Campaign[],days:number) {
  const series=(key:'spend'|'conversions'|'revenue',seed:number)=>rows.map(r=>daily(r[key],seed)).reduce((a,r)=>a.map((v,i)=>v+r[i]),Array(31).fill(0) as number[]).slice(-days);
  const spend=series('spend',0),conversions=series('conversions',1),revenue=series('revenue',2);
  return {spend,conversions,revenue,cpa:spend.map((v,i)=>cpa(v,conversions[i]))};
}
export const recs = [
 {id:1,campaignId:'search',kind:'revenue',title:'Увеличить бюджет на эффективные кампании',category:'Рост конверсий',platform:platforms[0],effect:142000,description:'Кампании приносят конверсии дешевле целевого CPA. Модель перераспределения бюджета: +32% конверсий.',detail:'Поиск | Бренд: бюджет ограничивает показы. Перераспределите 20% бюджета из низкоэффективных групп. Прогноз рассчитан по демонстрационным данным; фактический результат может отличаться.',icon:'up'},
 {id:2,campaignId:'rsya',kind:'saving',title:'Отключить неэффективные ключевые слова',category:'Снижение CPA',platform:platforms[0],effect:6840,description:'Модель: −28% расходов кампании РСЯ',detail:'24 запроса в РСЯ не принесли конверсий за период. Оценка экономии — 28% расходов кампании в выбранном срезе. Действие меняет только локальный сценарий.',icon:'search'},
 {id:3,campaignId:'tg',kind:'revenue',title:'Запустить ретаргетинг в Telegram',category:'Увеличение объёма',platform:platforms[2],effect:96000,description:'+18% конверсий на тёплой аудитории',detail:'Создайте сегмент посетителей, не совершивших покупку. Прогноз дополнительной выручки зависит от выбранного среза. В демо сегмент не передаётся рекламной площадке.',icon:'send'},
];
export function recommendationsFor(rows:Campaign[]) {
 return recs.flatMap(r=>{const row=rows.find(c=>c.id===r.campaignId),base=campaigns.find(c=>c.id===r.campaignId)!;return row&&row.spend>0?[{...r,effect:Math.round(r.effect*row.spend/base.spend)}]:[];});
}
export type LogEvent = {id:string; title:string; detail:string; date:string; type:string};
export type DemoState = { applied:number[]; campaigns:Campaign[]; connections:string[]; readSignals:number[]; events:LogEvent[]; members:{name:string;email:string;role:string}[]; profile:{name:string;email:string;notifications:boolean;weekly:boolean}; plan:string; queries:{question:string;answer:string;context?:string}[] };
export const initialState:DemoState = {applied:[], campaigns, connections:platforms.slice(0,4).concat('Яндекс Метрика'), readSignals:[], events:[
 {id:'a',title:'Применена рекомендация',detail:'Увеличить бюджет на +32% · пример',date:'2025-03-31T09:24:00Z',type:'Рекомендации'},
 {id:'b',title:'Обновлены ключевые слова',detail:'+1 245 ключей',date:'2025-03-30T15:42:00Z',type:'Кампании'},
 {id:'c',title:'Запущен ретаргетинг',detail:'Telegram Ads',date:'2025-03-02T07:15:00Z',type:'Кампании'},
 {id:'d',title:'Изменён бюджет кампании',detail:'VK Ads, −15%',date:'2025-03-01T13:30:00Z',type:'Кампании'},
 {id:'e',title:'Добавлен аккаунт',detail:'Авито',date:'2025-02-28T08:03:00Z',type:'Подключения'}
 ],members:[{name:'Александра',email:'alexandra@example.ru',role:'Владелец'}],profile:{name:'Александра',email:'alexandra@example.ru',notifications:true,weekly:true},plan:'Контроль',queries:[]};
export function applyRecommendation(state:DemoState,id:number):DemoState {
  if (state.applied.includes(id)||!recs.some(r=>r.id===id)) return state;
  return {...state,applied:[...state.applied,id]};
}
export const monthlyPrice = (price:number, annual:boolean) => annual ? price*.8 : price;
export function restoreState(raw:unknown):DemoState {
 if(!raw||typeof raw!=='object')return initialState;
 const s=raw as DemoState,strings=(values:unknown)=>Array.isArray(values)&&values.every(v=>typeof v==='string');
 if(!Array.isArray(s.applied)||!s.applied.every(id=>recs.some(r=>r.id===id))||new Set(s.applied).size!==s.applied.length)return initialState;
 if(!Array.isArray(s.campaigns)||!s.campaigns.every(c=>c&&['id','name','platform','account','status'].every(k=>typeof c[k as keyof Campaign]==='string')&&c.id.trim()&&c.name.trim()&&platforms.includes(c.platform)&&['Магазин','Агентство'].includes(c.account)&&['Активна','Пауза','Черновик'].includes(c.status)&&[c.spend,c.conversions,c.revenue].every(n=>Number.isSafeInteger(n)&&n>=0))||new Set(s.campaigns.map(c=>c.id)).size!==s.campaigns.length)return initialState;
 if(!strings(s.connections)||!s.connections.every(p=>platforms.slice(0,4).concat('Яндекс Метрика').includes(p))||new Set(s.connections).size!==s.connections.length||!Array.isArray(s.readSignals)||!s.readSignals.every(id=>[1,2,3].includes(id))||new Set(s.readSignals).size!==s.readSignals.length)return initialState;
 if(!Array.isArray(s.events)||!s.events.every(e=>e&&[e.id,e.title,e.detail,e.type,e.date].every(v=>typeof v==='string')&&Number.isFinite(Date.parse(e.date))))return initialState;
 if(!Array.isArray(s.members)||!s.members.length||!s.members.every((m,i)=>m&&[m.name,m.email,m.role].every(v=>typeof v==='string')&&m.name.trim()&&/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(m.email)&&(i===0?m.role==='Владелец':['Аналитик','Маркетолог','Администратор'].includes(m.role)))||new Set(s.members.map(m=>m.email.trim().toLowerCase())).size!==s.members.length)return initialState;
 if(!Array.isArray(s.queries)||!s.queries.every(q=>q&&typeof q.question==='string'&&typeof q.answer==='string'&&(q.context===undefined||typeof q.context==='string')))return initialState;
 if(!s.profile||typeof s.profile.name!=='string'||!s.profile.name.trim()||typeof s.profile.email!=='string'||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.profile.email)||typeof s.profile.notifications!=='boolean'||typeof s.profile.weekly!=='boolean'||!['Контроль','Бизнес','Премиум'].includes(s.plan))return initialState;
 if(s.members.slice(1).some(m=>m.email.trim().toLowerCase()===s.profile.email.trim().toLowerCase()))return initialState;
 if(s.members[0].email!==s.profile.email||s.members[0].name!==s.profile.name)return {...s,members:[{...s.members[0],name:s.profile.name,email:s.profile.email},...s.members.slice(1)]};
 return s;
}
export const signals = [
 {id:1,title:'Резкий рост расхода в VK Ads',severity:'Высокий',detail:'Расход вырос на 28% относительно предыдущего периода. Проверьте ставки и дневной бюджет.'},
 {id:2,title:'Снижение конверсий в Яндекс Директ',severity:'Средний',detail:'Конверсии снизились в двух группах объявлений. Проверьте поисковые запросы и посадочные страницы.'},
 {id:3,title:'Выигрышные аудитории',severity:'Новый',detail:'Повторные посетители показывают высокий отклик. Рекомендуем протестировать ретаргетинг.'},
];
