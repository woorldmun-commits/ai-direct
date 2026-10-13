"""Evidence Judge (AI_GOVERNANCE.md §2.3): детерминированная проверка ответа LLM против промпт-пакета.

Утверждение отбрасывается, если: нарушает контракт Claim (FACT / DERIVED_FACT от ИИ, недопустимый статус
причинности); ссылается на несуществующий evidence_id; содержит число, которого нет в процитированных фактах
(сравнение точное, по значению: «4 820» = 4820.00; округление не допускается — открытый вопрос §6.1); упоминает
неизвестную ссылку obj_N; похоже на инъекцию или ссылку; причинно («из-за») без HYPOTHESIS и причинного факта.
Отброшено ключевое утверждение, не осталось ни одного или не прошёл summary → весь ответ на шаблон."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from app.intelligence.contracts._validate import check_text
from app.intelligence.contracts.claims import CausalStatus, Claim, ClaimType
from app.intelligence.privacy import OBJECT_REF, Packet

CAUSAL_KINDS = frozenset({"finding", "policy_reason", "metric_change"})
_NUMBER = re.compile(r"(?<![\w@.,])\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?(?!\w)|(?<![\w@.,])\d+(?:[.,]\d+)?(?!\w)")
# ponytail: закрытые списки маркеров (§6 п.4); причинность без маркеров не ловится
_CAUSAL = re.compile(r"из-за|потому что|вследствие|в результате|привел|привёл|приводит|вызва|because|due to|caus",
                     re.IGNORECASE)
_INJECTION = re.compile(r"ignore|игнорир|инструкц|instruction|system|промпт|prompt|https?://|www\.|\S+@\S+\.\w+|<\s*/?"
                        r"\s*[a-z]", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    summary: str | None
    claims: tuple[Claim, ...]
    dropped: tuple[tuple[int, str], ...]  # (номер утверждения, код причины) — без текста, годится в лог
    reason: str | None                    # почему весь ответ ушёл на шаблон


def numbers_in(text: str) -> set[Decimal]:
    found = set()
    for match in _NUMBER.findall(text):
        found.add(abs(Decimal(re.sub(r"[   ]", "", match).replace(",", "."))))
    return found


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
    if _text_problem(summary, packet, {abs(n) for e in key_evidence for n in packet.numbers[e]}):
        return _template(dropped, "summary_unsupported")
    return Verdict(True, summary, tuple(kept), tuple(dropped), None)
