"""Tamper-evident audit trail: every event stores the hash of the previous event, so edits or deletions break the chain.
Never put clinical text or personal details in 'detail': record ids and field names only."""
import hashlib, json
from flask import current_app, g, has_request_context, request
from .db import insert, many, now, one, run

GENESIS = "0" * 64

def _digest(prev, ts, actor_type, actor_id, action, target_type, target_id, outcome, detail):
    data = json.dumps([ts, actor_type, actor_id, action, target_type, target_id, outcome, detail], separators=(",", ":"))
    return hashlib.sha256((prev + data).encode()).hexdigest()

def audit(action, target=None, detail=None, outcome="ok", actor=None):
    if actor is None and has_request_context():
        if getattr(g, "staff", None): actor = ("staff", g.staff["id"])
        elif getattr(g, "account", None): actor = ("patient", g.account["id"])
    a_type, a_id = actor or (None, None); t_type, t_id = target or (None, None)
    if current_app.config["PORTAL_DB"].is_pg: run("SELECT pg_advisory_xact_lock(7001)")   # keep the chain linear under concurrency
    last = one("SELECT row_hash FROM audit_events ORDER BY id DESC LIMIT 1"); prev = last["row_hash"] if last else GENESIS
    ts, d = now(), json.dumps(detail or {}, sort_keys=True, separators=(",", ":"))
    ip = request.remote_addr if has_request_context() else None
    insert("INSERT INTO audit_events (ts, actor_type, actor_id, action, target_type, target_id, outcome, detail, ip, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (ts, a_type, a_id, action, t_type, t_id, outcome, d, ip, prev, _digest(prev, ts, a_type, a_id, action, t_type, t_id, outcome, d)))

def verify_chain():
    """Returns (ok, first_bad_id, count)."""
    prev, n = GENESIS, 0
    for r in many("SELECT * FROM audit_events ORDER BY id"):
        n += 1
        if r["prev_hash"] != prev or r["row_hash"] != _digest(prev, r["ts"], r["actor_type"], r["actor_id"], r["action"], r["target_type"], r["target_id"], r["outcome"], r["detail"]):
            return False, r["id"], n
        prev = r["row_hash"]
    return True, None, n
