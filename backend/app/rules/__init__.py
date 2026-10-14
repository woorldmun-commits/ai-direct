from app.flags import active_flags
from app.rules.anomaly import ANOMALY, ANOMALY_V2
from app.rules.budget_underuse import BUDGET_UNDERUSE
from app.rules.high_cpa import (HIGH_CPA_BASELINE, HIGH_CPA_BASELINE_V2, HIGH_CPA_BASELINE_V3, HIGH_CPA_TARGET,
                                HIGH_CPA_TARGET_V2, HIGH_CPA_TARGET_V3)
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN, ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_CAMPAIGN_V3
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS, ZERO_CONV_PLACEMENTS_V2, ZERO_CONV_PLACEMENTS_V3
from app.rules.zero_conv_queries import ZERO_CONV_QUERIES

RULES_V1 = (HIGH_CPA_TARGET, HIGH_CPA_BASELINE, ZERO_CONV_CAMPAIGN, ZERO_CONV_PLACEMENTS)
RULES_V2 = (HIGH_CPA_TARGET_V2, HIGH_CPA_BASELINE_V2, ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_PLACEMENTS_V2)
# @3 — исправления аналитической корректности (статистический порог high_cpa, НДС в target_cpa, CPA сетей для площадок,
# абсолютный режим zero_conv_campaign без суммы); те же источники, что @2. Вычисляются при флаге audit_rules_v3.
RULES_V3 = (HIGH_CPA_TARGET_V3, HIGH_CPA_BASELINE_V3, ZERO_CONV_CAMPAIGN_V3, ZERO_CONV_PLACEMENTS_V3)
# Правила за флагом (app/flags.py): выключены, пока не проверены на живых кабинетах. Версия у них своя (@1), метки
# источников — из реестра метрик (rules/evidence.py), поэтому они добавляются к любому набору версий.
FLAGGED = {"audit_rules_candidates": (ZERO_CONV_QUERIES, ANOMALY_V2, BUDGET_UNDERUSE)}
# Все версии: старые выводы (@1) читаются и сопоставляются с семейством; вычислять их заново не нужно.
# Снятые версии: больше не вычисляются (за флагом теперь их преемник), но их выводы читаются по семейству.
RETIRED = (ANOMALY,)
ALL_RULES = RULES_V1 + RULES_V2 + RULES_V3 + RETIRED + tuple(r for rules in FLAGGED.values() for r in rules)


def active_rules(env=None):
    """Версии, которые аудит вычисляет: одна на семейство (issue_key общий — две версии дали бы дубли). Выбор по флагу
    source_of_truth_v2 (app/flags.py): выключен — @1, включён — @2, а при audit_rules_v3 — @3; выключенный флаг
    безопасности логируется предупреждением. Правила за флагом — в конце, если их флаг включён."""
    flags = active_flags(env)
    base = (RULES_V3 if flags["audit_rules_v3"] else RULES_V2) if flags["source_of_truth_v2"] else RULES_V1
    return base + tuple(r for name, rules in FLAGGED.items() if flags[name] for r in rules)


# Читается при импорте (старт процесса); safety_policy выбирает decide_active при каждом вызове — см. его docstring.
RULES = active_rules()
