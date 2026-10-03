import { Ban, CheckCircle2, EyeOff, FileSearch, Lock, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { AgentPipeline, KIND_LABEL } from "@/components/agents/agent-pipeline";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";
import { api } from "@/lib/api";
import type { AgentKind } from "@/lib/types/domain";

export const metadata: Metadata = { title: "AI-агенты" };

const PRINCIPLES = [
  { icon: Lock, title: "Без подтверждения — без изменений", text: "Ни одна ставка или бюджет не меняются без решения пользователя с нужной ролью." },
  { icon: FileSearch, title: "Прозрачные объяснения", text: "У каждого вывода есть источник, период, правило, формула и снимок данных." },
  { icon: Ban, title: "Нет данных — нет вывода", text: "Если данных недостаточно, Safety agent скрывает рекомендацию и говорит, что подключить." },
  { icon: CheckCircle2, title: "Числа считает код", text: "LLM объясняет и формулирует гипотезы, но не вводит чисел, которых нет во входных данных." },
  { icon: EyeOff, title: "В LLM — только агрегаты", text: "Без названий кампаний, текстов запросов, персональных данных и токенов." },
];

export default function AgentsPage() {
  const agents = api.agents();
  const counts = agents.reduce<Record<AgentKind, number>>((a, x) => ({ ...a, [x.kind]: a[x.kind] + 1 }), { deterministic: 0, llm: 0, human: 0 });
  return (
    <>
      <PageHeader title="AI-агенты" sub="Цепочка ролей для безопасной и точной работы с данными. Не все шаги — LLM." />
      <div className="grid items-start gap-6 xl:grid-cols-3">
        <Card className="p-5 xl:col-span-2">
          <CardHeader title="Конвейер решения" sub="От данных до замера результата · последний прогон сегодня в 10:42" />
          <div className="mt-5">
            <AgentPipeline agents={agents} />
          </div>
        </Card>
        <div className="space-y-6">
          <Card className="p-5">
            <CardHeader title="Принципы работы" />
            <ul className="mt-4 space-y-4">
              {PRINCIPLES.map((p) => (
                <li key={p.title} className="flex gap-3">
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
                    <p.icon size={16} aria-hidden />
                  </span>
                  <span>
                    <span className="block text-[13px] font-semibold">{p.title}</span>
                    <span className="block text-[12px] text-muted">{p.text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <CardHeader title="Кто что делает" />
            <ul className="mt-4 space-y-3">
              {(Object.keys(KIND_LABEL) as AgentKind[]).map((k) => (
                <li key={k} className="flex items-center gap-3 text-[13px]">
                  <Badge tone={k === "llm" ? "brand" : k === "human" ? "warning" : "neutral"}>{KIND_LABEL[k].label}</Badge>
                  <span className="flex-1 text-muted">{KIND_LABEL[k].hint}</span>
                  <span className="num font-semibold">{counts[k]}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <CardHeader title="Политика безопасности" sub="safety_policy@2" action={<ShieldCheck size={18} className="text-success" />} />
            <dl className="mt-4 space-y-2 text-[13px]">
              {[
                ["Свежесть данных", "не старше 24 часов"],
                ["Минимум конверсий", "10 за период правила"],
                ["Период", "7 полных дней"],
                ["Автоприменение", "выключено"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <Link href="/settings#safety" className="mt-4 inline-block text-[13px] font-medium text-brand hover:underline">
              Настроить пороги
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}
