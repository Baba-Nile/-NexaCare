"""Storage helpers for public website enquiries (SQLite): schema creation and migration, and retrieval that is safe on old databases.

Shared by app.py (writes) and the staff inbox in portal/staff.py (read-only). Keep this module free of Flask imports.
Backward compatibility: databases created before branches existed have no 'branch' column. ensure_schema() adds it without touching
existing rows, and rows() copes with a database that has not been migrated yet (for example one opened read-only)."""
import json
import branches as BM

SCHEMA = """CREATE TABLE IF NOT EXISTS enquiries(id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, kind TEXT NOT NULL,
            name TEXT, phone TEXT, email TEXT, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new')"""
UNSPECIFIED = "unspecified"        # filter value for enquiries that carry no branch (all enquiries made before branches existed)


def columns(c):
    return [r[1] for r in c.execute("PRAGMA table_info(enquiries)")]


def ensure_schema(c):
    """Create the table if needed and add the 'branch' column to an existing database. Safe to call on every connection."""
    c.execute(SCHEMA)
    if "branch" not in columns(c):
        try:
            c.execute("ALTER TABLE enquiries ADD COLUMN branch TEXT")
        except Exception:                         # another worker added it first
            if "branch" not in columns(c): raise
    c.execute("CREATE INDEX IF NOT EXISTS enquiries_branch ON enquiries(branch)")


def rows(c, limit=100, branch=None):
    """Most recent enquiries as dicts, each with 'branch' (slug or None), 'branch_name', 'service' and 'details' (stored payload).
    branch=None returns everything; a slug filters; UNSPECIFIED returns enquiries without a branch."""
    has_col = "branch" in columns(c)
    sel = "reference, created_at, kind, name, phone, email, status, payload" + (", branch" if has_col else "")
    where, args = "", []
    if branch == UNSPECIFIED:
        where = "WHERE branch IS NULL OR branch = ''" if has_col else ""
        # no column: every row is unspecified, unless its payload says otherwise (checked below)
    elif branch and has_col:
        where, args = "WHERE branch = ?", [branch]
    elif branch:
        where = ""                                # old database, nothing can match a specific branch
    names, out = BM.names(), []
    cur = c.execute(f"SELECT {sel} FROM enquiries {where} ORDER BY id DESC LIMIT ?", args + [int(limit)])
    cols = [d[0] for d in cur.description]
    for r in cur:
        d = dict(zip(cols, r))
        try: p = json.loads(d.pop("payload") or "{}")
        except ValueError: p = {}
        slug = (d.get("branch") if has_col else None) or p.get("branch") or None      # payload fallback for odd rows
        d["branch"], d["details"] = slug, p
        d["branch_name"] = names.get(slug, slug) if slug else "Not specified"
        d["service"] = p.get("service") or p.get("care_type") or ""
        if branch == UNSPECIFIED and slug: continue
        if branch and branch != UNSPECIFIED and slug != branch: continue
        out.append(d)
    return out


def branch_counts(c):
    """slug -> number of enquiries, for the staff inbox filter. Old rows count as UNSPECIFIED."""
    counts = {}
    for d in rows(c, limit=100000):
        k = d["branch"] or UNSPECIFIED
        counts[k] = counts.get(k, 0) + 1
    return counts
