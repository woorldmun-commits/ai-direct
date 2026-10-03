"use client";

import { Check, CreditCard, Receipt } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Meter, PageHeader } from "@/components/ui/misc";
import { Modal } from "@/components/ui/overlay";
import { EmptyState } from "@/components/ui/states";
import { api } from "@/lib/api";
import { day, rub } from "@/lib/formatters";
import type { Entitlements, Plan } from "@/lib/types/domain";

const ENT_LABEL: Record<keyof Entitlements, string> = { clients: "Клиенты", ad_accounts: "Рекламные кабинеты", seats: "Участники команды", connections: "Подключения" };

/** Price comes from configuration; null means terms are not approved — never a made-up number. */
export function PlanPrice({ plan }: { plan: Plan }) {
  if (!plan.price) return <span className="text-[15px] font-semibold text-muted">Стоимость уточняется</span>;
  return (
    <span className="text-[22px] font-semibold">
      {plan.price.amount === 0 ? "Бесплатно" : rub(plan.price.amount)} <span className="text-[13px] font-normal text-muted">{plan.price.per}</span>
    </span>
  );
}

export function Billing() {
  const { notify } = useApp();
  const sub = api.subscription();
  const usage = api.usage();
  const plans = api.plans();
  const plan = plans.find((p) => p.id === sub.plan_id)!;
  const [cancel, setCancel] = useState(false);
  const [request, setRequest] = useState<Plan | null>(null);

  return (
    <>
      <PageHeader title="Тариф и оплата" sub="Подписка, использование лимитов, оплата и счета" />
      <div className="grid items-start gap-6 xl:grid-cols-3">
        <Card className="p-6 xl:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[18px] font-semibold">{plan.name}</h2>
                <Badge tone="brand">{sub.status === "trial" ? "Пробный период" : "Активна"}</Badge>
              </div>
              <p className="mt-1 text-[13px] text-muted">{plan.description}</p>
              <p className="mt-3">
                <PlanPrice plan={plan} />
              </p>
            </div>
            <div className="text-right text-[13px]">
              <p className="text-muted">Пробный период до</p>
              <p className="font-semibold">{sub.trial_ends_at ? day(sub.trial_ends_at) + " 2026" : "—"}</p>
              <p className="mt-1 text-[12px] text-muted">Автопродления нет</p>
            </div>
          </div>
          <div className="mt-6 grid gap-5 border-t border-line pt-5 sm:grid-cols-2">
            {(Object.keys(ENT_LABEL) as (keyof Entitlements)[]).map((k) => (
              <Meter key={k} label={ENT_LABEL[k]} used={usage[k]} limit={plan.entitlements[k]} />
            ))}
          </div>
          <p className="mt-5 text-[12px] text-muted">Модель тарификации (по кабинетам или по участникам) ещё выбирается. Лимиты выше — права тарифа, а не цена.</p>
        </Card>

        <div className="space-y-6">
          <Card className="p-5">
            <CardHeader title="Способ оплаты" />
            <EmptyState compact icon={<CreditCard size={20} />} title="Способ оплаты не добавлен" text="Оплата станет доступна после утверждения тарифов. Сейчас списаний нет." />
          </Card>
          <Card className="p-5">
            <CardHeader title="Подписка" />
            <p className="mt-2 text-[13px] text-muted">Отменить можно в любой момент — доступ сохранится до конца оплаченного периода.</p>
            <Button variant="danger" size="sm" className="mt-4" onClick={() => setCancel(true)}>
              Отменить подписку
            </Button>
          </Card>
        </div>
      </div>

      <h2 className="mt-8 mb-3 text-[16px] font-semibold">Тарифы</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {plans.map((p) => (
          <Card key={p.id} className={`flex flex-col p-5 ${p.id === plan.id ? "ring-2 ring-brand" : ""}`}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-[15px] font-semibold">{p.name}</h3>
              {p.id === plan.id && <Badge tone="brand">Текущий</Badge>}
            </div>
            <p className="text-[12px] text-muted">{p.description}</p>
            <p className="mt-3">
              <PlanPrice plan={p} />
            </p>
            <ul className="mt-4 space-y-1.5 text-[13px]">
              {(Object.keys(ENT_LABEL) as (keyof Entitlements)[]).map((k) => (
                <li key={k} className="flex justify-between gap-2">
                  <span className="text-muted">{ENT_LABEL[k]}</span>
                  <span className="num font-medium">{p.entitlements[k] ?? "без лимита"}</span>
                </li>
              ))}
            </ul>
            <ul className="mt-4 space-y-1.5 border-t border-line pt-4 text-[13px]">
              {p.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <Check size={15} className="mt-0.5 shrink-0 text-success" aria-hidden /> {f}
                </li>
              ))}
            </ul>
            <div className="mt-auto pt-5">
              <Button size="sm" variant={p.id === plan.id ? "secondary" : "primary"} className="w-full" disabled={p.id === plan.id} onClick={() => setRequest(p)}>
                {p.id === plan.id ? "Ваш тариф" : "Оставить заявку"}
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-6 p-5">
        <CardHeader title="Счета" />
        <EmptyState compact icon={<Receipt size={20} />} title="Счетов пока нет" text="Они появятся здесь после первой оплаты." />
      </Card>

      <Modal
        open={cancel}
        onClose={() => setCancel(false)}
        title="Отменить подписку?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancel(false)}>
              Оставить
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setCancel(false);
                notify("Подписка будет отменена в конце пробного периода (демо).");
              }}
            >
              Отменить подписку
            </Button>
          </>
        }
      >
        <p className="text-[14px] text-muted">Аудит и рекомендации перестанут обновляться после 30 октября. История решений и отчёты останутся доступны для выгрузки.</p>
      </Modal>
      <Modal
        open={!!request}
        onClose={() => setRequest(null)}
        title={`Тариф ${request?.name ?? ""}`}
        footer={
          <Button
            onClick={() => {
              setRequest(null);
              notify("Заявка принята (демо). Менеджер свяжется с вами по email.");
            }}
          >
            Оставить заявку
          </Button>
        }
      >
        <p className="text-[14px] text-muted">Коммерческие условия тарифа ещё утверждаются. Оставьте заявку — мы пришлём условия и подключим тариф вручную.</p>
      </Modal>
    </>
  );
}
