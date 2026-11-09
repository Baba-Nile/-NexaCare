"""Central branch data for NexaCare: loading, validation and the 'only show verified facts' rules.

Used by build.py (public pages), app.py (accepted branch values for enquiries) and the staff inbox (branch names).
Source file: data/branches.json. Nothing in here invents information: every public value comes from that file and only
appears when its flag under "verified" is true."""
import json, re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "branches.json"
NO_PREFERENCE = "no-preference"                       # form value meaning "no branch chosen"
FACTS = ("locality", "address", "phone", "whatsapp", "email", "hours", "services", "directions")
STATUSES = {"details_pending", "open", "coming_soon"}
REQUIRED_BRANCHES = ["Maili Saba", "Manor House", "Meru Farm", "Tiwani", "Eldoret", "Nairobi"]
SLUG_RE, TEL_RE, EMAIL_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"), re.compile(r"^\+?[0-9]{7,15}$"), re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load(path=FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def everything(data=None):
    """Main centre first, then the six branches, in the order given in the data file."""
    data = data or load()
    return [data["main_centre"]] + list(data["branches"])


def slugs(data=None, include_none=True):
    s = [b["slug"] for b in everything(data)]
    return s + [NO_PREFERENCE] if include_none else s


def names(data=None):
    """slug -> display name (used by the staff inbox)."""
    d = {b["slug"]: (b["name"] + " (main centre)" if b.get("role") == "main_centre" else b["name"]) for b in everything(data)}
    d[NO_PREFERENCE] = "No preference"
    return d


def verified(b, fact):
    return bool(b.get("verified", {}).get(fact))


def value(b, fact):
    """The public value of a fact, or None when it is missing or not verified."""
    if not verified(b, fact):
        return None
    if fact == "locality": return b.get("locality") or None
    if fact == "address": return b.get("address") or None
    if fact == "email": return b.get("email") or None
    if fact == "hours": return [h for h in (b.get("hours") or []) if h] or None
    if fact == "services": return [s for s in (b.get("services") or []) if s] or None
    if fact == "phone":
        p = b.get("phone") or {}
        return p if p.get("display") and p.get("tel") else None
    if fact == "whatsapp":
        w = b.get("whatsapp") or {}
        return w if w.get("display") and w.get("number") else None
    if fact == "directions": return directions_url(b)
    return None


def coordinates(b):
    c = b.get("coordinates") or {}
    if verified(b, "directions") and isinstance(c.get("lat"), (int, float)) and isinstance(c.get("lng"), (int, float)):
        return c["lat"], c["lng"]
    return None


def directions_url(b):
    """A verified Google Maps directions link. Order: owner-supplied URL, then verified coordinates, then the verified address."""
    if not verified(b, "directions"):
        return None
    if b.get("directions_url"):
        return b["directions_url"]
    xy = coordinates(b)
    if xy:
        return f"https://www.google.com/maps/dir/?api=1&destination={xy[0]},{xy[1]}"
    if verified(b, "address") and b.get("address"):
        return "https://www.google.com/maps/dir/?api=1&destination=" + quote(f"{b['address']}")
    return None


def pending(b):
    """Facts that still have no verified public value."""
    return [f for f in FACTS if value(b, f) is None]


def indexable(b):
    """A branch page is offered to search engines only once the owner has confirmed the branch is operating AND at least one
    of address, phone or hours is verified. Until then the page exists for visitors but carries noindex."""
    return b.get("role") == "branch" and b.get("status") == "open" and any(value(b, f) for f in ("address", "phone", "hours"))


def validate(data=None, service_slugs=None):
    """Returns a list of problems (empty list = fine)."""
    data = data or load()
    bad, seen = [], set()
    items = everything(data)
    got = [b["name"] for b in data["branches"]]
    for n in REQUIRED_BRANCHES:
        if n not in got: bad.append(f"missing required branch: {n}")
    for b in items:
        s = b.get("slug", "?")
        if not SLUG_RE.match(s): bad.append(f"{s}: slug must be lowercase letters, digits and hyphens")
        if s in seen or s == NO_PREFERENCE: bad.append(f"{s}: duplicate or reserved slug")
        seen.add(s)
        for k in ("name", "status", "seo_title", "seo_description"):
            if not b.get(k): bad.append(f"{s}: missing {k}")
        if b.get("status") not in STATUSES: bad.append(f"{s}: status must be one of {sorted(STATUSES)}")
        v = b.get("verified", {})
        for f in FACTS:
            if f not in v: bad.append(f"{s}: verified flag missing for {f}")
        # a verified flag without a value would publish an empty field
        for f in FACTS:
            if v.get(f) and f != "directions" and not _has(b, f): bad.append(f"{s}: '{f}' is marked verified but has no value")
        if v.get("directions") and not (b.get("directions_url") or (b.get("coordinates") or {}).get("lat") is not None or (v.get("address") and b.get("address"))):
            bad.append(f"{s}: directions marked verified but there is no link, coordinates or verified address")
        p = b.get("phone") or {}
        if p.get("tel") and not TEL_RE.match(p["tel"]): bad.append(f"{s}: phone.tel must be digits with optional leading +")
        w = b.get("whatsapp") or {}
        if w.get("number") and not re.match(r"^[0-9]{8,15}$", w["number"]): bad.append(f"{s}: whatsapp.number must be digits only (no +), for wa.me links")
        if b.get("email") and not EMAIL_RE.match(b["email"]): bad.append(f"{s}: email looks invalid")
        u = b.get("directions_url")
        if u and not re.match(r"^https://(www\.google\.com/maps|maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com)", u): bad.append(f"{s}: directions_url must be a Google Maps https link")
        c = b.get("coordinates") or {}
        for k, lim in (("lat", 90), ("lng", 180)):
            if c.get(k) is not None and not (isinstance(c[k], (int, float)) and -lim <= c[k] <= lim): bad.append(f"{s}: coordinates.{k} out of range")
        if service_slugs is not None:
            for x in b.get("services") or []:
                if x not in service_slugs: bad.append(f"{s}: unknown service slug '{x}'")
        if b.get("status") == "open" and b.get("role") == "branch" and not any(value(b, f) for f in ("address", "phone", "hours")):
            bad.append(f"{s}: status is 'open' but no verified address, phone or hours")
    return bad


def _has(b, f):
    if f in ("phone", "whatsapp"):
        d = b.get(f) or {}
        return bool(d.get("display") and (d.get("tel") or d.get("number")))
    if f in ("services", "hours"): return bool([x for x in (b.get(f) or []) if x])
    return bool(b.get(f))
