"use client";

import { Send, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { BrandMark } from '../brand-mark';
import "./reference.css";
import "./motion.css";
import "./reference-details.css";

export function ReferenceLogo() {
  return <span className="ref-logo"><BrandMark/><span>AdPilot</span></span>;
}

export function ReferencePortrait({size=40,className=''}:{size?:number;className?:string}) {
  return <svg className={'ref-portrait '+className} width={size} height={size} viewBox="0 0 40 40" aria-hidden="true"><image href="/reference/portrait-source.png" x="-18" y="-49" width="515" height="263"/></svg>;
}

export function PlatformBadge({ platform, size = 30 }: { platform: string; size?: number }) {
  const name = platform.toLowerCase();
  const kind = name.includes("метрик") || name === "metrika" ? "metrika" : name.includes("vk") || name.includes("вк") ? "vk" : name.includes("telegram") || name.includes("телеграм") ? "telegram" : name.includes("avito") || name.includes("авито") ? "avito" : name.includes("crm") ? "crm" : name.includes('друго') ? 'other' : "direct";
  return <span className={`ref-platform ref-platform-${kind}`} style={{ width: size, height: size }} aria-hidden="true">
    {kind === "telegram" ? <Send size={size * .55} fill="currentColor" /> : kind === "vk" ? <b>ᴠκ</b> : kind === "direct" ? <b style={{fontSize:size*.72,lineHeight:1}}>Я</b> : kind === "avito" ? <span className="ref-avito-dots"><i /><i /><i /><i /></span> : kind === "metrika" ? <span className="ref-metrika-bars"><i /><i /><i /></span> : <span className="ref-crm-glyph">{kind === "other" ? "◈" : "▦"}</span>}
  </span>;
}

export function TableScrollHint() {
  const ref=useRef<HTMLParagraphElement>(null),[overflow,setOverflow]=useState(false);
  useEffect(()=>{
    const parent=ref.current?.parentElement,table=parent?.querySelector('table');
    if(!parent||!table)return;
    const update=()=>setOverflow(table.scrollWidth>parent.clientWidth+1);
    const observer=new ResizeObserver(update),frame=requestAnimationFrame(update);
    observer.observe(parent);observer.observe(table);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[]);
  return <p ref={ref} className="ap-table-hint" hidden={!overflow}>↔ Прокрутите таблицу, чтобы увидеть все показатели</p>;
}

export function ReferenceModal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement;
    dialog?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { dialog?.close(); document.body.style.overflow = overflow; if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  return <dialog ref={ref} className="ref-ui ref-modal" aria-labelledby="ref-modal-title" onCancel={onClose} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="ref-modal-inner">
      <div className="ref-modal-heading"><h2 id="ref-modal-title">{title}</h2><button type="button" className="ref-button ref-icon-button" aria-label="Закрыть окно" onClick={onClose} autoFocus><X size={18} /></button></div>
      {children}
    </div>
  </dialog>;
}

