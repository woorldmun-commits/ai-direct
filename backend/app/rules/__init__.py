from app.flags import flag
from app.rules.high_cpa import HIGH_CPA_BASELINE, HIGH_CPA_BASELINE_V2, HIGH_CPA_TARGET, HIGH_CPA_TARGET_V2
from app.rules.zero_conv_campaign import ZERO_CONV_CAMPAIGN, ZERO_CONV_CAMPAIGN_V2
from app.rules.zero_conv_placements import ZERO_CONV_PLACEMENTS, ZERO_CONV_PLACEMENTS_V2

RULES_V1 = (HIGH_CPA_TARGET, HIGH_CPA_BASELINE, ZERO_CONV_CAMPAIGN, ZERO_CONV_PLACEMENTS)
RULES_V2 = (HIGH_CPA_TARGET_V2, HIGH_CPA_BASELINE_V2, ZERO_CONV_CAMPAIGN_V2, ZERO_CONV_PLACEMENTS_V2)
# Все версии: старые выводы (@1) читаются и сопоставляются с семейством; вычислять их заново не нужно.
ALL_RULES = RULES_V1 + RULES_V2
# Версии, которые аудит вычисляет сейчас: одна на семейство (issue_key общий — две версии дали бы дубли).
# Выбор по флагу source_of_truth_v2 (app/flags.py), читается при импорте.
RULES = RULES_V2 if flag("source_of_truth_v2") else RULES_V1
