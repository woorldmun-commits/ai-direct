'use client';
import {useEffect, useId, useRef, useState} from 'react';
import Link from 'next/link';
import {ArrowLeft, ArrowRight, BarChart3, Check, Database, Fingerprint, Play, ShieldCheck, X} from 'lucide-react';
import {BrandMark} from '@/components/brand-mark';
import {useDialog} from './use-dialog';
import {DEFAULT_PUBLIC_START, type PublicStart} from '@/lib/public-start';
import '../midnight/site-wave2.css';

const STEPS = [
  {title: 'Добро пожаловать в INROU', text: 'Расходы, источники и рекомендации — в одной картине. Это короткое знакомство с интерфейсом, без подключения рекламного кабинета.', Icon: BarChart3, labels: ['Картина расходов', 'Основания рекомендаций', 'Ваше решение']},
  {title: 'Начните с источников', text: 'Яндекс Директ и Метрика подключаются отдельно от входа. После подключения проверьте права, свежесть и выбранную цель конверсии.', Icon: Database, labels: ['Яндекс Директ', 'Яндекс Метрика', 'Только чтение данных']},
  {title: 'Проверьте основание', text: 'Перед сравнением убедитесь, что периоды и определения конверсии сопоставимы. Если данных недостаточно, показатель не подменяется нулём.', Icon: ShieldCheck, labels: ['Источник и период', 'Расчёт и ограничения', 'Достаточность данных']},
  {title: 'Решение остаётся за вами', text: 'Изменения рекламы выполняет специалист вручную. Отметка выполнения и проверка результата — разные этапы. Экономия не гарантируется.', Icon: Fingerprint, labels: ['Принять решение', 'Выполнить вручную', 'Проверить результат']},
] as const;

function TourDialog({close, workspace, start}: {close: () => void; workspace?: string; start: PublicStart}) {
  const [step, setStep] = useState(0);
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialog(true, ref, close);
  useEffect(() => {const dialog = ref.current;dialog?.showModal();return () => dialog?.close();}, []);
  const current = STEPS[step];
  const Icon = current.Icon;
  return <dialog ref={ref} className="product-tour" aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={event => {event.preventDefault();close();}} onClick={event => {if (event.target === event.currentTarget) close();}}><div className="product-tour-panel">
    <button type="button" className="product-tour-close" aria-label="Закрыть знакомство" onClick={close}><X size={20}/></button>
    <div className={`product-tour-art product-tour-art--${step}`} aria-hidden="true"><span className="product-tour-ring"/><span className="product-tour-ring product-tour-ring--outer"/><div className="product-tour-brand"><BrandMark size={28}/><span>INROU</span></div><Icon size={49}/><div className="product-tour-art-label">ДАННЫЕ → ОСНОВАНИЕ → РЕШЕНИЕ</div></div>
    <div className="product-tour-copy"><span className="product-tour-kicker">ЗНАКОМСТВО · {step + 1} ИЗ {STEPS.length}</span><div aria-live="polite" aria-atomic="true"><h2 id={titleId}>{current.title}</h2><p id={descriptionId}>{current.text}</p></div><ul>{current.labels.map(label => <li key={label}><Check size={15}/>{label}</li>)}</ul>
      <div className="product-tour-footer"><div className="product-tour-dots" role="group" aria-label="Шаг знакомства">{STEPS.map((item, i) => <button type="button" key={item.title} aria-label={`Шаг ${i + 1}: ${item.title}`} aria-current={step === i ? 'step' : undefined} onClick={() => setStep(i)}/>)}</div><div className="product-tour-actions">{step === 0 ? <button type="button" onClick={close}>Пропустить</button> : <button type="button" onClick={() => setStep(step - 1)}><ArrowLeft size={16}/>Назад</button>}{step < STEPS.length - 1 ? <button type="button" className="product-tour-next" onClick={() => setStep(step + 1)}>Далее <ArrowRight size={16}/></button> : <Link className="product-tour-next" href={workspace ? `/onboarding/connect?workspace=${encodeURIComponent(workspace)}` : start.href} onClick={close}>{workspace ? 'К настройке' : start.label}<ArrowRight size={16}/></Link>}</div></div>
    </div>
  </div></dialog>;
}

export function ProductTour({workspace, label = 'Знакомство с INROU', start = DEFAULT_PUBLIC_START}: {workspace?: string; label?: string; start?: PublicStart}) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="product-tour-trigger" onClick={() => setOpen(true)} aria-haspopup="dialog"><Play size={14}/>{label}<ArrowRight size={15}/></button>{open && <TourDialog workspace={workspace} start={start} close={() => setOpen(false)}/>}</>;
}
