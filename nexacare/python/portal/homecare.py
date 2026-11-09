"""Homecare management: care plans and tasks, assessments, visit scheduling, caregiver assignment, visit status and documentation.
Caregivers can only open visits assigned to them and never see clinical records."""
from flask import abort, flash, g, redirect, render_template, request, url_for
from . import security as sec
from .audit import audit
from .db import insert, many, now, one, run
from .helpers import field, get_or_404, valid_dt
from .rbac import can, staff_required
from .staff import bp

VISIT_TYPES = ["Elderly care and daily living", "Nursing visit", "Post-discharge recovery", "Mobility and physiotherapy", "Medication support", "Mother and baby visit", "Assessment visit"]
CARER_ROLES = ("caregiver", "nurse")

# ---------- care plans, tasks, assessments
@bp.post("/patients/<int:pid>/careplans")
@staff_required("careplans.write")
def careplan_new(pid):
    get_or_404("patients", pid); title = field("title", 120)
    if not title: flash("Enter a title.", "error"); return redirect(url_for("staff.patient", pid=pid))
    cid = insert("INSERT INTO care_plans (patient_id, title, created_by, created_at, updated_at) VALUES (?,?,?,?,?)", (pid, title, g.staff["id"], now(), now()))
    audit("careplan.created", target=("care_plan", cid), detail={"patient_id": pid}); return redirect(url_for("staff.careplan", cid=cid))

@bp.get("/careplans/<int:cid>")
@staff_required("careplans.read")
def careplan(cid):
    plan = get_or_404("care_plans", cid); audit("careplan.viewed", target=("care_plan", cid))
    return render_template("careplan.html", plan=plan, p=get_or_404("patients", plan["patient_id"]), tasks=many("SELECT * FROM care_plan_tasks WHERE care_plan_id=? ORDER BY id", (cid,)))

@bp.post("/careplans/<int:cid>/tasks")
@staff_required("careplans.write")
def careplan_task(cid):
    plan = get_or_404("care_plans", cid); desc = field("description", 300)
    if not desc: flash("Enter the task.", "error"); return redirect(url_for("staff.careplan", cid=cid))
    tid = insert("INSERT INTO care_plan_tasks (care_plan_id, description, frequency, created_by, created_at) VALUES (?,?,?,?,?)", (cid, desc, field("frequency", 80) or None, g.staff["id"], now()))
    run("UPDATE care_plans SET version=version+1, updated_at=? WHERE id=?", (now(), cid)); audit("careplan.task_added", target=("care_plan", cid), detail={"task_id": tid})
    return redirect(url_for("staff.careplan", cid=cid))

@bp.post("/careplans/<int:cid>/publish")
@staff_required("careplans.write")
def careplan_publish(cid):
    plan = get_or_404("care_plans", cid); pub = 0 if plan["published"] else 1
    run("UPDATE care_plans SET published=?, status=?, updated_at=? WHERE id=?", (pub, "active" if pub else "draft", now(), cid))
    audit("careplan.published" if pub else "careplan.unpublished", target=("care_plan", cid)); return redirect(url_for("staff.careplan", cid=cid))

@bp.route("/patients/<int:pid>/assessments", methods=["GET", "POST"])
@staff_required("careplans.read")
def assessments(pid):
    p = get_or_404("patients", pid)
    if request.method == "POST":
        if not can("careplans.write"): audit("access.denied", detail={"path": request.path}, outcome="denied"); abort(403)
        summ, rec = field("summary", 2000), field("recommendation", 2000)
        if not summ: flash("Enter the assessment summary.", "error"); return redirect(url_for("staff.assessments", pid=pid))
        aid = insert("INSERT INTO care_assessments (patient_id, assessed_by, assessed_at, summary_enc, recommendation_enc, created_at) VALUES (?,?,?,?,?,?)", (pid, g.staff["id"], now(), sec.encrypt(summ), sec.encrypt(rec) if rec else None, now()))
        audit("assessment.created", target=("care_assessment", aid), detail={"patient_id": pid}); return redirect(url_for("staff.assessments", pid=pid))
    rows = [dict(r, summary=sec.decrypt(r["summary_enc"]), recommendation=sec.decrypt(r["recommendation_enc"])) for r in many("SELECT * FROM care_assessments WHERE patient_id=? ORDER BY id DESC", (pid,))]
    audit("assessment.viewed", target=("patient", pid)); return render_template("assessments.html", p=p, rows=rows)

# ---------- scheduling (coordinators)
@bp.get("/homecare")
@staff_required("visits.manage")
def visits():
    status = field("status", 20); q, a = "SELECT v.*, p.full_name FROM homecare_visits v JOIN patients p ON p.id=v.patient_id", []
    if status: q += " WHERE v.status=?"; a.append(status)
    rows = many(q + " ORDER BY v.scheduled_start DESC LIMIT 200", a)
    for r in rows: r["carer"] = (one("SELECT u.full_name FROM visit_assignments x JOIN users u ON u.id=x.caregiver_id WHERE x.visit_id=? AND x.status IN ('offered','accepted') ORDER BY x.id DESC", (r["id"],)) or {}).get("full_name")
    audit("visits.listed"); return render_template("visits.html", rows=rows, status=status)

@bp.route("/homecare/new", methods=["GET", "POST"])
@staff_required("visits.manage")
def visit_new():
    if request.method == "POST":
        pid, vt, s, e = field("patient_id", 12), field("visit_type", 80), field("start", 16), field("end", 16)
        errs = []
        if not pid.isdigit() or not one("SELECT id FROM patients WHERE id=?", (pid,)): errs.append("Choose a patient by number.")
        if vt not in VISIT_TYPES: errs.append("Choose a visit type.")
        if not (valid_dt(s) and valid_dt(e)) or e <= s: errs.append("Enter a valid start and a later end time.")
        plan = field("care_plan_id", 12)
        if plan and not (plan.isdigit() and one("SELECT id FROM care_plans WHERE id=? AND patient_id=?", (plan, pid))): errs.append("That care plan does not belong to this patient.")
        if errs:
            for m in errs: flash(m, "error")
            return render_template("visit_new.html", types=VISIT_TYPES), 400
        addr = field("address", 300)
        vid = insert("INSERT INTO homecare_visits (patient_id, care_plan_id, visit_type, scheduled_start, scheduled_end, location_area, address_enc, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (int(pid), int(plan) if plan else None, vt, s, e, field("area", 120) or None, sec.encrypt(addr) if addr else None, g.staff["id"], now(), now()))
        audit("visit.created", target=("visit", vid), detail={"patient_id": int(pid)}); return redirect(url_for("staff.visit", vid=vid))
    return render_template("visit_new.html", types=VISIT_TYPES)

def conflict(caregiver_id, visit):
    return one("SELECT v.id FROM visit_assignments a JOIN homecare_visits v ON v.id=a.visit_id WHERE a.caregiver_id=? AND a.status IN ('offered','accepted') AND v.status NOT IN ('cancelled','completed','missed') AND v.id<>? AND v.scheduled_start<? AND v.scheduled_end>?",
               (caregiver_id, visit["id"], visit["scheduled_end"], visit["scheduled_start"]))

@bp.post("/homecare/<int:vid>/assign")
@staff_required("visits.manage")
def visit_assign(vid):
    v = get_or_404("homecare_visits", vid); cid = field("caregiver_id", 12)
    u = one("SELECT * FROM users WHERE id=? AND active=1", (cid,)) if cid.isdigit() else None
    if v["status"] not in ("scheduled", "assigned"): flash("This visit can no longer be assigned.", "error")
    elif not u or u["role"] not in CARER_ROLES: flash("Choose an active caregiver or nurse.", "error")
    elif conflict(u["id"], v): flash("That person already has an overlapping visit.", "error")
    else:
        run("UPDATE visit_assignments SET status='cancelled', responded_at=? WHERE visit_id=? AND status IN ('offered','accepted')", (now(), vid))
        insert("INSERT INTO visit_assignments (visit_id, caregiver_id, assigned_by, assigned_at) VALUES (?,?,?,?)", (vid, u["id"], g.staff["id"], now()))
        run("UPDATE homecare_visits SET status='assigned', updated_at=? WHERE id=?", (now(), vid)); audit("visit.assigned", target=("visit", vid), detail={"caregiver_id": u["id"]}); flash("Assigned. The caregiver must accept.", "ok")
    return redirect(url_for("staff.visit", vid=vid))

@bp.post("/homecare/<int:vid>/status")
@staff_required("visits.manage")
def visit_status(vid):
    v = get_or_404("homecare_visits", vid); to = field("to", 20)
    allowed = {"cancelled": ("scheduled", "assigned", "confirmed"), "missed": ("assigned", "confirmed")}
    if to not in allowed or v["status"] not in allowed[to]: flash("That status change is not allowed from the current status.", "error")
    else:
        run("UPDATE homecare_visits SET status=?, updated_at=? WHERE id=?", (to, now(), vid)); run("UPDATE visit_assignments SET status='cancelled', responded_at=? WHERE visit_id=? AND status IN ('offered','accepted')", (now(), vid))
        audit(f"visit.{to}", target=("visit", vid))
    return redirect(url_for("staff.visit", vid=vid))

# ---------- caregivers
def my_assignment(vid):
    return one("SELECT * FROM visit_assignments WHERE visit_id=? AND caregiver_id=? AND status IN ('offered','accepted') ORDER BY id DESC", (vid, g.staff["id"]))

@bp.get("/my-visits")
@staff_required("visits.own")
def my_visits():
    rows = many("SELECT v.id, v.visit_type, v.scheduled_start, v.scheduled_end, v.location_area, v.status, a.status AS assignment, p.full_name FROM visit_assignments a JOIN homecare_visits v ON v.id=a.visit_id JOIN patients p ON p.id=v.patient_id WHERE a.caregiver_id=? AND a.status IN ('offered','accepted') ORDER BY v.scheduled_start", (g.staff["id"],))
    audit("visits.mine_listed"); return render_template("my_visits.html", rows=rows)

@bp.get("/visits/<int:vid>")
@staff_required()
def visit(vid):
    v = get_or_404("homecare_visits", vid); mine = my_assignment(vid) if can("visits.own") else None
    if not (can("visits.manage") or mine):
        audit("access.denied", target=("visit", vid), detail={"reason": "not assigned"}, outcome="denied"); abort(403)
    p = get_or_404("patients", v["patient_id"]); audit("visit.viewed", target=("visit", vid))
    show_addr = bool(v["address_enc"]) and (can("visits.manage") or (mine and mine["status"] == "accepted"))
    tasks = many("SELECT * FROM care_plan_tasks WHERE care_plan_id=? AND active=1 ORDER BY id", (v["care_plan_id"],)) if v["care_plan_id"] else []
    rec = one("SELECT * FROM visit_records WHERE visit_id=?", (vid,))
    done = {r["task_id"]: r for r in many("SELECT * FROM visit_task_records WHERE visit_record_id=?", (rec["id"],))} if rec else {}
    carers = many("SELECT id, full_name, role FROM users WHERE active=1 AND role IN ('caregiver','nurse') ORDER BY full_name") if can("visits.manage") else []
    return render_template("visit.html", v=v, p=p, mine=mine, address=sec.decrypt(v["address_enc"]) if show_addr else None, tasks=tasks, rec=rec, report=sec.decrypt(rec["report_enc"]) if rec else None, done=done, carers=carers)

@bp.post("/visits/<int:vid>/<action>")
@staff_required("visits.own")
def visit_action(vid, action):
    v, a = get_or_404("homecare_visits", vid), my_assignment(vid)
    if not a: audit("access.denied", target=("visit", vid), detail={"reason": "not assigned", "action": action}, outcome="denied"); abort(403)
    if action == "accept" and a["status"] == "offered" and v["status"] == "assigned":
        run("UPDATE visit_assignments SET status='accepted', responded_at=? WHERE id=?", (now(), a["id"])); run("UPDATE homecare_visits SET status='confirmed', updated_at=? WHERE id=?", (now(), vid))
    elif action == "decline" and a["status"] == "offered":
        run("UPDATE visit_assignments SET status='declined', responded_at=? WHERE id=?", (now(), a["id"])); run("UPDATE homecare_visits SET status='scheduled', updated_at=? WHERE id=?", (now(), vid))
    elif action == "start" and a["status"] == "accepted" and v["status"] == "confirmed":
        run("UPDATE homecare_visits SET status='in_progress', updated_at=? WHERE id=?", (now(), vid))
        if not one("SELECT id FROM visit_records WHERE visit_id=?", (vid,)): insert("INSERT INTO visit_records (visit_id, started_at, documented_by, created_at) VALUES (?,?,?,?)", (vid, now(), g.staff["id"], now()))
    elif action == "complete" and a["status"] == "accepted" and v["status"] == "in_progress":
        report = field("report", 3000)
        if len(report) < 5: flash("Write a short visit report before completing.", "error"); return redirect(url_for("staff.visit", vid=vid))
        rec = one("SELECT * FROM visit_records WHERE visit_id=?", (vid,))
        run("UPDATE visit_records SET report_enc=?, completed_at=? WHERE id=?", (sec.encrypt(report), now(), rec["id"]))
        for t in many("SELECT id FROM care_plan_tasks WHERE care_plan_id=? AND active=1", (v["care_plan_id"],)) if v["care_plan_id"] else []:
            note = field(f"note_{t['id']}", 300)
            run("DELETE FROM visit_task_records WHERE visit_record_id=? AND task_id=?", (rec["id"], t["id"]))
            insert("INSERT INTO visit_task_records (visit_record_id, task_id, done, note_enc, recorded_at) VALUES (?,?,?,?,?)", (rec["id"], t["id"], 1 if request.form.get(f"task_{t['id']}") == "on" else 0, sec.encrypt(note) if note else None, now()))
        run("UPDATE homecare_visits SET status='completed', updated_at=? WHERE id=?", (now(), vid))
    else: flash("That action is not available for this visit right now.", "error"); return redirect(url_for("staff.visit", vid=vid))
    audit(f"visit.{action}", target=("visit", vid)); return redirect(url_for("staff.visit", vid=vid))
