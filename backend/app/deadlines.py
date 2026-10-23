"""Deterministic deadlines.

Dates are produced only from facts that were entered by the user or that
already passed grounding. This module does not read raw documents and does
not assume a return window, warranty, or renewal policy.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.fields import DELIVERY_WORDS, PURCHASE_WORDS
from app.textutil import parse_iso_date, parse_positive_int

ANCHOR_PURCHASE = "purchase"
ANCHOR_DELIVERY = "delivery"

INT_LIMITS = {
    "return_days": 3650,
    "warranty_months": 600,
    "warranty_years": 40,
    "warranty_days": 3650,
    "renewal_period_months": 120,
}


@dataclass
class DeadlineDraft:
    kind: str
    due_date: date
    basis: str
    fact_ids: list[str]
    provisional: bool


@dataclass
class Gap:
    message: str


def add_months(start: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be positive")
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def severity_for(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return "overdue"
    if days <= 3:
        return "critical"
    if days <= 7:
        return "high"
    if days <= 30:
        return "medium"
    return "low"


def _locked(fact: dict) -> bool:
    return fact.get("status") in ("confirmed", "corrected")


def _usable(facts: list[dict]) -> list[dict]:
    chosen: list[dict] = []
    for fact in facts:
        status = fact.get("status")
        if status == "rejected":
            continue
        if status in ("confirmed", "corrected"):
            chosen.append(fact)
            continue
        if status == "extracted" and fact.get("grounded") and fact.get("confidence") == "high":
            chosen.append(fact)
    return chosen


def _pick(facts: list[dict], name: str) -> dict | None:
    matching = [fact for fact in facts if fact.get("field_name") == name and fact.get("value_text")]
    if not matching:
        return None
    rank = {"corrected": 3, "confirmed": 2, "extracted": 1}
    matching.sort(
        key=lambda fact: (rank.get(fact.get("status"), 0), fact.get("updated_at") or ""),
        reverse=True,
    )
    return matching[0]


def _provisional(facts: list[dict]) -> bool:
    return any(not _locked(fact) for fact in facts)


def _contains_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _anchor_from_quote(quote: str | None) -> str | None:
    if not quote:
        return None
    lowered = quote.lower()
    delivery = _contains_word(lowered, DELIVERY_WORDS)
    purchase = _contains_word(lowered, PURCHASE_WORDS)
    if delivery == purchase:
        return None
    if delivery:
        return ANCHOR_DELIVERY
    return ANCHOR_PURCHASE


def _plausible(due: date, today: date) -> bool:
    return date(1990, 1, 1) <= due <= date(today.year + 80, 12, 31)


def _basis(detail: str, facts: list[dict]) -> str:
    if all(_locked(fact) for fact in facts):
        follow = "Using values you confirmed."
    else:
        follow = "Taken from the document. Confirm the facts to lock this deadline in."
    return f"{detail} {follow}"


def _resolve_start(
    policy_fact: dict,
    purchase: dict | None,
    delivery: dict | None,
    gaps: list[Gap],
    subject: str,
    chosen: str | None = None,
) -> tuple[dict, date, str] | None:
    purchase_date = parse_iso_date(purchase["value_text"]) if purchase else None
    delivery_date = parse_iso_date(delivery["value_text"]) if delivery else None
    kind = _anchor_from_quote(policy_fact.get("quote"))
    purchase_ready = purchase is not None and purchase_date is not None and _locked(purchase)
    delivery_ready = delivery is not None and delivery_date is not None and _locked(delivery)

    if kind is None and chosen in (ANCHOR_PURCHASE, ANCHOR_DELIVERY):
        kind = chosen
    elif kind is None and not (_locked(policy_fact) and (purchase_ready or delivery_ready)):
        gaps.append(
            Gap(
                f"{subject} was found, but the text does not say whether it starts "
                "at purchase or delivery. Choose a start date below."
            )
        )
        return None

    if kind is None:
        if purchase_ready and not delivery_ready:
            kind = ANCHOR_PURCHASE
        elif delivery_ready and not purchase_ready:
            kind = ANCHOR_DELIVERY
        else:
            gaps.append(
                Gap(
                    f"{subject} has more than one possible start date. "
                    "Keep a single start date so a deadline can be calculated."
                )
            )
            return None

    if kind == ANCHOR_DELIVERY:
        if delivery is None or delivery_date is None:
            gaps.append(
                Gap(
                    f"{subject} counts from delivery, and no delivery date is on this item, "
                    "so no deadline was calculated."
                )
            )
            return None
        return delivery, delivery_date, "delivery date"

    if purchase is None or purchase_date is None:
        gaps.append(
            Gap(
                f"{subject} counts from purchase, and no purchase date is on this item, "
                "so no deadline was calculated."
            )
        )
        return None
    return purchase, purchase_date, "purchase date"


def _append_duration(
    drafts: list[DeadlineDraft],
    gaps: list[Gap],
    today: date,
    policy_fact: dict,
    amount: int,
    unit: str,
    purchase: dict | None,
    delivery: dict | None,
    chosen: str | None,
) -> None:
    if unit == "years":
        described = f"{amount} years"
        subject = f"A {amount}-year warranty"
    elif unit == "days":
        described = f"{amount} days"
        subject = f"A {amount}-day warranty"
    else:
        described = f"{amount} months"
        subject = f"A {amount}-month warranty"

    resolved = _resolve_start(policy_fact, purchase, delivery, gaps, subject, chosen)
    if resolved is None:
        return
    start_fact, start, label = resolved
    if unit == "days":
        due = start + timedelta(days=amount)
    elif unit == "years":
        due = add_months(start, amount * 12)
    else:
        due = add_months(start, amount)
    if not _plausible(due, today):
        gaps.append(Gap(f"The warranty end {due.isoformat()} is outside the range this app will schedule."))
        return
    used = [policy_fact, start_fact]
    drafts.append(
        DeadlineDraft(
            kind="warranty_end",
            due_date=due,
            basis=_basis(
                f"Warranty ends {due.isoformat()} — {label} {start.isoformat()} plus {described}.",
                used,
            ),
            fact_ids=[policy_fact["id"], start_fact["id"]],
            provisional=_provisional(used),
        )
    )


def compute(
    facts: list[dict], today: date | None = None, anchor: str | None = None
) -> tuple[list[DeadlineDraft], list[Gap]]:
    today = today or date.today()
    chosen = anchor if anchor in (ANCHOR_PURCHASE, ANCHOR_DELIVERY) else None
    usable = _usable(facts)
    drafts: list[DeadlineDraft] = []
    gaps: list[Gap] = []

    purchase = _pick(usable, "purchase_date")
    delivery = _pick(usable, "delivery_date")

    return_fact = _pick(usable, "return_days")
    if return_fact:
        days = parse_positive_int(return_fact.get("value_text"), INT_LIMITS["return_days"])
        if days is None:
            gaps.append(Gap("A return window was saved, but it is not a usable number of days."))
        else:
            resolved = _resolve_start(
                return_fact,
                purchase,
                delivery,
                gaps,
                f"A {days}-day return window",
                chosen,
            )
            if resolved is not None:
                start_fact, start, label = resolved
                due = start + timedelta(days=days)
                if _plausible(due, today):
                    used = [return_fact, start_fact]
                    drafts.append(
                        DeadlineDraft(
                            kind="return_window",
                            due_date=due,
                            basis=_basis(
                                f"Return window ends {due.isoformat()} — {label} {start.isoformat()} plus {days} days.",
                                used,
                            ),
                            fact_ids=[return_fact["id"], start_fact["id"]],
                            provisional=_provisional(used),
                        )
                    )
                else:
                    gaps.append(Gap(f"The return date {due.isoformat()} is outside the range this app will schedule."))

    warranty_end = _pick(usable, "warranty_end")
    warranty_end_date = parse_iso_date(warranty_end["value_text"]) if warranty_end else None
    if warranty_end and warranty_end_date:
        if _plausible(warranty_end_date, today):
            drafts.append(
                DeadlineDraft(
                    kind="warranty_end",
                    due_date=warranty_end_date,
                    basis=_basis(
                        f"Warranty end date {warranty_end_date.isoformat()} is written down.",
                        [warranty_end],
                    ),
                    fact_ids=[warranty_end["id"]],
                    provisional=_provisional([warranty_end]),
                )
            )
        else:
            gaps.append(
                Gap(
                    f"The warranty end {warranty_end['value_text']} is outside the range this app will schedule."
                )
            )
    else:
        duration_fact = None
        amount = None
        unit = None
        for field_name, unit_name in (
            ("warranty_months", "months"),
            ("warranty_years", "years"),
            ("warranty_days", "days"),
        ):
            fact = _pick(usable, field_name)
            if fact is None:
                continue
            parsed = parse_positive_int(fact.get("value_text"), INT_LIMITS[field_name])
            if parsed is None:
                gaps.append(Gap("A warranty length was saved, but it is not a usable number."))
                duration_fact = None
                break
            duration_fact = fact
            amount = parsed
            unit = unit_name
            break
        if duration_fact is not None and amount is not None and unit is not None:
            _append_duration(drafts, gaps, today, duration_fact, amount, unit, purchase, delivery, chosen)

    for field_name, kind, label in (
        ("renewal_date", "renewal", "Renewal date"),
        ("expiry_date", "document_expiry", "Expiration date"),
    ):
        fact = _pick(usable, field_name)
        if fact is None:
            continue
        due = parse_iso_date(fact.get("value_text"))
        if due is None:
            gaps.append(Gap(f"A {label.lower()} was saved, but it is not a valid calendar date."))
            continue
        if not _plausible(due, today):
            gaps.append(Gap(f"The {label.lower()} {fact['value_text']} is outside the range this app will schedule."))
            continue
        drafts.append(
            DeadlineDraft(
                kind=kind,
                due_date=due,
                basis=_basis(f"{label} {due.isoformat()} is written down.", [fact]),
                fact_ids=[fact["id"]],
                provisional=_provisional([fact]),
            )
        )

    period = _pick(usable, "renewal_period_months")
    renewal = _pick(usable, "renewal_date")
    if period and not renewal:
        gaps.append(
            Gap(
                "A renewal interval was found, but no renewal date was stated. "
                "Add the next renewal date to put it on the timeline."
            )
        )

    return drafts, gaps
