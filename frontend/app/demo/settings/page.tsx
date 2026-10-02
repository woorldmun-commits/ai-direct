"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { PageHeader, StateBox } from "@/components/ui";
import { TARGET_CPA, USER } from "@/lib/demo";

const SECTIONS = [
  ["profile", "Профиль"],
  ["business", "Бизнес"],
  ["cpa", "Целевой CPA"],
  ["notify", "Уведомления"],
  ["integrations", "Интеграции"],
  ["billing", "Тариф и оплата"],
  ["security", "Безопасность"],
] as const;

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="card scroll-mt-24 p-5 md:p-6" aria-labelledby={`${id}-t`}>
      <h2 id={`${id}-t`} className="mb-4 text-lg font-bold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const input = "h-11 w-full rounded-xl border border-line bg-surface px-3 outline-none focus:border-brand";

function Toggle({ label, defaultOn = false }: { label: string; defaultOn?: boolean }) {
  const [on, setOn] = useState(defaultOn);
  return (
    <button role="switch" aria-checked={on} onClick={() => setOn(!on)} className="flex w-full items-center justify-between py-2.5 text-left text-sm">
      {label}
      <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${on ? "bg-brand" : "bg-line"}`}>
        <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left] ${on ? "left-[18px]" : "left-0.5"}`} />
      </span>
    </button>
  );
}

export default function SettingsPage() {
  const [cpa, setCpa] = useState(String(TARGET_CPA));
  const cpaInvalid = cpa !== "" && (Number(cpa) <= 0 || Number(cpa) > 10_000_000);

  return (
    <>
      <PageHeader title="Настройки" />
      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <nav className="hidden lg:block" aria-label="Разделы настроек">
          <ul className="sticky top-24 space-y-1 text-sm">
            {SECTIONS.map(([id, t]) => (
              <li key={id}>
                <a href={`#${id}`} className="block rounded-lg px-3 py-2 text-muted hover:bg-surface-2 hover:text-text">
                  {t}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="space-y-4">
          <Block id="profile" title="Профиль">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Имя">
                <input className={input} defaultValue={USER.name} maxLength={80} />
              </Field>
              <Field label="Email">
                <input className={input} type="email" defaultValue="demo@example.com" autoComplete="email" maxLength={254} />
              </Field>
            </div>
          </Block>

          <Block id="business" title="Бизнес">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Название аккаунта">
                <input className={input} defaultValue={USER.account} maxLength={120} />
              </Field>
              <Field label="Часовой пояс">
                <select className={input} defaultValue="msk">
                  <option value="msk">Москва (UTC+3)</option>
                  <option value="ekb">Екатеринбург (UTC+5)</option>
                  <option value="nsk">Новосибирск (UTC+7)</option>
                </select>
              </Field>
            </div>
          </Block>

          <Block id="cpa" title="Целевой CPA">
            <Field label="Сколько вы готовы платить за конверсию, ₽">
              <input
                className={`${input} max-w-[240px] ${cpaInvalid ? "border-danger" : ""}`}
                inputMode="numeric"
                value={cpa}
                onChange={(e) => setCpa(e.target.value.replace(/\D/g, "").slice(0, 9))}
                aria-invalid={cpaInvalid}
              />
            </Field>
            {cpaInvalid && <p className="mt-2 text-sm text-danger">Введите сумму от 1 до 10 000 000 ₽.</p>}
            {cpa === "" && (
              <div className="mt-4">
                <StateBox kind="insufficient" title="Целевой CPA не задан" text="Укажите его, чтобы получать рекомендации по ставке." />
              </div>
            )}
          </Block>

          <Block id="notify" title="Уведомления">
            <div className="divide-y divide-line">
              <Toggle label="Новые проблемы — в Telegram" defaultOn />
              <Toggle label="Ежедневная сводка на почту" />
              <Toggle label="Замер эффекта после решения" defaultOn />
            </div>
          </Block>

          <Block id="integrations" title="Интеграции">
            <p className="text-sm text-muted">Яндекс Директ и Яндекс Метрика подключены.</p>
            <Link href="/demo/integrations" className="btn btn-secondary btn-sm mt-3">
              Управлять интеграциями
            </Link>
          </Block>

          <Block id="billing" title="Тариф и оплата">
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-surface-2 p-4">
              <div>
                <p className="font-semibold">Бесплатный аудит</p>
                <p className="text-sm text-muted">Результат только для чтения, без ежедневного мониторинга.</p>
              </div>
              <Link href="/#pricing" className="btn btn-primary">
                Продолжить мониторинг
              </Link>
            </div>
          </Block>

          <Block id="security" title="Безопасность">
            <ul className="space-y-2 text-sm">
              <li>Вход по email и паролю. Пароль хранится только в виде хеша.</li>
              <li>Токены Яндекса хранятся в зашифрованном виде.</li>
              <li>Активная сессия: этот браузер.</li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn btn-secondary btn-sm">Сменить пароль</button>
              <button className="btn btn-secondary btn-sm">Выйти на всех устройствах</button>
              <button className="btn btn-ghost btn-sm text-danger">Отозвать доступ и удалить данные</button>
            </div>
          </Block>
        </div>
      </div>
    </>
  );
}
