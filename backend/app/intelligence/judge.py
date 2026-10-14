"""Evidence Judge (AI_GOVERNANCE.md §2.3): детерминированная проверка ответа LLM против промпт-пакета.

Утверждение отбрасывается, если: нарушает контракт Claim (FACT / DERIVED_FACT от ИИ, недопустимый статус
причинности); ссылается на несуществующий evidence_id; содержит число, которого нет в процитированных фактах
(сравнение точное, по значению: «4 820» = 4820.00; округление не допускается — открытый вопрос §6.1); упоминает
неизвестную ссылку obj_N; похоже на инъекцию или ссылку; причинно («из-за») без HYPOTHESIS и причинного факта;
число со знаком «%» не из *_pct процитированных фактов или с «п.п.» не из *_pp (unit_mismatch: относительное
изменение и процентные пункты не взаимозаменяемы); упоминает объект obj_N, которого нет среди объектов процитированных
фактов (object_mismatch: цифра кампании A не подтверждает утверждение о кампании B); называет направление («вырос»,
«снизился»), противоположное знаку процитированного изменения (sign_mismatch: модуль числа совпал, смысл — нет).
Числа ищутся и приклеенными к буквам («50тыс», «3x»), с множителем тыс/млн/млрд/k, и словами («в два раза»).
Отброшено ключевое утверждение, не осталось ни одного или не прошёл summary → весь ответ на шаблон."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.intelligence.contracts._validate import check_text
from app.intelligence.contracts.claims import CausalStatus, Claim, ClaimType
from app.intelligence.privacy import OBJECT_REF, Packet

CAUSAL_KINDS = frozenset({"finding", "policy_reason", "metric_change"})
# Число — не часть идентификатора (obj_1, e1, rule@1), но может быть приклеено к единице («50тыс», «3x») или стоять
# после множителя («x3»); справа не цифра, чтобы «1 5000» не читалось как «1 500».
_START = r"(?:(?<![\w@.,])|(?<=(?<![\w@.,])[xXхХ×]))"
_NUMBER = re.compile(_START + r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?(?!\d)|" + _START + r"\d+(?:[.,]\d+)?(?!\d)")
_SCALE = re.compile(r"\s*(?:тыс|млрд|млн|миллиард|миллион)|[kк](?![а-яёa-z])", re.IGNORECASE)
_SCALES = (("тыс", 3), ("млрд", 9), ("миллиард", 9), ("млн", 6), ("миллион", 6), ("k", 3), ("к", 3))
# ponytail: числа словами — количественные 1…100 и кратности; составные («двадцать пять») читаются по частям,
# поэтому такой текст уходит на шаблон, даже если 25 есть в фактах. Порядковые («второй») не ловятся.
_WORDS = tuple((re.compile(rf"\b(?:{stems})\b", re.IGNORECASE), Decimal(value)) for stems, value in (
    ("один|одн(?:а|о|ого|ой|ому|у|им|ими|их)", "1"), ("полтор(?:а|ы|ух)", "1.5"), ("дв(?:а|е|ух|ум|умя)|вдвое", "2"),
    ("тр(?:и|ех|ёх|ем|ём|емя|ёмя)|втрое", "3"), ("четыр(?:е|ех|ёх|ем|ём|ьмя)|вчетверо", "4"),
    ("пят(?:ь|и|ью)", "5"), ("шест(?:ь|и|ью)", "6"), ("сем(?:ь|и|ью)", "7"), ("вос(?:емь|ьми|емью|ьмью)", "8"),
    ("девят(?:ь|и|ью)", "9"), ("десят(?:ь|и|ью)", "10"), ("одиннадцат(?:ь|и|ью)", "11"),
    ("двенадцат(?:ь|и|ью)", "12"), ("тринадцат(?:ь|и|ью)", "13"), ("четырнадцат(?:ь|и|ью)", "14"),
    ("пятнадцат(?:ь|и|ью)", "15"), ("шестнадцат(?:ь|и|ью)", "16"), ("семнадцат(?:ь|и|ью)", "17"),
    ("восемнадцат(?:ь|и|ью)", "18"), ("девятнадцат(?:ь|и|ью)", "19"), ("двадцат(?:ь|и|ью)", "20"),
    ("тридцат(?:ь|и|ью)", "30"), ("сорок(?:а)?", "40"), ("пятьдесят|пятидесяти", "50"),
    ("шестьдесят|шестидесяти", "60"), ("семьдесят|семидесяти", "70"), ("восемьдесят|восьмидесяти", "80"),
    ("девяност(?:о|а)", "90"), ("ст(?:о|а)", "100")))
# ponytail: закрытые списки маркеров (§6 п.4); причинность без маркеров не ловится
_CAUSAL = re.compile(r"из-за|потому что|вследствие|в результате|привел|привёл|приводит|вызва|объясня|благодаря|"
                     r"обусловл|связан\w* с|следстви|под влиянием|because|due to|caus", re.IGNORECASE)
_UNIT_NUMBER = {"pct": re.compile(r"(\d[\d   ]*(?:[.,]\d+)?)\s*%"),
                "pp": re.compile(r"(\d[\d   ]*(?:[.,]\d+)?)\s*(?:п\.\s?п\.?|pp\b)", re.IGNORECASE)}
# Направление в тексте против знака процитированного изменения (*_pct, *_pp, *delta*, from → to)
_UP = re.compile(r"\b(?:вырос|вырас|рост|увелич|выше|больше|подорож)", re.IGNORECASE)
_DOWN = re.compile(r"\b(?:сниз|сниж|упал|упад|паден|сократ|сокращ|ниже|меньше|подешев)", re.IGNORECASE)
_INJECTION = re.compile(r"ignore|игнорир|инструкц|instruction|system|промпт|prompt|https?://|www\.|\S+@\S+\.\w+|<\s*/?"
                        r"\s*[a-z]", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    summary: str | None
    claims: tuple[Claim, ...]
    dropped: tuple[tuple[int, str], ...]  # (номер утверждения, код причины) — без текста, годится в лог
    reason: str | None                    # почему весь ответ ушёл на шаблон


def _power(text: str, end: int) -> int:
    match = _SCALE.match(text, end)
    if not match:
        return 0
    word = match.group().strip().lower()
    return next(power for prefix, power in _SCALES if word.startswith(prefix))


def numbers_in(text: str) -> set[Decimal]:
    """Числа текста по модулю: цифрами (с множителем тыс/млн/млрд/k) и словами."""
    found = {value for pattern, value in _WORDS if pattern.search(text)}
    for match in _NUMBER.finditer(text):
        value = Decimal(re.sub(r"[   ]", "", match.group()).replace(",", "."))
        found.add(abs(value.scaleb(_power(text, match.end()))))
    return found


def _cited_signs(packet: Packet, evidence_ids) -> set[bool]:
    """Знаки процитированных изменений: True — рост, False — падение; нули и слаги не в счёт."""
    signs = set()
    for fact in packet.payload["facts"]:
        if fact["id"] not in evidence_ids:
            continue
        raw = [v for k, v in fact.get("values", {}).items() if k.endswith(("_pct", "_pp")) or "delta" in k]
        if "from" in fact and "to" in fact:
            raw.append(Decimal(fact["to"]) - Decimal(fact["from"]))
        for value in raw:
            try:
                d = Decimal(value)
            except (ArithmeticError, TypeError, ValueError):
                continue
            if d.is_finite() and d:
                signs.add(d > 0)
    return signs


def _sign_problem(text: str, packet: Packet, evidence_ids) -> bool:
    up, down = bool(_UP.search(text)), bool(_DOWN.search(text))
    if up == down:  # направление не названо или названы оба — сверять не с чем
        return False
    signs = _cited_signs(packet, evidence_ids)
    return bool(signs) and up not in signs


def _unit_problem(text: str, packet: Packet, evidence_ids) -> bool:
    for unit, pattern in _UNIT_NUMBER.items():
        cited = {n for e in evidence_ids for n in packet.units.get(e, {}).get(unit, ())}
        if any(numbers_in(m) - cited for m in pattern.findall(text)):
            return True
    return False


def _text_problem(text: str, packet: Packet, allowed: set[Decimal]) -> str | None:
    if _INJECTION.search(text):
        return "injection"
    if any(ref not in packet.refs for ref in OBJECT_REF.findall(text)):
        return "unknown_object"
    if not numbers_in(text) <= allowed:
        return "number_not_in_evidence"
    return None


def _claim_problem(raw: Mapping, packet: Packet, allowed_types: frozenset) -> tuple[Claim | None, str | None]:
    try:
        claim = Claim(type=ClaimType(raw["type"]), text=raw["text"], evidence_ids=tuple(raw["evidence_ids"]),
                      causal_status=CausalStatus(raw["causal_status"]), origin="ai")
    except (KeyError, TypeError, ValueError):
        return None, "contract"
    if claim.type not in allowed_types:
        return None, "claim_type_not_allowed"
    if not claim.evidence_ids or any(e not in packet.numbers for e in claim.evidence_ids):
        return None, "unknown_evidence"
    allowed = {abs(n) for e in claim.evidence_ids for n in packet.numbers[e]}
    problem = _text_problem(claim.text, packet, allowed)
    if problem:
        return None, problem
    if _unit_problem(claim.text, packet, claim.evidence_ids):
        return None, "unit_mismatch"
    if _sign_problem(claim.text, packet, claim.evidence_ids):
        return None, "sign_mismatch"
    cited_objects = {f.get("object") for f in packet.payload["facts"] if f["id"] in claim.evidence_ids}
    if set(OBJECT_REF.findall(claim.text)) - cited_objects:
        return None, "object_mismatch"
    if _CAUSAL.search(claim.text) and (claim.type is not ClaimType.HYPOTHESIS
                                       or not any(packet.kinds[e] in CAUSAL_KINDS for e in claim.evidence_ids)):
        return None, "causal_without_basis"
    return claim, None


def _template(dropped, reason: str) -> Verdict:
    return Verdict(False, None, (), tuple(dropped), reason)


def judge(answer: Mapping, packet: Packet, allowed_types: frozenset) -> Verdict:
    raws = answer.get("claims") or []
    keys = [bool(r.get("key")) for r in raws] if any(r.get("key") for r in raws) else [True] * len(raws)
    kept, dropped, key_evidence = [], [], set()
    for i, raw in enumerate(raws):
        claim, problem = _claim_problem(raw, packet, allowed_types)
        if problem:
            dropped.append((i, problem))
            if keys[i]:
                return _template(dropped, "key_claim_dropped")
            continue
        kept.append(claim)
        if keys[i]:
            key_evidence |= set(claim.evidence_ids)
    if not kept:
        return _template(dropped, "no_claims_left")
    summary = answer.get("summary")
    try:
        check_text("summary", summary)
    except ValueError:
        return _template(dropped, "summary_invalid")
    if (_text_problem(summary, packet, {abs(n) for e in key_evidence for n in packet.numbers[e]})
            or _sign_problem(summary, packet, key_evidence)):
        return _template(dropped, "summary_unsupported")
    return Verdict(True, summary, tuple(kept), tuple(dropped), None)
