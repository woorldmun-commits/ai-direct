"""Онбординг Метрики: какие счётчики доступны и какие цели похожи на реальные обращения клиентов.

Собственник не должен разбираться в десятках целей: система ранжирует их и предлагает, человек подтверждает —
цели не выбираются молча. Названия счётчиков и целей нужны только экрану выбора; в снимок попадают id
(ConversionDefinition), названия не сохраняются.

ponytail: ранжирование — тип цели + ключевые слова в названии. Уточнить на реальных счётчиках (какие цели
клиенты подтверждают, какие отклоняют); смена правил не влияет на уже подтверждённые определения конверсии."""

import json
import re
from dataclasses import dataclass
from typing import Literal

from app.sources.conversion import MAX_GOALS

Level = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class MetrikaCounter:
    id: int
    name: str
    site: str | None
    permission: str  # own · edit · view · analyst · …
    time_zone: str | None


@dataclass(frozen=True)
class MetrikaGoal:
    id: int
    name: str
    type: str        # url · action · phone · payment_system · … (management API)
    source: str | None  # user · auto (автоцели Метрики)


@dataclass(frozen=True)
class GoalCandidate:
    goal: MetrikaGoal
    level: Level
    reason: str      # код: purchase_or_lead · contact_click · engagement_only · unclear


def parse_counters(text: str) -> tuple[MetrikaCounter, ...]:
    return tuple(MetrikaCounter(int(c["id"]), c.get("name") or "", (c.get("site2") or {}).get("site"),
                                c.get("permission") or "", c.get("time_zone_name"))
                 for c in json.loads(text).get("counters") or ())


def parse_goal_list(text: str) -> tuple[MetrikaGoal, ...]:
    return tuple(MetrikaGoal(int(g["id"]), g.get("name") or "", g.get("type") or "", g.get("goal_source"))
                 for g in json.loads(text).get("goals") or ())


# Действия, которые сами по себе не обращение клиента: глубина, время, поиск, файлы, соцсети.
_ENGAGEMENT_TYPES = frozenset({"number", "visit_duration", "search", "file", "social"})
# Клик по контакту — намерение связаться, но не факт обращения.
_CONTACT_TYPES = frozenset({"phone", "email", "messenger", "chat"})
_LEAD_WORDS = re.compile(r"заявк|заказ|покупк|оплат|форм|запис|брон|корзин|оформ|спасибо|lead|order|purchase|"
                         r"checkout|submit|booking|thank", re.IGNORECASE)
_CONTACT_WORDS = re.compile(r"звон|телефон|whatsapp|telegram|почт|email|чат|call|phone", re.IGNORECASE)


def score_goal(g: MetrikaGoal) -> GoalCandidate:
    if g.type == "payment_system" or (g.type not in _ENGAGEMENT_TYPES and _LEAD_WORDS.search(g.name)):
        return GoalCandidate(g, "high", "purchase_or_lead")
    if g.type in _CONTACT_TYPES or (g.type not in _ENGAGEMENT_TYPES and _CONTACT_WORDS.search(g.name)):
        return GoalCandidate(g, "medium", "contact_click")
    if g.type in _ENGAGEMENT_TYPES:
        return GoalCandidate(g, "low", "engagement_only")
    return GoalCandidate(g, "low", "unclear")  # «Посещение страницы /about» без признаков обращения


def suggest_goals(goals: tuple[MetrikaGoal, ...]) -> tuple[GoalCandidate, ...]:
    """Предложение для экрана «Мы нашли N целей, похожих на обращения клиентов — [Подтвердить]».
    Сначала high; если таких нет — medium. low не предлагаются никогда: лучше «не нашли подходящих целей»,
    чем CPA по просмотрам страниц. Не больше MAX_GOALS — предел Goals в Reports API Директа."""
    ranked = [score_goal(g) for g in goals]
    for level in ("high", "medium"):
        picked = [c for c in ranked if c.level == level]
        if picked:
            return tuple(sorted(picked, key=lambda c: c.goal.id)[:MAX_GOALS])
    return ()
