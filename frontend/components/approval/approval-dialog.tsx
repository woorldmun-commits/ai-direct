"use client";

import { ArrowRight, Lock, RotateCcw, ShieldCheck } from "lucide-react";
import { useApp } from "@/components/layout/app-state";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { day, sources } from "@/lib/formatters";
import { can } from "@/lib/permissions";
import type { Risk } from "@/lib/types/domain";

const RISK: Record<Risk, [string, Tone]> = { low: ["Низкий", "success"], medium: ["Средний", "warning"], high: ["Высокий", "danger"] };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 sm:grid-cols-[120px_1fr] sm:gap-4">
      <dt className="text-[13px] text-muted">{label}</dt>
      <dd className="text-[14px]">{children}</dd>
    </div>
  );
}

/** v1: no change reaches the ad account without this explicit human confirmation. */
export function ApprovalDialog() {
  const { recs, approvalId, openApproval, decide } = useApp();
  const rec = recs.find((r) => r.id === approvalId);
  const a = rec?.approval;
  const close = () => openApproval(null);
  const allowed = can(api.user().role, "approve");

  function act(d: "approve" | "postpone" | "reject") {
    if (!rec) return;
    decide(rec.id, d);
    close();
  }

  return (
    <Modal
      open={!!a}
      onClose={close}
      title="Требуется подтверждение"
      width={560}
      footer={
        <>
          <Button variant="ghost" onClick={() => act("reject")} className="sm:mr-auto">
            Не выполнять
          </Button>
          <Button variant="secondary" onClick={() => act("postpone")}>
            Отложить
          </Button>
          <Button onClick={() => act("approve")} disabled={!allowed} icon={<ShieldCheck size={16} />}>
            Подтвердить
          </Button>
        </>
      }
    >
      {rec && a && (
        <>
          <p className="text-[13px] text-muted">
            {rec.client} · {rec.campaign}
          </p>
          <dl className="mt-2 divide-y divide-line">
            <Row label="Что изменится">
              <p className="font-semibold">{a.change}.</p>
              <p className="mt-0.5 text-[13px] text-muted">{a.object}</p>
              <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[13px]">
                <span className="num rounded-lg bg-surface-2 px-2.5 py-1">{a.before}</span>
                <ArrowRight size={15} className="text-subtle" aria-label="станет" />
                <span className="num rounded-lg bg-brand-soft px-2.5 py-1 font-semibold text-brand">{a.after}</span>
              </div>
            </Row>
            <Row label="Почему">{a.why}</Row>
            <Row label="Источник">
              {sources(rec.evidence.sources)}
              <span className="text-muted">
                {" "}
                · {day(rec.evidence.period.from)} — {day(rec.evidence.period.to)}
              </span>
            </Row>
            <Row label="Риск">
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={RISK[a.risk][1]} dot>
                  {RISK[a.risk][0]}
                </Badge>
                {a.reversible && (
                  <span className="inline-flex items-center gap-1 text-[12px] text-muted">
                    <RotateCcw size={13} aria-hidden /> Изменение можно откатить
                  </span>
                )}
              </span>
            </Row>
          </dl>
          <p className="mt-3 flex items-start gap-2 rounded-xl bg-bg px-3.5 py-3 text-[12px] text-muted">
            <Lock size={14} className="mt-0.5 shrink-0" aria-hidden />
            {allowed
              ? "Изменение будет отправлено в Яндекс Директ только после нажатия «Подтвердить». Через 7 дней AdPilot сравнит результат до и после."
              : "У вашей роли нет права подтверждать изменения. Попросите владельца или администратора."}
          </p>
        </>
      )}
    </Modal>
  );
}
