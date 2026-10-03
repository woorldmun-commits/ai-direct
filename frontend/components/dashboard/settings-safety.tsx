"use client";

import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useApp } from "@/components/layout/app-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/field";
import { Segmented } from "@/components/ui/tabs";

function Row({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 py-4">
      <div className="max-w-[52ch]">
        <p className="text-[14px] font-medium">{title}</p>
        <p className="text-[12px] text-muted">{hint}</p>
      </div>
      {children}
    </div>
  );
}

/** «Контроль безопасности»: thresholds Safety agent uses before any conclusion. */
export function SafetySettings() {
  const { notify } = useApp();
  const [freshness, setFreshness] = useState("24");
  const [minConv, setMinConv] = useState("10");
  const [sensitivity, setSensitivity] = useState<"conservative" | "balanced" | "sensitive">("balanced");
  const [error, setError] = useState<string>();

  function save(e: FormEvent) {
    e.preventDefault();
    const n = Number(minConv);
    if (!Number.isInteger(n) || n < 10 || n > 500) {
      setError("Введите целое число от 10 до 500. Меньше 10 конверсий — слишком мало для вывода.");
      return;
    }
    setError(undefined);
    notify("Пороги безопасности сохранены (демо).");
  }

  return (
    <form onSubmit={save}>
      <div className="mb-2 flex items-start gap-3 rounded-xl border border-[#abefc6] bg-success-soft p-4">
        <ShieldCheck size={18} className="mt-0.5 shrink-0 text-success" aria-hidden />
        <div>
          <p className="text-[13px] font-semibold text-success-ink">По умолчанию: никаких автоматических изменений.</p>
          <p className="text-[12px] text-[#05603a]">Каждое изменение в кабинете требует подтверждения человека. В версии 1.0 это нельзя отключить.</p>
        </div>
      </div>
      <div className="divide-y divide-line">
        <Row title="Минимальная свежесть данных" hint="Старше — Safety agent не даёт делать выводы">
          <Select aria-label="Свежесть данных" value={freshness} onChange={(e) => setFreshness(e.target.value)}>
            <option value="12">12 часов</option>
            <option value="24">24 часа</option>
            <option value="48">48 часов</option>
          </Select>
        </Row>
        <Row title="Минимум конверсий" hint="Ниже порога рекомендация не формируется">
          <Field id="min-conv" label={<span className="sr-only">Минимум конверсий</span>} error={error} className="w-[140px]">
            <Input id="min-conv" type="number" inputMode="numeric" min={10} max={500} value={minConv} onChange={(e) => setMinConv(e.target.value)} error={error} />
          </Field>
        </Row>
        <Row title="Чувствительность рекомендаций" hint="Как сильно метрика должна отклониться, чтобы появилась находка">
          <Segmented
            label="Чувствительность"
            value={sensitivity}
            onChange={setSensitivity}
            options={[
              { value: "conservative", label: "Осторожно" },
              { value: "balanced", label: "Сбалансировано" },
              { value: "sensitive", label: "Чутко" },
            ]}
          />
        </Row>
        <Row title="Подтверждение обязательно" hint="Изменения применяются только после решения человека с нужной ролью">
          <span className="flex items-center gap-3">
            <Badge tone="success">Всегда</Badge>
            <Switch checked label="Подтверждение обязательно" onChange={() => {}} disabled />
          </span>
        </Row>
        <Row title="Автоматическое применение" hint="Недоступно в версии 1.0: AdPilot ничего не меняет сам">
          <span className="flex items-center gap-3">
            <Badge>Выключено</Badge>
            <Switch checked={false} label="Автоматическое применение" onChange={() => {}} disabled />
          </span>
        </Row>
      </div>
      <div className="mt-4 flex justify-end">
        <Button type="submit">Сохранить</Button>
      </div>
    </form>
  );
}
