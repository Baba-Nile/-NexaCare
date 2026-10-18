"""NexaCare enquiry service. Serves the static site for local development and stores enquiry forms in SQLite.

Run locally:   pip install -r python/requirements.txt && python python/app.py
Maintenance:   python python/app.py list [N] | python python/app.py purge DAYS
Production:    serve the static files from your web server, run this app behind HTTPS (e.g. gunicorn, several workers is fine:
               the rate limit lives in SQLite), and set NEXACARE_TRUSTED_PROXIES to the number of reverse proxies in front of it.
This is an enquiry inbox only. It is NOT a patient-records system and must not be used to store clinical information."""
import base64, hashlib, json, logging, os, re, secrets, sqlite3, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("NEXACARE_DB", Path(__file__).parent / "instance" / "enquiries.db"))
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get("NEXACARE_ALLOWED_ORIGINS", "").split(",") if o.strip()}  # e.g. https://www.example.co.ke
TRUSTED_PROXIES = int(os.environ.get("NEXACARE_TRUSTED_PROXIES", "0"))     # number of proxies whose X-Forwarded-For is trusted
SALT = os.environ.get("NEXACARE_HASH_SALT", "change-me-in-production")      # used only to hash IPs for rate limiting
KINDS = {"appointment", "homecare", "contact", "quick"}
# Only these fields are ever stored (name -> max length). Anything else is ignored.
FIELDS = {"name": 120, "requester_name": 120, "relationship": 120, "phone": 20, "email": 120, "service": 60, "care_type": 120, "age_group": 40, "area": 120,
          "date": 10, "time": 20, "contact_time": 20, "contact_method": 20, "message": 600}
PHONE_RE, EMAIL_RE, DATE_RE = re.compile(r"^[0-9+()\s\-]{7,20}$"), re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"), re.compile(r"^\d{4}-\d{2}-\d{2}$")
RATE_MAX, RATE_WINDOW = 5, 600     # submissions per client per 10 minutes
JS_SNIPPET = 'document.documentElement.classList.add("js")'   # inline script in every page; allowed in the CSP by hash
CSP_HASH = "sha256-" + base64.b64encode(hashlib.sha256(JS_SNIPPET.encode()).digest()).decode()
CSP = ("default-src 'self'; script-src 'self' '%s'; style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
       "font-src https://fonts.gstatic.com https://cdnjs.cloudflare.com; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'self'; base-uri 'self'" % CSP_HASH)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nexacare")
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
if TRUSTED_PROXIES:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=TRUSTED_PROXIES, x_proto=TRUSTED_PROXIES, x_host=TRUSTED_PROXIES)

def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    new = not DB.exists()
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS enquiries(id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, kind TEXT NOT NULL,
                 name TEXT, phone TEXT, email TEXT, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new')""")
    c.execute("CREATE TABLE IF NOT EXISTS hits(client TEXT NOT NULL, ts REAL NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS hits_client ON hits(client, ts)")
    if new:
        try: os.chmod(DB, 0o600)
        except OSError: pass
    return c

def err(msg, code): return jsonify(ok=False, error=msg), code
def client_id(): return hashlib.sha256((SALT + (request.remote_addr or "?")).encode()).hexdigest()[:32]
def origin_ok():
    o = request.headers.get("Origin")
    if not o: return False                       # browsers always send Origin on cross-site and fetch() POSTs
    return o in ALLOWED_ORIGINS or o.split("://", 1)[-1] == request.host

@app.post("/api/enquiry")
def enquiry():
    if not origin_ok(): log.warning("blocked: origin"); return err("Request blocked.", 403)
    if not request.is_json: return err("Unsupported request.", 415)
    d = request.get_json(silent=True)
    if not isinstance(d, dict): return err("Invalid request.", 400)
    if d.get("website"): log.info("blocked: honeypot"); return err("Request blocked.", 400)
    kind = d.get("kind")
    if kind not in KINDS: return err("Invalid request.", 400)
    if d.get("consent") is not True: return err("Please tick the consent box.", 400)
    clean = {k: str(d[k]).strip()[:n] for k, n in FIELDS.items() if d.get(k) not in (None, "")}
    name = clean.get("name") or clean.get("requester_name")
    if not name: return err("Please enter your name.", 400)
    if kind != "contact" and not clean.get("phone"): return err("Please enter a telephone number.", 400)
    if not clean.get("phone") and not clean.get("email"): return err("Please give a phone number or an email address.", 400)
    if clean.get("phone") and not PHONE_RE.match(clean["phone"]): return err("Please enter a valid telephone number.", 400)
    if clean.get("email") and not EMAIL_RE.match(clean["email"]): return err("Please enter a valid email address.", 400)
    if clean.get("date") and not DATE_RE.match(clean["date"]): return err("Please enter a valid date.", 400)
    ref, now, cid = "NC-" + secrets.token_hex(4).upper(), time.time(), client_id()
    with db() as c:
        c.execute("DELETE FROM hits WHERE ts < ?", (now - RATE_WINDOW,))
        if c.execute("SELECT COUNT(*) FROM hits WHERE client=?", (cid,)).fetchone()[0] >= RATE_MAX:
            log.warning("blocked: rate limit"); return err("Too many requests. Please try again later or call us.", 429)
        c.execute("INSERT INTO hits(client, ts) VALUES(?,?)", (cid, now))
        c.execute("INSERT INTO enquiries(reference,created_at,kind,name,phone,email,payload) VALUES(?,?,?,?,?,?,?)",
                  (ref, datetime.now(timezone.utc).isoformat(timespec="seconds"), kind, name, clean.get("phone"), clean.get("email"), json.dumps(clean)))
    log.info("stored enquiry %s (%s)", ref, kind)   # never log names, phone numbers or message text
    return jsonify(ok=True, reference=ref), 201

PRIVATE = {"python", "data", "README.md", ".gitignore", ".git"}
@app.get("/", defaults={"p": "index.html"})
@app.get("/<path:p>")
def static_site(p):
    if p.split("/")[0] in PRIVATE: return not_found(None)
    if (ROOT / p).is_dir(): p = p.rstrip("/") + "/index.html"
    return send_from_directory(ROOT, p) if (ROOT / p).is_file() else not_found(None)

@app.errorhandler(404)
def not_found(_): return send_from_directory(ROOT, "404.html"), 404
@app.errorhandler(413)
def too_big(_): return err("Request too large.", 413)
@app.errorhandler(500)
def server_error(e): log.exception("server error"); return err("Something went wrong. Please call us instead.", 500)

@app.after_request
def headers(r):
    r.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin", "X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": CSP})
    return r

def cli(args):
    if args[0] == "list":
        n = int(args[1]) if len(args) > 1 else 20
        with db() as c:
            for r in c.execute("SELECT reference, created_at, kind, name, phone, email, status FROM enquiries ORDER BY id DESC LIMIT ?", (n,)): print(" | ".join(str(x) for x in r))
    elif args[0] == "purge" and len(args) == 2:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(args[1]))).isoformat(timespec="seconds")
        with db() as c: print("Deleted", c.execute("DELETE FROM enquiries WHERE created_at < ?", (cutoff,)).rowcount, "enquiries older than", args[1], "days")
    else: print(__doc__)

if __name__ == "__main__":
    if len(sys.argv) > 1: cli(sys.argv[1:])
    else: app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
