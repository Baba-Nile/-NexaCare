"""Database access. SQLite (development, tests) and PostgreSQL (production) share portable SQL:
'?' placeholders, ISO-8601 UTC text timestamps, INTEGER booleans and INSERT ... RETURNING id.
The PostgreSQL path (psycopg 3) could not be exercised in the build environment: run the test suite against a PostgreSQL database before use."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

class Database:
    def __init__(self, url):
        self.url = url
        self.is_pg = url.startswith(("postgres://", "postgresql://"))
        if not self.is_pg:
            if not url.startswith("sqlite:///"):
                raise ValueError("DATABASE_URL must be sqlite:///path or postgresql://...")
            self.path = url[len("sqlite:///"):]

    def connect(self):
        if self.is_pg:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg.connect(self.url, row_factory=dict_row)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def sql(self, q):
        return q.replace("?", "%s") if self.is_pg else q

    def migrate(self):
        """Apply migrations/NNN_*.sql in order, once each. Returns the list of versions applied."""
        c = self.connect(); cur = c.cursor(); applied = []
        cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        cur.execute("SELECT version FROM schema_migrations"); done = {r["version"] for r in cur.fetchall()}
        pk = "BIGSERIAL PRIMARY KEY" if self.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.stem in done: continue
            for stmt in [s.strip() for s in f.read_text(encoding="utf-8").replace("{PK}", pk).split(";\n") if s.strip()]:
                cur.execute(stmt)
            cur.execute(self.sql("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)"), (f.stem, now()))
            applied.append(f.stem)
        c.commit(); c.close()
        return applied

def conn():
    if "db" not in g:
        g.db = current_app.config["PORTAL_DB"].connect()
    return g.db

def run(q, args=()):
    cur = conn().cursor()
    cur.execute(current_app.config["PORTAL_DB"].sql(q), tuple(args))
    return cur

def one(q, args=()):
    r = run(q, args).fetchone()
    return dict(r) if r else None

def many(q, args=()):
    return [dict(r) for r in run(q, args).fetchall()]

def insert(q, args=()):
    return run(q + " RETURNING id", args).fetchone()["id"]

def close_db(exc):
    c = g.pop("db", None)
    if c is not None:
        c.rollback() if exc else c.commit()
        c.close()
