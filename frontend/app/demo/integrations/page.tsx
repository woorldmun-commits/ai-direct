import { AlertTriangle, BarChart3, CheckCircle2, KeyRound, Loader2, Megaphone, PlugZap, ShieldAlert, Wallet } from "lucide-react";
import { PageHeader, StateBox } from "@/components/ui";
import { SYNC } from "@/lib/demo";

const STATES = [
  { icon: CheckCircle2, tone: "text-success bg-success-bg", title: "Подключено", text: "Данные обновляются каждый день.", action: "Проверить синхронизацию" },
  { icon: Loader2, tone: "text-info bg-info-bg", title: "Синхронизация", text: "Загружаем статистику за 30 дней.", action: null, spin: true },
  { icon: AlertTriangle, tone: "text-danger bg-danger-bg", title: "Недоступно", text: "Доступ к Яндекс Директ недоступен.", action: "Переподключить" },
  { icon: ShieldAlert, tone: "text-warning bg-warning-bg", title: "Нет прав", text: "Аккаунт без доступа к статистике кампаний.", action: "Обновить доступ" },
  { icon: KeyRound, tone: "text-warning bg-warning-bg", title: "Токен истёк", text: "Яндекс отозвал доступ или истёк срок токена.", action: "Переподключить" },
  { icon: PlugZap, tone: "text-warning bg-warning-bg", title: "Частичные данные", text: "Метрика недоступна. Часть диагностик временно ограничена.", action: "Проверить синхронизацию" },
];

function Source({ icon: Icon, name, time, scope, rows }: { icon: typeof Megaphone; name: string; time: string; scope: string; rows: [string, string][] }) {
  return (
    <article className="card p-5">
      <div className="flex items-start gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-brand-soft text-brand">
          <Icon size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-bold">{name}</h2>
            <span className="badge bg-success-bg text-success">
              <span className="size-1.5 rounded-full bg-success" /> Подключено
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">{scope}</p>
        </div>
      </div>
      <dl className="mt-4 space-y-1.5 text-sm">
        {[...rows, ["Последняя синхронизация", `сегодня, ${time}`] as [string, string]].map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4">
            <dt className="text-muted">{k}</dt>
            <dd className="font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
        <button className="btn btn-secondary btn-sm">Управлять</button>
        <button className="btn btn-ghost btn-sm">Проверить синхронизацию</button>
      </div>
    </article>
  );
}

export default function Integrations() {
  return (
    <>
      <PageHeader title="Интеграции" sub="Яндекс — подключаемый источник данных, а не способ входа. AdPilot читает статистику и не вносит изменений в рекламу." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Source icon={Megaphone} name="Яндекс Директ" time={SYNC.direct} scope="Расходы · кампании · CPA" rows={[["Аккаунт", "Демо-аккаунт"]]} />
        <Source icon={BarChart3} name="Яндекс Метрика" time={SYNC.metrika} scope="Цели · конверсии · диагностика" rows={[["Счётчик", "12345678"], ["Цели", "3"]]} />
      </div>

      <div className="mt-4">
        <StateBox
          kind="empty"
          title="Источник выручки не подключён"
          text="Без фактической выручки ROAS и ДРР не считаются. CPA остаётся основной метрикой."
          action={
            <button className="btn btn-secondary btn-sm" disabled>
              <Wallet size={15} /> Подключить — скоро
            </button>
          }
        />
      </div>

      <h2 className="mt-10 text-xl font-bold">Как выглядят состояния подключения</h2>
      <p className="text-sm text-muted">Примеры для демо: так AdPilot сообщает о проблемах с доступом.</p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {STATES.map((s) => (
          <li key={s.title} className="card flex gap-3 p-4">
            <span className={`grid size-9 shrink-0 place-items-center rounded-full ${s.tone}`}>
              <s.icon size={16} className={s.spin ? "animate-spin" : ""} />
            </span>
            <div className="min-w-0">
              <p className="font-semibold">{s.title}</p>
              <p className="text-sm text-muted">{s.text}</p>
              {s.action && <button className="btn btn-secondary btn-sm mt-3">{s.action}</button>}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
