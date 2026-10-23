from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTH_PATTERN = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\.?"
)

NAMED_MONTH_DAY = re.compile(
    rf"\b{MONTH_PATTERN}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(19\d{{2}}|20\d{{2}})\b",
    re.IGNORECASE,
)
DAY_NAMED_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN},?\s+(19\d{{2}}|20\d{{2}})\b",
    re.IGNORECASE,
)
YEAR_FIRST = re.compile(r"\b(19\d{2}|20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
DAY_OR_MONTH_FIRST = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](19\d{2}|20\d{2})\b")


@dataclass
class DateScan:
    dates: list[date] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)


def normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.fullmatch(r"(19\d{2}|20\d{2})-(\d{2})-(\d{2})", value.strip())
    if not match:
        return None
    try:
        parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    if parsed < date(1990, 1, 1) or parsed > date(2100, 12, 31):
        return None
    return parsed


def _in_range(parsed: date) -> bool:
    return date(1990, 1, 1) <= parsed <= date(2100, 12, 31)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if not _in_range(parsed):
        return None
    return parsed


def _add_unique(found: list[date], parsed: date | None) -> None:
    if parsed is not None and parsed not in found:
        found.append(parsed)


def analyze_dates(text: str | None) -> DateScan:
    """Find calendar dates that can be read without choosing an interpretation."""
    source = normalize(text)
    found: list[date] = []
    ambiguous: list[str] = []

    for match in NAMED_MONTH_DAY.finditer(source):
        month = MONTHS[match.group(1).lower().rstrip(".")]
        _add_unique(found, _safe_date(int(match.group(3)), month, int(match.group(2))))

    for match in DAY_NAMED_MONTH.finditer(source):
        month = MONTHS[match.group(2).lower().rstrip(".")]
        _add_unique(found, _safe_date(int(match.group(3)), month, int(match.group(1))))

    for match in YEAR_FIRST.finditer(source):
        _add_unique(
            found,
            _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3))),
        )

    for match in DAY_OR_MONTH_FIRST.finditer(source):
        first = int(match.group(1))
        second = int(match.group(2))
        year = int(match.group(3))
        options: list[date] = []
        for month, day in ((first, second), (second, first)):
            parsed = _safe_date(year, month, day)
            if parsed is not None and parsed not in options:
                options.append(parsed)
        if len(options) == 1:
            _add_unique(found, options[0])
        elif len(options) > 1:
            ambiguous.append(match.group(0))

    return DateScan(dates=found, ambiguous=ambiguous)


def unambiguous_dates(text: str | None) -> list[date]:
    return analyze_dates(text).dates


def parse_amount(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", "")
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "").replace("₹", "")
    cleaned = cleaned.strip()
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount < 0 or amount > Decimal("10000000"):
        return None
    return format(amount.quantize(Decimal("0.01")), "f")


def amount_in_text(canonical: str, text: str | None) -> bool:
    target = parse_amount(canonical)
    if target is None or not text:
        return False
    wanted = Decimal(target)
    for match in re.finditer(r"\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?", text):
        parsed = parse_amount(match.group(0))
        if parsed is not None and Decimal(parsed) == wanted:
            return True
    return False


def parse_positive_int(value: str | None, limit: int) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not re.fullmatch(r"\d+", raw):
        return None
    number = int(raw)
    if number < 1 or number > limit:
        return None
    return number


def integer_in_text(number: int, text: str | None) -> bool:
    if text is None:
        return False
    return re.search(rf"\b{number}\b", text) is not None


def quote_in_text(quote: str | None, document: str | None) -> bool:
    cleaned = normalize(quote)
    if len(cleaned) < 4 or not document:
        return False
    return cleaned in normalize(document)


def clean_quote(quote: str | None, limit: int = 320) -> str | None:
    cleaned = re.sub(r"\s+", " ", quote or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def stringify_model_value(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    return str(value).strip()
