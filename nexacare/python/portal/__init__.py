"""NexaCare secure platform (staff dashboard, patient and family portal, homecare management, clinical records, billing).
Enabled only when PORTAL_ENABLED=1, so the public website keeps working exactly as before. Private pages live under /staff and /portal,
are rendered from templates outside the static folders, and are never cacheable."""
import json, logging, os, secrets
from pathlib import Path
from cryptography.fernet import Fernet
from flask import Flask, g, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader
from . import db as dbm
from .db import Database, close_db, one
from .security import csrf_valid, load_session, pre_csrf

log = logging.getLogger("nexacare.portal")
INSTANCE = Path(__file__).resolve().parent.parent / "instance"
PUBLIC_POSTS = {"staff.login", "patient.login", "patient.register"}

def load_settings(environ=os.environ):
    prod = environ.get("PORTAL_ENV", "development") == "production"
    cfg = {"production": prod, "database_url": environ.get("DATABASE_URL"), "secret_key": environ.get("PORTAL_SECRET_KEY"),
           "data_keys": (environ.get("PORTAL_DATA_KEY") or "").split(","), "hash_salt": environ.get("PORTAL_HASH_SALT")}
    if prod:
        missing = [n for n, v in (("DATABASE_URL", cfg["database_url"]), ("PORTAL_SECRET_KEY", cfg["secret_key"]), ("PORTAL_DATA_KEY", environ.get("PORTAL_DATA_KEY")), ("PORTAL_HASH_SALT", cfg["hash_salt"])) if not v]
        if missing: raise RuntimeError("Production needs these environment variables: " + ", ".join(missing))
        return cfg
    if cfg["secret_key"] and cfg["hash_salt"] and environ.get("PORTAL_DATA_KEY"):
        cfg["database_url"] = cfg["database_url"] or "sqlite:///" + str(INSTANCE / "portal.db"); return cfg
    # Development convenience only: generate throw-away secrets in python/instance (never use for real patient data).
    INSTANCE.mkdir(parents=True, exist_ok=True); f = INSTANCE / "dev-secrets.json"
    dev = json.loads(f.read_text()) if f.exists() else {"secret_key": secrets.token_urlsafe(32), "data_key": Fernet.generate_key().decode(), "salt": secrets.token_urlsafe(16)}
    if not f.exists(): f.write_text(json.dumps(dev)); os.chmod(f, 0o600)
    cfg["secret_key"] = cfg["secret_key"] or dev["secret_key"]; cfg["hash_salt"] = cfg["hash_salt"] or dev["salt"]
    cfg["database_url"] = cfg["database_url"] or "sqlite:///" + str(INSTANCE / "portal.db")
    if not environ.get("PORTAL_DATA_KEY"): cfg["data_keys"] = [dev["data_key"]]
    log.warning("PORTAL_ENV is not 'production': using development secrets. Do not store real patient data.")
    return cfg

def create_portal(app, enquiry_db=None, environ=os.environ):
    cfg = load_settings(environ)
    app.config.update(PORTAL=cfg, PORTAL_DB=Database(cfg["database_url"]), ENQUIRY_DB=enquiry_db, SECRET_KEY=cfg["secret_key"],
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=cfg["production"], SESSION_COOKIE_NAME="nc_pre")
    app.teardown_appcontext(close_db)
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(str(Path(__file__).parent / "templates"))])

    @app.before_request
    def identify_and_protect():
        g.staff = g.account = g.sess = None
        path = request.path
        if path.startswith("/staff"):
            s = load_session("staff", request.cookies.get("nc_staff"))
            u = one("SELECT * FROM users WHERE id=?", (s["subject_id"],)) if s else None
            if s and u and u["active"]: g.staff, g.sess = u, s
        elif path.startswith("/portal"):
            s = load_session("patient", request.cookies.get("nc_portal"))
            a = one("SELECT * FROM portal_accounts WHERE id=?", (s["subject_id"],)) if s else None
            if s and a and a["status"] in ("active", "pending"): g.account, g.sess = a, s
        else:
            return
        if request.method == "POST":
            expected = pre_csrf() if request.endpoint in PUBLIC_POSTS else (g.sess or {}).get("csrf")
            if not csrf_valid(expected):
                from .audit import audit; audit("csrf.failed", detail={"path": path}, outcome="denied")
                dbm.conn().commit()
                return render_template("error.html", code=400, message="Your form expired or was not valid. Please go back, reload the page and try again."), 400

    @app.after_request
    def private_headers(resp):
        if request.path.startswith(("/staff", "/portal")):
            resp.headers["Cache-Control"] = "no-store"; resp.headers["Pragma"] = "no-cache"
            resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
            resp.headers["X-Frame-Options"] = "DENY"; resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.context_processor
    def template_globals():
        from .rbac import ROLE_LABELS, can
        tok = g.sess["csrf"] if getattr(g, "sess", None) else pre_csrf() if request.path.startswith(("/staff", "/portal")) else ""
        return {"csrf_token": tok, "can": can, "ROLE_LABELS": ROLE_LABELS, "staff": getattr(g, "staff", None), "account": getattr(g, "account", None)}

    @app.errorhandler(403)
    def forbidden(_):
        if request.path.startswith(("/staff", "/portal")): return render_template("error.html", code=403, message="You do not have permission to open this page."), 403
        return "Forbidden", 403

    from . import staff, homecare, clinical, billing, patient_portal  # noqa: F401  (register routes)
    app.register_blueprint(staff.bp, url_prefix="/staff")
    app.register_blueprint(patient_portal.bp, url_prefix="/portal")
    return app
