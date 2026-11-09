"""Patient and family portal. Accounts are created by self-registration but stay 'pending' until staff verify identity and link the account to a
patient record. Every query is scoped to the patients this account holds an active access grant for. Clinical notes are never shown here."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from . import security as sec
from .audit import audit
from .db import insert, many, now, one, run
from .helpers import EMAIL_RE, PHONE_RE, clear_cookie, field, fmt_money, set_login_cookie, valid_date
from .rbac import account_required

bp = Blueprint("patient", __name__)
SERVICES = ["Outpatient consultation", "Maternal and child health", "Family planning", "Laboratory", "Physiotherapy", "Counselling", "Telemedicine", "Homecare assessment", "Other"]

@bp.before_request
def force_password_change():
    if g.account and g.account["must_change_password"] and request.endpoint not in ("patient.password", "patient.logout"): return redirect(url_for("patient.password"))

def granted_ids():
    if not g.account or g.account["status"] != "active": return []
    return [r["patient_id"] for r in many("SELECT patient_id FROM patient_access WHERE account_id=? AND status='active'", (g.account["id"],))]

def marks(ids): return ",".join("?" * len(ids))

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if sec.is_locked("register", sec.client_ip()): return render_template("p_register.html", done=False), 429
        sec.record_attempt("register", sec.client_ip(), False)       # counts every submission from this address
        name, email, phone, pw, again = field("full_name", 120), field("email", 190).lower(), field("phone", 20), request.form.get("password", "")[:200], request.form.get("again", "")[:200]
        errs = [m for ok, m in ((name, "Enter your name."), (EMAIL_RE.match(email), "Enter a valid email address."), (not phone or PHONE_RE.match(phone), "Enter a valid phone number."),
                                (request.form.get("consent") == "on", "Please confirm the consent statement."), (pw == again, "The two passwords do not match.")) if not ok]
        errs += sec.password_problems(pw, email, name)
        if errs:
            for e in errs: flash(e, "error")
            return render_template("p_register.html", done=False), 400
        if not one("SELECT id FROM portal_accounts WHERE email=?", (email,)):
            aid = insert("INSERT INTO portal_accounts (email, full_name, phone, password_hash, status, consent_at, created_at) VALUES (?,?,?,?, 'pending', ?, ?)", (email, name, phone or None, sec.hash_password(pw), now(), now()))
            audit("portal.registered", target=("portal_account", aid), actor=("patient", aid))
        return render_template("p_register.html", done=True)          # identical response whether or not the email already existed
    return render_template("p_register.html", done=False)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, pw = field("email", 190).lower(), request.form.get("password", "")[:200]
        if sec.is_locked("patient", email): flash("Too many failed attempts. Please wait 15 minutes and try again.", "error"); return render_template("login.html", realm="patient"), 429
        a = one("SELECT * FROM portal_accounts WHERE email=?", (email,))
        ok = sec.verify_password(a["password_hash"] if a else None, pw) and bool(a and a["status"] in ("active", "pending"))
        sec.record_attempt("patient", email, ok)
        if ok:
            token = sec.create_session("patient", a["id"]); run("UPDATE portal_accounts SET last_login_at=? WHERE id=?", (now(), a["id"])); audit("auth.login", target=("portal_account", a["id"]), actor=("patient", a["id"]))
            return set_login_cookie(redirect(url_for("patient.home")), "nc_portal", token, "/portal")
        audit("auth.failed", detail={"realm": "patient"}, outcome="denied", actor=None)
        flash("The email or password is not correct.", "error"); return render_template("login.html", realm="patient"), 401
    return render_template("login.html", realm="patient")

@bp.post("/logout")
def logout():
    if g.account: audit("auth.logout", target=("portal_account", g.account["id"]))
    sec.end_session(request.cookies.get("nc_portal"))
    return clear_cookie(redirect(url_for("patient.login")), "nc_portal", "/portal")

@bp.route("/password", methods=["GET", "POST"])
@account_required
def password():
    if request.method == "POST":
        cur, new, again = request.form.get("current", ""), request.form.get("new", ""), request.form.get("again", "")
        errs = sec.password_problems(new, g.account["email"], g.account["full_name"])
        if not sec.verify_password(g.account["password_hash"], cur): errs.insert(0, "The current password is not correct.")
        if new != again: errs.append("The two new passwords do not match.")
        if errs:
            for e in errs: flash(e, "error")
            return render_template("password.html"), 400
        run("UPDATE portal_accounts SET password_hash=?, must_change_password=0 WHERE id=?", (sec.hash_password(new), g.account["id"]))
        sec.end_all_sessions("patient", g.account["id"]); token = sec.create_session("patient", g.account["id"]); audit("auth.password_changed", target=("portal_account", g.account["id"]))
        return set_login_cookie(redirect(url_for("patient.home")), "nc_portal", token, "/portal")
    return render_template("password.html")

@bp.get("/")
@account_required
def home():
    ids = granted_ids(); people = many(f"SELECT id, full_name FROM patients WHERE id IN ({marks(ids)})", ids) if ids else []
    return render_template("p_home.html", people=people)

@bp.route("/appointments", methods=["GET", "POST"])
@account_required
def appointments():
    ids = granted_ids()
    if request.method == "POST":
        pid, svc, d, t, reason = field("patient_id", 12), field("service", 60), field("preferred_date", 10), field("preferred_time", 20), field("reason", 300)
        if not (pid.isdigit() and int(pid) in ids): audit("access.denied", detail={"path": request.path, "reason": "no grant"}, outcome="denied"); return render_template("error.html", code=403, message="You do not have permission to request an appointment for that person."), 403
        if svc not in SERVICES or (d and not valid_date(d)): flash("Choose a service and a valid date.", "error")
        else:
            aid = insert("INSERT INTO appointments (patient_id, requested_by_account, service, preferred_date, preferred_time, reason, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)", (int(pid), g.account["id"], svc, d or None, t or None, reason or None, now(), now()))
            audit("appointment.requested", target=("appointment", aid)); flash("Your request was sent. It is not confirmed until the team confirms it.", "ok"); return redirect(url_for("patient.appointments"))
    people = many(f"SELECT id, full_name FROM patients WHERE id IN ({marks(ids)})", ids) if ids else []
    rows = many(f"SELECT a.id, a.service, a.preferred_date, a.status, a.scheduled_at, a.staff_note, p.full_name FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE a.patient_id IN ({marks(ids)}) ORDER BY a.id DESC", ids) if ids else []
    return render_template("p_appointments.html", people=people, rows=rows, services=SERVICES)

@bp.get("/care-plan")
@account_required
def care_plan():
    ids = granted_ids(); plans = []
    if ids:
        for p in many(f"SELECT c.*, pt.full_name FROM care_plans c JOIN patients pt ON pt.id=c.patient_id WHERE c.published=1 AND c.patient_id IN ({marks(ids)}) ORDER BY c.id DESC", ids):
            p["tasks"] = many("SELECT description, frequency FROM care_plan_tasks WHERE care_plan_id=? AND active=1 ORDER BY id", (p["id"],)); plans.append(p)
    audit("portal.careplan_viewed"); return render_template("p_careplan.html", plans=plans)

@bp.get("/visits")
@account_required
def my_records():
    ids = granted_ids()
    rows = many(f"SELECT e.encounter_type, e.occurred_at, p.full_name FROM clinical_encounters e JOIN patients p ON p.id=e.patient_id WHERE e.released_to_patient=1 AND e.patient_id IN ({marks(ids)}) ORDER BY e.occurred_at DESC", ids) if ids else []
    audit("portal.records_viewed"); return render_template("p_records.html", rows=rows)

@bp.get("/invoices")
@account_required
def invoices():
    ids = granted_ids(); rows = []
    if ids:
        for i in many(f"SELECT i.*, p.full_name FROM invoices i JOIN patients p ON p.id=i.patient_id WHERE i.status<>'void' AND i.patient_id IN ({marks(ids)}) ORDER BY i.id DESC", ids):
            i["paid"] = one("SELECT COALESCE(SUM(amount_minor),0) AS s FROM payments WHERE invoice_id=?", (i["id"],))["s"]; rows.append(i)
    audit("portal.invoices_viewed"); return render_template("p_invoices.html", rows=rows, money=fmt_money)
