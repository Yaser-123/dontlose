from datetime import datetime, timedelta, timezone

import pytest

from app.validate import clean_reminder


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DONTLOSE_DATA_DIR", str(tmp_path))
    from app import db as database

    database.reset_connection()
    yield
    database.reset_connection()


def test_a_due_reminder_is_notified_once(db, monkeypatch):
    from app import scheduler, store

    shown: list[tuple[str, str, str]] = []

    def fake_toast(title: str, message: str, launch: str = "") -> bool:
        shown.append((title, message, launch))
        return True

    monkeypatch.setattr(scheduler.notify, "show_toast", fake_toast)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    due = store.create_reminder(clean_reminder({"message": "Return the cooker", "remind_at": past}))
    store.create_reminder(clean_reminder({"message": "Still later", "remind_at": future}))

    assert scheduler.dispatch_due() == 1
    assert shown == [("Don'tLose", "Return the cooker", "http://localhost:3000/reminders")]
    assert scheduler.dispatch_due() == 0
    assert store.due_unnotified_reminders() == []

    store.update_reminder(due["id"], "scheduled")
    assert scheduler.dispatch_due() == 1


def test_a_failed_toast_stays_pending(db, monkeypatch):
    from app import scheduler, store

    monkeypatch.setattr(scheduler.notify, "show_toast", lambda *_args, **_kwargs: False)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    store.create_reminder(clean_reminder({"message": "Try again", "remind_at": past}))
    assert scheduler.dispatch_due() == 0
    assert len(store.due_unnotified_reminders()) == 1
