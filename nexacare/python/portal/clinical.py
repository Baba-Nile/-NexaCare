"""Clinical records: structured encounters, observations, append-only clinical notes and medication orders.
Free text is encrypted at rest; every read and write is audited. Only doctors can order medication. Nothing here suggests or checks doses."""
import re
from flask import abort, flash, g, redirect, render_template, request, url_for
from . import security as sec
from .audit import audit
from .db import insert, many, now, one, run
from .helpers import field, get_or_404, valid_dt
from .rbac import staff_required
from .staff import bp

ENCOUNTER_TYPES = ["consultation", "follow_up", "homecare_clinical", "telemedicine"]
OBSERVATIONS = {"blood_pressure": ("mmHg", r"^\d{2,3}/\d{2,3}$"), "pulse": ("beats/min", r"^\d{2,3}$"), "temperature": ("°C", r"^\d{2}(\.\d)?$"),
                "respiratory_rate": ("breaths/min", r"^\d{1,2}$"), "oxygen_saturation": ("%", r"^\d{2,3}$"), "weight": ("kg", r"^\d{1,3}(\.\d{1,2})?$")}

@bp.get("/patients/<int:pid>/clinical")
@staff_required("clinical.read")
def clinical(pid):
    p = get_or_404("patients", pid); audit("clinical.opened", target=("patient", pid))
    return render_template("clinical.html", p=p, encounters=many("SELECT e.*, u.full_name AS clinician FROM clinical_encounters e JOIN users u ON u.id=e.clinician_id WHERE e.patient_id=? ORDER BY e.occurred_at DESC", (pid,)),
                           meds=[dict(m, instructions=sec.decrypt(m["instructions_enc"])) for m in many("SELECT * FROM medication_orders WHERE patient_id=? ORDER BY id DESC", (pid,))], types=ENCOUNTER_TYPES)

@bp.post("/patients/<int:pid>/encounters")
@staff_required("clinical.write")
def encounter_new(pid):
    get_or_404("patients", pid); t, when, reason = field("encounter_type", 30), field("occurred_at", 16), field("reason", 1000)
    if t not in ENCOUNTER_TYPES or not valid_dt(when): flash("Choose a type and enter a valid date and time.", "error"); return redirect(url_for("staff.clinical", pid=pid))
    eid = insert("INSERT INTO clinical_encounters (patient_id, clinician_id, encounter_type, occurred_at, reason_enc, created_at) VALUES (?,?,?,?,?,?)", (pid, g.staff["id"], t, when, sec.encrypt(reason) if reason else None, now()))
    audit("encounter.created", target=("encounter", eid), detail={"patient_id": pid}); return redirect(url_for("staff.encounter", eid=eid))

@bp.get("/encounters/<int:eid>")
@staff_required("clinical.read")
def encounter(eid):
    e = get_or_404("clinical_encounters", eid); audit("encounter.viewed", target=("encounter", eid), detail={"patient_id": e["patient_id"]})
    notes = [dict(n, body=sec.decrypt(n["body_enc"])) for n in many("SELECT n.*, u.full_name AS author FROM clinical_notes n JOIN users u ON u.id=n.author_id WHERE n.encounter_id=? ORDER BY n.id", (eid,))]
    return render_template("encounter.html", e=e, p=get_or_404("patients", e["patient_id"]), reason=sec.decrypt(e["reason_enc"]), notes=notes, obs=many("SELECT * FROM observations WHERE encounter_id=? ORDER BY id", (eid,)), kinds=OBSERVATIONS)

@bp.post("/encounters/<int:eid>/notes")
@staff_required("clinical.write")
def note_add(eid):
    e = get_or_404("clinical_encounters", eid); body = field("body", 4000)
    if len(body) < 3: flash("Write the note.", "error"); return redirect(url_for("staff.encounter", eid=eid))
    nid = insert("INSERT INTO clinical_notes (encounter_id, author_id, body_enc, created_at) VALUES (?,?,?,?)", (eid, g.staff["id"], sec.encrypt(body), now()))
    audit("note.created", target=("note", nid), detail={"encounter_id": eid}); return redirect(url_for("staff.encounter", eid=eid))   # notes are append-only: correct by adding a new note

@bp.post("/encounters/<int:eid>/observations")
@staff_required("clinical.write")
def observation_add(eid):
    get_or_404("clinical_encounters", eid); kind, value = field("kind", 30), field("value", 12)
    spec = OBSERVATIONS.get(kind)
    if not spec or not re.match(spec[1], value): flash("Choose a measurement and enter a value in the expected format.", "error"); return redirect(url_for("staff.encounter", eid=eid))
    oid = insert("INSERT INTO observations (encounter_id, recorded_by, kind, value, unit, recorded_at) VALUES (?,?,?,?,?,?)", (eid, g.staff["id"], kind, value, spec[0], now()))
    audit("observation.created", target=("observation", oid), detail={"encounter_id": eid, "kind": kind}); return redirect(url_for("staff.encounter", eid=eid))

@bp.post("/encounters/<int:eid>/release")
@staff_required("clinical.write")
def encounter_release(eid):
    e = get_or_404("clinical_encounters", eid); v = 0 if e["released_to_patient"] else 1
    run("UPDATE clinical_encounters SET released_to_patient=? WHERE id=?", (v, eid)); audit("encounter.released" if v else "encounter.unreleased", target=("encounter", eid)); return redirect(url_for("staff.encounter", eid=eid))

@bp.post("/patients/<int:pid>/medications")
@staff_required("meds.order")
def medication_add(pid):
    get_or_404("patients", pid); name, ins = field("medication_name", 120), field("instructions", 500)
    if not name or not ins: flash("Enter the medication and the prescriber's instructions.", "error"); return redirect(url_for("staff.clinical", pid=pid))
    mid = insert("INSERT INTO medication_orders (patient_id, ordered_by, medication_name, instructions_enc, ordered_at) VALUES (?,?,?,?,?)", (pid, g.staff["id"], name, sec.encrypt(ins), now()))
    audit("medication.ordered", target=("medication_order", mid), detail={"patient_id": pid}); return redirect(url_for("staff.clinical", pid=pid))

@bp.post("/medications/<int:mid>/stop")
@staff_required("meds.order")
def medication_stop(mid):
    m = get_or_404("medication_orders", mid)
    if m["status"] == "active": run("UPDATE medication_orders SET status='stopped', stopped_at=? WHERE id=?", (now(), mid)); audit("medication.stopped", target=("medication_order", mid))
    return redirect(url_for("staff.clinical", pid=m["patient_id"]))
