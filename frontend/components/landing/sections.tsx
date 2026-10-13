import { ArrowUpRight, ChartNoAxesCombined, Fingerprint, Link2, ListChecks, MousePointerClick, ShieldCheck, SlidersHorizontal, Target, Lightbulb, History, Search, Database } from "lucide-react";
import Link from "next/link";

const FEATURES = [
  {icon:Search,title:"Аудит и мониторинг",text:"Расход без конверсий, дорогие обращения и площадки РСЯ, которые требуют внимания."},
  {icon:ChartNoAxesCombined,title:"Аналитика и метрики",text:"Расход, конверсии и CPA. Период и источник рядом с каждой цифрой."},
  {icon:Lightbulb,title:"Рекомендации с объяснением",text:"Что проверить, почему это важно и какое действие стоит рассмотреть."},
  {icon:SlidersHorizontal,title:"Решения под вашим контролем",text:"Примите, отложите или отклоните совет. Рекламу меняете только вы."},
  {icon:History,title:"История и эффект",text:"Сверка изменений и сравнение до и после. Оценка результата без громких обещаний."},
  {icon:ShieldCheck,title:"Проверяемые выводы",text:"Формула, достаточность данных и доказательства. Без двойного учёта расходов."},
];
export function Pains() {
  return <section id="features" className="studio-section reference-features" aria-labelledby="features-title">
    <div className="studio-section-intro"><p className="studio-kicker">Всё главное — в одном месте</p><h2 id="features-title">Полный контроль<br/>вашей рекламы.</h2><p>Меньше таблиц и догадок. Больше понимания, где бюджет работает, а где стоит разобраться.</p><Link href="#product" className="reference-text-link">Посмотреть в действии <ArrowUpRight size={17}/></Link></div>
    <div className="reference-feature-grid">{FEATURES.map(f=><article className="reference-feature" key={f.title}><span className="reference-icon"><f.icon size={23}/></span><h3>{f.title}</h3><p>{f.text}</p></article>)}</div>
  </section>;
}
const STEPS=[
  {icon:Link2,title:"Подключите Директ и Метрику",text:"Официальный доступ через Яндекс. Не нужно передавать пароль."},
  {icon:ListChecks,title:"Получите первый аудит",text:"AdPilot проверит статистику и покажет находки с источниками."},
  {icon:MousePointerClick,title:"Изучите рекомендации",text:"Понятные причины, приоритеты и конкретные следующие шаги."},
  {icon:Target,title:"Примите решение",text:"Внесите изменения вручную и следите за результатом в кабинете."},
];
export function HowItWorks() {
  return <section id="how" className="studio-section studio-process" aria-labelledby="how-title"><div className="studio-section-heading"><p className="studio-kicker">Простой путь к результату</p><h2 id="how-title">От данных<br/><span>к решениям.</span></h2><p className="mt-5 text-muted">Четыре шага — и у вашей рекламы появляется ясный курс.</p></div><ol>{STEPS.map((s,i)=><li key={s.title}><span className="reference-icon"><s.icon size={24}/></span><div><h3>{i+1}. {s.title}</h3><p>{s.text}</p></div></li>)}</ol></section>;
}
export function Transparency() {
  return <>
    <section className="studio-section reference-integrations" aria-labelledby="integrations-title"><div className="studio-section-intro"><p className="studio-kicker">Работает с вашими инструментами</p><h2 id="integrations-title">Ваши данные.<br/>Одна ясная картина.</h2><p>Подключите рекламный кабинет и цели. Если данных не хватает, AdPilot покажет, что нужно проверить.</p></div><div className="reference-integration-list"><Link href="/onboarding"><span className="integration-mark direct-mark">Я</span><strong>Яндекс Директ</strong><span>Кампании и расходы</span><ArrowUpRight size={17}/></Link><Link href="/onboarding"><span className="integration-mark metrika-mark"><ChartNoAxesCombined size={25}/></span><strong>Яндекс Метрика</strong><span>Цели и конверсии</span><ArrowUpRight size={17}/></Link><div><span className="integration-mark upcoming-mark"><Database size={23}/></span><strong>Другие источники</strong><span>Планируются</span></div></div></section>
    <section className="studio-section reference-trust" aria-labelledby="trust-title"><Fingerprint size={32}/><div><h2 id="trust-title">Вы видите причину.<br/>Вы принимаете решение.</h2><p>Каждый вывод опирается на данные. AI объясняет обезличенные расчёты; названия кампаний, запросы и токены ему не передаются.</p></div><Link href="/legal/privacy" className="reference-text-link">Как защищены данные <ShieldCheck size={18}/></Link></section>
  </>;
}
