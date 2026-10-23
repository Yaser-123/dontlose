from __future__ import annotations

import io
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from app import config, notify, pipeline, present, scheduler, store
from app.fields import CATEGORIES, ITEM_STATUSES
from app.ocr import tesseract_status
from app.ollama_client import ollama_status
from app.validate import NotFound, ValidationError, clean_note, clean_reminder, parse_id

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dontlose")

MAX_BYTES = 20 * 1024 * 1024
ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
}
_health_cache: dict = {"at": 0.0, "body": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.get_item_row("0" * 32)
    pipeline.start_worker()
    scheduler.start()
    for document_id in store.interrupted_document_ids():
        pipeline.enqueue(document_id)
    yield


app = FastAPI(title="Don'tLose", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store(request, call_next):
    response = await call_next(request)
    if not request.url.path.endswith("/file"):
        response.headers["Cache-Control"] = "no-store"
    return response


def run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _clean_filename(name: str) -> str:
    base = Path(name or "document").name
    suffix = Path(base).suffix.lower()
    stem = re.sub(r"[^\w.\- ()]", "_", Path(base).stem).strip("._") or "document"
    if suffix not in ALLOWED:
        raise ValidationError(f"{base} needs to be an image or a PDF.")
    return f"{stem[:160]}{suffix}"


async def _read_upload(upload: UploadFile) -> tuple[str, bytes, str, str]:
    original = _clean_filename(upload.filename or "document")
    suffix = Path(original).suffix.lower()
    data = await upload.read()
    if not data:
        raise ValidationError(f"{original} is empty.")
    if len(data) > MAX_BYTES:
        raise ValidationError(f"{original} is larger than 20 MB.")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise ValidationError(f"{original} is not a PDF.")
    else:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise ValidationError(f"{original} could not be opened as an image.") from exc
    return original, data, ALLOWED[suffix], suffix


def _store_upload(original: str, data: bytes, mime: str, suffix: str, target_item_id: str | None) -> dict:
    document_id = uuid.uuid4().hex
    stored_name = f"{document_id}{suffix}"
    path = config.upload_dir() / stored_name
    path.write_bytes(data)
    try:
        return store.create_document(original, stored_name, mime, len(data), target_item_id)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.get("/")
def root() -> dict:
    return {"name": "Don'tLose", "health": "/health", "docs": "/docs"}


@app.get("/health")
def health() -> dict:
    now = time.time()
    cached = _health_cache["body"]
    if cached and now - _health_cache["at"] < 5:
        return cached
    database_ok = True
    try:
        store.get_item_row("0" * 32)
    except Exception:
        logger.exception("Database health check failed")
        database_ok = False
    body = {
        "ok": database_ok,
        "database": database_ok,
        "tesseract": tesseract_status(),
        "ollama": ollama_status(),
        "windows_notifications": notify.notifications_enabled(),
    }
    _health_cache["at"] = now
    _health_cache["body"] = body
    return body


@app.get("/dashboard")
def dashboard() -> dict:
    return run(present.dashboard)


@app.get("/items")
def get_items(
    q: str = "",
    category: str = "",
    status: str = "",
) -> dict:
    if category and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a category from the list.")
    if status and status not in ITEM_STATUSES:
        raise HTTPException(status_code=400, detail="Status needs to be active, resolved, or archived.")
    bundles = run(store.list_bundles, q, category, status, 200)
    return {"items": [present.item_summary(bundle) for bundle in bundles]}


@app.post("/items")
def create_item(payload: dict) -> dict:
    item_id = run(store.create_manual_item, payload)
    return present.item_detail(store.item_detail_record(item_id))


@app.get("/items/{item_id}")
def get_item(item_id: str) -> dict:
    return present.item_detail(run(store.item_detail_record, parse_id(item_id, "That item")))


@app.patch("/items/{item_id}")
def patch_item(item_id: str, payload: dict) -> dict:
    item_id = parse_id(item_id, "That item")
    run(store.update_item, item_id, payload)
    return present.item_detail(store.item_detail_record(item_id))


@app.post("/items/{item_id}/anchor")
def post_anchor(item_id: str, payload: dict) -> dict:
    item_id = parse_id(item_id, "That item")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Choose purchase or delivery.")
    run(store.set_start_anchor, item_id, str(payload.get("anchor") or ""))
    return present.item_detail(store.item_detail_record(item_id))


@app.post("/items/{item_id}/notes")
def post_note(item_id: str, payload: dict) -> dict:
    item_id = parse_id(item_id, "That item")
    run(store.add_note, item_id, run(clean_note, payload))
    return present.item_detail(store.item_detail_record(item_id))


@app.delete("/items/{item_id}/notes/{note_id}", status_code=204)
def remove_note(item_id: str, note_id: str) -> Response:
    run(store.delete_note, parse_id(item_id, "That item"), parse_id(note_id, "That note"))
    return Response(status_code=204)


@app.delete("/items/{item_id}", status_code=204)
def remove_item(item_id: str) -> Response:
    run(store.delete_item, parse_id(item_id, "That item"))
    return Response(status_code=204)


@app.post("/items/{item_id}/facts")
def add_fact(item_id: str, payload: dict) -> dict:
    item_id = parse_id(item_id, "That item")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The fact could not be read.")
    run(store.set_user_fact, item_id, str(payload.get("field_name") or ""), payload.get("value_text"))
    return present.item_detail(store.item_detail_record(item_id))


@app.post("/items/{item_id}/confirm-extracted")
def confirm_extracted(item_id: str) -> dict:
    item_id = parse_id(item_id, "That item")
    count = run(store.confirm_extracted, item_id)
    detail = present.item_detail(store.item_detail_record(item_id))
    detail["confirmed_count"] = count
    return detail


@app.post("/items/{item_id}/merge")
def merge_item(item_id: str, payload: dict) -> dict:
    item_id = parse_id(item_id, "That item")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Choose an item to merge into.")
    target = run(parse_id, str(payload.get("into_item_id") or ""), "That item")
    run(store.merge_items, item_id, target)
    return present.item_detail(store.item_detail_record(target))


@app.post("/items/{item_id}/links/{other_id}/dismiss")
def dismiss_link(item_id: str, other_id: str) -> dict:
    item_id = parse_id(item_id, "That item")
    other_id = parse_id(other_id, "That item")
    run(store.dismiss_suggestion, item_id, other_id)
    return present.item_detail(store.item_detail_record(item_id))


@app.patch("/facts/{fact_id}")
def patch_fact(fact_id: str, payload: dict) -> dict:
    fact_id = parse_id(fact_id, "That fact")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The fact could not be read.")
    item_id = run(
        store.mutate_fact,
        fact_id,
        str(payload.get("action") or ""),
        payload.get("value_text"),
    )
    return present.item_detail(store.item_detail_record(item_id))


@app.post("/documents")
async def upload_documents(
    files: list[UploadFile] = File(...),
    item_id: str | None = Form(default=None),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file.")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Upload up to 10 files at a time.")
    target = item_id or None
    if target:
        target = parse_id(target, "That item")
        run(store.require_item, target)
    try:
        prepared = [await _read_upload(upload) for upload in files]
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    saved = []
    for original, data, mime, suffix in prepared:
        try:
            saved.append(_store_upload(original, data, mime, suffix, target))
        except (ValidationError, NotFound) as exc:
            status = 404 if isinstance(exc, NotFound) else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc
    for document in saved:
        pipeline.enqueue(document["id"])
    rows = []
    for document in saved:
        current = store.require_document(document["id"])
        current["linked_items"] = store.items_for_document(document["id"])
        rows.append(present.document_out(current))
    return {"documents": rows}


@app.get("/documents")
def get_documents(limit: int = Query(default=12, ge=1, le=50)) -> dict:
    rows = run(store.list_documents, limit)
    return {"documents": [present.document_out(row) for row in rows]}


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    document_id = parse_id(document_id, "That file")
    document = run(store.require_document, document_id)
    document["linked_items"] = store.items_for_document(document_id)
    return present.document_out(document, include_text=True)


@app.get("/documents/{document_id}/file")
def get_document_file(document_id: str):
    from fastapi.responses import FileResponse

    document = run(store.require_document, parse_id(document_id, "That file"))
    path = run(store.document_path, document)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored file is missing.")
    return FileResponse(path, media_type=document.get("mime_type") or "application/octet-stream", filename=document["original_name"])


@app.post("/documents/{document_id}/reprocess")
def reprocess_document(document_id: str) -> dict:
    document_id = parse_id(document_id, "That file")
    document = run(store.require_document, document_id)
    if document["processing_status"] in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="This file is already being read.")
    run(
        store.update_document,
        document_id,
        processing_status="queued",
        processing_stage="queued",
        error_message=None,
        result_note=None,
    )
    pipeline.enqueue(document_id)
    current = store.require_document(document_id)
    current["linked_items"] = store.items_for_document(document_id)
    return present.document_out(current)


@app.delete("/documents/{document_id}", status_code=204)
def remove_document(document_id: str) -> Response:
    run(store.delete_document, parse_id(document_id, "That file"))
    return Response(status_code=204)


@app.get("/deadlines")
def get_deadlines(status: str = "open") -> dict:
    if status not in ("open", "done", "dismissed"):
        raise HTTPException(status_code=400, detail="Status needs to be open, done, or dismissed.")
    rows = run(store.list_deadlines, status)
    from datetime import date

    today = date.today()
    return {"deadlines": [present.deadline_out(row, today) for row in rows]}


@app.post("/deadlines/{deadline_id}/status")
def post_deadline_status(deadline_id: str, payload: dict) -> dict:
    deadline_id = parse_id(deadline_id, "That deadline")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The deadline could not be read.")
    run(store.set_deadline_status, deadline_id, str(payload.get("status") or ""))
    from datetime import date

    row = next(item for item in store.list_deadlines(None) if item["id"] == deadline_id)
    return present.deadline_out(row, date.today())


@app.get("/reminders")
def get_reminders() -> dict:
    return {"reminders": [present.reminder_out(row) for row in run(store.list_reminders)]}


@app.post("/reminders")
def post_reminder(payload: dict) -> dict:
    cleaned = run(clean_reminder, payload)
    if cleaned["item_id"]:
        cleaned["item_id"] = run(parse_id, cleaned["item_id"], "That item")
    if cleaned["deadline_id"]:
        cleaned["deadline_id"] = run(parse_id, cleaned["deadline_id"], "That deadline")
    return present.reminder_out(run(store.create_reminder, cleaned))


@app.patch("/reminders/{reminder_id}")
def patch_reminder(reminder_id: str, payload: dict) -> dict:
    reminder_id = parse_id(reminder_id, "That reminder")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The reminder could not be read.")
    return present.reminder_out(run(store.update_reminder, reminder_id, str(payload.get("status") or "")))


@app.delete("/reminders/{reminder_id}", status_code=204)
def remove_reminder(reminder_id: str) -> Response:
    run(store.delete_reminder, parse_id(reminder_id, "That reminder"))
    return Response(status_code=204)
