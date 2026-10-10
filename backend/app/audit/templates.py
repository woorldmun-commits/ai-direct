"""Шаблонное объяснение вывода — работает без LLM (ARCHITECTURE.md §6). Все числа — из Finding, ничего не добавляется.
Решение принимают правило (кандидат) и политика безопасности (уровень); здесь только текст. Изменение настроек
предлагается, только если политика его разрешила."""

from decimal import Decimal

from app.audit.policy import Decision
from app.rules.domain import Finding
from app.rules.evidence import PARTIAL_REASON


def _rub(x: Decimal) -> str:
    """Число как в ValueView фронтенда (frontend/lib/value.ts: formatAmount): без округления — копейки показываются,
    если они есть («2 500,50»), целое — без «,00» («2 500»); группы разрядов — пробелом, дробная часть — запятой.
    Никакого банковского (или любого другого) округления: 2 500,50 не становится 2 500, а 2 501,50 — 2 502."""
    sign, digits = ("-", -x) if x < 0 else ("", x)
    whole, _, frac = format(digits, "f").partition(".")
    frac = frac.rstrip("0")
    if frac:
        frac = frac.ljust(2, "0")
    grouped = f"{int(whole):,}".replace(",", " ")
    return sign + grouped + ("," + frac if frac else "")


def _bid_advice(f: Finding, d: Decision, strategy: str) -> str:
    change = abs(f.action["change_pct"])
    if d.level != "inspect_only" and strategy != "manual":
        # рычаг «ставка» есть только у ручной стратегии; у автоматической или неизвестной ставку не советуем
        return ("Проверьте рычаги кампании для снижения CPA: какие из них доступны, зависит от стратегии "
                "(целевой CPA, цели конверсий).")
    if d.level == "inspect_only":
        conv = f.evidence["conversions"].amount
        return (f"Конверсий за период пока мало ({_rub(conv)}) для безопасного изменения ставки — продолжаем "
                "наблюдать. Проверьте, какие запросы и площадки дают расход без заявок.")
    if d.level == "review":
        return (f"Можно снизить ставку на {change}% — проверьте перед изменением, доступна ли ручная ставка "
                "в стратегии кампании.")
    return f"Рекомендуется снизить ставку на {change}%."


_ZERO_CONV_REFERENCE = {
    "target_cpa": ("target_cpa", "целевого CPA"),
    "campaign_baseline": ("baseline_cpa", "CPA кампании за прошлые 30 дней"),
    "account_baseline": ("account_baseline_cpa", "CPA аккаунта за прошлые 30 дней"),
}


def _zero_conv(f: Finding) -> str:
    """Числа — только из Finding: расход, клики, порог и CPA-ориентир из доказательств."""
    ev = f.evidence
    text = (f"Кампания {f.object_id} потратила {_rub(f.actual)} ₽ ({_rub(ev['clicks'].amount)} кликов) за период "
            f"и не получила ни одной конверсии. Порог достаточного объёма — {_rub(f.reference)} ₽")
    if (ref := _ZERO_CONV_REFERENCE.get(f.evidence_meta.get("reference_source"))) and ref[0] in ev:
        text += f", рассчитан от {ref[1]} {_rub(ev[ref[0]].amount)} ₽"
    text += (". Проверьте: учитываются ли цели и конверсии Метрики в кампании, стратегию и её цель, поисковые "
             "запросы и минус-фразы.")
    if f.action.get("suggest") == "set_target_cpa":
        text += " Укажите целевой CPA — порог станет точнее."
    return text


_PLACEMENT_REFERENCE = {"target": "целевой CPA", "campaign": "CPA кампании за период снимка"}
NAMES_SHOWN = 5  # имён площадок в тексте; полный список — в доказательствах и действии


def _placement_names(f: Finding) -> list[str]:
    ids = [i for i in f.evidence_meta.get("placement_ids", "").split(",") if i]
    return [n for i in ids if (n := f.evidence_meta.get(f"placement_{i}_name"))]


def _placements(f: Finding, d: Decision) -> str:
    """Числа — только из Finding: расход и клики площадок, их число, ориентир CPA. Отклонение не пишется: у правила
    его нет (delta_pct = 0 — служебное значение, а не «расход на 0% выше ориентира»)."""
    ev = f.evidence
    text = (f"В кампании {f.object_id} площадок РСЯ без конверсий: {_rub(ev['placements'].amount)}. За период они "
            f"потратили {_rub(f.actual)} ₽ ({_rub(ev['clicks'].amount)} кликов), а конверсий не было ни за период, "
            f"ни раньше в истории снимка. Каждая потратила не меньше ориентира — "
            f"{_PLACEMENT_REFERENCE.get(f.evidence_meta.get('reference_mode'), 'CPA')} {_rub(f.reference)} ₽.")
    if names := _placement_names(f):
        text += " Площадки: " + ", ".join(names[:NAMES_SHOWN]) + (" и другие." if len(names) > NAMES_SHOWN else ".")
    if f.evidence_meta.get("level_reason") == PARTIAL_REASON:
        text += " Конверсии последних дней ещё досчитываются — проверьте площадки перед исключением."
    if d.level == "inspect_only":
        text += (" Расхода пока мало для уверенного вывода: проверьте, что это за площадки и подходит ли их аудитория, "
                 "прежде чем исключать.")
    else:
        text += (" Проверьте площадки и исключите лишние вручную в настройках кампании в Директе. Сколько удастся "
                 "сэкономить, не оцениваем: Директ может перераспределить бюджет на другие площадки.")
    return text


def _queries(f: Finding) -> str:
    """Тексты запросов в объяснение не попадают никогда (их нет и в выводе): только число, расход и клики."""
    ev = f.evidence
    text = (f"В кампании {f.object_id} поисковых запросов без конверсий: {_rub(ev['queries'].amount)}. За период они "
            f"потратили {_rub(f.actual)} ₽ ({_rub(ev['clicks'].amount)} кликов), конверсий не было ни за период, ни "
            f"раньше в истории снимка. Каждый потратил не меньше двух ориентиров CPA "
            f"({_PLACEMENT_REFERENCE.get(f.evidence_meta.get('reference_mode'), 'CPA')} {_rub(f.reference)} ₽).")
    if f.evidence_meta.get("level_reason") == PARTIAL_REASON:
        text += " Конверсии последних дней ещё досчитываются."
    return text + (" Проверьте запросы в отчёте Директа: подходящие нерелевантные — кандидаты в минус-фразы. "
                   "Минус-фраза отсекает и похожие будущие запросы — решение за вами.")


def _anomaly(f: Finding) -> str:
    """Только «проверить причину»: ставок и бюджета не советуем."""
    ev = f.evidence
    if f.reason_code == "spend_spike":
        text = (f"Расход кампании {f.object_id} за период — {_rub(f.actual)} ₽, это на {f.delta_pct}% выше её "
                f"обычного уровня {_rub(f.reference)} ₽ (по прошлым 30 дням). Оценка расхода сверх нормы, не "
                f"объяснённого ростом конверсий, ≈ {_rub(f.lost.amount)} ₽.")
    else:
        text = (f"Конверсий кампании {f.object_id} за завершённые дни периода — {_rub(f.actual)}, ожидалось около "
                f"{_rub(f.reference)} по прошлым 30 дням, а расход не снизился ({_rub(ev['complete_cost'].amount)} ₽). "
                f"Оценка расхода сверх обычного CPA ≈ {_rub(f.lost.amount)} ₽.")
    return text + (" Проверьте причину: изменения стратегии, бюджета или ставок, учёт целей, работу сайта, "
                   "сезонность. Это сигнал для проверки, а не совет что-то менять.")


def _budget_underuse(f: Finding) -> str:
    ev = f.evidence
    return (f"Кампания {f.object_id} потратила за период {_rub(ev['cost'].amount)} ₽ — {_rub(f.actual)}% своего "
            f"ограничения {_rub(ev['budget_limit'].amount)} ₽, при этом CPA {_rub(ev['cpa'].amount)} ₽ ниже "
            "ориентира. Проверьте, что сдерживает расход: стратегию и её цель CPA, ставки, охват. Сколько конверсий "
            "это добавит, не оцениваем.")


def explain(f: Finding, d: Decision, strategy: str = "unknown") -> str:
    """strategy — как в audit/present.py: manual · auto · unknown. Сейчас в снимке стратегии нет — тогда unknown."""
    if f.reason_code == "zero_conversions":
        return _zero_conv(f)
    if f.reason_code == "placements_without_conversions":
        return _placements(f, d)
    if f.reason_code == "queries_without_conversions":
        return _queries(f)
    if f.reason_code in ("spend_spike", "conversion_drop"):
        return _anomaly(f)
    if f.reason_code == "budget_underused_good_cpa":
        return _budget_underuse(f)
    head = f"CPA кампании {f.object_id} — {_rub(f.actual)} ₽"
    if f.reason_code == "cpa_above_target":
        return f"{head}, это на {f.delta_pct}% выше целевого CPA {_rub(f.reference)} ₽. {_bid_advice(f, d, strategy)}"
    if f.reason_code == "cpa_above_baseline":
        return (f"{head}, это на {f.delta_pct}% выше исторического базового уровня {_rub(f.reference)} ₽. "
                "Проверьте причину роста и укажите целевой CPA — оценка станет точнее.")
    return f"{f.metric} = {f.actual}, ориентир {f.reference} ({f.reference_type}), отклонение {f.delta_pct}%."
