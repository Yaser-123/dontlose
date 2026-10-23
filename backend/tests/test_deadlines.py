from datetime import date

from app.deadlines import add_months, compute


def fact(fact_id, field_name, value, quote, status="extracted", grounded=1, confidence="high"):
    return {
        "id": fact_id,
        "field_name": field_name,
        "value_text": value,
        "quote": quote,
        "status": status,
        "grounded": grounded,
        "confidence": confidence,
        "updated_at": "2026-03-01T00:00:00+00:00",
    }


def test_add_months_clamps_short_months():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 3, 2), 12) == date(2027, 3, 2)


def test_return_window_uses_purchase_anchor_from_the_quote():
    drafts, gaps = compute(
        [
            fact("p", "purchase_date", "2026-03-02", "Date: March 2, 2026"),
            fact("r", "return_days", "30", "Items may be returned within 30 days of purchase."),
        ],
        date(2026, 3, 10),
    )
    assert gaps == []
    assert drafts[0].kind == "return_window"
    assert drafts[0].due_date == date(2026, 4, 1)
    assert drafts[0].provisional is True


def test_policy_without_a_start_does_not_invent_a_deadline():
    drafts, gaps = compute(
        [
            fact("p", "purchase_date", "2026-03-02", "Date: March 2, 2026"),
            fact("r", "return_days", "30", "Return policy: 30 days."),
        ],
        date(2026, 3, 10),
    )
    assert drafts == []
    assert gaps


def test_delivery_policy_without_a_delivery_date_is_not_scheduled():
    drafts, gaps = compute(
        [
            fact("p", "purchase_date", "2026-03-02", "Date: March 2, 2026"),
            fact("r", "return_days", "14", "Return within 14 days of delivery."),
        ],
        date(2026, 3, 10),
    )
    assert drafts == []
    assert any("delivery" in gap.message for gap in gaps)


def test_confirmed_values_can_be_calculated_without_a_policy_quote():
    drafts, _gaps = compute(
        [
            fact("p", "purchase_date", "2026-03-02", "Entered manually", status="confirmed"),
            fact("r", "return_days", "30", "Entered manually", status="confirmed"),
            fact("w", "warranty_months", "12", "Entered manually", status="confirmed"),
        ],
        date(2026, 3, 10),
    )
    by_kind = {draft.kind: draft for draft in drafts}
    assert by_kind["return_window"].due_date == date(2026, 4, 1)
    assert by_kind["warranty_end"].due_date == date(2027, 3, 2)
    assert by_kind["return_window"].provisional is False
    assert "confirmed" in by_kind["return_window"].basis.lower() or "Using values" in by_kind["return_window"].basis


def test_written_warranty_end_beats_a_duration():
    drafts, _gaps = compute(
        [
            fact("e", "warranty_end", "2027-01-15", "Warranty ends January 15, 2027", status="confirmed"),
            fact("m", "warranty_months", "24", "Entered manually", status="confirmed"),
            fact("p", "purchase_date", "2026-03-02", "Entered manually", status="confirmed"),
        ],
        date(2026, 3, 10),
    )
    warranty = [draft for draft in drafts if draft.kind == "warranty_end"]
    assert len(warranty) == 1
    assert warranty[0].due_date == date(2027, 1, 15)


def test_ungrounded_date_is_ignored():
    drafts, _gaps = compute(
        [fact("p", "purchase_date", "2026-03-02", "March 2, 2026", grounded=0, confidence="low")],
        date(2026, 3, 10),
    )
    assert drafts == []


def test_renewal_interval_without_a_date_is_only_a_gap():
    drafts, gaps = compute(
        [fact("n", "renewal_period_months", "12", "Billed every 12 months.", status="confirmed")],
        date(2026, 3, 10),
    )
    assert drafts == []
    assert any("renewal date" in gap.message.lower() for gap in gaps)


def test_explicit_renewal_and_expiry_are_copied_not_shifted():
    drafts, _gaps = compute(
        [
            fact("n", "renewal_date", "2026-11-01", "Renews on November 1, 2026", status="confirmed"),
            fact("e", "expiry_date", "2026-12-31", "Expires December 31, 2026", status="confirmed"),
        ],
        date(2026, 3, 10),
    )
    by_kind = {draft.kind: draft.due_date for draft in drafts}
    assert by_kind == {"renewal": date(2026, 11, 1), "document_expiry": date(2026, 12, 31)}
