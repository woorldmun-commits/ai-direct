import Link from 'next/link';
import {ArrowRight,Check} from 'lucide-react';

export const launchPlans=[
 {id:'control',name:'Контроль',price:2990,caption:'Один бизнес · один рекламный аккаунт',accounts:1,workspaces:1,features:['1 аккаунт Директа и связанная Метрика','План / факт и темп расходования бюджета','Свежесть источников и состояние целей','Рекомендации, основания и история решений']},
 {id:'business',name:'Бизнес',price:4990,caption:'Один бизнес · несколько аккаунтов',accounts:5,workspaces:1,features:['До 5 аккаунтов в одном пространстве','Общий доступ команды к этим аккаунтам','Весь основной контроль и рекомендации','Источники, периоды и ограничения расчётов']},
 {id:'agency',name:'Агентство',price:9990,caption:'Несколько клиентов · отдельные доступы',accounts:15,workspaces:5,features:['До 5 отдельных рабочих пространств','До 15 аккаунтов суммарно в подписке','Создание клиентских пространств владельцем','Основной функционал в каждом пространстве']},
] as const;

export function LandingPricing(){return <section id="pricing" className="ap-launch-pricing" aria-labelledby="pricing-title">
 <div className="ap-launch-section-heading"><span>Выберите свой масштаб</span><h2 id="pricing-title">Подписка под ваши проекты.</h2><p>Во всех тарифах — контроль расходов, проверка источников и рекомендации с основаниями. Для разных клиентов — отдельные пространства.</p></div>
 <div className="ap-launch-price-grid">{launchPlans.map((p,i)=><article key={p.id} className={'ap-launch-price '+(i===1?'is-recommended':'')}>
  {i===1&&<span className="ap-launch-plan-label">Для нескольких аккаунтов</span>}<h3>{p.name}</h3><p>{p.caption}</p><div className="ap-launch-price-value"><strong>{new Intl.NumberFormat('ru-RU').format(p.price)} ₽</strong><span>/ 30 дней</span></div>
  <ul>{p.features.map(f=><li key={f}><Check size={16} aria-hidden="true"/>{f}</li>)}</ul><a href="/signup" className={'ref-button '+(i===1?'ref-primary':'')} aria-label={'Создать аккаунт · '+p.name}>Создать аккаунт <ArrowRight size={16}/></a>
 </article>)}</div>
 <p className="ap-launch-price-note">Оплата пока не подключена. Без автосписаний. Рекламный бюджет оплачивается отдельно. Подписка не гарантирует экономию или рост заявок. Условия подписки — в <Link href="/legal/offer">договоре-оферте</Link>.</p>
 </section>;}
