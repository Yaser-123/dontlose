from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.db import get_db
from app.deadlines import Gap, compute
from app.extract import ItemDraft, placeholder_item
from app.validate import NotFound, ValidationError, canonical_fact_value, clean_item_patch, clean_manual

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "item",
    "receipt",
    "warranty",
    "document",
    "inc",
    "llc",
    "ltd",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _query(sql: str, params: tuple = ()) -> list[dict]:
    return get_db().query(sql, params)


def _execute(sql: str, params: tuple = ()) -> None:
    get_db().execute(sql, params)


def _one(sql: str, params: tuple = ()) -> dict | None:
    rows = _query(sql, params)
    return rows[0] if rows else None


def _scalar(sql: str, params: tuple = ()) -> int:
    row = _one(sql, params)
    if not row:
        return 0
    return int(next(iter(row.values())))


def _placeholders(values: list) -> str:
    return ",".join("?" for _ in values)


def _like(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_item_row(item_id: str) -> dict | None:
    return _one("SELECT * FROM items WHERE id = ?", (item_id,))


def require_item(item_id: str) -> dict:
    item = get_item_row(item_id)
    if item is None:
        raise NotFound("That item was not found.")
    return item


def _touch(item_id: str, user_edited: bool = False) -> None:
    if user_edited:
        _execute(
            "UPDATE items SET user_edited = 1, updated_at = ? WHERE id = ?",
            (now_iso(), item_id),
        )
    else:
        _execute("UPDATE items SET updated_at = ? WHERE id = ?", (now_iso(), item_id))


def _insert_fact(
    item_id: str,
    field_name: str,
    value_text: str,
    *,
    document_id: str | None,
    quote: str | None,
    confidence: str,
    status: str,
    grounded: bool,
) -> str:
    fact_id = new_id()
    stamp = now_iso()
    _execute(
        """
        INSERT INTO facts (
            id, item_id, document_id, field_name, value_text, quote,
            confidence, status, grounded, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fact_id,
            item_id,
            document_id,
            field_name,
            value_text,
            quote,
            confidence,
            status,
            1 if grounded else 0,
            stamp,
            stamp,
        ),
    )
    return fact_id


def _reject_other_extracted(item_id: str, field_name: str, keep_id: str) -> None:
    _execute(
        """
        UPDATE facts
        SET status = 'rejected', updated_at = ?
        WHERE item_id = ? AND field_name = ? AND status = 'extracted' AND id != ?
        """,
        (now_iso(), item_id, field_name, keep_id),
    )


def apply_deadlines(item_id: str) -> None:
    with get_db().transaction():
        facts = _query("SELECT * FROM facts WHERE item_id = ?", (item_id,))
        item = _one("SELECT deadline_anchor FROM items WHERE id = ?", (item_id,))
        drafts, gaps = compute(facts, anchor=item["deadline_anchor"] if item else None)
        ungrounded = any(row["status"] == "extracted" and not row["grounded"] for row in facts)
        usable = any(
            row["status"] in ("confirmed", "corrected")
            or (row["status"] == "extracted" and row["grounded"] and row["confidence"] == "high")
            for row in facts
        )
        if ungrounded:
            gaps.append(
                Gap(
                    "Some extracted values were not in the document text, so they were left off the timeline."
                )
            )
        elif not usable:
            gaps.append(
                Gap("No deadline facts are verified yet. Add a date or a term you can see on the document.")
            )
        existing = {
            row["kind"]: row
            for row in _query("SELECT * FROM deadlines WHERE item_id = ?", (item_id,))
        }
        seen: set[str] = set()
        stamp = now_iso()
        messages: list[str] = []
        for gap in gaps:
            if gap.message not in messages:
                messages.append(gap.message)
        for draft in drafts:
            seen.add(draft.kind)
            previous = existing.get(draft.kind)
            due = draft.due_date.isoformat()
            status = "open"
            if previous and previous["due_date"] == due and previous["status"] in ("done", "dismissed"):
                status = previous["status"]
            _execute(
                """
                INSERT INTO deadlines (
                    id, item_id, kind, due_date, basis, fact_ids, provisional, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id, kind) DO UPDATE SET
                    due_date = excluded.due_date,
                    basis = excluded.basis,
                    fact_ids = excluded.fact_ids,
                    provisional = excluded.provisional,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    previous["id"] if previous else new_id(),
                    item_id,
                    draft.kind,
                    due,
                    draft.basis,
                    json.dumps(draft.fact_ids),
                    1 if draft.provisional else 0,
                    status,
                    previous["created_at"] if previous else stamp,
                    stamp,
                ),
            )
        if seen:
            marks = _placeholders(list(seen))
            _execute(
                f"DELETE FROM deadlines WHERE item_id = ? AND kind NOT IN ({marks})",
                (item_id, *seen),
            )
        else:
            _execute("DELETE FROM deadlines WHERE item_id = ?", (item_id,))
        _execute("DELETE FROM gaps WHERE item_id = ?", (item_id,))
        for message in messages:
            _execute(
                "INSERT INTO gaps (id, item_id, message) VALUES (?, ?, ?)",
                (new_id(), item_id, message),
            )
        _execute("UPDATE items SET updated_at = ? WHERE id = ?", (stamp, item_id))


def _tokens(value: str | None) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _match_reason(left: dict, right: dict) -> str | None:
    left_title = set() if left["title"] == "Untitled item" else _tokens(left["title"])
    right_title = set() if right["title"] == "Untitled item" else _tokens(right["title"])
    title_score = _jaccard(left_title, right_title)
    same_merchant = bool(_tokens(left.get("merchant"))) and _tokens(left.get("merchant")) == _tokens(
        right.get("merchant")
    )
    if same_merchant and title_score >= 0.34:
        return "Same merchant and a similar name."
    if title_score >= 0.62:
        return "These names look like the same item."
    return None


def _suggestion_blocked(source_id: str, target_id: str) -> bool:
    rows = _query(
        """
        SELECT status FROM item_links
        WHERE (source_item_id = ? AND target_item_id = ?)
           OR (source_item_id = ? AND target_item_id = ?)
        """,
        (source_id, target_id, target_id, source_id),
    )
    return any(row["status"] == "dismissed" for row in rows)


def refresh_suggestions(item_id: str) -> None:
    with get_db().transaction():
        item = get_item_row(item_id)
        if item is None or item["status"] != "active":
            return
        others = _query(
            "SELECT * FROM items WHERE id != ? AND status = 'active'",
            (item_id,),
        )
        for other in others:
            reason = _match_reason(item, other)
            if not reason or _suggestion_blocked(item_id, other["id"]):
                continue
            stamp = now_iso()
            for source, target in ((item_id, other["id"]), (other["id"], item_id)):
                if _one(
                    "SELECT 1 AS ok FROM item_links WHERE source_item_id = ? AND target_item_id = ?",
                    (source, target),
                ):
                    continue
                _execute(
                    """
                    INSERT INTO item_links (source_item_id, target_item_id, reason, status, created_at)
                    VALUES (?, ?, ?, 'suggested', ?)
                    """,
                    (source, target, reason, stamp),
                )


def create_manual_item(data: dict) -> str:
    cleaned = clean_manual(data)
    item_id = new_id()
    stamp = now_iso()
    with get_db().transaction():
        _execute(
            """
            INSERT INTO items (
                id, title, merchant, category, status, notes, user_edited, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, 1, ?, ?)
            """,
            (item_id, cleaned["title"], cleaned["merchant"], cleaned["category"], "", stamp, stamp),
        )
        if cleaned["notes"]:
            _execute(
                "INSERT INTO item_notes (id, item_id, body, created_at) VALUES (?, ?, ?, ?)",
                (new_id(), item_id, cleaned["notes"], stamp),
            )
        for field_name, value in cleaned["facts"]:
            _insert_fact(
                item_id,
                field_name,
                value,
                document_id=None,
                quote="Entered manually",
                confidence="high",
                status="confirmed",
                grounded=True,
            )
        apply_deadlines(item_id)
        refresh_suggestions(item_id)
    return item_id


def update_item(item_id: str, data: dict) -> None:
    require_item(item_id)
    cleaned = clean_item_patch(data)
    note = cleaned.pop("notes", None)
    assignments = []
    params: list = []
    for key in ("title", "merchant", "category", "status"):
        if key in cleaned:
            assignments.append(f"{key} = ?")
            params.append(cleaned[key])
    assignments.append("user_edited = 1")
    assignments.append("updated_at = ?")
    params.append(now_iso())
    params.append(item_id)
    with get_db().transaction():
        _execute(f"UPDATE items SET {', '.join(assignments)} WHERE id = ?", tuple(params))
        if note:
            _execute(
                "INSERT INTO item_notes (id, item_id, body, created_at) VALUES (?, ?, ?, ?)",
                (new_id(), item_id, note, now_iso()),
            )
        refresh_suggestions(item_id)


def set_start_anchor(item_id: str, anchor: str) -> None:
    if anchor not in ("purchase", "delivery"):
        raise ValidationError("Choose purchase or delivery.")
    require_item(item_id)
    field_name = "purchase_date" if anchor == "purchase" else "delivery_date"
    with get_db().transaction():
        _execute(
            "UPDATE items SET deadline_anchor = ?, user_edited = 1, updated_at = ? WHERE id = ?",
            (anchor, now_iso(), item_id),
        )
        fact = _one(
            """
            SELECT * FROM facts
            WHERE item_id = ? AND field_name = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (item_id, field_name),
        )
        if fact is not None and fact["status"] == "rejected":
            _execute(
                "UPDATE facts SET status = 'confirmed', updated_at = ? WHERE id = ?",
                (now_iso(), fact["id"]),
            )
        apply_deadlines(item_id)


def add_note(item_id: str, body: str) -> None:
    require_item(item_id)
    with get_db().transaction():
        _execute(
            "INSERT INTO item_notes (id, item_id, body, created_at) VALUES (?, ?, ?, ?)",
            (new_id(), item_id, body, now_iso()),
        )
        _touch(item_id, user_edited=True)


def delete_note(item_id: str, note_id: str) -> None:
    require_item(item_id)
    row = _one("SELECT id FROM item_notes WHERE id = ? AND item_id = ?", (note_id, item_id))
    if row is None:
        raise NotFound("That note was not found.")
    with get_db().transaction():
        _execute("DELETE FROM item_notes WHERE id = ?", (note_id,))
        _touch(item_id, user_edited=True)


def delete_item(item_id: str) -> None:
    require_item(item_id)
    _execute("DELETE FROM items WHERE id = ?", (item_id,))


def list_item_ids(q: str = "", category: str = "", status: str = "", limit: int = 200) -> list[str]:
    filters = ["1 = 1"]
    params: list = []
    if q.strip():
        pattern = _like(q.strip())
        filters.append(
            """
            (
                lower(i.title) LIKE ? ESCAPE '\\'
                OR lower(coalesce(i.merchant, '')) LIKE ? ESCAPE '\\'
                OR lower(coalesce(i.notes, '')) LIKE ? ESCAPE '\\'
                OR EXISTS (
                    SELECT 1 FROM item_notes n
                    WHERE n.item_id = i.id AND lower(n.body) LIKE ? ESCAPE '\\'
                )
                OR EXISTS (
                    SELECT 1 FROM facts f
                    WHERE f.item_id = i.id AND lower(f.value_text) LIKE ? ESCAPE '\\'
                )
            )
            """
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])
    if category:
        filters.append("i.category = ?")
        params.append(category)
    if status:
        filters.append("i.status = ?")
        params.append(status)
    params.append(limit)
    rows = _query(
        f"""
        SELECT i.id FROM items i
        WHERE {' AND '.join(filters)}
        ORDER BY i.updated_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [row["id"] for row in rows]


def _attach_document_names(facts: list[dict]) -> None:
    doc_ids = sorted({fact["document_id"] for fact in facts if fact.get("document_id")})
    if not doc_ids:
        for fact in facts:
            fact["document_name"] = None
        return
    marks = _placeholders(doc_ids)
    names = {
        row["id"]: row["original_name"]
        for row in _query(f"SELECT id, original_name FROM documents WHERE id IN ({marks})", tuple(doc_ids))
    }
    for fact in facts:
        fact["document_name"] = names.get(fact.get("document_id"))


def load_bundles(item_ids: list[str]) -> list[dict]:
    if not item_ids:
        return []
    marks = _placeholders(item_ids)
    items = {
        row["id"]: row
        for row in _query(f"SELECT * FROM items WHERE id IN ({marks})", tuple(item_ids))
    }
    facts = _query(
        f"SELECT * FROM facts WHERE item_id IN ({marks}) ORDER BY updated_at DESC",
        tuple(item_ids),
    )
    _attach_document_names(facts)
    deadlines = _query(
        f"SELECT * FROM deadlines WHERE item_id IN ({marks}) ORDER BY due_date ASC",
        tuple(item_ids),
    )
    gaps = _query(f"SELECT * FROM gaps WHERE item_id IN ({marks})", tuple(item_ids))
    bundles = []
    for item_id in item_ids:
        item = items.get(item_id)
        if item is None:
            continue
        bundles.append(
            {
                "item": item,
                "facts": [fact for fact in facts if fact["item_id"] == item_id],
                "deadlines": [row for row in deadlines if row["item_id"] == item_id],
                "gaps": [row for row in gaps if row["item_id"] == item_id],
            }
        )
    return bundles


def list_bundles(q: str = "", category: str = "", status: str = "", limit: int = 200) -> list[dict]:
    return load_bundles(list_item_ids(q, category, status, limit))


def suggestions_for(item_id: str) -> list[dict]:
    return _query(
        """
        SELECT l.target_item_id AS item_id, l.reason, i.title, i.merchant
        FROM item_links l
        JOIN items i ON i.id = l.target_item_id
        WHERE l.source_item_id = ? AND l.status = 'suggested' AND i.status = 'active'
        ORDER BY i.title
        """,
        (item_id,),
    )


def documents_for_item(item_id: str) -> list[dict]:
    return _query(
        """
        SELECT d.* FROM documents d
        JOIN item_documents link ON link.document_id = d.id
        WHERE link.item_id = ?
        ORDER BY d.created_at DESC
        """,
        (item_id,),
    )


def item_detail_record(item_id: str) -> dict:
    require_item(item_id)
    bundle = load_bundles([item_id])[0]
    documents = documents_for_item(item_id)
    for document in documents:
        linked = items_for_document(document["id"])
        document["linked_items"] = linked
    bundle["documents"] = documents
    bundle["suggestions"] = suggestions_for(item_id)
    bundle["notes"] = _query(
        "SELECT id, body, created_at FROM item_notes WHERE item_id = ? ORDER BY created_at DESC",
        (item_id,),
    )
    return bundle


def items_for_document(document_id: str) -> list[dict]:
    return _query(
        """
        SELECT i.id, i.title
        FROM items i
        JOIN item_documents link ON link.item_id = i.id
        WHERE link.document_id = ?
        ORDER BY i.title
        """,
        (document_id,),
    )


def get_fact(fact_id: str) -> dict:
    fact = _one("SELECT * FROM facts WHERE id = ?", (fact_id,))
    if fact is None:
        raise NotFound("That fact was not found.")
    return fact


def mutate_fact(fact_id: str, action: str, value: str | None = None) -> str:
    fact = get_fact(fact_id)
    with get_db().transaction():
        if action == "confirm":
            if fact["status"] == "rejected":
                raise ValidationError("This fact was rejected. Enter the value again if you want to use it.")
            _execute(
                "UPDATE facts SET status = 'confirmed', updated_at = ? WHERE id = ?",
                (now_iso(), fact_id),
            )
            _reject_other_extracted(fact["item_id"], fact["field_name"], fact_id)
        elif action == "reject":
            _execute(
                "UPDATE facts SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now_iso(), fact_id),
            )
        elif action == "correct":
            canonical = canonical_fact_value(fact["field_name"], value)
            _execute(
                """
                UPDATE facts
                SET value_text = ?, status = 'corrected', grounded = 1, confidence = 'high', updated_at = ?
                WHERE id = ?
                """,
                (canonical, now_iso(), fact_id),
            )
            _reject_other_extracted(fact["item_id"], fact["field_name"], fact_id)
        else:
            raise ValidationError("Use confirm, reject, or correct.")
        _touch(fact["item_id"], user_edited=True)
        apply_deadlines(fact["item_id"])
    return fact["item_id"]


def set_user_fact(item_id: str, field_name: str, value: object) -> str:
    require_item(item_id)
    canonical = canonical_fact_value(field_name, value)
    with get_db().transaction():
        existing = _query(
            """
            SELECT * FROM facts
            WHERE item_id = ? AND field_name = ? AND status != 'rejected'
            ORDER BY updated_at DESC
            """,
            (item_id, field_name),
        )
        if existing:
            keep = existing[0]
            _execute(
                """
                UPDATE facts
                SET value_text = ?, status = 'confirmed', grounded = 1, confidence = 'high',
                    quote = COALESCE(quote, 'Entered manually'), updated_at = ?
                WHERE id = ?
                """,
                (canonical, now_iso(), keep["id"]),
            )
            fact_id = keep["id"]
            _reject_other_extracted(item_id, field_name, fact_id)
        else:
            fact_id = _insert_fact(
                item_id,
                field_name,
                canonical,
                document_id=None,
                quote="Entered manually",
                confidence="high",
                status="confirmed",
                grounded=True,
            )
        _touch(item_id, user_edited=True)
        apply_deadlines(item_id)
    return fact_id


def confirm_extracted(item_id: str) -> int:
    require_item(item_id)
    rows = _query(
        """
        SELECT * FROM facts
        WHERE item_id = ? AND status = 'extracted' AND grounded = 1 AND confidence = 'high'
        """,
        (item_id,),
    )
    if not rows:
        return 0
    with get_db().transaction():
        for row in rows:
            _execute(
                "UPDATE facts SET status = 'confirmed', updated_at = ? WHERE id = ?",
                (now_iso(), row["id"]),
            )
            _reject_other_extracted(item_id, row["field_name"], row["id"])
        _touch(item_id, user_edited=True)
        apply_deadlines(item_id)
    return len(rows)


def dismiss_suggestion(source_id: str, target_id: str) -> None:
    require_item(source_id)
    require_item(target_id)
    with get_db().transaction():
        before = _scalar(
            """
            SELECT COUNT(*) FROM item_links
            WHERE status = 'suggested'
              AND ((source_item_id = ? AND target_item_id = ?)
                OR (source_item_id = ? AND target_item_id = ?))
            """,
            (source_id, target_id, target_id, source_id),
        )
        if before == 0:
            raise NotFound("That suggestion was not found.")
        _execute(
            """
            UPDATE item_links SET status = 'dismissed'
            WHERE (source_item_id = ? AND target_item_id = ?)
               OR (source_item_id = ? AND target_item_id = ?)
            """,
            (source_id, target_id, target_id, source_id),
        )


def merge_items(source_id: str, target_id: str) -> str:
    if source_id == target_id:
        raise ValidationError("Choose a different item to merge into.")
    require_item(source_id)
    require_item(target_id)
    with get_db().transaction():
        for document in documents_for_item(source_id):
            _link_document(target_id, document["id"])
        _execute("UPDATE facts SET item_id = ? WHERE item_id = ?", (target_id, source_id))
        _execute("UPDATE reminders SET item_id = ? WHERE item_id = ?", (target_id, source_id))
        _execute("DELETE FROM items WHERE id = ?", (source_id,))
        _touch(target_id, user_edited=True)
        apply_deadlines(target_id)
        refresh_suggestions(target_id)
    return target_id


def _link_document(item_id: str, document_id: str) -> None:
    if _one(
        "SELECT 1 AS ok FROM item_documents WHERE item_id = ? AND document_id = ?",
        (item_id, document_id),
    ):
        return
    _execute(
        "INSERT INTO item_documents (item_id, document_id, created_at) VALUES (?, ?, ?)",
        (item_id, document_id, now_iso()),
    )


def _upsert_extracted(item_id: str, document_id: str, draft) -> None:
    rows = _query(
        """
        SELECT * FROM facts
        WHERE item_id = ? AND field_name = ? AND status != 'rejected'
        ORDER BY updated_at DESC
        """,
        (item_id, draft.field_name),
    )
    if any(row["status"] in ("confirmed", "corrected") for row in rows):
        return
    extracted = next((row for row in rows if row["status"] == "extracted"), None)
    if extracted:
        _execute(
            """
            UPDATE facts
            SET document_id = ?, value_text = ?, quote = ?, confidence = ?, grounded = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                document_id,
                draft.value_text,
                draft.quote,
                draft.confidence,
                1 if draft.grounded else 0,
                now_iso(),
                extracted["id"],
            ),
        )
        return
    _insert_fact(
        item_id,
        draft.field_name,
        draft.value_text,
        document_id=document_id,
        quote=draft.quote,
        confidence=draft.confidence,
        status="extracted",
        grounded=draft.grounded,
    )


def _create_extracted_item(document_id: str, draft: ItemDraft) -> str:
    item_id = new_id()
    stamp = now_iso()
    _execute(
        """
        INSERT INTO items (
            id, title, merchant, category, status, notes, user_edited, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'active', '', 0, ?, ?)
        """,
        (item_id, draft.title, draft.merchant, draft.category, stamp, stamp),
    )
    _link_document(item_id, document_id)
    for fact in draft.facts:
        _upsert_extracted(item_id, document_id, fact)
    apply_deadlines(item_id)
    refresh_suggestions(item_id)
    return item_id


def _attach_drafts(item_id: str, document_id: str, drafts: list[ItemDraft]) -> None:
    _link_document(item_id, document_id)
    item = require_item(item_id)
    for draft in drafts:
        if item["title"] == "Untitled item" and draft.title != "Untitled item" and not item["user_edited"]:
            _execute(
                "UPDATE items SET title = ?, updated_at = ? WHERE id = ?",
                (draft.title, now_iso(), item_id),
            )
            item["title"] = draft.title
        if not item.get("merchant") and draft.merchant:
            _execute(
                "UPDATE items SET merchant = ?, updated_at = ? WHERE id = ?",
                (draft.merchant, now_iso(), item_id),
            )
            item["merchant"] = draft.merchant
        if item["category"] == "other" and draft.category != "other" and not item["user_edited"]:
            _execute(
                "UPDATE items SET category = ?, updated_at = ? WHERE id = ?",
                (draft.category, now_iso(), item_id),
            )
            item["category"] = draft.category
        for fact in draft.facts:
            _upsert_extracted(item_id, document_id, fact)
    apply_deadlines(item_id)
    refresh_suggestions(item_id)


def _reset_document_items(document_id: str) -> str | None:
    document = get_document(document_id)
    target = document["target_item_id"] if document else None
    linked = _query(
        """
        SELECT i.* FROM items i
        JOIN item_documents link ON link.item_id = i.id
        WHERE link.document_id = ?
        """,
        (document_id,),
    )
    keep = target if target and get_item_row(target) else None
    for item in linked:
        facts = _query("SELECT status FROM facts WHERE item_id = ?", (item["id"],))
        doc_count = _scalar("SELECT COUNT(*) FROM item_documents WHERE item_id = ?", (item["id"],))
        protected = (
            item["id"] == target
            or item["user_edited"]
            or bool((item.get("notes") or "").strip())
            or _scalar("SELECT COUNT(*) FROM item_notes WHERE item_id = ?", (item["id"],))
            or doc_count > 1
            or any(fact["status"] in ("confirmed", "corrected") for fact in facts)
        )
        if protected:
            _execute(
                """
                DELETE FROM facts
                WHERE item_id = ? AND document_id = ? AND status = 'extracted'
                """,
                (item["id"], document_id),
            )
            keep = keep or item["id"]
        else:
            _execute("DELETE FROM items WHERE id = ?", (item["id"],))
    return keep


def save_document_extraction(document_id: str, drafts: list[ItemDraft]) -> dict:
    with get_db().transaction():
        anchor = _reset_document_items(document_id)
        usable = drafts or [placeholder_item()]
        if anchor and get_item_row(anchor):
            _attach_drafts(anchor, document_id, usable)
            return {"item_ids": [anchor], "attached": True}
        return {
            "item_ids": [_create_extracted_item(document_id, draft) for draft in usable],
            "attached": False,
        }


def count_grounded_facts(document_id: str) -> int:
    return _scalar(
        "SELECT COUNT(*) FROM facts WHERE document_id = ? AND grounded = 1",
        (document_id,),
    )


def get_document(document_id: str) -> dict | None:
    return _one("SELECT * FROM documents WHERE id = ?", (document_id,))


def require_document(document_id: str) -> dict:
    document = get_document(document_id)
    if document is None:
        raise NotFound("That file was not found.")
    return document


_DOCUMENT_FIELDS = {
    "ocr_text",
    "page_count",
    "processing_status",
    "processing_stage",
    "error_message",
    "result_note",
    "model_name",
    "processed_at",
    "target_item_id",
}


def update_document(document_id: str, **fields) -> None:
    unknown = set(fields) - _DOCUMENT_FIELDS
    if unknown:
        raise ValidationError("That file update is not valid.")
    if not fields:
        return
    assignments = [f"{key} = ?" for key in fields]
    _execute(
        f"UPDATE documents SET {', '.join(assignments)} WHERE id = ?",
        (*fields.values(), document_id),
    )


def mark_document_error(document_id: str, message: str) -> None:
    current = get_document(document_id)
    if current is None or current["processing_status"] == "error":
        return
    update_document(
        document_id,
        processing_status="error",
        processing_stage="error",
        error_message=message,
    )


def create_document(
    original_name: str,
    stored_name: str,
    mime_type: str,
    size_bytes: int,
    target_item_id: str | None,
) -> dict:
    if target_item_id:
        require_item(target_item_id)
    document_id = Path(stored_name).stem
    stamp = now_iso()
    _execute(
        """
        INSERT INTO documents (
            id, original_name, stored_name, mime_type, size_bytes, ocr_text, page_count,
            processing_status, processing_stage, error_message, result_note, target_item_id,
            model_name, created_at, processed_at
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, 'queued', 'queued', NULL, NULL, ?, NULL, ?, NULL)
        """,
        (document_id, original_name, stored_name, mime_type, size_bytes, target_item_id, stamp),
    )
    document = require_document(document_id)
    return document


def document_path(document: dict) -> Path:
    root = config.upload_dir().resolve()
    path = (root / document["stored_name"]).resolve()
    if path.parent != root:
        raise ValidationError("That file path is not valid.")
    return path


def list_documents(limit: int = 20) -> list[dict]:
    rows = _query(
        "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    for row in rows:
        row["linked_items"] = items_for_document(row["id"])
    return rows


def delete_document(document_id: str) -> None:
    document = require_document(document_id)
    path = document_path(document)
    _execute("DELETE FROM documents WHERE id = ?", (document_id,))
    if path.exists():
        path.unlink()


def interrupted_document_ids() -> list[str]:
    rows = _query(
        """
        SELECT id FROM documents
        WHERE processing_status IN ('queued', 'processing')
        ORDER BY created_at
        """
    )
    for row in rows:
        update_document(row["id"], processing_status="queued", processing_stage="queued")
    return [row["id"] for row in rows]


def list_deadlines(status: str | None = None) -> list[dict]:
    sql = """
        SELECT d.*, i.title AS item_title, i.merchant
        FROM deadlines d
        JOIN items i ON i.id = d.item_id
    """
    params: tuple = ()
    if status:
        sql += " WHERE d.status = ?"
        params = (status,)
    sql += " ORDER BY d.due_date ASC, i.title ASC"
    return _query(sql, params)


def set_deadline_status(deadline_id: str, status: str) -> str:
    if status not in ("open", "done", "dismissed"):
        raise ValidationError("Status needs to be open, done, or dismissed.")
    row = _one("SELECT * FROM deadlines WHERE id = ?", (deadline_id,))
    if row is None:
        raise NotFound("That deadline was not found.")
    _execute(
        "UPDATE deadlines SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), deadline_id),
    )
    return row["item_id"]


def counts(today: str) -> dict:
    return {
        "active_items": _scalar("SELECT COUNT(*) FROM items WHERE status = 'active'"),
        "open_deadlines": _scalar("SELECT COUNT(*) FROM deadlines WHERE status = 'open'"),
        "overdue": _scalar(
            "SELECT COUNT(*) FROM deadlines WHERE status = 'open' AND due_date < ?",
            (today,),
        ),
        "needs_review": _scalar(
            """
            SELECT COUNT(*) FROM items i
            WHERE i.status = 'active' AND (
                EXISTS (
                    SELECT 1 FROM facts f WHERE f.item_id = i.id AND f.status = 'extracted'
                )
                OR EXISTS (SELECT 1 FROM gaps g WHERE g.item_id = i.id)
            )
            """
        ),
    }


def list_reminders() -> list[dict]:
    return _query(
        """
        SELECT r.*, i.title AS item_title
        FROM reminders r
        LEFT JOIN items i ON i.id = r.item_id
        ORDER BY r.remind_at ASC
        LIMIT 200
        """
    )


def create_reminder(data: dict) -> dict:
    item_id = data.get("item_id")
    deadline_id = data.get("deadline_id")
    if item_id:
        require_item(item_id)
    deadline = None
    if deadline_id:
        deadline = _one("SELECT * FROM deadlines WHERE id = ?", (deadline_id,))
        if deadline is None:
            raise NotFound("That deadline was not found.")
        if item_id and deadline["item_id"] != item_id:
            raise ValidationError("That deadline belongs to a different item.")
        item_id = item_id or deadline["item_id"]
    reminder_id = new_id()
    _execute(
        """
        INSERT INTO reminders (id, item_id, deadline_id, remind_at, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'scheduled', ?)
        """,
        (reminder_id, item_id, deadline_id, data["remind_at"], data["message"], now_iso()),
    )
    row = _one(
        """
        SELECT r.*, i.title AS item_title
        FROM reminders r
        LEFT JOIN items i ON i.id = r.item_id
        WHERE r.id = ?
        """,
        (reminder_id,),
    )
    if row is None:
        raise NotFound("That reminder was not found.")
    return row


def update_reminder(reminder_id: str, status: str) -> dict:
    if status not in ("scheduled", "seen", "dismissed"):
        raise ValidationError("Status needs to be scheduled, seen, or dismissed.")
    row = _one("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    if row is None:
        raise NotFound("That reminder was not found.")
    if status == "scheduled":
        _execute(
            "UPDATE reminders SET status = ?, notified_at = NULL WHERE id = ?",
            (status, reminder_id),
        )
    else:
        _execute("UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id))
    updated = _one(
        """
        SELECT r.*, i.title AS item_title
        FROM reminders r LEFT JOIN items i ON i.id = r.item_id
        WHERE r.id = ?
        """,
        (reminder_id,),
    )
    if updated is None:
        raise NotFound("That reminder was not found.")
    return updated


def due_unnotified_reminders(now: datetime | None = None) -> list[dict]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    rows = _query(
        """
        SELECT r.*, i.title AS item_title
        FROM reminders r
        LEFT JOIN items i ON i.id = r.item_id
        WHERE r.status = 'scheduled' AND r.notified_at IS NULL
        """
    )
    due: list[dict] = []
    for row in rows:
        try:
            parsed = datetime.fromisoformat(str(row["remind_at"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed <= moment:
            due.append(row)
    due.sort(key=lambda row: row["remind_at"])
    return due


def mark_reminder_notified(reminder_id: str) -> None:
    _execute(
        "UPDATE reminders SET notified_at = ? WHERE id = ? AND status = 'scheduled' AND notified_at IS NULL",
        (now_iso(), reminder_id),
    )


def delete_reminder(reminder_id: str) -> None:
    row = _one("SELECT id FROM reminders WHERE id = ?", (reminder_id,))
    if row is None:
        raise NotFound("That reminder was not found.")
    _execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
