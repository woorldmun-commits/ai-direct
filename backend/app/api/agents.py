"""Evidence-bound advisory team: capability state comes from audited inputs, never model claims."""

from dataclasses import dataclass

from fastapi import APIRouter

from app.api.deps import Conn, CurrentWorkspace
from app.api.active import FAMILY_OF

router = APIRouter()


@dataclass(frozen=True)
class Specialist:
    id: str
    name: str
    scope: str
    families: tuple[str, ...] = ()
    required: tuple[str, ...] = ()


SPECIALISTS = (
    Specialist("data_quality", "Качество данных", "Полнота снимков и достаточность данных", required=("audit",)),
    Specialist("direct_search", "Яндекс Поиск", "Расход и стоимость конверсий кампаний", ("high_cpa", "zero_conv_campaign"), ("audit",)),
    Specialist("rsya", "РСЯ и площадки", "Расход на площадках без конверсий", ("zero_conv_placements",), ("audit",)),
    Specialist("measurement", "Метрика и цели", "Корректность целей и измерения результата", required=("metrika", "implementation")),
    Specialist("economics", "Экономика бизнеса", "Маржа, прибыль и допустимая стоимость клиента", required=("sales", "margin", "implementation")),
    Specialist("industry", "Контекст отрасли", "Ограничения, цикл сделки и особенности бизнеса", required=("business_profile", "implementation")),
    Specialist("creative", "Объявления и предложение", "Соответствие предложения потребности клиента", required=("creative_data", "implementation")),
    Specialist("landing", "Сайт и конверсия", "Путь от рекламного перехода до заявки", required=("site_analytics", "implementation")),
    Specialist("experiments", "Эксперименты", "Проверка гипотез и измерение изменений", required=("experiment_data", "implementation")),
    Specialist("vk", "VK Реклама", "Анализ кампаний VK", required=("vk_connection", "implementation")),
)

MISSING = {
    "audit": "Подключить Директ, выбрать кабинет и получить первый аудит",
    "metrika": "Подключить Метрику и выбрать цели",
    "sales": "Подключить данные о продажах и качестве заявок",
    "margin": "Указать маржу и ограничения стоимости клиента",
    "business_profile": "Заполнить профиль бизнеса",
    "creative_data": "Предоставить данные объявлений и предложения",
    "site_analytics": "Подключить аналитику сайта",
    "experiment_data": "Накопить результаты проверяемого эксперимента",
    "vk_connection": "Подключить VK после реализации интеграции",
    "implementation": "Этот специализированный анализ ещё не реализован",
}


def team_state(audit: dict | None, families: set[str], metrika: bool = False) -> dict:
    """Only existing deterministic rule families are available; no synthetic industry benchmarks."""
    available = {"audit": audit is not None, "metrika": metrika}
    skipped = set() if audit is None else {
        FAMILY_OF.get(item.get("rule"), str(item.get("rule")).split("@")[0])
        for item in audit.get("rules_skipped", [])}
    specialists = []
    for spec in SPECIALISTS:
        missing = [MISSING[key] for key in spec.required if not available.get(key, False)]
        if spec.families and not set(spec.families) & families:
            missing.append("Последний аудит не содержит правил этой области")
        if set(spec.families) & skipped:
            missing.append("Часть проверок этой области пропущена: недостаточно данных")
        specialists.append({"id": spec.id, "name": spec.name, "scope": spec.scope,
                            "status": "needs_data" if missing else "available",
                            "missing_data": missing,
                            "rule_families": sorted(set(spec.families) & families)})
    return {"mode": "recommendations_only",
            "coordinator": {"id": "chief_analyst", "name": "Главный аналитик",
                            "status": "available" if audit else "needs_data",
                            "responsibility": "Согласует выводы правил, исключает двойной учёт и показывает доказательства"},
            "specialists": specialists, "audit": audit,
            "limitations": ["Изменения в рекламных кабинетах не выполняются",
                            "Отраслевые нормы и обещания экономии без подтверждённых данных не используются",
                            "Доступность роли не означает, что все виды анализа этой области реализованы"]}


@router.get("/workspaces/{workspace_id}/agents")
def agents(conn: Conn, ws: CurrentWorkspace):
    row = conn.execute("""SELECT id, created_at, data_cutoff, rules_run, rules_skipped FROM audit_runs
                          WHERE workspace_id = %s ORDER BY created_at DESC, id DESC LIMIT 1""",
                       (ws.id,)).fetchone()
    metrika = conn.execute("""SELECT EXISTS(SELECT 1 FROM metrika_connections
                             WHERE workspace_id = %s AND status = 'connected')""", (ws.id,)).fetchone()[0]
    audit = None if row is None else {"id": f"audit_{row[0]}", "computed_at": row[1].isoformat(),
                                      "data_cutoff": row[2].isoformat(), "rules": list(row[3]),
                                      "rules_skipped": row[4]}
    return team_state(audit, set() if row is None else {
        FAMILY_OF.get(rule, rule.split("@")[0]) for rule in row[3]}, metrika)
