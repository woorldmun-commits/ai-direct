import {cpa,num,rub,sum,type Campaign} from './model';
export function downloadFile(blob:Blob,name:string){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export function exportCSV(rows:Campaign[],label:string) {
 const escape=(v:string)=>'"'+(/^[\t\r\n]|^[\s\p{Cc}]*[=+\-@]/u.test(v)?"'":"")+v.replaceAll('"','""')+'"';
 const total=sum(rows);
 const cells=[['inrou · Демо',label],['Канал / кампания','Расходы, ₽','Конверсии','CPA, ₽','Выручка, ₽'],...rows.map(r=>[r.name,String(r.spend),String(r.conversions),r.conversions?String(Math.round(cpa(r.spend,r.conversions))):'—',String(r.revenue)]),['Итого',String(total.spend),String(total.conversions),total.conversions?String(Math.round(total.cpa)):'—',String(total.revenue)]];
 downloadFile(new Blob(['\uFEFF'+cells.map(r=>r.map(escape).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}),'inrou-report.csv');
}
// Canvas preserves Cyrillic without a font dependency; use CSV for selectable data.
export async function exportPDF(rows:Campaign[],label:string){
 await document.fonts.ready;
 const canvas=document.createElement('canvas');canvas.width=1684;canvas.height=Math.max(1190,470+(rows.length+1)*67);
 const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Не удалось создать PDF');
 ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.fillStyle='#7044f6';ctx.font='bold 38px Arial';ctx.fillText('inrou',80,90);
 ctx.fillStyle='#10152f';ctx.font='bold 34px Arial';ctx.fillText('Отчёт по рекламе',80,160);
 ctx.fillStyle='#667397';ctx.font='22px Arial';ctx.fillText(label,80,205);ctx.fillText('Демонстрационные данные · суммы в рублях',80,245);
 const headers=['Канал / кампания','Расходы','Конверсии','CPA','Выручка'],x=[80,650,900,1130,1320];
 ctx.fillStyle='#f1f0ff';ctx.fillRect(60,285,1560,60);ctx.fillStyle='#55608b';ctx.font='22px Arial';
 headers.forEach((h,i)=>ctx.fillText(h,x[i],323));
 const total=rows.reduce((a,r)=>({spend:a.spend+r.spend,conversions:a.conversions+r.conversions,revenue:a.revenue+r.revenue}),{spend:0,conversions:0,revenue:0});
 const lines=[...rows,{...total,name:'Итого'}];
 lines.forEach((r,i)=>{const y=385+i*67;ctx.strokeStyle='#e9edf8';ctx.beginPath();ctx.moveTo(60,y+24);ctx.lineTo(1620,y+24);ctx.stroke();ctx.fillStyle='#161b3b';ctx.font=(i===lines.length-1?'bold ':'')+'23px Arial';const values=[r.name,rub(r.spend),num(r.conversions),r.conversions?rub(cpa(r.spend,r.conversions)):'—',rub(r.revenue)];values.forEach((v,j)=>ctx.fillText(v,x[j],y,j===0?530:240));});
 ctx.fillStyle='#687396';ctx.font='20px Arial';ctx.fillText('inrou · Локальный демонстрационный отчёт',80,canvas.height-70);
 const base64=canvas.toDataURL('image/jpeg',.96).split(',')[1],bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
 const encoder=new TextEncoder(),chunks:Uint8Array[]=[],offsets=[0];let size=0;
 const push=(value:string|Uint8Array)=>{const b=typeof value==='string'?encoder.encode(value):value;chunks.push(b);size+=b.length;};
 const object=(id:number,value:string)=>{offsets[id]=size;push(id+' 0 obj\n'+value+'\nendobj\n');};
 push('%PDF-1.4\n');
 object(1,'<< /Type /Catalog /Pages 2 0 R >>');object(2,'<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
 object(3,'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 '+canvas.height/2+'] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>');
 offsets[4]=size;push('4 0 obj\n<< /Type /XObject /Subtype /Image /Width 1684 /Height '+canvas.height+' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length '+bytes.length+' >>\nstream\n');push(bytes);push('\nendstream\nendobj\n');
 const stream='q 842 0 0 '+canvas.height/2+' 0 0 cm /Im0 Do Q';object(5,'<< /Length '+stream.length+' >>\nstream\n'+stream+'\nendstream');
 const start=size;push('xref\n0 6\n0000000000 65535 f \n');for(let i=1;i<=5;i++)push(String(offsets[i]).padStart(10,'0')+' 00000 n \n');
 push('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+start+'\n%%EOF');
 downloadFile(new Blob(chunks as BlobPart[],{type:'application/pdf'}),'inrou-report.pdf');
}

