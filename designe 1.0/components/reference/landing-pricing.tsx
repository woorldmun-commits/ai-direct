import Link from 'next/link';
import {ArrowRight,Check} from 'lucide-react';

export const launchPlans=[
 {id:'control',name:'Контроль',price:2990,caption:'Владельцу бизнеса или директологу',accounts:1,features:['1 рекламный аккаунт','Контроль расходов и плана','Проверка свежести источников','Рекомендации с основаниями']},
 {id:'business',name:'Бизнес',price:4990,caption:'Для специалиста с несколькими клиентами',accounts:5,features:['До 5 рекламных аккаунтов','Отдельные рабочие пространства','Показатели по каждому проекту','Рекомендации с основаниями']},
 {id:'agency',name:'Агентство',price:9990,caption:'Для агентства с портфелем проектов',accounts:15,features:['До 15 рекламных аккаунтов','Отдельные рабочие пространства','Показатели и источники по проектам','Рекомендации с основаниями']},
] as const;

export function LandingPricing(){return <section id="pricing" className="ap-launch-pricing" aria-labelledby="pricing-title">
 <div className="ap-launch-section-heading"><span>Выберите свой масштаб</span><h2 id="pricing-title">Подписка под ваши проекты.</h2><p>Во всех тарифах — контроль расходов, проверка источников и рекомендации с основаниями. Выберите количество рекламных аккаунтов.</p></div>
 <div className="ap-launch-price-grid">{launchPlans.map((p,i)=><article key={p.id} className={'ap-launch-price '+(i===1?'is-recommended':'')}>
  {i===1&&<span className="ap-launch-plan-label">Для нескольких проектов</span>}<h3>{p.name}</h3><p>{p.caption}</p><div className="ap-launch-price-value"><strong>{p.id === 'control' ? new Intl.NumberFormat('ru-RU').format(p.price) + ' ₽' : 'Уточняется'}</strong><span>/ месяц</span></div>
  <ul>{p.features.map(f=><li key={f}><Check size={16} aria-hidden="true"/>{f}</li>)}</ul><a href="/signup" className={'ref-button '+(i===1?'ref-primary':'')} aria-label={'Создать аккаунт · '+p.name}>Создать аккаунт <ArrowRight size={16}/></a>
 </article>)}</div>
 <p className="ap-launch-price-note">Планируемые цены. Оплата пока не подключена. Рекламный бюджет оплачивается отдельно. Подписка не гарантирует экономию или рост заявок. Условия подписки — в <Link href="/legal/offer">договоре-оферте</Link>.</p>
 </section>;}
