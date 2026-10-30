'use client';
import {useState} from 'react';
import Link from 'next/link';
import {ArrowRight, Check, Layers, ShieldCheck} from 'lucide-react';
import {launchPlans} from '@/components/reference/landing-pricing';
import './site-wave2.css';
import {DEFAULT_PUBLIC_START, type PublicStart} from '@/lib/public-start';

export function PricingPlans({start = DEFAULT_PUBLIC_START}: {start?: PublicStart}) {
  const [selected, setSelected] = useState<string>('control');
  return <div className="inrou-pricing">
    <div className="pricing-toolbar"><span>Один бизнес или несколько клиентов</span><div className="pricing-scope" role="group" aria-label="Масштаб подписки">{launchPlans.map(plan => <button key={plan.id} type="button" aria-pressed={selected === plan.id} onClick={() => setSelected(plan.id)}>{plan.id==='agency'?'До 5 клиентов':plan.accounts === 1 ? '1 аккаунт' : `До ${plan.accounts} аккаунтов`}</button>)}</div><span className="pricing-period">Без годовой предоплаты</span></div>
    <div className="pricing-plan-grid">{launchPlans.map(plan => <article key={plan.id} className={`pricing-plan${selected === plan.id ? ' is-selected' : ''}`} aria-label={`Тариф ${plan.name}`}>
      <div className="pricing-plan-top"><Layers size={21} aria-hidden="true"/><span>{selected === plan.id ? 'Выбранный масштаб' : plan.id==='business'?'Для одного бизнеса':'Прозрачная подписка'}</span></div>
      <h2>{plan.name}</h2><p className="pricing-caption">{plan.caption}</p>
      <div className="pricing-amount"><strong>{new Intl.NumberFormat('ru-RU').format(plan.price)} ₽</strong><span>/ 30 дней</span></div>
      <Link className="pricing-cta" href={start.href}>{start.label} <span className="pricing-sr">{plan.name}</span><ArrowRight size={17} aria-hidden="true"/></Link>
      <div className="pricing-included"><span>ЧТО ВХОДИТ</span><ul>{plan.features.map(feature => <li key={feature}><Check size={15} aria-hidden="true"/>{feature}</li>)}</ul></div>
      <p className="pricing-plan-scope">{plan.id==='agency'?'5 пространств, включая основное. 15 аккаунтов суммарно; доступы клиентов разделены. Приглашения участников — через оператора.':`Одно рабочее пространство · ${plan.accounts===1?'1 рекламный аккаунт':`до ${plan.accounts} рекламных аккаунтов`}. Участники этого пространства имеют общий контур доступа.`}</p>
    </article>)}</div>
    <aside className="pricing-terms pricing-founder"><Layers size={19} aria-hidden="true"/><div><strong>Первые 20 участников пилота · «Контроль» за 1 990 ₽</strong><p>Первые три оплаченных периода по 30 дней, затем 2 990 ₽. Одно предложение на пользователя и первое выбранное для оплаты пространство. Наличие места и точную цену проверяем перед оформлением заказа; ожидание незавершённой оплаты резервирует место. Автосписаний нет.</p></div></aside>
    <div className="pricing-terms"><ShieldCheck size={19} aria-hidden="true"/><div><strong>7 дней на своих данных, без карты</strong><p>Пробный период начинается после первой успешной загрузки Директа, один раз для первого пространства пользователя. Ранее начавшиеся пробные периоды сохраняют свои даты. Оплата пока не подключена; приём платежей откроется после настройки провайдера и утверждения документов. Рекламный бюджет оплачивается отдельно. Подписка не гарантирует экономию или рост заявок. <Link href="/legal/offer">Условия подписки</Link>.</p><p>Во всех планах — основания рекомендаций, история и состояние данных. Изменения рекламы выполняются вручную.</p></div></div>
  </div>;
}
