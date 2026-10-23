from __future__ import annotations

import logging
import queue
import threading

from app import config
from app.errors import OcrError, OllamaError
from app.extract import item_drafts
from app.ocr import extract_text
from app.ollama_client import extract_facts
from app.store import (
    count_grounded_facts,
    document_path,
    get_document,
    mark_document_error,
    save_document_extraction,
    update_document,
)

logger = logging.getLogger("dontlose.pipeline")

_jobs: queue.Queue[str] = queue.Queue()
_started = False
_start_lock = threading.Lock()


def start_worker() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_loop, name="dontlose-worker", daemon=True).start()


def enqueue(document_id: str) -> None:
    _jobs.put(document_id)


def _loop() -> None:
    while True:
        document_id = _jobs.get()
        try:
            process_document(document_id)
        except Exception:
            logger.exception("Processing failed for %s", document_id)
            mark_document_error(document_id, "Could not process this file.")
        finally:
            _jobs.task_done()


def process_document(document_id: str) -> None:
    document = get_document(document_id)
    if document is None:
        return
    path = document_path(document)
    try:
        update_document(
            document_id,
            processing_status="processing",
            processing_stage="reading",
            error_message=None,
        )
        text, pages = extract_text(path)
        update_document(
            document_id,
            ocr_text=text,
            page_count=pages,
            processing_stage="model",
            model_name=config.ollama_model(),
        )
        payload = extract_facts(text)
        drafts = item_drafts(payload, text)
        update_document(document_id, processing_stage="saving")
        saved = save_document_extraction(document_id, drafts)
        grounded = count_grounded_facts(document_id)
        item_ids = saved["item_ids"]
        if grounded == 0:
            note = (
                "The file is saved. No deadline facts could be verified from the text. "
                "You can enter them yourself."
            )
        elif saved["attached"]:
            note = "Extracted facts were added to the existing item."
        elif len(item_ids) == 1:
            note = "An item was created from this file."
        else:
            note = f"{len(item_ids)} items were created from this file."
        update_document(
            document_id,
            processing_status="ready",
            processing_stage="ready",
            error_message=None,
            result_note=note,
            processed_at=_processed_now(),
        )
    except OcrError as exc:
        mark_document_error(document_id, str(exc))
    except OllamaError as exc:
        mark_document_error(document_id, str(exc))


def _processed_now() -> str:
    from app.store import now_iso

    return now_iso()
