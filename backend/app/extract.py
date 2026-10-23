from __future__ import annotations

from dataclasses import dataclass, field

from app.fields import CATEGORIES, DATE_FIELDS, FIELD_LABELS, GENERIC_TITLES, INT_LIMITS
from app.grounding import supporting_quote, title_is_grounded
from app.textutil import (
    analyze_dates,
    clean_quote,
    normalize,
    parse_amount,
    parse_iso_date,
    parse_positive_int,
    stringify_model_value,
)

NULL_WORDS = {"null", "none", "n/a", "na", "unknown", "not specified", "-"}


@dataclass
class FactDraft:
    field_name: str
    value_text: str
    quote: str | None
    confidence: str
    grounded: bool


@dataclass
class ItemDraft:
    title: str
    merchant: str | None
    category: str
    facts: list[FactDraft] = field(default_factory=list)


# Model keys we accept, mapped to our field names.
_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("merchant", ("merchant", "seller", "store")),
    ("price", ("price_amount", "price", "total")),
    ("currency", ("currency",)),
    ("purchase_date", ("purchase_date", "purchaseDate", "date_of_purchase")),
    ("delivery_date", ("delivery_date", "deliveryDate")),
    ("return_days", ("return_days", "return_window_days", "returnDays")),
    ("warranty_months", ("warranty_months", "warrantyMonths")),
    ("warranty_years", ("warranty_years", "warrantyYears")),
    ("warranty_days", ("warranty_days", "warrantyDays")),
    ("warranty_end", ("warranty_end", "warranty_end_date", "warrantyEnd")),
    ("renewal_date", ("renewal_date", "renewalDate", "next_renewal_date")),
    ("renewal_period_months", ("renewal_period_months", "renewal_period")),
    ("expiry_date", ("expiry_date", "expiration_date", "expiryDate")),
)


def _lookup(raw: dict, names: tuple[str, ...]) -> tuple[object, str | None]:
    quotes = raw.get("quotes") if isinstance(raw.get("quotes"), dict) else {}
    for name in names:
        if name not in raw:
            continue
        value = raw.get(name)
        quote = quotes.get(name)
        if isinstance(value, dict):
            quote = value.get("quote") or quote
            value = value.get("value")
        if isinstance(quote, str):
            quote = quote.strip() or None
        else:
            quote = None
        if value is None or (isinstance(value, str) and value.strip().lower() in NULL_WORDS):
            continue
        return value, quote
    return None, None


def _date_value(raw_text: str) -> tuple[str, bool]:
    """Return a stored value and whether it is a single unambiguous ISO date."""
    iso = parse_iso_date(raw_text)
    if iso is not None:
        return iso.isoformat(), True
    scan = analyze_dates(raw_text)
    if len(scan.dates) == 1 and not scan.ambiguous:
        return scan.dates[0].isoformat(), True
    return raw_text[:80], False


def _build_fact(field_name: str, raw_value: object, model_quote: str | None, document: str) -> FactDraft | None:
    raw_text = stringify_model_value(raw_value)
    if not raw_text or raw_text.lower() in NULL_WORDS:
        return None

    if field_name in DATE_FIELDS:
        stored, unambiguous = _date_value(raw_text)
        if not unambiguous:
            return FactDraft(field_name, stored, clean_quote(model_quote), "low", False)
        quote = supporting_quote(document, field_name, stored, model_quote)
        if quote:
            return FactDraft(field_name, stored, quote, "high", True)
        return FactDraft(field_name, stored, clean_quote(model_quote), "low", False)

    if field_name in INT_LIMITS:
        number = parse_positive_int(raw_text.split(".", 1)[0], INT_LIMITS[field_name])
        if number is None:
            return FactDraft(field_name, raw_text[:40], clean_quote(model_quote), "low", False)
        stored = str(number)
        quote = supporting_quote(document, field_name, stored, model_quote)
        if quote:
            return FactDraft(field_name, stored, quote, "high", True)
        return FactDraft(field_name, stored, clean_quote(model_quote), "low", False)

    if field_name == "price":
        amount = parse_amount(raw_text)
        if amount is None:
            return FactDraft(field_name, raw_text[:40], clean_quote(model_quote), "low", False)
        quote = supporting_quote(document, field_name, amount, model_quote)
        if quote:
            return FactDraft(field_name, amount, quote, "high", True)
        return FactDraft(field_name, amount, clean_quote(model_quote), "low", False)

    if field_name == "currency":
        code = raw_text.strip().upper()
        if len(code) != 3 or not code.isalpha():
            return FactDraft(field_name, raw_text[:8], clean_quote(model_quote), "low", False)
        quote = supporting_quote(document, field_name, code, model_quote)
        if quote:
            return FactDraft(field_name, code, quote, "high", True)
        return FactDraft(field_name, code, clean_quote(model_quote), "low", False)

    if field_name == "merchant":
        merchant = raw_text[:160]
        if normalize(merchant) not in normalize(document):
            return FactDraft(field_name, merchant, clean_quote(model_quote), "low", False)
        quote = supporting_quote(document, field_name, merchant, model_quote) or clean_quote(merchant)
        return FactDraft(field_name, merchant, quote, "high", True)

    return None


def _title(raw: dict, document: str) -> str:
    value, _quote = _lookup(raw, ("title", "product", "name", "item"))
    text = stringify_model_value(value)[:160]
    if not text or normalize(text) in GENERIC_TITLES:
        return "Untitled item"
    if title_is_grounded(text, document):
        return text
    return "Untitled item"


def _category(raw: dict) -> str:
    value = raw.get("category")
    if isinstance(value, dict):
        value = value.get("value")
    text = stringify_model_value(value).lower()
    if text in CATEGORIES:
        return text
    return "other"


def build_item(raw: dict, document: str) -> ItemDraft:
    facts: list[FactDraft] = []
    merchant_value: str | None = None
    for field_name, aliases in _SPECS:
        value, quote = _lookup(raw, aliases)
        if value is None:
            continue
        draft = _build_fact(field_name, value, quote, document)
        if draft is None:
            continue
        facts.append(draft)
        if field_name == "merchant" and draft.grounded:
            merchant_value = draft.value_text
    return ItemDraft(
        title=_title(raw, document),
        merchant=merchant_value,
        category=_category(raw),
        facts=facts,
    )


def item_drafts(payload: dict, document: str) -> list[ItemDraft]:
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    drafts: list[ItemDraft] = []
    for raw in raw_items[:8]:
        if isinstance(raw, dict):
            drafts.append(build_item(raw, document))
    useful = [draft for draft in drafts if draft.facts or draft.title != "Untitled item"]
    if useful:
        return useful
    return drafts[:1]


def placeholder_item() -> ItemDraft:
    return ItemDraft(title="Untitled item", merchant=None, category="document", facts=[])


def field_label(field_name: str) -> str:
    return FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())
