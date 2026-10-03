import type { Kpi } from "@/lib/types/domain";
import { NoData } from "@/components/ui/states";
import { Delta, ValueMeta, ValueText } from "@/components/ui/value";

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const v = kpi.value;
  return (
    <div className="card flex flex-col p-5">
      <p className="text-[13px] font-medium text-muted">{kpi.label}</p>
      {v.calculation_type === "unavailable" ? (
        <NoData className="mt-3" why={v.missing} />
      ) : (
        <>
          <p className="mt-2 text-[26px] leading-8 font-semibold tracking-[-0.02em]">
            <ValueText value={v} />
          </p>
          <div className="mt-1.5">
            <Delta value={kpi.delta} goodWhenDown={kpi.goodWhenDown} />
          </div>
        </>
      )}
      <div className="mt-auto pt-4">
        <ValueMeta value={v} className="border-t border-line pt-3" />
      </div>
    </div>
  );
}

export function KpiGrid({ kpis }: { kpis: Kpi[] }) {
  return (
    <div className={`grid gap-4 sm:grid-cols-2 ${kpis.length > 4 ? "xl:grid-cols-3 2xl:grid-cols-6" : "xl:grid-cols-4"}`}>
      {kpis.map((k) => (
        <KpiCard key={k.id} kpi={k} />
      ))}
    </div>
  );
}
