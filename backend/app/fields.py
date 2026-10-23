from __future__ import annotations

CATEGORIES = ("receipt", "warranty", "subscription", "renewal", "document", "other")
ITEM_STATUSES = ("active", "resolved", "archived")
FACT_STATUSES = ("extracted", "confirmed", "corrected", "rejected")

CATEGORY_LABELS = {
    "receipt": "Receipt",
    "warranty": "Warranty",
    "subscription": "Subscription",
    "renewal": "Renewal",
    "document": "Document",
    "other": "Other",
}

FIELD_LABELS = {
    "merchant": "Merchant",
    "price": "Price",
    "currency": "Currency",
    "purchase_date": "Purchase date",
    "delivery_date": "Delivery date",
    "return_days": "Return window (days)",
    "warranty_months": "Warranty length (months)",
    "warranty_years": "Warranty length (years)",
    "warranty_days": "Warranty length (days)",
    "warranty_end": "Warranty end",
    "renewal_date": "Renewal date",
    "renewal_period_months": "Renewal interval (months)",
    "expiry_date": "Expiration date",
}

DATE_FIELDS = {
    "purchase_date",
    "delivery_date",
    "warranty_end",
    "renewal_date",
    "expiry_date",
}

INT_LIMITS = {
    "return_days": 3650,
    "warranty_months": 600,
    "warranty_years": 40,
    "warranty_days": 3650,
    "renewal_period_months": 120,
}

DEADLINE_LABELS = {
    "return_window": "Return window",
    "warranty_end": "Warranty end",
    "renewal": "Renewal",
    "document_expiry": "Document expiration",
}

GENERIC_TITLES = {
    "receipt",
    "invoice",
    "warranty",
    "document",
    "statement",
    "order",
    "confirmation",
    "untitled item",
}

# Words that say which calendar day a duration starts on.
PURCHASE_WORDS = (
    "purchase",
    "purchased",
    "sale",
    "sales",
    "invoice",
    "receipt",
    "bought",
)
DELIVERY_WORDS = ("deliver", "delivered", "delivery", "received")

FIELD_KEYWORDS = {
    "return_days": ("return", "refund"),
    "warranty_months": ("warrant", "guarantee"),
    "warranty_years": ("warrant", "guarantee"),
    "warranty_days": ("warrant", "guarantee"),
    "renewal_period_months": ("renew", "subscription", "billed", "billing", "membership"),
    "price": ("total", "amount", "paid", "price", "subtotal", "$", "€", "£"),
}

CURRENCY_MARKS = {
    "USD": ("$", "usd", "us$"),
    "EUR": ("€", "eur"),
    "GBP": ("£", "gbp"),
    "CAD": ("cad", "c$"),
    "AUD": ("aud", "a$"),
    "INR": ("inr", "₹"),
}
