"""
backend/app/services/journal_store.py

CRITICAL INVARIANT:
  JSON is source of truth. SQLite is a derived, read-optimized index.
  NEVER write to SQLite directly. Always write JSON first, then sync SQLite.
  SQLite is rebuilt automatically if missing or schema version mismatches.
  Atomic writes (temp file + rename) protect against data corruption.
"""
import json
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import (
    JOURNAL_DIR, JOURNAL_FILENAME, JOURNAL_INDEX_FILENAME,
    JOURNAL_BACKUP_SUFFIX, MAX_JOURNAL_ENTRIES,
)
from ..models.journal import JournalEntry, JournalEntryCreate, JournalEntryUpdate

JOURNAL_FILE = JOURNAL_DIR / JOURNAL_FILENAME
INDEX_FILE   = JOURNAL_DIR / JOURNAL_INDEX_FILENAME
INDEX_SCHEMA_VERSION = 1


def _safe_journal_path(filename: str) -> Path:
    """Reject path traversal. Output must stay within JOURNAL_DIR."""
    resolved = (JOURNAL_DIR / filename).resolve()
    if not str(resolved).startswith(str(JOURNAL_DIR.resolve())):
        raise ValueError(f"Path traversal rejected: {filename}")
    return resolved


class JournalStore:

    def __init__(self):
        self._ensure_files()

    def _ensure_files(self):
        if not JOURNAL_FILE.exists():
            self._atomic_write([])
        self._ensure_index()

    def _load_all(self) -> list[dict]:
        try:
            with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Journal file must contain a JSON array.")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Journal file corrupted: {e}") from e

    def _atomic_write(self, entries: list[dict]):
        """Write atomically: temp file → rename. Never leaves a partial write."""
        if len(entries) > MAX_JOURNAL_ENTRIES:
            raise ValueError(f"Journal exceeds maximum entry count ({MAX_JOURNAL_ENTRIES}).")
        fd, tmp_path = tempfile.mkstemp(dir=JOURNAL_DIR, suffix=".tmp")
        try:
            with open(fd, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2, default=str)
            Path(tmp_path).replace(JOURNAL_FILE)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def _backup(self):
        if JOURNAL_FILE.exists():
            shutil.copy2(JOURNAL_FILE, JOURNAL_FILE.with_suffix(JOURNAL_BACKUP_SUFFIX))

    # ── SQLite index ──────────────────────────────────────────────────

    def _get_index_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(INDEX_FILE)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_index(self):
        needs_rebuild = not INDEX_FILE.exists()
        if not needs_rebuild:
            try:
                with self._get_index_conn() as conn:
                    row = conn.execute(
                        "SELECT value FROM meta WHERE key='schema_version'"
                    ).fetchone()
                    if row is None or int(row['value']) != INDEX_SCHEMA_VERSION:
                        needs_rebuild = True
            except sqlite3.OperationalError:
                needs_rebuild = True
        if needs_rebuild:
            self._rebuild_index()

    def _rebuild_index(self):
        with self._get_index_conn() as conn:
            conn.executescript("""
                DROP TABLE IF EXISTS entries;
                DROP TABLE IF EXISTS tags;
                DROP TABLE IF EXISTS meta;
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    type TEXT,
                    desert_value REAL,
                    starred INTEGER,
                    roget_class_a TEXT,
                    roget_class_b TEXT,
                    fabrication_status TEXT
                );
                CREATE TABLE tags (
                    entry_id TEXT,
                    tag TEXT,
                    FOREIGN KEY (entry_id) REFERENCES entries(id)
                );
                CREATE INDEX idx_tags_tag      ON tags(tag);
                CREATE INDEX idx_entries_desert ON entries(desert_value);
                CREATE INDEX idx_entries_starred ON entries(starred);
                CREATE INDEX idx_entries_type   ON entries(type);
            """)
            conn.execute(
                "INSERT INTO meta VALUES ('schema_version', ?)",
                (str(INDEX_SCHEMA_VERSION),)
            )
            for e in self._load_all():
                self._index_entry(conn, e)

    def _index_entry(self, conn: sqlite3.Connection, entry: dict):
        rc  = entry.get('roget_context') or {}
        fab = entry.get('fabrication_notes') or {}
        conn.execute(
            "INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?)",
            (
                entry['id'], entry.get('timestamp'), entry.get('type'),
                entry.get('desert_value', 0.0),
                1 if entry.get('starred') else 0,
                rc.get('class_a'), rc.get('class_b'),
                fab.get('status', 'idea'),
            )
        )
        conn.execute("DELETE FROM tags WHERE entry_id=?", (entry['id'],))
        for tag in entry.get('tags', []):
            conn.execute("INSERT INTO tags VALUES (?,?)", (entry['id'], tag))

    def _sync_index_entry(self, entry: dict):
        with self._get_index_conn() as conn:
            self._index_entry(conn, entry)

    def _remove_from_index(self, entry_id: str):
        with self._get_index_conn() as conn:
            conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
            conn.execute("DELETE FROM tags WHERE entry_id=?", (entry_id,))

    # ── Public API ────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        return self._load_all()

    def get_by_id(self, entry_id: str) -> dict | None:
        for e in self._load_all():
            if e.get('id') == entry_id:
                return e
        return None

    def create(self, entry_create: JournalEntryCreate) -> dict:
        entries = self._load_all()
        new_entry = JournalEntry(
            **entry_create.model_dump(),
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
        )
        entry_dict = json.loads(new_entry.model_dump_json())
        entries.append(entry_dict)
        self._atomic_write(entries)
        self._sync_index_entry(entry_dict)
        return entry_dict

    def update(self, entry_id: str, update: JournalEntryUpdate) -> dict | None:
        entries = self._load_all()
        for i, e in enumerate(entries):
            if e.get('id') == entry_id:
                update_data = {k: v for k, v in update.model_dump().items() if v is not None}
                entries[i] = {**e, **update_data}
                self._atomic_write(entries)
                self._sync_index_entry(entries[i])
                return entries[i]
        return None

    def query(
        self,
        tags: list[str] | None = None,
        min_desert: float | None = None,
        starred: bool | None = None,
        entry_type: str | None = None,
        fabrication_status: str | None = None,
        roget_class: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[str]:
        """Returns matching entry IDs via SQLite index."""
        self._ensure_index()
        clauses: list[str] = ["1=1"]
        params:  list[Any] = []
        if min_desert is not None:
            clauses.append("e.desert_value >= ?");  params.append(min_desert)
        if starred is not None:
            clauses.append("e.starred = ?");         params.append(1 if starred else 0)
        if entry_type is not None:
            clauses.append("e.type = ?");            params.append(entry_type)
        if fabrication_status is not None:
            clauses.append("e.fabrication_status = ?"); params.append(fabrication_status)
        if roget_class is not None:
            clauses.append("(e.roget_class_a = ? OR e.roget_class_b = ?)")
            params.extend([roget_class, roget_class])
        where = " AND ".join(clauses)
        if tags:
            tag_clauses = " AND ".join(
                "EXISTS (SELECT 1 FROM tags t WHERE t.entry_id=e.id AND t.tag=?)"
                for _ in tags
            )
            where += f" AND ({tag_clauses})"
            params.extend(tags)
        sql = (
            f"SELECT e.id FROM entries e WHERE {where} "
            f"ORDER BY e.timestamp DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._get_index_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [row['id'] for row in rows]


_store: JournalStore | None = None

def get_store() -> JournalStore:
    global _store
    if _store is None:
        _store = JournalStore()
    return _store
