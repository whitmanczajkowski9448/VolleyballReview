"""Local SQLite storage. JSON records preserve source field names and types."""
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
TABLES = {"plays", "email_recipients", "play_comments", "video_angles", "app_users"}


def database_path():
    return Path(os.environ.get("VOLLEYREVIEW_DB", str(ROOT / "data" / "volleyball_review.db"))).expanduser().resolve()


def _table(name):
    if name not in TABLES:
        raise ValueError(f"Unsupported table: {name}")
    return name


def _field(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid field: {name}")
    return "json_extract(record, '$." + name + "')"


def _encode(row):
    return json.dumps(row, ensure_ascii=False, allow_nan=False)


@contextmanager
def connection(path=None):
    path = Path(path or database_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA journal_mode=WAL")
        for name in sorted(TABLES):
            con.execute(f"CREATE TABLE IF NOT EXISTS {name} (row_id TEXT PRIMARY KEY, record TEXT NOT NULL CHECK(json_valid(record)))")
        for field in ("dvsport_id", "match_date", "conference", "set_number", "score"):
            con.execute(f"CREATE INDEX IF NOT EXISTS plays_{field} ON plays ({_field(field)})")
        con.commit()
        with con:
            yield con
    finally:
        con.close()


def _new_id(con, table):
    existing = con.execute(f"SELECT row_id FROM {table} LIMIT 1").fetchone()
    if existing and not existing[0].isdigit():
        return str(uuid.uuid4())
    largest = con.execute(f"SELECT MAX(CAST(row_id AS INTEGER)) FROM {table} WHERE row_id NOT GLOB '*[^0-9]*'").fetchone()[0]
    return (largest or 0) + 1


def _insert(con, table, row):
    row = dict(row)
    if row.get("id") in (None, ""):
        row["id"] = _new_id(con, table)
    con.execute(f"INSERT INTO {table} (row_id, record) VALUES (?, ?)", (str(row["id"]), _encode(row)))
    return row


class Query:
    """Only the chain operations used by this application are supported."""
    def __init__(self, table, path):
        self.table = _table(table)
        self.path = path
        self.columns = None
        self.filters = []
        self.orders = []
        self.count = None
        self.offset = 0
        self.action = "select"
        self.payload = None

    def select(self, columns="*"):
        self.columns = None if columns == "*" else [c.strip() for c in columns.split(",")]
        for column in self.columns or []:
            _field(column)
        return self

    def eq(self, field, value):
        expression = "row_id" if field == "id" else _field(field)
        if field == "id" and value is not None:
            value = str(value)
        self.filters.append((expression + (" IS NULL" if value is None else " = ?"), [] if value is None else [value]))
        return self

    def order(self, field, desc=False):
        self.orders.append(_field(field) + (" DESC" if desc else " ASC"))
        return self

    def limit(self, count):
        self.count = max(0, int(count))
        return self

    def range(self, start, end):
        self.offset = max(0, int(start))
        self.count = max(0, int(end) - self.offset + 1)
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    def execute(self):
        with connection(self.path) as con:
            if self.action in {"insert", "update"}:
                con.execute("BEGIN IMMEDIATE")
            if self.action == "insert":
                items = self.payload if isinstance(self.payload, list) else [self.payload]
                return SimpleNamespace(data=[_insert(con, self.table, row) for row in items])
            clauses = [sql for sql, _ in self.filters]
            params = [v for _, values in self.filters for v in values]
            sql = f"SELECT row_id, record FROM {self.table}"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            if self.action == "update":
                if not clauses:
                    raise ValueError("Refusing an unfiltered update")
                if "id" in self.payload:
                    raise ValueError("Cannot change an existing id")
                updated = []
                for key, raw in con.execute(sql, params).fetchall():
                    row = json.loads(raw)
                    row.update(self.payload)
                    con.execute(f"UPDATE {self.table} SET record=? WHERE row_id=?", (_encode(row), key))
                    updated.append(row)
                if not updated:
                    raise LookupError("No matching record to update")
                return SimpleNamespace(data=updated)
            sql += " ORDER BY " + ", ".join(self.orders + ["row_id ASC"])
            if self.count is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([self.count, self.offset])
            rows = [json.loads(raw) for _, raw in con.execute(sql, params)]
            if self.columns is not None:
                rows = [{k: row.get(k) for k in self.columns} for row in rows]
            return SimpleNamespace(data=rows)


class SQLiteClient:
    def __init__(self, path=None):
        self.path = Path(path or database_path())

    def table(self, name):
        return Query(name, self.path)


def get_database():
    return SQLiteClient()


# Compatibility alias for the original review views and sync code.
get_supabase = get_database


def backup_database():
    path = database_path()
    if not path.exists():
        return None
    folder = path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"volleyball_review-{date.today().isoformat()}.db"
    if target.exists():
        return target
    temporary = target.with_suffix(".tmp")
    with connection(path) as source:
        dest = sqlite3.connect(temporary)
        try:
            source.backup(dest)
        finally:
            dest.close()
    temporary.replace(target)
    return target


def import_records(table, rows):
    """Import into an empty table atomically; never overwrite existing data."""
    table = _table(table)
    with connection() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
            raise ValueError(f"{table} is not empty. Import canceled to protect your data.")
        for row in rows:
            if not isinstance(row, dict) or row.get("id") in (None, ""):
                raise ValueError("Every exported record must contain its original id")
            _insert(con, table, row)
    return len(rows)
