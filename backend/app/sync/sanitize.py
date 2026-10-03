"""Санитизация текста до записи в снимок (ARCHITECTURE.md §2.4). Свободный текст в MVP один —
текст поискового запроса. Имена людей регулярками не ловятся: второй барьер — тексты запросов не уходят в LLM
и хранятся 60 дней.

Порядок важен: сначала нормализация (NFKC: полноширинные цифры → ASCII; все пробельные символы, включая переводы
строк, → один пробел; длина ограничена), затем контакты и ссылки, затем маркеры адреса/документов, затем любые
группы цифр. Осознанный перекос в сторону приватности: «диван 160 200» тоже маскируется (5+ цифр через
разделители) — лучше потерять размер в минус-слове, чем пропустить телефон «916.123.45.67»."""

import re
import unicodedata

MASK = "***"
MAX_LENGTH = 400  # реальные запросы короче; предел защищает регулярки от патологически длинного ввода

_SEP = r"[\s\-.()/+_‐‑‒–—―]"
_PATTERNS = [
    # email, в том числе «ivan @ mail.ru» и «ivan(at)mail.ru»; линейный шаблон — без катастрофического перебора
    re.compile(r"[^\s@]+\s*(?:@|\(at\)|\[at\])\s*[^\s@]+\.[^\s@]+", re.IGNORECASE),
    # ссылки: со схемой, www., домены и мессенджеры без схемы (t.me/…, vk.com/…, site.ru/?q=…)
    re.compile(r"(?:[a-z]+://|www\.)\S+", re.IGNORECASE),
    re.compile(r"(?<![\w@])[\w-]+(?:\.[\w-]+)*\.(?:ru|рф|su|com|net|org|me|io|info|biz|pro|by|kz|ua|uz|online|site|"
               r"shop|store)(?![\w-])\S*", re.IGNORECASE),
    re.compile(r"(?<!\w)@[\w.]{3,}"),  # @ник
    # маркеры документов, контактов и адреса — всё до конца строки
    re.compile(r"(?<!\w)(?:инн|снилс|паспорт\w*|серия|тел(?:ефон)?|phone|whats\s?app|вотсап|ватсап|telegram|"
               r"телеграм\w*|ул|улица|пр-т|просп\w*|пер|переулок|наб|набережная|шоссе|бульвар|б-р|корп|корпус)"
               r"(?!\w).*$", re.IGNORECASE),
    # номер дома/квартиры/строения: «д. 12», «кв 4», «стр 2» (без цифры «кв» — это «50 кв м»)
    re.compile(r"(?<!\w)(?:д|дом|кв|стр)\.?\s*\d.*$", re.IGNORECASE),
    # любые цифры: 5+ цифр подряд или через разделители — телефон, ИНН, паспорт, карта, СНИЛС, заказ
    re.compile(rf"\+?\d(?:{_SEP}*\d){{4,}}"),
]


def sanitize(text: str) -> str:
    text = " ".join(unicodedata.normalize("NFKC", text).split())[:MAX_LENGTH]
    for pattern in _PATTERNS:
        text = pattern.sub(MASK, text)
    text = re.sub(r"\*{3}(?:\s*\*{3})+", MASK, text)
    return " ".join(text.split())


# --- Площадки РСЯ -----------------------------------------------------------------------------------------------
# Placement — домен сайта («avito.ru») или идентификатор приложения («com.avito.android»), не ПД и не свободный
# текст. Поэтому не маскирование кусков, а строгий allowlist формы: метки из латиницы/кириллицы/цифр/«-» через точку
# (как в домене: «-» не первым и не последним символом метки, «_» нет), хотя бы одна буква, длина — не больше домена
# (253). Нормализация: NFKC, нижний регистр, без «www.» и завершающей точки — «WWW.Avito.ru.» и «avito.ru» одна
# площадка. Всё остальное → MASK: такой строке в снимке не место, а правило не предлагает исключать площадку без имени.
# Сверх формы — то, что похоже на номер или подделку, а не на имя площадки (тоже MASK):
# - метка целиком из цифр или любая метка с ≥ 7 цифрами — телефон, номер договора, IP;
# - латиница и кириллица в одной метке — гомоглифы («аvito.ru» с кириллической «а»).
# Те же правила — CHECK таблицы placement_names (db/schema.sql).
MAX_PLACEMENT_LENGTH = 253
MAX_LABEL_DIGITS = 6
_LABEL = r"[0-9a-zа-яё](?:[0-9a-zа-яё-]{0,61}[0-9a-zа-яё])?"
_PLACEMENT = re.compile(rf"{_LABEL}(?:\.{_LABEL})*")


def _suspicious(label: str) -> bool:
    digits = sum(c.isdigit() for c in label)
    mixed = re.search(r"[a-z]", label) and re.search(r"[а-яё]", label)
    return digits == len(label) or digits > MAX_LABEL_DIGITS or bool(mixed)


def sanitize_placement(raw: str) -> str:
    name = unicodedata.normalize("NFKC", raw).strip().lower().rstrip(".")
    name = name.removeprefix("www.")
    if (len(name) > MAX_PLACEMENT_LENGTH or not _PLACEMENT.fullmatch(name) or not re.search(r"[a-zа-яё]", name)
            or any(_suspicious(label) for label in name.split("."))):
        return MASK
    return name
