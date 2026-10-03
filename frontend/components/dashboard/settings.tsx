"use client";

import { Bell, Building2, CreditCard, Database, KeyRound, PlugZap, ShieldCheck, User, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge } from "@/components/ui/badge";
import { Button, buttonCls } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input, Select, Switch } from "@/components/ui/field";
import { Avatar, PageHeader } from "@/components/ui/misc";
import { Modal } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { can, PERMISSION_LABEL, ROLE_LABEL, type Permission, type Role } from "@/lib/permissions";
import { SafetySettings } from "./settings-safety";

const SECTIONS = [
  { id: "profile", label: "Профиль", icon: User },
  { id: "workspace", label: "Рабочее пространство", icon: Building2 },
  { id: "team", label: "Команда", icon: Users },
  { id: "roles", label: "Роли и права", icon: KeyRound },
  { id: "integrations", label: "Интеграции", icon: PlugZap },
  { id: "notifications", label: "Уведомления", icon: Bell },
  { id: "safety", label: "Безопасность", icon: ShieldCheck },
  { id: "billing", label: "Тариф и оплата", icon: CreditCard },
  { id: "privacy", label: "Данные и приватность", icon: Database },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function Profile() {
  const { notify } = useApp();
  const u = api.user();
  const [name, setName] = useState(u.fullName);
  return (
    <form
      className="max-w-[520px] space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        notify("Профиль сохранён (демо).");
      }}
    >
      <div className="flex items-center gap-4">
        <Avatar initials={u.initials} size={56} />
        <div>
          <p className="font-semibold">{u.fullName}</p>
          <p className="text-[13px] text-muted">{ROLE_LABEL[u.role]}</p>
        </div>
      </div>
      <Field id="p-name" label="Имя">
        <Input id="p-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
      </Field>
      <Field id="p-email" label="Email" hint="Используется для входа. Смена — через подтверждение по почте.">
        <Input id="p-email" value={u.email} disabled />
      </Field>
      <div className="flex gap-2">
        <Button type="submit">Сохранить</Button>
        <Link href="/reset-password" className={buttonCls("secondary")}>
          Сменить пароль
        </Link>
      </div>
    </form>
  );
}

function Workspace() {
  const { notify } = useApp();
  const [target, setTarget] = useState("700");
  const err = Number(target) > 0 ? undefined : "Целевой CPA должен быть больше нуля";
  return (
    <form
      className="max-w-[520px] space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!err) notify("Настройки пространства сохранены (демо).");
      }}
    >
      <Field id="w-name" label="Название">
        <Input id="w-name" defaultValue="Пилот Медиа" />
      </Field>
      <Field id="w-type" label="Тип">
        <Select id="w-type" className="w-full [&>select]:h-10" defaultValue="agency">
          <option value="agency">Агентство — несколько клиентов</option>
          <option value="business">Собственный бизнес</option>
        </Select>
      </Field>
      <Field id="w-cpa" label="Целевой CPA по умолчанию, ₽" hint="Источник «Настройки»: используется правилами, если у кампании нет своей цели." error={err}>
        <Input id="w-cpa" type="number" inputMode="numeric" min={1} value={target} onChange={(e) => setTarget(e.target.value)} error={err} />
      </Field>
      <Field id="w-tz" label="Часовой пояс">
        <Select id="w-tz" className="w-full [&>select]:h-10" defaultValue="msk">
          <option value="msk">Москва (UTC+3)</option>
          <option value="ekb">Екатеринбург (UTC+5)</option>
          <option value="nsk">Новосибирск (UTC+7)</option>
        </Select>
      </Field>
      <Button type="submit">Сохранить</Button>
    </form>
  );
}

function Team() {
  const { notify } = useApp();
  const [members, setMembers] = useState(api.team);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("analyst");
  const [error, setError] = useState<string>();
  const limit = api.plans().find((p) => p.id === api.subscription().plan_id)!.entitlements.seats;

  function invite(e: FormEvent) {
    e.preventDefault();
    if (!EMAIL_RE.test(email.trim())) return setError("Введите корректный email");
    if (members.some((m) => m.email === email.trim())) return setError("Этот человек уже в команде");
    setError(undefined);
    setMembers((m) => [...m, { name: email.trim(), email: email.trim(), role, last: "приглашение отправлено" }]);
    setEmail("");
    notify("Приглашение создано (демо — письмо не отправляется).");
  }

  return (
    <div className="space-y-5">
      <form onSubmit={invite} noValidate className="flex flex-wrap items-start gap-2">
        <Field id="t-email" label={<span className="sr-only">Email участника</span>} error={error} className="min-w-[240px] flex-1">
          <Input id="t-email" type="email" placeholder="email@company.ru" value={email} onChange={(e) => setEmail(e.target.value)} error={error} />
        </Field>
        <Select aria-label="Роль" className="[&>select]:h-10" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {(["admin", "analyst", "viewer"] as Role[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </Select>
        <Button type="submit" disabled={limit !== null && members.length >= limit}>
          Пригласить
        </Button>
      </form>
      <p className="text-[12px] text-muted">
        Участников: {members.length} из {limit ?? "∞"} по тарифу.
      </p>
      <ul className="divide-y divide-line rounded-xl border border-line">
        {members.map((m) => (
          <li key={m.email} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <Avatar initials={m.name.slice(0, 2).toUpperCase()} size={32} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold">{m.name}</span>
              <span className="block text-[12px] text-muted">
                {m.email} · {m.last}
              </span>
            </span>
            <Badge tone={m.role === "owner" ? "brand" : "neutral"}>{ROLE_LABEL[m.role]}</Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Roles() {
  const roles: Role[] = ["owner", "admin", "analyst", "viewer"];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[12px] text-muted">
            <th scope="col" className="py-2.5 pr-4 font-medium">
              Право
            </th>
            {roles.map((r) => (
              <th key={r} scope="col" className="px-3 py-2.5 text-center font-medium">
                {ROLE_LABEL[r]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {(Object.keys(PERMISSION_LABEL) as Permission[]).map((p) => (
            <tr key={p}>
              <td className="py-2.5 pr-4">{PERMISSION_LABEL[p]}</td>
              {roles.map((r) => (
                <td key={r} className="px-3 py-2.5 text-center">
                  {can(r, p) ? <span className="text-success" aria-label="Есть">●</span> : <span className="text-[#d0d5dd]" aria-label="Нет">○</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Notifications() {
  const [s, set] = useState({ digest: true, high: true, measured: true, weekly: false });
  const rows: [keyof typeof s, string, string][] = [
    ["digest", "Ежедневная сводка", "Утром — что произошло за сутки"],
    ["high", "Проблемы высокого приоритета", "Сразу, как только аудит их нашёл"],
    ["measured", "Результаты замеров", "Когда закончилось окно 7 дней после изменения"],
    ["weekly", "Еженедельный отчёт", "По понедельникам в 9:00"],
  ];
  return (
    <div className="divide-y divide-line">
      {rows.map(([k, t, h]) => (
        <div key={k} className="flex items-center justify-between gap-4 py-3.5">
          <div>
            <p className="text-[14px] font-medium">{t}</p>
            <p className="text-[12px] text-muted">{h} · email</p>
          </div>
          <Switch checked={s[k]} label={t} onChange={(v) => set({ ...s, [k]: v })} />
        </div>
      ))}
      <div className="flex items-center justify-between gap-4 py-3.5">
        <div>
          <p className="text-[14px] font-medium text-muted">Telegram</p>
          <p className="text-[12px] text-muted">Уведомления в Telegram</p>
        </div>
        <Badge>Скоро</Badge>
      </div>
    </div>
  );
}

function LinkCard({ text, href, label }: { text: string; href: string; label: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-bg p-4">
      <p className="text-[13px] text-muted">{text}</p>
      <Link href={href} className={buttonCls("secondary", "sm")}>
        {label}
      </Link>
    </div>
  );
}

function Privacy() {
  const { notify } = useApp();
  const [confirm, setConfirm] = useState(false);
  const [typed, setTyped] = useState("");
  return (
    <div className="space-y-5 text-[13px]">
      <p className="text-muted">Персональные данные обрабатываются по 152-ФЗ и хранятся на серверах в России. В LLM передаются только обезличенные агрегаты — без названий кампаний, текстов запросов, ПД и токенов.</p>
      <div className="flex flex-wrap gap-2">
        <Link href="/legal/privacy" className={buttonCls("secondary", "sm")}>
          Политика обработки ПД
        </Link>
        <Link href="/legal/pd-consent" className={buttonCls("secondary", "sm")}>
          Согласие на обработку ПД
        </Link>
        <Button size="sm" variant="secondary" onClick={() => notify("Выгрузка данных будет отправлена на email владельца (демо).")}>
          Выгрузить мои данные
        </Button>
      </div>
      <div className="rounded-xl border border-[#fecdca] p-4">
        <p className="font-semibold text-danger-ink">Удалить рабочее пространство</p>
        <p className="mt-1 text-muted">Подключения будут отозваны, данные удалены по истечении сроков хранения из политики. Действие необратимо.</p>
        <Button size="sm" variant="danger" className="mt-3" onClick={() => setConfirm(true)}>
          Удалить пространство
        </Button>
      </div>
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Удалить «Пилот Медиа»?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              disabled={typed !== "Пилот Медиа"}
              onClick={() => {
                setConfirm(false);
                notify("Демо: пространство не удалено — в демо-режиме это действие отключено.");
              }}
            >
              Удалить навсегда
            </Button>
          </>
        }
      >
        <Field id="del-confirm" label="Введите название пространства для подтверждения">
          <Input id="del-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Пилот Медиа" />
        </Field>
      </Modal>
    </div>
  );
}

const BODY: Record<SectionId, () => React.ReactNode> = {
  profile: Profile,
  workspace: Workspace,
  team: Team,
  roles: Roles,
  integrations: () => <LinkCard text="Яндекс Директ и Метрика подключены. Остальные платформы — в разработке." href="/integrations" label="Открыть интеграции" />,
  notifications: Notifications,
  safety: SafetySettings,
  billing: () => <LinkCard text="Пробный период тарифа Agency до 30 октября 2026." href="/billing" label="Тариф и использование" />,
  privacy: Privacy,
};

export function Settings() {
  const [section, setSection] = useState<SectionId>("profile");
  useEffect(() => {
    const fromHash = () => {
      const h = window.location.hash.slice(1);
      if (SECTIONS.some((s) => s.id === h)) setSection(h as SectionId);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);
  const current = SECTIONS.find((s) => s.id === section)!;
  const Body = BODY[section];

  return (
    <>
      <PageHeader title="Настройки" sub="Профиль, команда, безопасность и данные" />
      <div className="grid items-start gap-6 lg:grid-cols-[240px_1fr]">
        <nav aria-label="Разделы настроек" className="card p-2">
          <ul className="flex gap-1 overflow-x-auto lg:block lg:space-y-0.5">
            {SECTIONS.map((s) => (
              <li key={s.id} className="shrink-0">
                <a
                  href={`#${s.id}`}
                  aria-current={s.id === section ? "page" : undefined}
                  className={`flex h-9 items-center gap-2.5 rounded-lg px-3 text-[13px] whitespace-nowrap ${s.id === section ? "bg-brand-soft font-semibold text-brand" : "text-[#475467] hover:bg-surface-2"}`}
                >
                  <s.icon size={16} aria-hidden /> {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <Card className="p-6" aria-label={current.label}>
          <h2 className="mb-5 text-[17px] font-semibold">{section === "safety" ? "Контроль безопасности" : current.label}</h2>
          <Body />
        </Card>
      </div>
    </>
  );
}
