"""MVP-0: прогон одного реального аккаунта без БД и без UI — Метрика → определение конверсии → отчёты Директа →
снимок → проверки целостности → контекст кампаний → правила → safety_policy@1 → объяснения.

Только чтение. Токены — из окружения, в вывод, лог и файлы не попадают; названия кампаний не печатаются (только
id), логин в файлах — хэшем. Результат каждого прогона — артефакт: <out>/<время>/run.json и summary.txt.

  set YANDEX_API_TOKEN=...          (права direct:api и metrika:read)
  python scripts/e2e_account.py --login <client_login> --counter <id> [--goals 111,222] [--target-cpa 3000]
                                [--sandbox] [--period-to 2026-09-29] [--out e2e-result]

STATUS: PASS — проверки целостности пройдены; REVIEW — есть что проверить глазами; FAIL — источник не ответил.
`change` в итоге означает «политика считает изменение допустимым», а не «система умеет изменить рекламу»."""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
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
from app.sources.metrika_discovery import parse_counters, parse_goal_list, suggest_goals  # noqa: E402
from app.sync.snapshot import Snapshot, SyncFailure, sync_account, sync_metrika, to_view, with_metrika  # noqa: E402
from app.worker.measure import DATA_TIMEZONE  # noqa: E402

MAX_WAIT = timedelta(minutes=30)
CENT = Decimal("0.01")


def definition(metrika: MetrikaApi, counter: int, goals: str | None) -> ConversionDefinition:
    if goals:
        return ConversionDefinition(counter, tuple(sorted(int(g) for g in goals.split(","))))
    suggested = suggest_goals(parse_goal_list(metrika.fetch_goals(counter)))
    print(f"Подбор целей: {[(c.goal.id, c.level, c.reason) for c in suggested] or 'подходящих целей нет'}")
    if not suggested:
        sys.exit("Нет целей, похожих на обращения: задайте --goals явно")
    return ConversionDefinition(counter, tuple(sorted(c.goal.id for c in suggested)))


def direct_snapshot(direct: DirectApi, login: str, d: ConversionDefinition, period_to: date) -> Snapshot | SyncFailure:
    """Как воркер: 201/202 → ждать retryIn и повторить тот же запрос (тот же ReportName)."""
    deadline = time.monotonic() + MAX_WAIT.total_seconds()
    while True:
        try:
            return sync_account(direct, login, d, period_to)
        except RetryLater as e:
            if time.monotonic() + e.retry_in > deadline:
                return SyncFailure(login, "report_timeout", e.reason)
            print(f"Отчёт строится ({e.reason}), повтор через {e.retry_in} с")
            time.sleep(e.retry_in)


def integrity(snap: Snapshot) -> dict:
    """Итоги считаются двумя путями (по дням и по кампаниям) и обязаны совпасть; каждая дата периода — в таблице.
    Дня нет в отчёте (no_row_observation): API не вернул строк, и по Reports API причина неразличима — отсутствие
    активности или отсутствие строки. Доказанным нулём это не считается; проверить можно только по кабинету."""
    rows = [r for r in snap.rows if r.level == "campaign"]
    period = [snap.period_from + timedelta(i) for i in range((snap.period_to - snap.period_from).days + 1)]
    by_date, by_campaign = defaultdict(lambda: [set(), Decimal(0), 0, Decimal(0)]), defaultdict(Decimal)
    for r in rows:
        day = by_date[r.date]
        day[0].add(r.campaign_id)
        day[1] += r.cost
        day[2] += r.clicks
        day[3] += r.conversions or 0
        by_campaign[r.campaign_id] += r.cost
    cost = sum((v[1] for v in by_date.values()), Decimal(0))
    clicks = sum(v[2] for v in by_date.values())
    conv = sum((v[3] for v in by_date.values()), Decimal(0))
    sums_match = (cost == sum(by_campaign.values(), Decimal(0)) == sum((r.cost for r in rows), Decimal(0))
                  and clicks == sum(r.clicks for r in rows))
    cpa = (cost / conv).quantize(CENT) if conv else None
    return {
        "period": f"{snap.period_from}..{snap.period_to}", "partial_from": str(snap.partial_from),
        "dates_expected": len(period), "dates_found": len(by_date),
        "no_row_observation_dates": [str(d) for d in period if d not in by_date],
        "out_of_period_rows": sum(1 for r in snap.rows if not snap.period_from <= r.date <= snap.period_to),
        "duplicate_rows": sum(n - 1 for n in Counter(r.key() for r in snap.rows).values() if n > 1),
        "campaigns": len(by_campaign), "spend": str(cost), "clicks": clicks, "conversions": str(conv),
        "computed_cpa": str(cpa) if cpa else None,
        "cpa_check": cpa is None or abs(cpa * conv - cost) <= conv * CENT,
        "sums_match": sums_match,
        "by_date": [{"date": str(d), "campaigns": len(v[0]), "spend": str(v[1]), "clicks": v[2],
                     "conversions": str(v[3])} for d, v in sorted(by_date.items())],
    }


def metrika_check(snap: Snapshot, d: ConversionDefinition, period_days: int) -> dict:
    reached = Counter()
    for g in snap.goal_rows:
        reached[g.goal_id] += g.conversions
    return {"selected_goals": list(d.goal_ids), "report_rows": len(snap.goal_rows),
            "rows_expected": len(d.goal_ids) * period_days if snap.goal_rows else 0,
            "goal_reaches_all_traffic": {str(k): str(v) for k, v in reached.items()},
            "failure": dict(snap.source_failures).get("yandex_metrika")}


def time_zones(contexts: dict, counter_tz: str | None) -> dict:
    """Граница суток должна совпадать у источников: Директ — в поясе кампаний, Метрика — в поясе счётчика.
    Europe/Moscow — ожидаемый случай по умолчанию, не эталон: Екатеринбург у обоих — тоже согласовано.
    product_match — совпадает ли с поясом, в котором продукт сейчас считает «вчера» и окна (DATA_TIMEZONE)."""
    campaigns = Counter(c.time_zone or "unknown" for c in contexts.values())
    sources = set(campaigns) | {counter_tz or "unknown"}
    return {"direct_campaigns": dict(campaigns), "metrika_counter": counter_tz,
            "match": len(sources) == 1 and "unknown" not in sources,
            "product": str(DATA_TIMEZONE), "product_match": sources == {str(DATA_TIMEZONE)}}


def outcome(campaigns: set[int], found: set[int], insufficient: set[int], account_skipped: bool) -> dict:
    """0 выводов — не один исход: кампании проверены и проблем нет (NO_PROBLEMS_FOUND) или проверить было не по чему
    (NO_ACTIONABLE_DATA). Ошибка интеграции до аудита не доходит — это STATUS: FAIL."""
    checked_ok = set() if account_skipped else campaigns - found - insufficient
    label = "FINDINGS" if found else "NO_PROBLEMS_FOUND" if checked_ok else "NO_ACTIONABLE_DATA"
    return {"outcome": label, "campaigns_with_findings": len(found), "campaigns_checked_no_problem": len(checked_ok),
            "campaigns_not_enough_data": len(campaigns) if account_skipped else len(insufficient - found)}


def audit(snap: Snapshot, settings: AuditSettings, contexts: dict) -> dict:
    view = to_view(snap, snapshot_id=0, workspace_id=0, direct_account_id=0)
    levels, skipped, found, insufficient, account_skipped = Counter(), Counter(), set(), set(), False
    for o in (o for rule in RULES for o in run(rule, view, settings)):
        if isinstance(o, NotEnoughData):
            skipped[o.reason.value] += 1
            if o.object_id is None:
                account_skipped = True  # правило не вычислялось для всего аккаунта (нет источника)
            else:
                insufficient.add(o.object_id)
            continue
        found.add(o.object_id)
        assert isinstance(o, Finding)
        d = decide(o)
        levels[d.level] += 1
        ctx = contexts.get(o.object_id)
        strategy = f"{ctx.strategy.value} ({ctx.search.provider_type if ctx.search else '-'})" if ctx else "?"
        print(f"\n[{o.rule_version} → {d.level}{' ← ' + ','.join(d.reasons) if d.reasons else ''}] "
              f"кампания {o.object_id} · стратегия {strategy} · потеряно ≈ {o.lost.amount} ₽")
        print(f"  {explain(o, d)}")
    campaigns = {d.campaign_id for d in view.campaign_days}
    return {"findings": sum(levels.values()), **{k: levels[k] for k in ("inspect_only", "review", "change")},
            "not_enough_data": dict(skipped), **outcome(campaigns, found, insufficient, account_skipped)}


def status(r: dict) -> str:
    if r["errors"]:
        return "FAIL"
    i, m = r["integrity"], r["metrika"]
    clean = (i["duplicate_rows"] == 0 and i["out_of_period_rows"] == 0 and i["sums_match"] and i["cpa_check"]
             and i["dates_found"] > 0 and r["time_zones"]["match"] and m["report_rows"] == m["rows_expected"])
    return "PASS" if clean else "REVIEW"


def summary(r: dict) -> str:
    if "integrity" not in r:  # источник не ответил — до проверок не дошли
        return "\n".join(["MVP-0 E2E", "", f"Account: {r['account']}", "", "Errors",
                          f"  Direct: {r['errors'].get('direct')}", "", "STATUS: FAIL"])
    i, m, a, tz = r["integrity"], r["metrika"], r.get("audit", {}), r["time_zones"]
    lines = [
        "MVP-0 E2E", "", f"Account: {r['account']}", f"Period: {i['period']} (partial from {i['partial_from']})",
        f"Timezone: Direct campaigns {tz['direct_campaigns']} · Metrika counter {tz['metrika_counter']} · "
        f"sources match {tz['match']} · product ({tz['product']}) match {tz['product_match']}", "",
        "Direct", f"  campaigns: {i['campaigns']}", f"  spend: {i['spend']} ₽", f"  clicks: {i['clicks']}",
        f"  conversions: {i['conversions']}", f"  CPA: {i['computed_cpa'] or 'нет (0 конверсий)'} ₽"
        f" · check {i['cpa_check']} · sums match {i['sums_match']}", "",
        "Data integrity", f"  expected dates: {i['dates_expected']}", f"  dates with rows: {i['dates_found']}",
        f"  no row observation (API не вернул строк; ноль или пропуск — неразличимо): "
        f"{i['no_row_observation_dates'] or 0}",
        f"  duplicate rows: {i['duplicate_rows']}", f"  rows out of period: {i['out_of_period_rows']}", "",
        "Metrika", f"  selected goals: {m['selected_goals']}",
        f"  report rows: {m['report_rows']} of {m['rows_expected']}",
        f"  goal reaches, all site traffic: {m['goal_reaches_all_traffic']}", "",
        "Campaign strategies", *[f"  {k}: {v}" for k, v in sorted(r["strategies"].items())], "",
        "Audit", f"  outcome: {a.get('outcome')}",
        *[f"  {k}: {a.get(k, 0)}" for k in ("findings", "inspect_only", "review", "change", "campaigns_with_findings",
                                            "campaigns_checked_no_problem", "campaigns_not_enough_data")],
        f"  not enough data: {a.get('not_enough_data', {})}", "",
        "Errors", f"  Direct: {r['errors'].get('direct', 0)}", f"  Metrika: {m['failure'] or 0}", "",
        f"STATUS: {r['status']}",
    ]
    return "\n".join(lines)


def save(r: dict, out: Path) -> Path:
    run_dir = out / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.txt").write_text(summary(r), encoding="utf-8")
    return run_dir


def args_() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--login", required=True)
    p.add_argument("--counter", type=int, required=True)
    p.add_argument("--goals")
    p.add_argument("--target-cpa", type=Decimal)
    p.add_argument("--sandbox", action="store_true")
    p.add_argument("--period-to", type=date.fromisoformat, help="последний день периода; по умолчанию вчера по МСК")
    p.add_argument("--out", type=Path, default=Path("e2e-result"))
    return p.parse_args()


def main() -> None:
    args = args_()
    token = os.environ.get("YANDEX_API_TOKEN") or sys.exit("Задайте YANDEX_API_TOKEN")
    logging.basicConfig(level=logging.INFO, format="  · %(message)s")
    metrika = MetrikaApi(api_client("yandex_metrika"), token)
    direct = DirectApi(api_client("yandex_direct"), token, f"e2e-{int(time.time())}", "sandbox" if args.sandbox else "api")
    d = definition(metrika, args.counter, args.goals)
    counter_tz = next((c.time_zone for c in parse_counters(metrika.fetch_counters()) if c.id == args.counter), None)
    period_to = args.period_to or datetime.now(timezone.utc).astimezone(DATA_TIMEZONE).date() - timedelta(1)
    r = {"account": hashlib.sha256(args.login.encode()).hexdigest()[:12], "errors": {}, "strategies": {}}
    snap = direct_snapshot(direct, args.login, d, period_to)
    if isinstance(snap, SyncFailure):
        r["errors"]["direct"] = " ".join(x for x in (snap.error_code, snap.reason, f"request_id={snap.request_id}") if x)
        r.update(status="FAIL")
        print(f"Директ: {r['errors']['direct']}\nРезультат: {save(r, args.out)}")
        sys.exit(1)
    snap = with_metrika(snap, sync_metrika(metrika, d, snap.period_from, snap.period_to))
    r["integrity"] = integrity(snap)
    r["metrika"] = metrika_check(snap, d, r["integrity"]["dates_expected"])
    ids = sorted({row.campaign_id for row in snap.rows if row.level == "campaign"})
    contexts = get_campaign_contexts(direct.http, token, args.login, ids, env=direct.env) if ids else {}
    r["strategies"] = dict(Counter(c.strategy.value for c in contexts.values()))
    r["time_zones"] = time_zones(contexts, counter_tz)
    r["audit"] = audit(snap, AuditSettings(args.target_cpa), contexts)
    r["status"] = status(r)
    print("\n" + summary(r) + f"\n\nРезультат: {save(r, args.out)}")


if __name__ == "__main__":
    main()
