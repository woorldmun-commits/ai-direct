"""MVP-0: прогон одного реального аккаунта без БД и без UI — Метрика → определение конверсии → отчёты Директа →
снимок → проверки семантики → контекст кампаний → правила → safety_policy@1 → объяснения.

Только чтение. Токены — из окружения, в вывод и лог не попадают; названия кампаний не печатаются (только id).

  set YANDEX_API_TOKEN=...          (права direct:api и metrika:read; для песочницы — токен песочницы)
  python scripts/e2e_account.py --login <client_login> --counter <id> [--goals 111,222] [--target-cpa 3000] [--sandbox]

Без --goals цели предлагает подбор (metrika_discovery) — в реальном продукте их подтверждает человек."""

import argparse
import logging
import os
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.policy import decide  # noqa: E402
from app.audit.templates import explain  # noqa: E402
from app.rules import RULES  # noqa: E402
from app.rules.domain import AuditSettings, Finding, NotEnoughData, run  # noqa: E402
from app.sources.campaigns import get_campaign_contexts  # noqa: E402
from app.sources.conversion import ConversionDefinition  # noqa: E402
from app.sources.direct import DirectApi, RetryLater  # noqa: E402
from app.sources.http import api_client  # noqa: E402
from app.sources.metrika import MetrikaApi  # noqa: E402
from app.sources.metrika_discovery import parse_goal_list, suggest_goals  # noqa: E402
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_metrika, to_view, with_metrika  # noqa: E402
from app.worker.measure import DATA_TIMEZONE  # noqa: E402

MAX_WAIT = timedelta(minutes=30)


def definition(metrika: MetrikaApi, counter: int, goals: str | None) -> ConversionDefinition:
    if goals:
        return ConversionDefinition(counter, tuple(sorted(int(g) for g in goals.split(","))))
    suggested = suggest_goals(parse_goal_list(metrika.fetch_goals(counter)))
    print(f"Подбор целей: {[(c.goal.id, c.level, c.reason) for c in suggested] or 'подходящих целей нет'}")
    if not suggested:
        sys.exit("Нет целей, похожих на обращения: задайте --goals явно")
    return ConversionDefinition(counter, tuple(sorted(c.goal.id for c in suggested)))


def direct_snapshot(direct: DirectApi, login: str, d: ConversionDefinition, period_to) -> Snapshot:
    """Как воркер: 201/202 → ждать retryIn и повторить тот же запрос (тот же ReportName)."""
    deadline = time.monotonic() + MAX_WAIT.total_seconds()
    while True:
        try:
            snap = sync_account(direct, login, d, period_to)
        except RetryLater as e:
            if time.monotonic() + e.retry_in > deadline:
                sys.exit(f"Отчёт не готов за {MAX_WAIT}: {e.reason}")
            print(f"Отчёт строится ({e.reason}), повтор через {e.retry_in} с")
            time.sleep(e.retry_in)
            continue
        if isinstance(snap, SyncFailure):
            sys.exit(f"Директ: {snap.error_code} {snap.reason or ''} request_id={snap.request_id}")
        return snap


def check_semantics(snap: Snapshot) -> list[str]:
    """Факты, которые проверяются глазами до правил: период, дыры, дубли, итоги."""
    campaign = [r for r in snap.rows if r.level == "campaign"]
    dups = [k for k, n in Counter(r.key() for r in snap.rows).items() if n > 1]
    days = {r.date for r in campaign}
    period = (snap.period_to - snap.period_from).days + 1
    cost = sum((r.cost for r in campaign), Decimal(0))
    conv = sum((r.conversions or Decimal(0) for r in campaign), Decimal(0))
    print(f"Период {snap.period_from}–{snap.period_to} ({period} дн.), предварительные с {snap.partial_from}")
    print(f"Кампаний {len({r.campaign_id for r in campaign})} · дней с данными {len(days)} из {period} · "
          f"расход {cost} ₽ · клики {sum(r.clicks for r in campaign)} · конверсии {conv}"
          + (f" · CPA {(cost / conv).quantize(Decimal('0.01'))} ₽" if conv else " · CPA нет (0 конверсий)"))
    if snap.goal_rows:
        by_goal = Counter()
        for g in snap.goal_rows:
            by_goal[g.goal_id] += g.conversions
        print(f"Метрика, достижения целей по сайту: {dict(by_goal)} (все источники трафика — больше Директа это норма)")
    gaps = []
    if dups:
        gaps.append(f"дубли строк: {len(dups)}")
    if any(not snap.period_from <= r.date <= snap.period_to for r in snap.rows):
        gaps.append("строки вне периода")
    if len(days) < period:
        gaps.append(f"дней без строк кампаний: {period - len(days)} (Директ не отдаёт дни без показов)")
    if snap.source_failures:
        gaps.append(f"отказ источников: {dict(snap.source_failures)}")
    return gaps


def audit(snap: Snapshot, settings: AuditSettings, contexts: dict) -> Counter:
    view = to_view(snap, snapshot_id=0, workspace_id=0, direct_account_id=0)
    outputs = [o for rule in RULES for o in run(rule, view, settings)]
    levels, skipped = Counter(), Counter()
    for o in outputs:
        if isinstance(o, NotEnoughData):
            skipped[o.reason.value] += 1
            continue
        assert isinstance(o, Finding)
        d = decide(o)
        levels[d.level] += 1
        ctx = contexts.get(o.object_id)
        strategy = f"{ctx.strategy.value} ({ctx.search.provider_type if ctx.search else '-'})" if ctx else "?"
        print(f"\n[{o.rule_version} → {d.level}{' ← ' + ','.join(d.reasons) if d.reasons else ''}] "
              f"кампания {o.object_id} · стратегия {strategy} · потеряно ≈ {o.lost.amount} ₽")
        print(f"  {explain(o, d)}")
    if skipped:
        print(f"\nНедостаточно данных: {dict(skipped)}")
    if not levels:
        print("\nПроблем не обнаружено.")
    return levels


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--login", required=True)
    p.add_argument("--counter", type=int, required=True)
    p.add_argument("--goals")
    p.add_argument("--target-cpa", type=Decimal)
    p.add_argument("--sandbox", action="store_true")
    p.add_argument("--period-to", type=date.fromisoformat, help="последний день периода; по умолчанию вчера по МСК")
    args = p.parse_args()
    token = os.environ.get("YANDEX_API_TOKEN") or sys.exit("Задайте YANDEX_API_TOKEN")
    logging.basicConfig(level=logging.INFO, format="  · %(message)s")

    metrika = MetrikaApi(api_client("yandex_metrika"), token)
    direct = DirectApi(api_client("yandex_direct"), token, f"e2e-{int(time.time())}",
                       "sandbox" if args.sandbox else "api")
    d = definition(metrika, args.counter, args.goals)
    period_to = args.period_to or datetime.now(timezone.utc).astimezone(DATA_TIMEZONE).date() - timedelta(1)
    snap = direct_snapshot(direct, args.login, d, period_to)
    snap = with_metrika(snap, sync_metrika(metrika, d, snap.period_from, snap.period_to))
    gaps = check_semantics(snap)
    ids = sorted({r.campaign_id for r in snap.rows if r.level == "campaign"})
    contexts = get_campaign_contexts(direct.http, token, args.login, ids, env=direct.env) if ids else {}
    levels = audit(snap, AuditSettings(args.target_cpa), contexts)
    strategies = Counter(c.strategy.value for c in contexts.values())
    print("\nAccount | Campaigns | Conv | Strategy | Findings | Inspect | Review | Change | Data gaps")
    conv = sum((r.conversions or 0 for r in snap.rows if r.level == "campaign"), Decimal(0))
    print(f"{args.login} | {len(ids)} | {conv} | {dict(strategies)} | {sum(levels.values())} | "
          f"{levels['inspect_only']} | {levels['review']} | {levels['change']} | {'; '.join(gaps) or '—'}")


if __name__ == "__main__":
    main()
