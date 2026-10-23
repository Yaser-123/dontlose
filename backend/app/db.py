from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Iterator

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  merchant TEXT,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  user_edited INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  mime_type TEXT,
  size_bytes INTEGER NOT NULL,
  ocr_text TEXT,
  page_count INTEGER,
  processing_status TEXT NOT NULL,
  processing_stage TEXT NOT NULL,
  error_message TEXT,
  result_note TEXT,
  target_item_id TEXT,
  model_name TEXT,
  created_at TEXT NOT NULL,
  processed_at TEXT,
  FOREIGN KEY (target_item_id) REFERENCES items(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS item_documents (
  item_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (item_id, document_id),
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  document_id TEXT,
  field_name TEXT NOT NULL,
  value_text TEXT NOT NULL,
  quote TEXT,
  confidence TEXT NOT NULL,
  status TEXT NOT NULL,
  grounded INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS deadlines (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  due_date TEXT NOT NULL,
  basis TEXT NOT NULL,
  fact_ids TEXT NOT NULL,
  provisional INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (item_id, kind),
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gaps (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  message TEXT NOT NULL,
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS item_links (
  source_item_id TEXT NOT NULL,
  target_item_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (source_item_id, target_item_id),
  FOREIGN KEY (source_item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY (target_item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
  id TEXT PRIMARY KEY,
  item_id TEXT,
  deadline_id TEXT,
  remind_at TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY (deadline_id) REFERENCES deadlines(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS item_notes (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_facts_item ON facts(item_id);
CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(status, due_date);
CREATE INDEX IF NOT EXISTS idx_item_documents_doc ON item_documents(document_id);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status, remind_at);
CREATE INDEX IF NOT EXISTS idx_item_notes_item ON item_notes(item_id, created_at);
"""

_db: "Database | None" = None
_db_key: str | None = None


class Database:
    def __init__(self, path: str) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._depth = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._depth += 1
            try:
                if self._depth == 1:
                    self._conn.execute("BEGIN IMMEDIATE")
                yield
                if self._depth == 1:
                    self._conn.commit()
            except Exception:
                if self._depth == 1:
                    self._conn.rollback()
                raise
            finally:
                self._depth -= 1

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        if self._depth:
            return self._conn.execute(sql, params)
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        if self._depth:
            return [dict(row) for row in self._conn.execute(sql, params).fetchall()]
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

    def close(self) -> None:
        self._conn.close()


def _migrate_legacy_notes(database: Database) -> None:
    rows = database.query(
        "SELECT id, notes, created_at FROM items WHERE trim(coalesce(notes, '')) != ''"
    )
    for row in rows:
        database.execute(
            "INSERT INTO item_notes (id, item_id, body, created_at) VALUES (?, ?, ?, ?)",
            (uuid.uuid4().hex, row["id"], row["notes"].strip(), row["created_at"]),
        )
        database.execute("UPDATE items SET notes = '' WHERE id = ?", (row["id"],))


def _ensure_item_columns(database: Database) -> None:
    names = {row["name"] for row in database.query("PRAGMA table_info(items)")}
    if "deadline_anchor" not in names:
        database.execute("ALTER TABLE items ADD COLUMN deadline_anchor TEXT")


def _ensure_reminder_columns(database: Database) -> None:
    names = {row["name"] for row in database.query("PRAGMA table_info(reminders)")}
    if "notified_at" not in names:
        database.execute("ALTER TABLE reminders ADD COLUMN notified_at TEXT")


def init_schema(database: Database) -> None:
    with database.transaction():
        for statement in SCHEMA.split(";"):
            sql = statement.strip()
            if sql:
                database.execute(sql)
        _migrate_legacy_notes(database)
        _ensure_item_columns(database)
        _ensure_reminder_columns(database)


def get_db() -> Database:
    global _db, _db_key
    path = str(config.db_path())
    if _db is not None and _db_key != path:
        _db.close()
        _db = None
    if _db is None:
        config.db_path().parent.mkdir(parents=True, exist_ok=True)
        _db = Database(path)
        init_schema(_db)
        _db_key = path
    return _db


def reset_connection() -> None:
    global _db, _db_key
    if _db is not None:
        _db.close()
    _db = None
    _db_key = None
