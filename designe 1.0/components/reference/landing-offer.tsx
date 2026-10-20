import {ArrowRight,ChartNoAxesColumnIncreasing,CalendarDays,ContactRound} from 'lucide-react';

const outcomes=[
 {Icon:ChartNoAxesColumnIncreasing,question:'На что уходит бюджет?',title:'Расходы и CPA с контекстом',text:'Показатели кампаний вместе с периодом и источником. Видите, на каких данных основан вывод, и где информации пока недостаточно.',result:'Для вас: основа для проверки расходов.'},
 {Icon:CalendarDays,question:'Какие кампании проверить?',title:'Рекомендации с основаниями',text:'У рекомендации есть причина и данные, которые можно изучить перед решением. Изменения в Директе выполняете вы.',result:'Для вас: конкретный повод для разбора кампании.'},
 {Icon:ContactRound,question:'Как работать с разными клиентами?',title:'Отдельные пространства проектов',text:'Данные проектов разделены по рабочим пространствам. Тариф выбираете по количеству рекламных аккаунтов, с которыми работаете.',result:'Для вас: контекст каждого клиента отдельно.'},
];
const questions=[
 ['Кому подойдёт Rekvero?','Владельцам бизнеса, маркетологам, директологам и агентствам, которые используют Яндекс Директ и хотят разбирать расходы и рекомендации с опорой на данные. Если вам нужно, чтобы сервис самостоятельно управлял ставками и бюджетами, текущий Rekvero эту задачу не решает.'],
 ['Чем подписка полезна, если у меня уже есть Директ и Метрика?','Директ и Метрика остаются источниками данных. Rekvero собирает показатели расходов и CPA вместе с рекомендациями и их основаниями. Вы платите за этот рабочий инструмент для анализа, а не за доступ к рекламным площадкам.'],
 ['Сервис может сам изменить мою рекламу?','Нет. Доступ к рекламным данным — только для чтения. Рекомендации помогают разобраться в кампании; решение и изменения в рекламном кабинете остаются за вами.'],
 ['Что потребуется для начала работы?','Аккаунт Rekvero и отдельное подключение Директа и Метрики администратором вашего пространства. Вход через Яндекс ID сам по себе не открывает доступ к рекламе. Без подключённых источников реальные показатели не появятся.'],
];

export function SubscriptionValue(){return <section id="subscription-value" className="ap-launch-how ap-subscription-value" aria-labelledby="value-title">
 <div className="ap-launch-section-heading"><span>За что вы платите</span><h2 id="value-title">От расходов — к понятному решению</h2><p>Подписка даёт рабочий инструмент для трёх задач, с которыми вы сталкиваетесь при ведении рекламы.</p></div>
 <div className="ap-offer-grid">{outcomes.map(({Icon,question,title,text,result})=><article key={title}><div className="ap-offer-question"><Icon size={22} aria-hidden="true"/><span>{question}</span></div><h3>{title}</h3><p>{text}</p><strong>{result}</strong></article>)}</div>
 <p className="ap-offer-summary">Вы выбираете действие на основе данных. Rekvero не обещает гарантированную экономию и не меняет рекламу за вас.</p>
 </section>;}

export function SubscriptionQuestions(){return <section className="ap-offer-faq" aria-labelledby="questions-title">
 <div className="ap-launch-section-heading"><span>Перед выбором подписки</span><h2 id="questions-title">Ответы на важные вопросы</h2></div>
 <div className="ap-offer-faq-list">{questions.map(([question,answer])=><details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div>
 <div className="ap-offer-next"><h3>Ведёте рекламу в Яндекс Директе?</h3><p>Выберите подписку под количество рекламных аккаунтов.</p><a href="#pricing" className="ref-button ref-primary">Выбрать подписку <ArrowRight size={17}/></a></div>
 </section>;}
