"""Authentication primitives: password hashing and policy, server-side sessions, CSRF, login throttling, field encryption."""
import hashlib, hmac, os, re, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from .db import insert, now, one, run

SESSION_RULES = {"staff": {"idle": 20 * 60, "absolute": 8 * 3600}, "patient": {"idle": 30 * 60, "absolute": 12 * 3600}}
LOCK_AFTER, LOCK_WINDOW, IP_LIMIT = 5, 15 * 60, 30
COMMON = {"password1234", "123456789012", "qwertyuiop12", "nexacare1234", "welcome12345", "letmein12345", "administrator1"}

def _ts(s): return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
def _ago(sec): return (datetime.now(timezone.utc) - timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")
def _h(*parts): return hashlib.sha256(":".join(parts).encode()).hexdigest()

# ---- passwords
def hash_password(pw): return generate_password_hash(pw, method="scrypt")
_DUMMY = None
def verify_password(stored, pw):
    """Constant-ish time: when there is no stored hash, still do the same work so unknown accounts cannot be detected by timing."""
    global _DUMMY
    if _DUMMY is None: _DUMMY = hash_password("not-a-real-password")
    ok = check_password_hash(stored or _DUMMY, pw)
    return bool(stored) and ok

def password_problems(pw, *personal):
    out = []
    if len(pw) < 12: out.append("Use at least 12 characters.")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)): out.append("Include letters and numbers.")
    low = pw.lower()
    if low in COMMON or any(p and p.lower() in low for p in personal if len(p or "") >= 4): out.append("That password is too easy to guess.")
    return out

# ---- field encryption (clinical text at rest). Keys: PORTAL_DATA_KEY=comma-separated Fernet keys, newest first (supports rotation).
def _fernet():
    f = current_app.config.get("_FERNET")
    if f is None:
        keys = [k.strip() for k in current_app.config["PORTAL"]["data_keys"] if k.strip()]
        f = current_app.config["_FERNET"] = MultiFernet([Fernet(k.encode()) for k in keys])
    return f
def encrypt(text):
    return None if text is None else _fernet().encrypt(text.encode()).decode()
def decrypt(token):
    if token is None: return None
    try: return _fernet().decrypt(token.encode()).decode()
    except InvalidToken: return "[unreadable: wrong or missing key]"

# ---- sessions (server-side, revocable). The cookie holds a random token; only its hash is stored.
def create_session(realm, subject_id):
    rules = SESSION_RULES[realm]; token, csrf, t = secrets.token_urlsafe(32), secrets.token_urlsafe(32), now()
    exp = (datetime.now(timezone.utc) + timedelta(seconds=rules["absolute"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    insert("INSERT INTO sessions (token_hash, realm, subject_id, csrf, created_at, last_seen, expires_at) VALUES (?,?,?,?,?,?,?)", (_h(token), realm, subject_id, csrf, t, t, exp))
    return token

def load_session(realm, token):
    if not token: return None
    s = one("SELECT * FROM sessions WHERE token_hash=? AND realm=?", (_h(token), realm))
    if not s: return None
    t = datetime.now(timezone.utc)
    if t > _ts(s["expires_at"]) or (t - _ts(s["last_seen"])).total_seconds() > SESSION_RULES[realm]["idle"]:
        run("DELETE FROM sessions WHERE id=?", (s["id"],)); return None
    if (t - _ts(s["last_seen"])).total_seconds() > 30: run("UPDATE sessions SET last_seen=? WHERE id=?", (now(), s["id"]))
    return s

def end_session(token):
    if token: run("DELETE FROM sessions WHERE token_hash=?", (_h(token),))
def end_all_sessions(realm, subject_id): run("DELETE FROM sessions WHERE realm=? AND subject_id=?", (realm, subject_id))

# ---- CSRF: logged-in forms use the per-session token; login/registration use a token kept in the signed Flask session cookie.
def pre_csrf():
    if "pre_csrf" not in session: session["pre_csrf"] = secrets.token_urlsafe(24)
    return session["pre_csrf"]
def submitted_token(): return request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
def csrf_valid(expected): return bool(expected) and hmac.compare_digest(str(expected), submitted_token())

# ---- login throttling: counts failures per account identifier AND per client address, whether or not the account exists
def client_ip(): return request.remote_addr or "unknown"
def _ip_hash(): return _h(current_app.config["PORTAL"]["hash_salt"], client_ip())
def _ident(realm, email): return _h(realm, (email or "").strip().lower())
def is_locked(realm, email):
    n = one("SELECT COUNT(*) AS n FROM login_attempts WHERE identifier_hash=? AND success=0 AND ts>?", (_ident(realm, email), _ago(LOCK_WINDOW)))["n"]
    m = one("SELECT COUNT(*) AS n FROM login_attempts WHERE ip_hash=? AND success=0 AND ts>?", (_ip_hash(), _ago(LOCK_WINDOW)))["n"]
    return n >= LOCK_AFTER or m >= IP_LIMIT
def record_attempt(realm, email, ok):
    insert("INSERT INTO login_attempts (realm, identifier_hash, ip_hash, ts, success) VALUES (?,?,?,?,?)", (realm, _ident(realm, email), _ip_hash(), now(), 1 if ok else 0))
    if ok: run("DELETE FROM login_attempts WHERE identifier_hash=? AND success=0", (_ident(realm, email),))
