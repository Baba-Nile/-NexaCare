"""Staff dashboard: login, accounts, audit log, patients, portal registrations, appointments, enquiries."""
import secrets, sqlite3
from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, url_for, current_app
from . import security as sec
from .audit import audit, verify_chain
from .db import insert, many, now, one, run
from .helpers import EMAIL_RE, PHONE_RE, clear_cookie, field, get_or_404, safe_next, set_login_cookie, valid_date, valid_dt
from .rbac import ASSIGNABLE, ROLE_LABELS, ROLE_PERMS, can, staff_required

bp = Blueprint("staff", __name__)

def temp_password(): return secrets.token_urlsafe(12) + "9a"

# ---------- authentication
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email, pw = field("email", 190).lower(), request.form.get("password", "")[:200]
        if sec.is_locked("staff", email):
            audit("auth.locked", detail={"realm": "staff"}, outcome="denied", actor=None)
            flash("Too many failed attempts. Please wait 15 minutes and try again.", "error")
            return render_template("login.html", realm="staff"), 429
        user = one("SELECT * FROM users WHERE email=?", (email,))
        ok = sec.verify_password(user["password_hash"] if user else None, pw) and bool(user and user["active"])
        sec.record_attempt("staff", email, ok)
        if ok:
            token = sec.create_session("staff", user["id"])
            run("UPDATE users SET last_login_at=? WHERE id=?", (now(), user["id"]))
            audit("auth.login", target=("user", user["id"]), actor=("staff", user["id"]))
            resp = redirect(safe_next(request.args.get("next")))
            return set_login_cookie(resp, "nc_staff", token, "/staff")
        audit("auth.failed", detail={"realm": "staff"}, outcome="denied", actor=None)
        flash("The email or password is not correct.", "error")      # same message whether or not the account exists
        return render_template("login.html", realm="staff"), 401
    return render_template("login.html", realm="staff")

@bp.post("/logout")
def logout():
    if g.staff: audit("auth.logout", target=("user", g.staff["id"]))
    sec.end_session(request.cookies.get("nc_staff"))
    return clear_cookie(redirect(url_for("staff.login")), "nc_staff", "/staff")

@bp.route("/password", methods=["GET", "POST"])
@staff_required()
def password():
    if request.method == "POST":
        cur, new, again = request.form.get("current", ""), request.form.get("new", ""), request.form.get("again", "")
        problems = sec.password_problems(new, g.staff["email"], g.staff["full_name"])
        if not sec.verify_password(g.staff["password_hash"], cur): problems.insert(0, "The current password is not correct.")
        if new != again: problems.append("The two new passwords do not match.")
        if new == cur: problems.append("Choose a password different from the current one.")
        if problems:
            for p in problems: flash(p, "error")
            return render_template("password.html"), 400
        run("UPDATE users SET password_hash=?, must_change_password=0, password_changed_at=? WHERE id=?", (sec.hash_password(new), now(), g.staff["id"]))
        sec.end_all_sessions("staff", g.staff["id"])
        token = sec.create_session("staff", g.staff["id"])
        audit("auth.password_changed", target=("user", g.staff["id"]))
        resp = redirect(url_for("staff.dashboard")); flash("Password changed.", "ok")
        return set_login_cookie(resp, "nc_staff", token, "/staff")
    return render_template("password.html")

# ---------- dashboard
@bp.get("/")
@staff_required()
def dashboard():
    c = {}
    if can("patients.read"): c["patients"] = one("SELECT COUNT(*) n FROM patients")["n"]
    if can("appointments.manage"): c["appointments"] = one("SELECT COUNT(*) n FROM appointments WHERE status='requested'")["n"]
    if can("portal.manage"): c["registrations"] = one("SELECT COUNT(*) n FROM portal_accounts WHERE status='pending'")["n"]
    if can("visits.manage"): c["visits"] = one("SELECT COUNT(*) n FROM homecare_visits WHERE status IN ('scheduled','assigned')")["n"]
    if can("billing.read"): c["unpaid"] = one("SELECT COUNT(*) n FROM invoices WHERE status IN ('issued','part_paid')")["n"]
    if can("visits.own"): c["mine"] = one("SELECT COUNT(*) n FROM visit_assignments WHERE caregiver_id=? AND status IN ('offered','accepted')", (g.staff["id"],))["n"]
    return render_template("dashboard.html", counts=c)

# ---------- staff accounts
def manageable(target_role): return target_role in ASSIGNABLE.get(g.staff["role"], set())

@bp.get("/users")
@staff_required("staff.manage")
def users():
    return render_template("users.html", users=many("SELECT id, email, full_name, role, active, last_login_at FROM users ORDER BY full_name"), assignable=sorted(ASSIGNABLE[g.staff["role"]]))

@bp.post("/users/new")
@staff_required("staff.manage")
def user_new():
    email, name, role = field("email", 190).lower(), field("full_name", 120), field("role", 40)
    if not EMAIL_RE.match(email) or not name or role not in ROLE_PERMS: flash("Enter a valid email, a name and a role.", "error"); return redirect(url_for("staff.users"))
    if not manageable(role): audit("access.denied", detail={"action": "create_role", "role": role}, outcome="denied"); abort(403)
    if one("SELECT id FROM users WHERE email=?", (email,)): flash("An account with that email already exists.", "error"); return redirect(url_for("staff.users"))
    tmp = temp_password()
    uid = insert("INSERT INTO users (email, full_name, role, password_hash, must_change_password, active, created_at) VALUES (?,?,?,?,1,1,?)", (email, name, role, sec.hash_password(tmp), now()))
    audit("user.created", target=("user", uid), detail={"role": role})
    return render_template("temp_password.html", who=name, email=email, password=tmp)

@bp.post("/users/<int:uid>/<action>")
@staff_required("staff.manage")
def user_action(uid, action):
    u = get_or_404("users", uid)
    if u["id"] == g.staff["id"]: flash("You cannot change your own account here.", "error"); return redirect(url_for("staff.users"))
    if not manageable(u["role"]): audit("access.denied", target=("user", uid), detail={"action": action}, outcome="denied"); abort(403)
    if action == "deactivate":
        if u["role"] == "system_admin" and one("SELECT COUNT(*) n FROM users WHERE role='system_admin' AND active=1")["n"] <= 1: flash("At least one active system administrator is required.", "error"); return redirect(url_for("staff.users"))
        run("UPDATE users SET active=0 WHERE id=?", (uid,)); sec.end_all_sessions("staff", uid)
    elif action == "activate": run("UPDATE users SET active=1 WHERE id=?", (uid,))
    elif action == "role":
        role = field("role", 40)
        if role not in ROLE_PERMS or not manageable(role): abort(403)
        run("UPDATE users SET role=? WHERE id=?", (role, uid)); sec.end_all_sessions("staff", uid)
    elif action == "reset":
        tmp = temp_password()
        run("UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?", (sec.hash_password(tmp), uid)); sec.end_all_sessions("staff", uid)
        audit("user.password_reset", target=("user", uid))
        return render_template("temp_password.html", who=u["full_name"], email=u["email"], password=tmp)
    else: abort(404)
    audit(f"user.{action}", target=("user", uid)); flash("Done.", "ok"); return redirect(url_for("staff.users"))

# ---------- audit
@bp.get("/audit")
@staff_required("audit.read")
def audit_log():
    q, args = "SELECT * FROM audit_events", []
    act = field("action", 60)
    if act: q += " WHERE action LIKE ?"; args.append(act + "%")
    rows = many(q + " ORDER BY id DESC LIMIT 200", args)
    audit("audit.viewed")
    return render_template("audit.html", rows=rows, action=act, chain=verify_chain())

# ---------- patients (demographics only; clinical data is a separate permission)
@bp.get("/patients")
@staff_required("patients.read")
def patients():
    q = field("q", 80)
    rows = many("SELECT id, full_name, date_of_birth, phone, area FROM patients WHERE full_name LIKE ? ORDER BY full_name LIMIT 100", (f"%{q}%",)) if q else many("SELECT id, full_name, date_of_birth, phone, area FROM patients ORDER BY id DESC LIMIT 50")
    audit("patient.search", detail={"has_query": bool(q)})
    return render_template("patients.html", rows=rows, q=q)

@bp.route("/patients/new", methods=["GET", "POST"])
@staff_required("patients.write")
def patient_new():
    if request.method == "POST":
        name, dob, phone, email, area, addr = field("full_name", 120), field("date_of_birth", 10), field("phone", 20), field("email", 190), field("area", 120), field("address", 300)
        errs = [m for ok, m in ((name, "Enter the patient's name."), (not dob or valid_date(dob), "Enter the date of birth as YYYY-MM-DD."), (not phone or PHONE_RE.match(phone), "Enter a valid phone number."), (not email or EMAIL_RE.match(email), "Enter a valid email address.")) if not ok]
        if errs:
            for e in errs: flash(e, "error")
            return render_template("patient_form.html"), 400
        pid = insert("INSERT INTO patients (full_name, date_of_birth, phone, email, area, address_enc, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)", (name, dob or None, phone or None, email or None, area or None, sec.encrypt(addr) if addr else None, g.staff["id"], now()))
        audit("patient.created", target=("patient", pid)); return redirect(url_for("staff.patient", pid=pid))
    return render_template("patient_form.html")

@bp.get("/patients/<int:pid>")
@staff_required("patients.read")
def patient(pid):
    p = get_or_404("patients", pid); audit("patient.viewed", target=("patient", pid))
    ctx = {"p": p, "address": sec.decrypt(p["address_enc"]) if can("patients.write") else None}
    ctx["appointments"] = many("SELECT * FROM appointments WHERE patient_id=? ORDER BY id DESC LIMIT 20", (pid,)) if (can("appointments.manage") or can("appointments.view")) else None
    ctx["plans"] = many("SELECT * FROM care_plans WHERE patient_id=? ORDER BY id DESC", (pid,)) if can("careplans.read") else None
    ctx["visits"] = many("SELECT * FROM homecare_visits WHERE patient_id=? ORDER BY scheduled_start DESC LIMIT 20", (pid,)) if can("visits.manage") else None
    ctx["invoices"] = many("SELECT * FROM invoices WHERE patient_id=? ORDER BY id DESC LIMIT 20", (pid,)) if can("billing.read") else None
    ctx["grants"] = many("SELECT g.*, a.email, a.full_name AS account_name FROM patient_access g JOIN portal_accounts a ON a.id=g.account_id WHERE g.patient_id=? ORDER BY g.id", (pid,)) if can("portal.manage") else None
    return render_template("patient.html", **ctx)

# ---------- patient and family portal: registrations and access grants
@bp.get("/portal-accounts")
@staff_required("portal.manage")
def portal_accounts():
    return render_template("accounts.html", rows=many("SELECT id, email, full_name, phone, status, created_at FROM portal_accounts ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC LIMIT 200"))

@bp.post("/portal-accounts/<int:aid>/review")
@staff_required("portal.manage")
def portal_review(aid):
    a = get_or_404("portal_accounts", aid); decision = field("decision", 20)
    if decision == "approve":
        pid, note = field("patient_id", 12), field("verification", 300)
        if not note: flash("Record how identity was verified.", "error"); return redirect(url_for("staff.portal_accounts"))
        if pid:
            patient_ = get_or_404("patients", pid)
        else:
            pid = insert("INSERT INTO patients (full_name, phone, email, created_by, created_at) VALUES (?,?,?,?,?)", (a["full_name"], a["phone"], a["email"], g.staff["id"], now())); patient_ = {"id": pid}
        run("UPDATE portal_accounts SET status='active', reviewed_by=?, reviewed_at=? WHERE id=?", (g.staff["id"], now(), aid))
        if not one("SELECT id FROM patient_access WHERE account_id=? AND patient_id=?", (aid, patient_["id"])):
            insert("INSERT INTO patient_access (account_id, patient_id, relationship, consent_note, status, granted_by, granted_at) VALUES (?,?,?,?, 'active', ?, ?)", (aid, patient_["id"], "self", note, g.staff["id"], now()))
        audit("portal.approved", target=("portal_account", aid), detail={"patient_id": patient_["id"]})
    elif decision in ("reject", "suspend", "reactivate"):
        status = {"reject": "rejected", "suspend": "suspended", "reactivate": "active"}[decision]
        run("UPDATE portal_accounts SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?", (status, g.staff["id"], now(), aid))
        if status != "active": sec.end_all_sessions("patient", aid)
        audit(f"portal.{decision}", target=("portal_account", aid))
    elif decision == "reset":
        tmp = temp_password()
        run("UPDATE portal_accounts SET password_hash=?, must_change_password=1 WHERE id=?", (sec.hash_password(tmp), aid)); sec.end_all_sessions("patient", aid)
        audit("portal.password_reset", target=("portal_account", aid))
        return render_template("temp_password.html", who=a["full_name"], email=a["email"], password=tmp)
    else: abort(400)
    flash("Done.", "ok"); return redirect(url_for("staff.portal_accounts"))

@bp.post("/patients/<int:pid>/grants")
@staff_required("portal.manage")
def grant_add(pid):
    get_or_404("patients", pid)
    acct = one("SELECT * FROM portal_accounts WHERE email=? AND status='active'", (field("email", 190).lower(),))
    rel, note = field("relationship", 60), field("consent_note", 300)
    if not acct or not rel or not note: flash("Needs an active portal account email, the relationship and a note of who consented and how.", "error"); return redirect(url_for("staff.patient", pid=pid))
    if one("SELECT id FROM patient_access WHERE account_id=? AND patient_id=?", (acct["id"], pid)): run("UPDATE patient_access SET status='active', relationship=?, consent_note=?, granted_by=?, granted_at=? WHERE account_id=? AND patient_id=?", (rel, note, g.staff["id"], now(), acct["id"], pid))
    else: insert("INSERT INTO patient_access (account_id, patient_id, relationship, consent_note, status, granted_by, granted_at) VALUES (?,?,?,?, 'active', ?, ?)", (acct["id"], pid, rel, note, g.staff["id"], now()))
    audit("access.granted", target=("patient", pid), detail={"account_id": acct["id"], "relationship": rel}); flash("Access granted.", "ok"); return redirect(url_for("staff.patient", pid=pid))

@bp.post("/patients/<int:pid>/grants/<int:gid>/revoke")
@staff_required("portal.manage")
def grant_revoke(pid, gid):
    g_ = get_or_404("patient_access", gid)
    if g_["patient_id"] != pid: abort(404)
    run("UPDATE patient_access SET status='revoked' WHERE id=?", (gid,)); audit("access.revoked", target=("patient", pid), detail={"account_id": g_["account_id"]})
    flash("Access revoked.", "ok"); return redirect(url_for("staff.patient", pid=pid))

# ---------- appointments
@bp.get("/appointments")
@staff_required()
def appointments():
    if not (can("appointments.manage") or can("appointments.view")): audit("access.denied", detail={"path": request.path}, outcome="denied"); abort(403)
    rows = many("SELECT a.*, p.full_name FROM appointments a JOIN patients p ON p.id=a.patient_id ORDER BY CASE a.status WHEN 'requested' THEN 0 ELSE 1 END, a.id DESC LIMIT 200")
    audit("appointments.viewed")
    return render_template("appointments.html", rows=rows)

@bp.post("/appointments/<int:aid>")
@staff_required("appointments.manage")
def appointment_update(aid):
    a = get_or_404("appointments", aid); decision = field("decision", 20); note = field("staff_note", 300)
    if decision == "confirm":
        when = field("scheduled_at", 16)
        if not valid_dt(when): flash("Enter the confirmed date and time.", "error"); return redirect(url_for("staff.appointments"))
        run("UPDATE appointments SET status='confirmed', scheduled_at=?, staff_note=?, updated_at=?, updated_by=? WHERE id=?", (when, note, now(), g.staff["id"], aid))
    elif decision in ("decline", "cancel", "complete"):
        run("UPDATE appointments SET status=?, staff_note=?, updated_at=?, updated_by=? WHERE id=?", ({"decline": "declined", "cancel": "cancelled", "complete": "completed"}[decision], note, now(), g.staff["id"], aid))
    else: abort(400)
    audit(f"appointment.{decision}", target=("appointment", aid)); flash("Updated.", "ok"); return redirect(url_for("staff.appointments"))

@bp.post("/patients/<int:pid>/appointments")
@staff_required("appointments.manage")
def appointment_create(pid):
    get_or_404("patients", pid); svc, when = field("service", 60), field("scheduled_at", 16)
    if not svc or not valid_dt(when): flash("Enter the service and a valid date and time.", "error"); return redirect(url_for("staff.patient", pid=pid))
    aid = insert("INSERT INTO appointments (patient_id, requested_by_user, service, status, scheduled_at, created_at, updated_at, updated_by) VALUES (?,?,?, 'confirmed', ?, ?, ?, ?)", (pid, g.staff["id"], svc, when, now(), now(), g.staff["id"]))
    audit("appointment.created", target=("appointment", aid)); return redirect(url_for("staff.patient", pid=pid))

# ---------- public website enquiries (separate database, read-only here)
@bp.get("/enquiries")
@staff_required("enquiries.read")
def enquiries():
    import branches as BM, enquiry_store
    path, rows, counts = current_app.config.get("ENQUIRY_DB"), [], {}
    names = BM.names(); names[enquiry_store.UNSPECIFIED] = "Not specified"
    want = request.args.get("branch", "").strip()
    if want and want not in names: want = ""                      # ignore unknown filter values
    if path and path.exists():
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try: rows, counts = enquiry_store.rows(c, 100, want or None), enquiry_store.branch_counts(c)
        finally: c.close()
    audit("enquiries.viewed", detail={"branch_filter": want or "all"})
    options = [(s, names[s], counts.get(s, 0)) for s in list(names) if s != BM.NO_PREFERENCE] + [(BM.NO_PREFERENCE, names[BM.NO_PREFERENCE], counts.get(BM.NO_PREFERENCE, 0))]
    return render_template("enquiries.html", rows=rows, options=options, want=want, total=sum(counts.values()))
