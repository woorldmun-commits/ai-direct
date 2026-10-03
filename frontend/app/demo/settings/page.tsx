"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { PageHeader, Section, StateBox } from "@/components/ui";
import { SYNC, TARGET_CPA, USER } from "@/lib/demo";

const INDEX = [
  ["integrations", "Подключения"],
  ["cpa", "Целевой CPA"],
  ["workspace", "Рабочее пространство"],
  ["team", "Участники и роли"],
  ["notify", "Уведомления"],
  ["billing", "Тариф и оплата"],
  ["security", "Безопасность и API"],
  ["data", "Данные и удаление"],
] as const;

const SOURCES = [
  { name: "Яндекс Директ", scope: "расходы · кампании · ставки", time: SYNC.direct, extra: "Аккаунт: Демо-аккаунт" },
  { name: "Яндекс Метрика", scope: "цели · конверсии", time: SYNC.metrika, extra: "Счётчик 12345678 · 3 цели" },
];

const STATES = [
  ["Синхронизация", "Загружаем статистику за 30 дней", "—"],
  ["Токен истёк", "Яндекс отозвал доступ; новые данные не приходят", "Переподключить"],
  ["Нет прав", "Аккаунт без доступа к статистике кампаний", "Обновить доступ"],
  ["Частичные данные", "Метрика недоступна — часть правил выключена", "Проверить"],
];

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      {children}
      <span className="caption mt-1 block">{label}</span>
    </label>
  );
}

function Toggle({ label, note, defaultOn = false }: { label: string; note?: string; defaultOn?: boolean }) {
  const [on, setOn] = useState(defaultOn);
  return (
    <button role="switch" aria-checked={on} onClick={() => setOn(!on)} className="flex w-full items-center justify-between gap-4 border-b border-line py-3 text-left">
      <span>
        <span className="block text-sm font-semibold">{label}</span>
        {note && <span className="caption">{note}</span>}
      </span>
      <span className={`flex h-6 w-11 shrink-0 items-center border p-0.5 ${on ? "justify-end border-brand bg-brand" : "justify-start border-rule bg-surface"}`}>
        <span className={`size-4 ${on ? "bg-on-brand" : "bg-rule"}`} />
      </span>
    </button>
  );
}

function Integrations() {
  return (
    <Section id="integrations" title="Подключения" aside={<span className="caption">Ошибок: 0</span>}>
      <div className="overflow-x-auto">
        <table className="mt-1 w-full min-w-[520px] text-sm">
          <tbody>
            {SOURCES.map((s) => (
              <tr key={s.name} className="border-b border-line align-top">
                <td className="py-3 pr-3">
                  <b>{s.name}</b>
                  <span className="caption block">{s.scope}</span>
                </td>
                <td className="py-3 pr-3">
                  <span className="badge text-success">● Подключено</span>
                  <span className="reqs mt-1 block">{s.extra}</span>
                </td>
                <td className="reqs py-3 pr-3 text-text">сегодня {s.time}</td>
                <td className="py-3 text-right">
                  <button className="btn btn-ghost btn-sm">Проверить</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4">
        <StateBox
          kind="empty"
          title="CRM и выручка — не подключены"
          text="Без фактической выручки ROI, ROAS и ДРР не считаются. CPA остаётся основной метрикой."
          action={
            <button className="btn btn-secondary btn-sm" disabled>
              Подключить — скоро
            </button>
          }
        />
      </div>
      <p className="mt-5 text-sm font-semibold">Как AdPilot сообщает о проблемах с подключением</p>
      <p className="caption">Статус здесь, уведомление в Telegram и строка на экране «Сегодня».</p>
      <table className="mt-2 w-full text-sm">
        <tbody>
          {STATES.map(([t, d, a]) => (
            <tr key={t} className="border-b border-line">
              <td className="w-36 py-2 pr-3 font-semibold">{t}</td>
              <td className="py-2 pr-3 text-muted">{d}</td>
              <td className="hidden py-2 text-right text-muted sm:table-cell">{a}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption mt-3">Яндекс — источник данных, а не способ входа. Доступ можно отозвать в любой момент.</p>
    </Section>
  );
}

function TargetCpa() {
  const [cpa, setCpa] = useState(String(TARGET_CPA));
  const invalid = cpa !== "" && (Number(cpa) <= 0 || Number(cpa) > 10_000_000);
  return (
    <Section id="cpa" title="Целевой CPA">
      <div className="mt-3 max-w-[260px]">
        <Field label="Сколько вы готовы платить за конверсию, ₽">
          <input
            className={`field money text-[20px] ${invalid ? "border-danger" : ""}`}
            inputMode="numeric"
            value={cpa}
            onChange={(e) => setCpa(e.target.value.replace(/\D/g, "").slice(0, 9))}
            aria-invalid={invalid}
          />
        </Field>
      </div>
      {invalid && <p className="mt-2 text-sm text-danger">Введите сумму от 1 до 10 000 000 ₽.</p>}
      {cpa === "" && (
        <div className="mt-4">
          <StateBox kind="insufficient" title="Целевой CPA не задан" text="Без него оценки идут от прошлого уровня. Укажите цель — рекомендации по ставкам станут точнее." />
        </div>
      )}
    </Section>
  );
}

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Настройки" sub="Как подключено и кто имеет доступ." />
      <div className="grid gap-10 lg:grid-cols-[190px_1fr]">
        <nav className="hidden lg:block" aria-label="Разделы настроек">
          <ol className="sticky top-24 text-sm">
            {INDEX.map(([id, t]) => (
              <li key={id}>
                <a href={`#${id}`} className="block border-b border-line py-2 text-muted hover:text-text">
                  {t}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="max-w-[760px] min-w-0 space-y-12">
          <Integrations />
          <TargetCpa />

          <Section id="workspace" title="Рабочее пространство и кабинеты">
            <div className="mt-3 grid gap-5 sm:grid-cols-2">
              <Field label="Название рабочего пространства">
                <input className="field" defaultValue={USER.workspace} maxLength={120} />
              </Field>
              <Field label="Часовой пояс отчётов">
                <select className="field" defaultValue="msk">
                  <option value="msk">Москва (UTC+3)</option>
                  <option value="ekb">Екатеринбург (UTC+5)</option>
                  <option value="nsk">Новосибирск (UTC+7)</option>
                </select>
              </Field>
            </div>
            <p className="mt-5 flex justify-between gap-3 border-b border-line py-2 text-sm">
              <span>
                <b>{USER.account}</b> <span className="caption">· Яндекс Директ</span>
              </span>
              <span className="caption">основной кабинет</span>
            </p>
            <p className="caption mt-2">Агентства ведут несколько клиентских пространств и переключаются между ними в боковой панели.</p>
          </Section>

          <Section id="team" title="Участники и роли">
            <table className="mt-1 w-full text-sm">
              <tbody>
                <tr className="border-b border-line">
                  <td className="py-2.5 font-semibold">{USER.name}</td>
                  <td className="reqs py-2.5 text-text">demo@example.com</td>
                  <td className="py-2.5 text-right">Владелец</td>
                </tr>
              </tbody>
            </table>
            <ul className="caption mt-3 space-y-1">
              <li>Владелец — одобряет и применяет изменения, управляет тарифом.</li>
              <li>Маркетолог — готовит решения; в агентствах одобрение и применение — разные роли.</li>
              <li>Наблюдатель — только чтение, удобно для клиента агентства.</li>
            </ul>
            <button className="btn btn-secondary btn-sm mt-4" disabled>
              Пригласить участника — в рабочей версии
            </button>
          </Section>

          <Section id="notify" title="Уведомления">
            <Toggle label="Утренний дайджест в Telegram" note="потери ≈, что изменилось, что требует решения" defaultOn />
            <Toggle label="Недельный отчёт собственнику" note="сколько потрачено и сколько сэкономлено ≈" defaultOn />
            <Toggle label="Новая проблема — сразу" />
            <Toggle label="Ошибки подключений" note="отозванный токен, нет прав, частичные данные" defaultOn />
          </Section>

          <Section id="billing" title="Тариф и оплата">
            <div className="mt-3 flex flex-wrap items-center justify-between gap-4 border border-rule p-4">
              <div>
                <p className="font-semibold">Бесплатный аудит</p>
                <p className="text-sm text-muted">Один раз на кабинет, только чтение, без ежедневной сверки.</p>
              </div>
              <Link href="/#pricing" className="btn btn-ink">
                Продолжить мониторинг
              </Link>
            </div>
            <p className="caption mt-2">Подписка продлевается только с вашего согласия; о списании предупредим за 3 дня.</p>
          </Section>

          <Section id="security" title="Безопасность и API-доступ">
            <ul className="mt-3 space-y-1.5 text-sm">
              <li>Вход по email и паролю. Пароль хранится только в виде хеша.</li>
              <li>Токены Яндекса хранятся в зашифрованном виде.</li>
              <li>Активная сессия: этот браузер.</li>
              <li>API-ключи для своих систем — в рабочей версии.</li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn btn-secondary btn-sm">Сменить пароль</button>
              <button className="btn btn-secondary btn-sm">Выйти на всех устройствах</button>
            </div>
          </Section>

          <Section id="data" title="Данные и удаление">
            <p className="mt-3 max-w-[70ch] text-sm text-muted">
              Данные обрабатываются по 152-ФЗ. Можно выгрузить историю решений или удалить аккаунт: доступы Яндекса будут отозваны, данные удалены.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn btn-secondary btn-sm">Выгрузить историю</button>
              <button className="btn btn-ghost btn-sm text-danger">Отозвать доступ и удалить данные</button>
            </div>
          </Section>
        </div>
      </div>
    </>
  );
}
