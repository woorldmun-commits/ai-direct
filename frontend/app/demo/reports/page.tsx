"use client";

import { useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { PageHeader } from "@/components/ui";
import { CAMPAIGNS, P7 } from "@/lib/demo";
import { campaignsCsv } from "@/lib/campaigns-csv";
import { formatPeriod } from "@/lib/value";

export default function Reports() {
  const [message, setMessage] = useState("");

  function download() {
    try {
      const url = URL.createObjectURL(new Blob([campaignsCsv(CAMPAIGNS)], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `adpilot-demo-${P7.from}-${P7.to}.csv`;
      try {
        document.body.appendChild(link);
        link.click();
      } finally {
        link.remove();
        // Give the browser time to start reading the download before releasing it.
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      setMessage("CSV подготовлен. Загрузка передана браузеру.");
    } catch {
      setMessage("Не удалось подготовить CSV. Попробуйте скачать ещё раз.");
    }
  }

  return <>
    <PageHeader title="Отчёты" sub="Сохраните статистику для обсуждения с командой." />
    <article className="card flex flex-wrap items-center gap-5 p-6">
      <span className="grid size-14 place-items-center rounded-2xl bg-brand-soft text-brand"><FileSpreadsheet size={27} /></span>
      <div className="flex-1">
        <h2 className="font-semibold">Статистика кампаний</h2>
        <p className="mt-1 text-sm text-muted">{formatPeriod(P7)} · {CAMPAIGNS.length} кампании · CSV</p>
        <p className="mt-2 text-xs text-muted">Демонстрационные данные Яндекс Директа. Расход и конверсии по каждой кампании.</p>
      </div>
      <button onClick={download} className="btn btn-primary"><Download size={16} />Скачать CSV</button>
    </article>
    <p role="status" className="mt-3 text-sm text-muted">{message}</p>
  </>;
}
