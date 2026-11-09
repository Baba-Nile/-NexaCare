import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import abort, current_app, flash, request, url_for
from .db import one

def field(name, maxlen=200):
    return (request.form.get(name) or "").strip()[:maxlen]

def get_or_404(table, ident):
    """table is always a literal chosen by our own code, never user input."""
    try: ident = int(ident)
    except (TypeError, ValueError): abort(404)
    row = one(f"SELECT * FROM {table} WHERE id=?", (ident,))
    if not row: abort(404)
    return row

def safe_next(target, prefix="/staff", default="/staff/"):
    return target if target and target.startswith(prefix) and not target.startswith("//") and "\\" not in target else default

def set_login_cookie(resp, name, token, path):
    resp.set_cookie(name, token, httponly=True, samesite="Strict", secure=current_app.config["PORTAL"]["production"], path=path)
    return resp

def clear_cookie(resp, name, path):
    resp.delete_cookie(name, path=path); return resp

def valid_date(s):
    try: datetime.strptime(s, "%Y-%m-%d"); return True
    except (TypeError, ValueError): return False

def valid_dt(s):
    """Local (East Africa Time) date and time from <input type=datetime-local>: YYYY-MM-DDTHH:MM."""
    try: datetime.strptime(s, "%Y-%m-%dT%H:%M"); return True
    except (TypeError, ValueError): return False

def money_to_minor(s):
    try: d = Decimal((s or "").replace(",", "").strip())
    except InvalidOperation: return None
    if d <= 0 or d > Decimal("100000000") or d != d.quantize(Decimal("0.01")): return None
    return int(d * 100)

def fmt_money(minor): return f"{minor / 100:,.2f}"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^[0-9+()\s\-]{7,20}$")
