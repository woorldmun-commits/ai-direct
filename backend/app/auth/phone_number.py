"""Номер для входа: только российский мобильный (+7 9XX XXX-XX-XX) → E.164. Всё остальное — отказ без отправки.

Защита от SMS pumping начинается здесь: SMS уходит только на российские мобильные коды (DEF 9XX). Иностранные
номера, в т.ч. с тем же кодом страны +7 (Казахстан: +7 6XX/7XX), городские, короткие и платные — не принимаются.
+7 940 — мобильные сети Абхазии (не российский оператор) — тоже отказ; перечень исключений сверять с реестром
Россвязи (план нумерации) — **проверить** перед запуском."""

import re

MAX_INPUT_LENGTH = 32  # длиннее любой записи номера с пробелами и скобками — дальше не разбираем
# Разделители, которые люди пишут в номере: пробелы, скобки, дефисы, точки.
_SEPARATORS = re.compile(r"[\s()\-. ]")
_E164_RU_MOBILE = re.compile(r"\+79\d{9}")
NOT_RUSSIAN_MOBILE = frozenset({"940"})  # DEF-коды +7 9XX вне российских операторов


class InvalidPhone(ValueError):
    """Номер не российский мобильный или записан неразборчиво (API: 400 invalid_request)."""


def normalize_phone(raw: object) -> str:
    """'8 (912) 345-67-89', '+7 912 345 67 89', '79123456789' → '+79123456789'. Иное — InvalidPhone."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_INPUT_LENGTH:
        raise InvalidPhone("phone")
    compact = _SEPARATORS.sub("", raw)
    if compact.startswith("+7"):
        digits = compact[2:]
    elif compact.startswith(("8", "7")) and not compact.startswith("+"):
        digits = compact[1:]
    else:
        raise InvalidPhone("phone")  # +380…, 00…, 9123456789 без кода страны — не угадываем
    phone = "+7" + digits
    # isascii: \d в Python совпадает и с не-ASCII цифрами («٩١٢…») — такие не принимаем
    if not (phone.isascii() and _E164_RU_MOBILE.fullmatch(phone)) or digits[:3] in NOT_RUSSIAN_MOBILE:
        raise InvalidPhone("phone")
    return phone


def phone_prefix(phone_e164: str) -> str:
    """'+79123456789' → '+7912': код оператора/региона для счётчиков аномалий (не идентифицирует абонента)."""
    return phone_e164[:5]
