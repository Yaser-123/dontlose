from __future__ import annotations

import re

from app.fields import CURRENCY_MARKS, DATE_FIELDS, FIELD_KEYWORDS, INT_LIMITS
from app.textutil import (
    amount_in_text,
    analyze_dates,
    clean_quote,
    integer_in_text,
    normalize,
    parse_amount,
    parse_iso_date,
    parse_positive_int,
    quote_in_text,
    unambiguous_dates,
)


def _windows(document: str) -> list[str]:
    lines = [line.strip() for line in document.splitlines() if line.strip()]
    if not lines:
        return [document.strip()] if document.strip() else []
    windows: list[str] = []
    for index, line in enumerate(lines):
        windows.append(line)
        if index:
            windows.append(f"{lines[index - 1]} {line}")
    return windows


UNIT_WORDS = {
    "return_days": ("day",),
    "warranty_months": ("month",),
    "warranty_years": ("year",),
    "warranty_days": ("day",),
    "renewal_period_months": ("month",),
}


def _keywords_present(field_name: str, text: str) -> bool:
    lowered = text.lower()
    words = FIELD_KEYWORDS.get(field_name, ())
    if words and not any(word in lowered for word in words):
        return False
    units = UNIT_WORDS.get(field_name, ())
    if units and not any(unit in lowered for unit in units):
        return False
    return True


def _value_supported(field_name: str, canonical: str, excerpt: str) -> bool:
    if field_name in DATE_FIELDS:
        target = parse_iso_date(canonical)
        return target is not None and target in unambiguous_dates(excerpt)
    if field_name in INT_LIMITS:
        number = parse_positive_int(canonical, INT_LIMITS[field_name])
        if number is None or not integer_in_text(number, excerpt):
            return False
        return _keywords_present(field_name, excerpt)
    if field_name == "price":
        if not amount_in_text(canonical, excerpt):
            return False
        return _keywords_present(field_name, excerpt)
    if field_name == "currency":
        return _currency_supported(canonical, excerpt)
    if field_name == "merchant":
        return normalize(canonical) in normalize(excerpt)
    return False


def _currency_supported(code: str, excerpt: str) -> bool:
    marks = CURRENCY_MARKS.get(code.upper(), (code.lower(),))
    lowered = excerpt.lower()
    return any(mark.lower() in lowered for mark in marks)


def _scan(document: str, field_name: str, canonical: str) -> str | None:
    if field_name in DATE_FIELDS:
        target = parse_iso_date(canonical)
        if target is None:
            return None
        for window in _windows(document):
            if target in unambiguous_dates(window):
                return clean_quote(window)
        return None

    for window in _windows(document):
        if _value_supported(field_name, canonical, window):
            return clean_quote(window)
    return None


def supporting_quote(
    document: str,
    field_name: str,
    canonical: str,
    model_quote: str | None,
) -> str | None:
    """Return an excerpt that actually contains the value, or None.

    A model's quote is used only when it appears in the document and the
    value can be read from that excerpt without resolving an ambiguous date.
    """
    if model_quote and quote_in_text(model_quote, document):
        if _value_supported(field_name, canonical, model_quote):
            return clean_quote(model_quote)
    return _scan(document, field_name, canonical)


def title_is_grounded(title: str, document: str) -> bool:
    cleaned = normalize(title)
    if len(cleaned) < 2:
        return False
    return cleaned in normalize(document)


def text_has_ambiguous_date(text: str) -> bool:
    return bool(analyze_dates(text).ambiguous)


def line_mentions_number(text: str, number: int) -> bool:
    return integer_in_text(number, text) and bool(re.search(r"\d", text))
