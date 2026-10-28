'use client';
import {useEffect, useRef} from 'react';
import {BarChart3, Moon, Pencil, TrendingUp} from 'lucide-react';
import {SectionMotion} from '../ix/public/section-motion';
import {CookieSettingsButton} from '@/components/cookie-banner';
import {applyTheme, readTheme} from '@/lib/theme';
import {SapphireChart} from './chart';
import {HomeLanding} from './home';

function ThemeSwitch() {
  const select=useRef<HTMLSelectElement>(null);
  useEffect(()=>{if(select.current)select.current.value=readTheme();const media=matchMedia('(prefers-color-scheme: dark)');const update=()=>{if(readTheme()==='system')applyTheme('system');};media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
  return <label className="ms-theme"><Moon size={16}/><span className="ms-sr">Тема</span><select ref={select} aria-label="Тема" defaultValue="light" onChange={e=>{const t=e.target.value;if(t!=='light'&&t!=='dark'&&t!=='system')return;applyTheme(t);try{localStorage.setItem('inrou-theme',t);}catch{}}}><option value="system">Системная</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>;
}


function LaptopScene() {
  const scene=useRef<HTMLDivElement>(null);
  useEffect(()=>{const node=scene.current;if(!node)return;const observer=new ResizeObserver(entries=>node.style.setProperty('--ms-art-scale',String(entries[0].contentRect.width/771)));observer.observe(node);return()=>observer.disconnect();},[]);
  return <div ref={scene} className="ms-scene" aria-label="Ноутбук с иллюстративным графиком INROU"><div className="ms-device-overlay" aria-hidden="true"><div className="ms-device-ui"><aside><b>✧ INROU</b>{['Обзор','Аналитика','Рекомендации','Кампании','Подключения','Отчёты'].map((t,i)=><span key={t} className={i===0?'is-active':''}>{t}</span>)}</aside><div className="ms-device-content"><div className="ms-device-toolbar">INROU <span>Мой бизнес · Демо</span></div><h3>Обзор показателей и результатов</h3><SapphireChart small/><div className="ms-device-stats"><span>Расходы<strong>248 640 ₽</strong></span><span>Конверсии<strong>1 284</strong></span><span>CPA<strong>194 ₽</strong></span></div><h4>Последние рекомендации</h4><p>◈ Проверить CPA в поиске</p><p>◇ Проверить распределение бюджета</p></div></div></div>
  <div className="ms-floating ms-signal"><span><BarChart3/></span><div><strong>Сигнал<br/>обнаружен</strong><p>Отклонения, которые<br/>стоит проверить</p></div></div><div className="ms-floating ms-reason"><span><TrendingUp/></span><div><strong>Причина<br/>и источники</strong><p>Понятно, на чём<br/>основан вывод</p></div></div><div className="ms-floating ms-decision"><span><Pencil/></span><div><strong>Решение<br/>за вами</strong><p>Вы выбираете действие<br/>и проверяете результат</p></div></div>
</div>;}


export function MidnightHome() {return <div className="ms-root ms-reference-landing ms-live-home"><SectionMotion/><a className="ms-skip" href="#ms-main">Перейти к содержимому</a><HomeLanding/><div className="ms-site-controls"><CookieSettingsButton/><ThemeSwitch/></div></div>;}


export function SapphireArtwork() {return <div className="ms-root ms-artwork" aria-label="Ноутбук INROU. Показатели синтетические."><div className="ms-artwork-stage"><LaptopScene/></div></div>;}
