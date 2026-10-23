from app.extract import item_drafts
from app.grounding import supporting_quote
from app.deadlines import compute
from datetime import date


RECEIPT = """
ACME ELECTRONICS
SoundBar 500
Date: March 2, 2026
Total: $249.00
Items may be returned within 30 days of purchase.
Warranty: 12 months from the date of purchase.
"""


def test_named_date_price_and_terms_are_grounded():
    assert supporting_quote(RECEIPT, "purchase_date", "2026-03-02", None)
    assert supporting_quote(RECEIPT, "return_days", "30", None)
    assert supporting_quote(RECEIPT, "warranty_months", "12", None)
    assert supporting_quote(RECEIPT, "price", "249.00", None)
    assert supporting_quote(RECEIPT, "currency", "USD", "Total: $249.00")
    assert supporting_quote(RECEIPT, "return_days", "14", None) is None


def test_ambiguous_numeric_date_is_not_grounded():
    text = "Purchased 03/04/2026"
    assert supporting_quote(text, "purchase_date", "2026-03-04", "Purchased 03/04/2026") is None
    assert supporting_quote(text, "purchase_date", "2026-04-03", "Purchased 03/04/2026") is None


def test_unambiguous_numeric_dates():
    assert supporting_quote("Date 04/18/2026", "purchase_date", "2026-04-18", None)
    assert supporting_quote("Delivered 13/04/2026", "delivery_date", "2026-04-13", None)


def test_model_cannot_schedule_a_date_that_is_not_in_the_document():
    drafts = item_drafts(
        {
            "items": [
                {
                    "title": "SoundBar 500",
                    "purchase_date": "2026-01-01",
                    "quotes": {"purchase_date": "January 1, 2026"},
                }
            ]
        },
        RECEIPT,
    )
    purchase = next(fact for fact in drafts[0].facts if fact.field_name == "purchase_date")
    assert purchase.grounded is False
    deadlines, _gaps = compute(
        [
            {
                "id": "1",
                "field_name": purchase.field_name,
                "value_text": purchase.value_text,
                "quote": purchase.quote,
                "status": "extracted",
                "confidence": purchase.confidence,
                "grounded": purchase.grounded,
                "updated_at": "2026-03-01T00:00:00+00:00",
            }
        ],
        date(2026, 3, 10),
    )
    assert deadlines == []


def test_receipt_extraction_can_be_scheduled_from_the_text_alone():
    drafts = item_drafts(
        {
            "items": [
                {
                    "title": "SoundBar 500",
                    "merchant": "Acme Electronics",
                    "category": "receipt",
                    "price_amount": 249,
                    "currency": "USD",
                    "purchase_date": "2026-03-02",
                    "return_days": 30,
                    "warranty_months": 12,
                }
            ]
        },
        RECEIPT,
    )
    item = drafts[0]
    assert item.title == "SoundBar 500"
    assert item.merchant == "Acme Electronics"
    grounded = {fact.field_name: fact for fact in item.facts if fact.grounded}
    assert {"purchase_date", "return_days", "warranty_months", "price", "currency"} <= set(grounded)
    deadlines, gaps = compute(
        [
            {
                "id": str(index),
                "field_name": fact.field_name,
                "value_text": fact.value_text,
                "quote": fact.quote,
                "status": "extracted",
                "confidence": fact.confidence,
                "grounded": fact.grounded,
                "updated_at": "2026-03-01T00:00:00+00:00",
            }
            for index, fact in enumerate(item.facts)
        ],
        date(2026, 3, 10),
    )
    by_kind = {draft.kind: draft.due_date for draft in deadlines}
    assert by_kind["return_window"] == date(2026, 4, 1)
    assert by_kind["warranty_end"] == date(2027, 3, 2)
    assert not any("not in the document" in gap.message.lower() for gap in gaps)
