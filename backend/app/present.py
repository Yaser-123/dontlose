from __future__ import annotations

from datetime import date

from app.deadlines import severity_for
from app.fields import DEADLINE_LABELS, FIELD_LABELS
from app.store import counts, list_bundles, list_deadlines
from app.textutil import parse_amount

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}


def _preferred(facts: list[dict], name: str) -> dict | None:
    rank = {"corrected": 3, "confirmed": 2, "extracted": 1}
    pool = [
        fact
        for fact in facts
        if fact["field_name"] == name and fact["status"] != "rejected" and fact.get("value_text")
    ]
    if not pool:
        return None
    pool.sort(key=lambda fact: (rank.get(fact["status"], 0), fact.get("updated_at") or ""), reverse=True)
    return pool[0]


def _price(price: dict | None, currency: dict | None) -> str | None:
    if price is None:
        return None
    amount = parse_amount(price["value_text"]) or price["value_text"]
    code = currency["value_text"] if currency else ""
    symbol = SYMBOLS.get(code)
    if symbol:
        return f"{symbol}{amount}"
    if code:
        return f"{amount} {code}"
    return amount


def _needs_review(bundle: dict) -> bool:
    if any(fact["status"] == "extracted" for fact in bundle["facts"]):
        return True
    return bool(bundle["gaps"])


def deadline_out(row: dict, today: date, item_title: str | None = None, merchant: str | None = None) -> dict:
    due = date.fromisoformat(row["due_date"])
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "item_title": item_title if item_title is not None else row.get("item_title"),
        "merchant": merchant if merchant is not None else row.get("merchant"),
        "kind": row["kind"],
        "label": DEADLINE_LABELS.get(row["kind"], row["kind"].replace("_", " ").title()),
        "due_date": row["due_date"],
        "basis": row["basis"],
        "provisional": bool(row["provisional"]),
        "status": row["status"],
        "severity": severity_for(due, today),
        "days_remaining": (due - today).days,
    }


def fact_out(fact: dict) -> dict:
    return {
        "id": fact["id"],
        "field_name": fact["field_name"],
        "label": FIELD_LABELS.get(fact["field_name"], fact["field_name"].replace("_", " ").title()),
        "value_text": fact["value_text"],
        "quote": fact.get("quote"),
        "confidence": fact["confidence"],
        "status": fact["status"],
        "grounded": bool(fact["grounded"]),
        "document_id": fact.get("document_id"),
        "document_name": fact.get("document_name"),
    }


def document_out(row: dict, include_text: bool = False) -> dict:
    payload = {
        "id": row["id"],
        "original_name": row["original_name"],
        "mime_type": row.get("mime_type"),
        "size_bytes": row["size_bytes"],
        "page_count": row.get("page_count"),
        "processing_status": row["processing_status"],
        "processing_stage": row["processing_stage"],
        "error_message": row.get("error_message"),
        "result_note": row.get("result_note"),
        "created_at": row["created_at"],
        "processed_at": row.get("processed_at"),
        "file_path": f"/documents/{row['id']}/file",
        "items": row.get("linked_items") or [],
    }
    if include_text:
        payload["ocr_text"] = row.get("ocr_text")
    return payload


def item_summary(bundle: dict, today: date | None = None) -> dict:
    today = today or date.today()
    item = bundle["item"]
    facts = bundle["facts"]
    deadlines = [
        deadline_out(row, today, item["title"], item.get("merchant")) for row in bundle["deadlines"]
    ]
    open_deadlines = sorted(
        (row for row in deadlines if row["status"] == "open"),
        key=lambda row: row["due_date"],
    )
    purchased = _preferred(facts, "purchase_date")
    return {
        "id": item["id"],
        "title": item["title"],
        "merchant": item.get("merchant"),
        "category": item["category"],
        "status": item["status"],
        "deadline_anchor": item.get("deadline_anchor"),
        "notes": item.get("notes") or "",
        "price_display": _price(_preferred(facts, "price"), _preferred(facts, "currency")),
        "purchase_date": purchased["value_text"] if purchased else None,
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "needs_review": _needs_review(bundle),
        "open_deadline_count": len(open_deadlines),
        "next_deadline": open_deadlines[0] if open_deadlines else None,
    }


def item_detail(record: dict) -> dict:
    today = date.today()
    item = record["item"]
    deadlines = [
        deadline_out(row, today, item["title"], item.get("merchant"))
        for row in sorted(record["deadlines"], key=lambda row: row["due_date"])
    ]
    return {
        "item": item_summary(record, today),
        "facts": [fact_out(fact) for fact in sorted(record["facts"], key=lambda fact: fact["field_name"])],
        "deadlines": deadlines,
        "gaps": [{"id": gap["id"], "message": gap["message"]} for gap in record["gaps"]],
        "documents": [document_out(document, include_text=True) for document in record.get("documents") or []],
        "suggestions": [
            {
                "item_id": row["item_id"],
                "title": row["title"],
                "merchant": row.get("merchant"),
                "reason": row["reason"],
            }
            for row in record.get("suggestions") or []
        ],
        "notes": [
            {"id": row["id"], "body": row["body"], "created_at": row["created_at"]}
            for row in record.get("notes") or []
        ],
    }


def reminder_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "item_id": row.get("item_id"),
        "item_title": row.get("item_title"),
        "deadline_id": row.get("deadline_id"),
        "remind_at": row["remind_at"],
        "message": row["message"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def dashboard() -> dict:
    today = date.today()
    summaries = [item_summary(bundle, today) for bundle in list_bundles(status="active", limit=300)]
    deadlines = [deadline_out(row, today) for row in list_deadlines("open")]
    return {
        "today": today.isoformat(),
        "counts": counts(today.isoformat()),
        "alerts": [row for row in deadlines if row["severity"] in ("overdue", "critical", "high")][:8],
        "upcoming": [row for row in deadlines if row["days_remaining"] > 7][:8],
        "needs_review": [row for row in summaries if row["needs_review"]][:8],
        "recent_items": sorted(summaries, key=lambda row: row["updated_at"], reverse=True)[:6],
    }
