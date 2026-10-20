"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState, type ReactNode } from "react";
import { PageHeader, StateBox } from "@/components/ui";
import { ValueView } from "@/components/value-view";
import { RECOMMENDATIONS, TARGET_CPA, USER } from "@/lib/demo";
import { SETTINGS_KEY, readSettings, validSettings, writeSettings, type DemoSettings } from "./demo-settings";

const DEFAULT_SETTINGS: DemoSettings = {
  name: USER.name, account: USER.account, email: "demo@example.com", timezone: "msk",
  cpa: String(TARGET_CPA), problems: true, digest: false, effect: true,
};

const SECTIONS = [
  ["profile", "Профиль"],
  ["business", "Бизнес"],
  ["cpa", "Целевой CPA"],
  ["notify", "Уведомления"],
  ["integrations", "Интеграции"],
  ["billing", "Тариф и оплата"],
  ["security", "Безопасность"],
] as const;
const SECTION_ICON: Record<string, string> = { notify: "Bell", business: "Globe", billing: "CreditCard", security: "LockKeyhole" };

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

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)} className="flex w-full items-center justify-between py-2.5 text-left text-sm">
      {label}
      <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${on ? "bg-brand" : "bg-line"}`}>
        <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left] ${on ? "left-[18px]" : "left-0.5"}`} />
      </span>
    </button>
  );
}

export default function SettingsPage() {
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [ready, setReady] = useState(false);
  const { cpa } = settings;
  const cpaInvalid = cpa !== "" && (Number(cpa) <= 0 || Number(cpa) > 10_000_000);

  useEffect(() => {
    // Browser storage is read after hydration so server and first client render match.
    try {
      const saved = readSettings(localStorage);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setSettings(saved);
    } catch {
      setNotice("Не удалось загрузить настройки этого браузера. Можно сохранить их заново или сбросить.");
    }
    setReady(true);
  }, []);

  function update<K extends keyof DemoSettings>(key: K, value: DemoSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
    setNotice("");
  }

  function save() {
    const next = { ...settings, name: settings.name.trim(), account: settings.account.trim(), email: settings.email.trim() };
    if (!validSettings(next)) {
      setNotice("Проверьте имя, название аккаунта, email и целевой CPA (от 1 до 10 000 000 ₽ или пустое поле).");
      return;
    }
    try {
      writeSettings(localStorage, next);
      setSettings(next);
      setNotice("Демо-настройки сохранены в этом браузере. Реальные аккаунты и отправка уведомлений не изменены.");
    } catch {
      setNotice("Браузер не разрешил сохранить настройки. Ваши изменения остаются на этой странице.");
    }
  }

  function reset() {
    try {
      localStorage.removeItem(SETTINGS_KEY);
      setSettings(DEFAULT_SETTINGS);
      setNotice("Демо-настройки сброшены в этом браузере.");
    } catch {
      setNotice("Браузер не разрешил сбросить сохранённые настройки.");
    }
  }

  return (
    <>
      <PageHeader title="Настройки" sub="Демо-настройки сохраняются только в этом браузере и не влияют на реальные аккаунты. Используйте вымышленные данные." />
      <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
        <nav aria-label="Разделы настроек" className="reference-settings-nav">
          <a href="#profile" className="reference-settings-profile"><Image src="/figma/liquid/6-41157-img2.png" alt="" width={25} height={30} unoptimized/><span>{settings.name}<small>Владелец аккаунта</small></span></a>
          <ul className="flex flex-wrap gap-1 text-sm lg:sticky lg:top-24 lg:block lg:space-y-1">
            {SECTIONS.map(([id, t]) => (
              <li key={id}>
                <a href={`#${id}`} className="block rounded-lg px-3 py-2 text-muted hover:bg-surface-2 hover:text-text">
                  {SECTION_ICON[id] && <Image src={`/figma/liquid/6-41157-img${SECTION_ICON[id]}.svg`} alt="" width={24} height={24} unoptimized/>}
                  {t}
                </a>
              </li>
            ))}
          </ul>
          <Link href="/legal/offer" className="reference-settings-help"><Image src="/figma/liquid/6-41157-imgCircleHelp.svg" alt="" width={24} height={24} unoptimized/>Помощь и поддержка</Link>
        </nav>
        <div className="space-y-4">
          <Block id="profile" title="Профиль">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Имя">
                <input className={input} value={settings.name} onChange={(e) => update("name", e.target.value)} maxLength={80} required aria-invalid={!settings.name.trim()} disabled={!ready} />
              </Field>
              <Field label="Телефон для входа">
                <input className={`${input} text-muted`} defaultValue="+7 900 000-00-00" readOnly aria-readonly />
              </Field>
              <Field label="Email для чеков (необязательно)">
                <input className={input} type="email" value={settings.email} onChange={(e) => update("email", e.target.value)} autoComplete="email" maxLength={254} disabled={!ready} />
              </Field>
            </div>
          </Block>

          <Block id="business" title="Бизнес">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Название аккаунта">
                <input className={input} value={settings.account} onChange={(e) => update("account", e.target.value)} maxLength={120} required aria-invalid={!settings.account.trim()} disabled={!ready} />
              </Field>
              <Field label="Часовой пояс">
                <select className={input} value={settings.timezone} onChange={(e) => update("timezone", e.target.value)} disabled={!ready}>
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
                onChange={(e) => update("cpa", e.target.value.replace(/\D/g, "").slice(0, 9))}
                aria-invalid={cpaInvalid}
                disabled={!ready}
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
              <div>
                <Toggle label="Новые проблемы — в кабинете" on={settings.problems} onChange={(on) => update("problems", on)} />
                <p className="pb-2.5 text-xs text-muted">
                  Пример: «🔴 Новая проблема · Расход с признаками неэффективности <ValueView v={RECOMMENDATIONS[0].exposure} hint={false} className="font-semibold" /> · Открыть AdPilot». Без названий
                  клиентов, кампаний и запросов — подробности после входа.
                </p>
              </div>
              <Toggle label="Утренний дайджест по email" on={settings.digest} onChange={(on) => update("digest", on)} />
              <Toggle label="Замер эффекта после решения" on={settings.effect} onChange={(on) => update("effect", on)} />
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
              <li>Вход по номеру телефона и одноразовому коду из SMS. Пароля нет.</li>
              <li>Токены Яндекса хранятся в зашифрованном виде.</li>
              <li>Активная сессия: этот браузер.</li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn btn-secondary btn-sm" onClick={() => setNotice("В демо смена номера недоступна. Войдите в ваш личный аккаунт, чтобы управлять входом.")}>Сменить номер телефона</button>
              <button className="btn btn-secondary btn-sm" onClick={() => setNotice("Это демонстрационный кабинет. Реальные сессии пользователей не изменены.")}>Выйти на всех устройствах</button>
              <button className="btn btn-ghost btn-sm text-danger" onClick={() => setNotice("Это демонстрационные данные. Доступы Яндекса не подключены, реальные данные не удаляются.")}>Отозвать доступ и удалить данные</button>
            </div>
          </Block>
          <div className="card p-5 md:p-6">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-primary" onClick={save} disabled={!ready || cpaInvalid}>Сохранить демо-настройки</button>
              <button type="button" className="btn btn-secondary" onClick={reset} disabled={!ready}>Сбросить демо-настройки</button>
            </div>
            <p className="mt-3 text-xs text-muted">Сохранение относится только к этой странице демо. Уведомления не отправляются.</p>
            <p role="status" aria-live="polite" className="mt-3 text-sm text-brand">{notice}</p>
          </div>
        </div>
      </div>
    </>
  );
}
