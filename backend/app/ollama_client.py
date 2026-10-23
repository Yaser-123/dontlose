from __future__ import annotations

import json
import re

import httpx

from app import config
from app.errors import OllamaError

SYSTEM = (
    "You extract financial deadline facts from one personal document. "
    "Return JSON only. Use null when a value is not explicitly written. "
    "Never invent a date, a number, a price, or a policy. "
    "For every non-null value, copy a short verbatim quote from the document into quotes."
)


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= 14000:
        return text, False
    return text[:9000] + "\n...\n" + text[-5000:], True


def _prompt(text: str) -> str:
    clipped, trimmed = _clip(text)
    note = "The document text was shortened to the beginning and the end.\n" if trimmed else ""
    return f"""{note}Document text:
\"\"\"
{clipped}
\"\"\"

Return JSON with this shape. Leave a field null unless the document states it.
Dates must be YYYY-MM-DD only when that calendar date is written in the document.
category must be one of: receipt, warranty, subscription, renewal, document, other.
If the document describes one purchase, return one item.

{{
  "items": [
    {{
      "title": null,
      "merchant": null,
      "category": "other",
      "price_amount": null,
      "currency": null,
      "purchase_date": null,
      "delivery_date": null,
      "return_days": null,
      "warranty_months": null,
      "warranty_years": null,
      "warranty_days": null,
      "warranty_end": null,
      "renewal_date": null,
      "renewal_period_months": null,
      "expiry_date": null,
      "quotes": {{
        "title": null,
        "merchant": null,
        "price_amount": null,
        "currency": null,
        "purchase_date": null,
        "delivery_date": null,
        "return_days": null,
        "warranty_months": null,
        "warranty_years": null,
        "warranty_days": null,
        "warranty_end": null,
        "renewal_date": null,
        "renewal_period_months": null,
        "expiry_date": null
      }}
    }}
  ]
}}"""


def parse_model_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise OllamaError("Gemma didn't return readable JSON. Nothing was guessed.")
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise OllamaError("Gemma didn't return readable JSON. Nothing was guessed.") from exc
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise OllamaError("Gemma didn't return readable JSON. Nothing was guessed.") from exc
    if not isinstance(data, dict):
        raise OllamaError("Gemma didn't return a JSON object. Nothing was guessed.")
    return data


def extract_facts(text: str) -> dict:
    model = config.ollama_model()
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _prompt(text)},
        ],
        "options": {"temperature": 0, "num_predict": 1200},
    }
    try:
        response = httpx.post(
            f"{config.ollama_base_url()}/api/chat",
            json=payload,
            timeout=httpx.Timeout(180.0, connect=5.0),
        )
    except httpx.ConnectError as exc:
        raise OllamaError(
            "Ollama isn't running. Start it, then reprocess this file. The text from the file was saved."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaError("Gemma took too long to answer. Try reprocessing. Nothing was guessed.") from exc
    if response.status_code == 404:
        raise OllamaError(f"The model {model} is not available in Ollama. The text from the file was saved.")
    if response.status_code >= 400:
        raise OllamaError("Ollama could not read this document. The text from the file was saved.")
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise OllamaError("Ollama returned an unreadable response. Nothing was guessed.") from exc
    if body.get("error"):
        message = str(body["error"])
        if "not found" in message.lower():
            raise OllamaError(f"The model {model} is not available in Ollama. The text from the file was saved.")
        raise OllamaError("Ollama could not read this document. The text from the file was saved.")
    content = ((body.get("message") or {}).get("content")) or ""
    if not content.strip():
        raise OllamaError("Gemma returned an empty response. Nothing was guessed.")
    return parse_model_json(content)


def ollama_status() -> dict:
    model = config.ollama_model()
    try:
        response = httpx.get(f"{config.ollama_base_url()}/api/tags", timeout=3.0)
        response.raise_for_status()
        names = [
            item.get("name")
            for item in response.json().get("models", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    except Exception as exc:
        return {"available": False, "model": model, "model_present": False, "error": str(exc.__class__.__name__)}
    present = any(name == model or name.startswith(f"{model}-") for name in names)
    return {"available": True, "model": model, "model_present": present, "error": None}
