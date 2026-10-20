import type { ManualAction } from '@/lib/insights-contract';
const checks:Record<string,string>={conversion_goals:'Проверьте счётчик и цели конверсий.',strategy:'Уточните действующую стратегию кампании.',search_queries_negative_keywords:'Проверьте поисковые запросы и минус-слова.',network_placements:'Проверьте площадки РСЯ.'};
export function ActionInstructions({action}:{action:ManualAction|null}){
 if(!action)return <p>Конкретное действие недоступно: сначала проверьте основания.</p>;
 return <div><h3>Что проверить или изменить вручную</h3>
  {action.type==='investigate'&&<ul>{action.checks?.map(check=><li key={check}>{checks[check]}</li>)}</ul>}
  {action.type==='decrease_bid'&&<p>Изменение ручной ставки: {action.change_pct}%. Проверьте применимость к текущей стратегии.</p>}
  {action.type==='lower_cpa'&&<><p>Сначала уточните стратегию. Применяйте только подходящий для неё вариант.</p><ul>{action.levers?.map(lever=><li key={lever.lever}>{lever.lever==='decrease_bid'?`При ручной стратегии — изменение ставки ${lever.change_pct}%.`:lever.lever==='lower_target_cpa'?'При автостратегии — проверьте возможность снижения целевой цены конверсии.':'При автостратегии — проверьте цели конверсий.'}</li>)}</ul></>}
  {(action.type==='exclude_placements'||Boolean(action.placements?.length))&&<><p>{action.type==='exclude_placements'?'Площадки для проверки перед ручным исключением:':'Площадки для проверки:'}</p><ul>{action.placements?.map(item=><li key={item.id}>{item.name??`ID ${item.id}`}</li>)}</ul></>}
 </div>;
}
