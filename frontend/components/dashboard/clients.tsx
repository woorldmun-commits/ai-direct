"use client";

import { MoreVertical, Plus, Search, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { Meter, PageHeader } from "@/components/ui/misc";
import { Modal, Popover } from "@/components/ui/overlay";
import { EmptyState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { rub } from "@/lib/formatters";
import type { Client, ClientStatus } from "@/lib/types/domain";

const STATUS: Record<ClientStatus, [string, Tone]> = { active: ["Активен", "success"], attention: ["Требует внимания", "warning"], paused: ["Пауза", "neutral"] };
const TINTS = ["bg-[#eef0ff] text-brand", "bg-[#f4f0ff] text-violet", "bg-[#eff6ff] text-sky", "bg-[#fff1e6] text-[#e04f16]", "bg-success-soft text-success-ink"];
const plural = (n: number, one: string, few: string, many: string) => (n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many);

function AddClient({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (c: Client) => void }) {
  const [name, setName] = useState("");
  const [login, setLogin] = useState("");
  const [errors, setErrors] = useState<{ name?: string; login?: string }>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = {
      name: name.trim().length < 2 ? "Укажите название клиента" : undefined,
      login: login && !/^[a-z0-9.-]{3,}$/i.test(login.trim()) ? "Логин кабинета: латиница, цифры, точка или дефис" : undefined,
    };
    setErrors(next);
    if (next.name || next.login) return;
    onAdd({ id: `new-${Date.now()}`, name: name.trim(), accounts: login ? 1 : 0, projects: 0, spend: 0, problems: 0, recommendations: 0, status: "paused" });
    setName("");
    setLogin("");
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Новый клиент"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="add-client">
            Добавить клиента
          </Button>
        </>
      }
    >
      <form id="add-client" onSubmit={submit} noValidate className="space-y-4">
        <Field id="client-name" label="Название" error={errors.name}>
          <Input id="client-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="ООО «Ромашка»" error={errors.name} autoFocus />
        </Field>
        <Field id="client-login" label="Логин кабинета Яндекс Директа" hint="Необязательно. Доступ к кабинету подтверждается через Яндекс OAuth на странице интеграций." error={errors.login}>
          <Input id="client-login" value={login} onChange={(e) => setLogin(e.target.value)} placeholder="client-login" error={errors.login} />
        </Field>
      </form>
    </Modal>
  );
}

export function Clients() {
  const { notify } = useApp();
  const [list, setList] = useState(api.clients);
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const usage = api.usage();
  const plan = api.plans().find((p) => p.id === api.subscription().plan_id)!;
  const shown = useMemo(() => list.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase())), [list, q]);
  const atLimit = plan.entitlements.clients !== null && list.length >= plan.entitlements.clients;

  return (
    <>
      <PageHeader
        title="Клиенты"
        sub="Управление клиентами и рекламными кабинетами"
        actions={
          <Button icon={<Plus size={16} />} onClick={() => setAdding(true)} disabled={atLimit} title={atLimit ? "Достигнут лимит клиентов по тарифу" : undefined}>
            Добавить клиента
          </Button>
        }
      />

      <Card className="mb-5 grid gap-5 p-5 sm:grid-cols-3">
        <Meter label="Клиенты" used={list.length} limit={plan.entitlements.clients} />
        <Meter label="Рекламные кабинеты" used={usage.ad_accounts} limit={plan.entitlements.ad_accounts} />
        <Meter label="Участники команды" used={usage.seats} limit={plan.entitlements.seats} />
        <p className="text-[12px] text-muted sm:col-span-3">
          Лимиты пробного периода тарифа {plan.name}. <Link href="/billing" className="font-medium text-brand hover:underline">Тариф и использование</Link>
        </p>
      </Card>

      <Card className="overflow-hidden">
        <div className="border-b border-line p-3">
          <span className="relative block max-w-[320px]">
            <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск клиента…" aria-label="Поиск клиента" className="input h-9 pl-8 text-[13px]" />
          </span>
        </div>
        {shown.length === 0 ? (
          <EmptyState icon={<Users size={22} />} title={q ? "Клиент не найден" : "Клиентов пока нет"} text={q ? "Проверьте написание." : "Добавьте первого клиента и подключите его рекламный кабинет."} />
        ) : (
          <ul className="divide-y divide-line">
            {shown.map((c, i) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 hover:bg-bg">
                <div className="flex min-w-[240px] flex-1 items-center gap-3">
                  <span className={`grid size-10 shrink-0 place-items-center rounded-xl text-[14px] font-bold ${TINTS[i % TINTS.length]}`} aria-hidden>
                    {c.name.replace(/^(ООО|ИП)\s*|[«»"]/g, "").trim().charAt(0)}
                  </span>
                  <div className="min-w-0">
                    <Link href={`/campaigns?client=${c.id}`} className="block truncate text-[14px] font-semibold hover:text-brand">
                      {c.name}
                    </Link>
                    <p className="text-[12px] text-muted">
                      {c.accounts} {plural(c.accounts, "кабинет", "кабинета", "кабинетов")} · {c.projects} {plural(c.projects, "проект", "проекта", "проектов")}
                    </p>
                  </div>
                </div>
                <dl className="grid grid-cols-3 gap-6 text-[13px] sm:w-[360px]">
                  <div>
                    <dt className="text-[12px] text-muted">Расход, 30 дн.</dt>
                    <dd className="num font-semibold">{c.spend ? rub(c.spend) : "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-[12px] text-muted">Проблемы</dt>
                    <dd className={`num font-semibold ${c.problems ? "text-danger" : ""}`}>{c.problems}</dd>
                  </div>
                  <div>
                    <dt className="text-[12px] text-muted">Рекомендации</dt>
                    <dd className="num font-semibold">{c.recommendations}</dd>
                  </div>
                </dl>
                <Badge tone={STATUS[c.status][1]} dot className="w-[150px] justify-center">
                  {c.accounts === 0 ? "Нет кабинета" : STATUS[c.status][0]}
                </Badge>
                <Popover
                  label={`Действия: ${c.name}`}
                  width={220}
                  trigger={({ open, toggle }) => (
                    <button type="button" onClick={toggle} aria-expanded={open} aria-label={`Действия: ${c.name}`} className="btn btn-ghost size-8 p-0">
                      <MoreVertical size={16} />
                    </button>
                  )}
                >
                  <div className="p-1.5 text-[13px]">
                    <Link href={`/campaigns?client=${c.id}`} className="block rounded-lg px-3 py-2 hover:bg-surface-2">
                      Кампании клиента
                    </Link>
                    <Link href="/reports" className="block rounded-lg px-3 py-2 hover:bg-surface-2">
                      Отчёт для клиента
                    </Link>
                    <Link href="/integrations" className="block rounded-lg px-3 py-2 hover:bg-surface-2">
                      Подключить кабинет
                    </Link>
                  </div>
                </Popover>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <AddClient
        open={adding}
        onClose={() => setAdding(false)}
        onAdd={(c) => {
          setList((l) => [...l, c]);
          notify(`Клиент «${c.name}» добавлен. Подключите его кабинет на странице интеграций.`);
        }}
      />
    </>
  );
}
