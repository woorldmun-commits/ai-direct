from app.flags import active_flags
from app.rules.high_cpa import HIGH_CPA_BASELINE, HIGH_CPA_BASELINE_V2, HIGH_CPA_TARGET, HIGH_CPA_TARGET_V2
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN, ZERO_CONV_CAMPAIGN_V2
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS, ZERO_CONV_PLACEMENTS_V2

RULES_V1 = (HIGH_CPA_TARGET, HIGH_CPA_BASELINE, ZERO_CONV_CAMPAIGN, ZERO_CONV_PLACEMENTS)
RULES_V2 = (HIGH_CPA_TARGET_V2, HIGH_CPA_BASELINE_V2, ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_PLACEMENTS_V2)
# Все версии: старые выводы (@1) читаются и сопоставляются с семейством; вычислять их заново не нужно.
ALL_RULES = RULES_V1 + RULES_V2


def active_rules(env=None):
    """Версии, которые аудит вычисляет: одна на семейство (issue_key общий — две версии дали бы дубли). Выбор по флагу
    source_of_truth_v2 (app/flags.py); выключенный флаг безопасности логируется предупреждением."""
    return RULES_V2 if active_flags(env)["source_of_truth_v2"] else RULES_V1


# Читается при импорте (старт процесса); safety_policy выбирает decide_active при каждом вызове — см. его docstring.
RULES = active_rules()
