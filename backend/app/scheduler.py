from __future__ import annotations

import logging
import threading

from app import config, notify, store

logger = logging.getLogger("dontlose.reminders")

_started = False
_start_lock = threading.Lock()
_stop = threading.Event()
_INTERVAL_SECONDS = 15


def dispatch_due() -> int:
    origin = config.cors_origins()[0].rstrip("/")
    sent = 0
    for row in store.due_unnotified_reminders():
        item_id = row.get("item_id")
        launch = f"{origin}/items/{item_id}" if item_id else f"{origin}/reminders"
        if notify.show_toast("Don'tLose", str(row["message"]), launch):
            store.mark_reminder_notified(row["id"])
            sent += 1
            logger.info("Showed reminder %s", row["id"])
    return sent


def start() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        _stop.clear()
        notify.claim_app_id()
        threading.Thread(target=_loop, name="dontlose-reminders", daemon=True).start()


def _loop() -> None:
    while not _stop.is_set():
        try:
            dispatch_due()
        except Exception:
            logger.exception("Reminder check failed")
        if _stop.wait(_INTERVAL_SECONDS):
            return
