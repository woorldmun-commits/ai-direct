"use client";

import { BarChart3, Megaphone, RefreshCw, Send, ShieldCheck, ShoppingBag, Store } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/formatters";
import type { Integration, IntegrationStatus } from "@/lib/types/domain";

const STATUS: Record<IntegrationStatus, [string, Tone]> = {
  connected: ["Подключено", "success"],
  not_connected: ["Не подключено", "neutral"],
  error: ["Ошибка", "danger"],
  soon: ["Скоро", "neutral"],
};
const LOGO: Record<string, [React.ReactNode, string]> = {
  yandex_direct: [<span key="d" className="text-[15px] font-bold">Я</span>, "bg-[#fff1e6] text-[#e04f16]"],
  yandex_metrika: [<BarChart3 key="m" size={18} />, "bg-[#fff1e6] text-[#e04f16]"],
  vk_ads: [<Megaphone key="v" size={18} />, "bg-[#eff6ff] text-sky"],
  telegram_ads: [<Send key="t" size={18} />, "bg-[#eff6ff] text-sky"],
  ozon: [<ShoppingBag key="o" size={18} />, "bg-[#eef0ff] text-brand"],
  wildberries: [<Store key="w" size={18} />, "bg-[#f4f0ff] text-violet"],
};

function IntegrationCard({ i }: { i: Integration }) {
  const { notify } = useApp();
  const [syncing, setSyncing] = useState(false);
  const [logo, tint] = LOGO[i.id];
  return (
    <article className={`card flex flex-col p-5 ${i.status === "soon" ? "bg-[#fcfcfd]" : ""}`}>
      <div className="flex items-start gap-3">
        <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${tint}`} aria-hidden>
          {logo}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={`text-[15px] font-semibold ${i.status === "soon" ? "text-muted" : ""}`}>{i.name}</h3>
          <p className="text-[12px] text-muted">{i.description}</p>
        </div>
        <Badge tone={STATUS[i.status][1]} dot={i.status !== "soon"}>
          {STATUS[i.status][0]}
        </Badge>
      </div>
      {i.status === "connected" && (
        <dl className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-bg p-3 text-[12px]">
          <div>
            <dt className="text-muted">{i.id === "yandex_metrika" ? "Счётчики" : "Кабинеты"}</dt>
            <dd className="num text-[14px] font-semibold">{i.accounts}</dd>
          </div>
          <div>
            <dt className="text-muted">Синхронизация</dt>
            <dd className="text-[13px] font-medium">{i.last_sync ? dateTime(i.last_sync) : "—"}</dd>
          </div>
        </dl>
      )}
      <div className="mt-auto flex gap-2 pt-4">
        {i.status === "connected" ? (
          <>
            <Button
              size="sm"
              variant="secondary"
              loading={syncing}
              icon={<RefreshCw size={14} />}
              onClick={() => {
                setSyncing(true);
                setTimeout(() => {
                  setSyncing(false);
                  notify(`${i.name}: синхронизация завершена (демо).`);
                }, 1200);
              }}
            >
              Синхронизировать
            </Button>
            <Button size="sm" variant="ghost" onClick={() => notify("Настройки доступа откроются после подключения API.")}>
              Настроить
            </Button>
          </>
        ) : i.status === "soon" ? (
          <Button size="sm" variant="secondary" disabled>
            Скоро
          </Button>
        ) : (
          <Button size="sm">Подключить</Button>
        )}
      </div>
    </article>
  );
}

export function Integrations() {
  const { notify } = useApp();
  const [errors, setErrors] = useState(api.syncErrors);
  const list = api.integrations();
  return (
    <>
      <PageHeader title="Интеграции" sub="Источники данных для аудита. Сейчас работают Яндекс Директ и Яндекс Метрика." />
      {errors.length > 0 && (
        <div className="mb-6 space-y-3">
          {errors.map((e) => (
            <ErrorState
              key={e.reference}
              title={e.message}
              integration={`${e.integration} · кабинет ${e.account}`}
              at={e.at}
              reference={e.reference}
              onRetry={() => {
                setErrors((all) => all.filter((x) => x.reference !== e.reference));
                notify("Повторная синхронизация запущена (демо).");
              }}
            />
          ))}
        </div>
      )}
      <h2 className="mb-3 text-[15px] font-semibold">Подключены</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {list
          .filter((i) => i.status !== "soon")
          .map((i) => (
            <IntegrationCard key={i.id} i={i} />
          ))}
      </div>
      <h2 className="mt-8 mb-3 text-[15px] font-semibold">В разработке</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {list
          .filter((i) => i.status === "soon")
          .map((i) => (
            <IntegrationCard key={i.id} i={i} />
          ))}
      </div>
      <p className="mt-8 flex items-start gap-2 text-[13px] text-muted">
        <ShieldCheck size={16} className="mt-0.5 shrink-0 text-success" aria-hidden />
        Кабинеты подключаются через Яндекс OAuth — AdPilot не видит ваш пароль. Доступ можно отозвать в любой момент в настройках Яндекс ID.
      </p>
    </>
  );
}
