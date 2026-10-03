"use client";

import { CalendarClock, Download, FileText, Plus, Printer } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/field";
import { Logo, PageHeader } from "@/components/ui/misc";
import { Modal } from "@/components/ui/overlay";
import { ValueText } from "@/components/ui/value";
import { api } from "@/lib/api";
import { dateTime, formatValue } from "@/lib/formatters";
import { campaignsCsv, downloadCsv } from "./analytics";

type Report = ReturnType<typeof api.reports>[number] | { id: string; kind: "weekly" | "monthly"; title: string; period: string; client: string; status: "generating" | "ready" | "scheduled"; created: string };

function Preview({ r }: { r: Report }) {
  const kpis = api.todayKpis();
  const recs = api.recommendations().filter((x) => x.safety.verdict !== "blocked").slice(0, 4);
  const measured = api.measuredTotal();
  return (
    <div id="report-preview" className="rounded-2xl border border-line bg-surface p-6 md:p-8">
      <div className="flex items-start justify-between gap-4 border-b border-line pb-5">
        <div>
          <Logo size={22} />
          <h2 className="mt-4 text-[20px] font-semibold">{r.title}</h2>
          <p className="text-[13px] text-muted">
            {r.period} · {r.client}
          </p>
        </div>
        <Badge tone="warning">Демо-данные</Badge>
      </div>
      <section className="mt-5">
        <h3 className="text-[13px] font-semibold tracking-wide text-muted uppercase">Ключевые показатели</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {kpis.map((k) => (
            <div key={k.id} className="rounded-xl bg-bg p-3">
              <p className="text-[12px] text-muted">{k.label}</p>
              <p className="text-[16px] font-semibold">
                <ValueText value={k.value} />
              </p>
            </div>
          ))}
        </div>
      </section>
      <section className="mt-6">
        <h3 className="text-[13px] font-semibold tracking-wide text-muted uppercase">Проблемы и решения</h3>
        <ul className="mt-3 divide-y divide-line text-[13px]">
          {recs.map((x) => (
            <li key={x.id} className="flex flex-wrap justify-between gap-2 py-2.5">
              <span>
                <b>{x.title}</b>
                <span className="block text-muted">Действие: {x.action}</span>
              </span>
              <span className="num font-medium">{formatValue(x.effect.value)}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="mt-6 rounded-xl bg-success-soft p-4">
        <h3 className="text-[13px] font-semibold text-success-ink">Измеренный эффект решений</h3>
        <p className="mt-1 text-[20px] font-semibold text-success-ink">
          <ValueText value={measured} />
        </p>
        <p className="text-[12px] text-[#05603a]">Только решения с подтверждённым исполнением и замером 7 дней до/после.</p>
      </section>
      <p className="mt-6 text-[11px] text-subtle">Сформировано AdPilot {dateTime(r.created)} · снимок snap_2026-10-01_4815 · Источники: Яндекс Директ, Яндекс Метрика</p>
    </div>
  );
}

export function Reports() {
  const { notify } = useApp();
  const [list, setList] = useState<Report[]>(api.reports);
  const [selected, setSelected] = useState(list[0].id);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ kind: "weekly", client: "Все клиенты" });
  const current = list.find((r) => r.id === selected) ?? list[0];

  function create(e: FormEvent) {
    e.preventDefault();
    const id = `r-${Date.now()}`;
    const r: Report = { id, kind: form.kind as "weekly", title: form.kind === "weekly" ? "Еженедельный отчёт" : "Ежемесячный отчёт", period: form.kind === "weekly" ? "25 сентября — 1 октября 2026" : "Сентябрь 2026", client: form.client, status: "generating", created: new Date().toISOString() };
    setList((l) => [r, ...l]);
    setCreating(false);
    setTimeout(() => {
      setList((l) => l.map((x) => (x.id === id ? { ...x, status: "ready" } : x)));
      setSelected(id);
      notify("Отчёт готов.");
    }, 1500);
  }

  return (
    <>
      <PageHeader title="Отчёты" sub="Еженедельные и ежемесячные отчёты для команды и клиентов" actions={<Button icon={<Plus size={16} />} onClick={() => setCreating(true)}>Создать отчёт</Button>} />
      <div className="grid items-start gap-6 xl:grid-cols-[360px_1fr]">
        <Card className="p-2">
          <ul>
            {list.map((r) => {
              const on = r.id === current.id;
              return (
                <li key={r.id}>
                  <button type="button" disabled={r.status !== "ready"} onClick={() => setSelected(r.id)} aria-current={on || undefined} className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition-colors disabled:cursor-default ${on ? "bg-brand-soft" : "hover:bg-bg"}`}>
                    <span className={`grid size-9 shrink-0 place-items-center rounded-lg ${on ? "bg-surface text-brand" : "bg-surface-2 text-muted"}`}>{r.status === "scheduled" ? <CalendarClock size={16} /> : <FileText size={16} />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-semibold">{r.title}</span>
                      <span className="block text-[12px] text-muted">{r.period}</span>
                      <span className="block truncate text-[12px] text-muted">{r.client}</span>
                    </span>
                    {r.status === "generating" ? <Badge tone="brand">Формируется…</Badge> : r.status === "scheduled" ? <Badge>По расписанию</Badge> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
        <div>
          <div className="mb-3 flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="secondary" icon={<Download size={15} />} onClick={() => downloadCsv(`adpilot-${current.id}.csv`, campaignsCsv(api.campaigns()))}>
              Экспорт CSV
            </Button>
            <Button size="sm" variant="secondary" icon={<Printer size={15} />} onClick={() => window.print()}>
              Печать / PDF
            </Button>
          </div>
          <Preview r={current} />
        </div>
      </div>

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="Новый отчёт"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Отмена
            </Button>
            <Button type="submit" form="new-report">
              Сформировать
            </Button>
          </>
        }
      >
        <form id="new-report" onSubmit={create} className="space-y-4">
          <Field id="rep-kind" label="Тип отчёта">
            <Select id="rep-kind" className="w-full [&>select]:h-10" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              <option value="weekly">Еженедельный</option>
              <option value="monthly">Ежемесячный</option>
            </Select>
          </Field>
          <Field id="rep-client" label="Клиент">
            <Select id="rep-client" className="w-full [&>select]:h-10" value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })}>
              <option>Все клиенты</option>
              {api.clients().map((c) => (
                <option key={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
        </form>
      </Modal>
    </>
  );
}
