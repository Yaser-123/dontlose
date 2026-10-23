from __future__ import annotations

import re

from app.errors import AppError
from app.fields import CATEGORIES, DATE_FIELDS, FIELD_LABELS, INT_LIMITS, ITEM_STATUSES
from app.textutil import (
    analyze_dates,
    parse_amount,
    parse_iso_date,
    parse_positive_int,
    stringify_model_value,
)


class ValidationError(AppError):
    pass


class NotFound(AppError):
    pass


_ID = re.compile(r"^[a-f0-9]{32}$")


def parse_id(value: str, label: str = "That record") -> str:
    if not _ID.fullmatch(value or ""):
        raise NotFound(f"{label} was not found.")
    return value


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return stringify_model_value(value).strip()


def canonical_fact_value(field_name: str, raw: object) -> str:
    if field_name not in FIELD_LABELS:
        raise ValidationError("That field is not tracked.")
    text = _text(raw)
    if not text:
        raise ValidationError(f"Enter a {FIELD_LABELS[field_name].lower()}.")

    if field_name in DATE_FIELDS:
        parsed = parse_iso_date(text)
        if parsed is not None:
            return parsed.isoformat()
        scan = analyze_dates(text)
        if scan.ambiguous:
            raise ValidationError(
                f"{FIELD_LABELS[field_name]} could be read two ways. Enter it as YYYY-MM-DD."
            )
        if len(scan.dates) == 1:
            return scan.dates[0].isoformat()
        raise ValidationError(f"{FIELD_LABELS[field_name]} needs a real date in YYYY-MM-DD form.")

    if field_name in INT_LIMITS:
        whole = text.split(".", 1)[0] if re.fullmatch(r"\d+\.0+", text) else text
        number = parse_positive_int(whole, INT_LIMITS[field_name])
        if number is None:
            raise ValidationError(
                f"{FIELD_LABELS[field_name]} needs a whole number of 1 to {INT_LIMITS[field_name]}."
            )
        return str(number)

    if field_name == "price":
        amount = parse_amount(text)
        if amount is None:
            raise ValidationError("Enter a price like 249.00.")
        return amount

    if field_name == "currency":
        code = text.upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValidationError("Currency needs a 3-letter code such as USD.")
        return code

    if field_name == "merchant":
        if len(text) > 160:
            raise ValidationError("Merchant needs to be 160 characters or fewer.")
        return text

    raise ValidationError("That field is not tracked.")


def clean_manual(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("The item could not be read.")
    title = _text(data.get("title"))
    if not title:
        raise ValidationError("Give the item a name.")
    if len(title) > 160:
        raise ValidationError("The name needs to be 160 characters or fewer.")

    category = _text(data.get("category") or "other").lower()
    if category not in CATEGORIES:
        raise ValidationError("Choose a category from the list.")

    notes = _text(data.get("notes"))
    if len(notes) > 2000:
        raise ValidationError("Notes need to be 2000 characters or fewer.")

    facts: list[tuple[str, str]] = []
    merchant = None
    if not _blank(data.get("merchant")):
        merchant = canonical_fact_value("merchant", data.get("merchant"))
        facts.append(("merchant", merchant))

    for field_name in ("price", "currency", *DATE_FIELDS, *INT_LIMITS):
        if _blank(data.get(field_name)):
            continue
        facts.append((field_name, canonical_fact_value(field_name, data.get(field_name))))

    return {
        "title": title,
        "merchant": merchant,
        "category": category,
        "notes": notes,
        "facts": facts,
    }


def clean_item_patch(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("The item could not be read.")
    cleaned: dict = {}
    if "title" in data:
        title = _text(data.get("title"))
        if not title:
            raise ValidationError("Give the item a name.")
        if len(title) > 160:
            raise ValidationError("The name needs to be 160 characters or fewer.")
        cleaned["title"] = title
    if "merchant" in data:
        if _blank(data.get("merchant")):
            cleaned["merchant"] = None
        else:
            cleaned["merchant"] = canonical_fact_value("merchant", data.get("merchant"))
    if "category" in data:
        category = _text(data.get("category")).lower()
        if category not in CATEGORIES:
            raise ValidationError("Choose a category from the list.")
        cleaned["category"] = category
    if "status" in data:
        status = _text(data.get("status")).lower()
        if status not in ITEM_STATUSES:
            raise ValidationError("Status needs to be active, resolved, or archived.")
        cleaned["status"] = status
    if "notes" in data:
        notes = _text(data.get("notes"))
        if len(notes) > 2000:
            raise ValidationError("Notes need to be 2000 characters or fewer.")
        cleaned["notes"] = notes
    if not cleaned:
        raise ValidationError("Nothing to update.")
    return cleaned


def clean_note(data: object) -> str:
    if not isinstance(data, dict):
        raise ValidationError("The note could not be read.")
    body = _text(data.get("body"))
    if not body:
        raise ValidationError("Write a note first.")
    if len(body) > 2000:
        raise ValidationError("A note needs to be 2000 characters or fewer.")
    return body


def clean_reminder(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("The reminder could not be read.")
    message = _text(data.get("message"))
    if not message:
        raise ValidationError("Write a reminder message.")
    if len(message) > 240:
        raise ValidationError("The reminder needs to be 240 characters or fewer.")
    remind_at = _text(data.get("remind_at"))
    if not remind_at:
        raise ValidationError("Choose a date and time.")
    from datetime import datetime

    normalized = remind_at.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError("Choose a valid date and time.") from exc
    if parsed.tzinfo is None:
        raise ValidationError("The reminder time needs a timezone.")
    item_id = data.get("item_id") or None
    deadline_id = data.get("deadline_id") or None
    if item_id is not None and not isinstance(item_id, str):
        raise ValidationError("The item could not be read.")
    if deadline_id is not None and not isinstance(deadline_id, str):
        raise ValidationError("The deadline could not be read.")
    return {
        "message": message,
        "remind_at": parsed.isoformat(),
        "item_id": item_id,
        "deadline_id": deadline_id,
    }
