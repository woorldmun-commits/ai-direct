"""Санитизация поисковых запросов на противниковых примерах из security-ревью: всё, что утекало, — теперь тест."""

import time

import pytest

from app.sync.sanitize import MASK, sanitize

LEAKS = [
    # телефоны с любыми разделителями, без «+», полноширинными цифрами, в ссылке мессенджера
    "8.916.123.45.67", "tel: 8(916)123.45.67", "+7/916/123/45/67", "+7 916 12 34 567", "8 916 123 4 567",
    "+7 9 1 6 1 2 3 4 5 6 7", "8‑916‑123‑45‑67", "8–916–123–45–67", "79161234567", "wa.me/79161234567",
    "８９１６１２３４５６７", "тел 89161234567",
    # документы: паспорт, карта, СНИЛС, ИНН (в том числе через пробел и 12-значный)
    "паспорт 45 12 345678", "4512 345678", "серия 4512 номер 345 678", "4276 1234 5678 9012", "4276-1234-5678-9012",
    "снилс 123-456-789 01", "7707 083893", "770708389312",
    # контакты и ссылки без схемы
    "t.me/ivan_petrov", "@ivan_petrov", "yandex.ru/search?text=x", "vk.com/id12345", "instagram.com/ivan",
    "ivan @ mail.ru", "ivan(at)mail.ru", "иван@почта.рф", "https://shop.ru/item?id=5",
    # адреса с маркерами
    "москва пр-т мира 10 стр 2", "дом 5 кв 12", "москва д. 12 кв. 4", "доставка ул ленина 5",
]
SECRETS = ["916", "123", "4512", "345678", "4276", "7707", "0838", "ivan", "petrov", "иван", "мира", "ленина",
           "12345", "５６７"]


@pytest.mark.parametrize("raw", LEAKS)
def test_no_personal_data_survives(raw):
    clean = sanitize(raw)
    assert MASK in clean
    assert not any(s in clean for s in SECRETS if s in raw), clean


@pytest.mark.parametrize("raw", ["купить диван", "купить квартиру", "купить 50 кв м дешево", "диван 2024",
                                 "iphone 15 pro", "ремонт квартир под ключ"])
def test_ordinary_queries_are_kept(raw):
    assert sanitize(raw) == raw


def test_newlines_do_not_hide_markers():
    assert sanitize("line1\nинн 7707\nline3") == "line1 ***"


def test_long_input_is_bounded_and_fast():
    """Патологический ввод не вешает синхронизацию: длина ограничена, шаблоны без катастрофического перебора."""
    start = time.perf_counter()
    for text in ("a@" * 5000, "1 " * 5000, "@" + "a" * 10000):
        assert len(sanitize(text)) <= 400
    assert time.perf_counter() - start < 1


def test_known_limitation_address_without_marker():
    """Адрес без маркера регуляркой не отличить от «iphone 15 pro» — второй барьер: тексты не уходят в LLM,
    хранятся 60 дней; дальше — NER (Natasha), ARCHITECTURE.md §2.4."""
    assert sanitize("г. москва ленина 5") == "г. москва ленина 5"
