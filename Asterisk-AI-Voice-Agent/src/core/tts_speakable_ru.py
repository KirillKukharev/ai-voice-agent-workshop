"""Normalize assistant text for Russian TTS: digits and screen-style times/dates → words."""

from __future__ import annotations

import re
from typing import Match

# Hours 0–23 as spoken in 24h-style phrases (no declension; good enough for telephony).
_H24 = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
    "двадцать",
    "двадцать один",
    "двадцать два",
    "двадцать три",
)

_UNITS = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
_TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят")

_MONTH_GEN = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

# Neuter ordinals for calendar day (девятое ноября …).
_ORD_NEUT = (
    "",
    "первое",
    "второе",
    "третье",
    "четвёртое",
    "пятое",
    "шестое",
    "седьмое",
    "восьмое",
    "девятое",
    "десятое",
    "одиннадцатое",
    "двенадцатое",
    "тринадцатое",
    "четырнадцатое",
    "пятнадцатое",
    "шестнадцатое",
    "семнадцатое",
    "восемнадцатое",
    "девятнадцатое",
    "двадцатое",
    "двадцать первое",
    "двадцать второе",
    "двадцать третье",
    "двадцать четвёртое",
    "двадцать пятое",
    "двадцать шестое",
    "двадцать седьмое",
    "двадцать восьмое",
    "двадцать девятое",
    "тридцатое",
    "тридцать первое",
)


def _minutes_words(m: int) -> str:
    if m < 0 or m > 59:
        return str(m)
    if m == 0:
        return "ноль ноль"
    if m < 10:
        return f"ноль {_UNITS[m]}"
    if m < 20:
        return _TEENS[m - 10]
    tens, u = divmod(m, 10)
    head = _TENS[tens]
    if u == 0:
        return head
    return f"{head} {_UNITS[u]}"


def _clock_words(h: int, m: int) -> str:
    if 0 <= h <= 23:
        hw = _H24[h]
    else:
        hw = str(h)
    return f"{hw} {_minutes_words(m)}"


def _year_phrase(y: int) -> str:
    """Spoken year like 2026 → «две тысячи двадцать шесть» (cardinal tail, clear for TTS)."""
    if y < 2000 or y > 2099:
        return str(y)
    if y == 2000:
        return "две тысячи"
    last = y % 100
    if last == 0:
        return "две тысячи"
    if last < 10:
        tail = _UNITS[last]
    elif last < 20:
        tail = _TEENS[last - 10]
    else:
        tens, u = divmod(last, 10)
        tail = _TENS[tens] if u == 0 else f"{_TENS[tens]} {_UNITS[u]}"
    return f"две тысячи {tail}"


def _date_ymd_words(y: int, month: int, day: int) -> str:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    if day >= len(_ORD_NEUT):
        return ""
    ord_day = _ORD_NEUT[day]
    mname = _MONTH_GEN[month]
    yw = _year_phrase(y)
    return f"{ord_day} {mname} {yw}"


def _replace_iso_date(m: Match[str]) -> str:
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    w = _date_ymd_words(y, mo, d)
    return w if w else m.group(0)


def _replace_dotted_date(m: Match[str]) -> str:
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000 if y < 70 else 1900
    w = _date_ymd_words(y, mo, d)
    return w if w else m.group(0)


def _replace_clock(m: Match[str]) -> str:
    h = int(m.group(1))
    mi = int(m.group(2))
    if h > 23 or mi > 59:
        return m.group(0)
    return _clock_words(h, mi)


def _replace_plus7(m: Match[str]) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if len(digits) != 11 or not digits.startswith("7"):
        return m.group(0)
    body = digits[1:]
    parts = ["плюс семь"]
    for ch in body:
        parts.append(_UNITS[int(ch)])
    return ", ".join(parts)


def normalize_russian_tts_text(text: str) -> str:
    """Rewrite digit-heavy fragments so Silero/other RU TTS reads words, not digit strings."""
    if not text or not text.strip():
        return text

    s = text.replace("\u202f", " ").replace("\xa0", " ")

    # ISO dates 2026-04-06 (skip if glued to URL path / or query =)
    def iso_sub(mm: Match[str]) -> str:
        if mm.start() > 0 and mm.string[mm.start() - 1] in "/=":
            return mm.group(0)
        return _replace_iso_date(mm)

    s = re.sub(
        r"(?<![\w/])(\d{4})-(\d{2})-(\d{2})(?![\w-])",
        iso_sub,
        s,
    )

    # Dotted dates 06.04.2026 or 6.4.26
    s = re.sub(
        r"(?<![\w.])(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?![\w.])",
        _replace_dotted_date,
        s,
    )

    # Clock 10:00, 9:05, optional seconds (ignored for speech)
    s = re.sub(
        r"(?<![\w:])(\d{1,2}):(\d{2})(?::\d{2})?(?![\w:])",
        _replace_clock,
        s,
    )

    # Russian mobile +7 and ten digits (spaces/dashes between digits allowed)
    s = re.sub(
        r"\+7(?:[\s\-]*\d){10}(?!\d)",
        _replace_plus7,
        s,
    )

    return s
