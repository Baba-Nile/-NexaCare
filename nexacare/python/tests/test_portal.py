"""Security and permission tests. Run:  python -m unittest discover -s python/tests -v   (from the project root)
Uses a throw-away SQLite database per test. PostgreSQL is not exercised here."""
import os, re, sqlite3, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from flask import Flask
from portal import create_portal, db as dbm, security as sec
from portal.audit import audit, verify_chain

CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')
PW = "Correct-horse-battery-9"

class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); self.enq = Path(self.dir) / "enquiries.db"
        env = {"PORTAL_ENV": "development", "DATABASE_URL": f"sqlite:///{self.dir}/portal.db", "PORTAL_SECRET_KEY": "test-secret", "PORTAL_HASH_SALT": "salt", "PORTAL_DATA_KEY": Fernet.generate_key().decode()}
        self.app = Flask(__name__, static_folder=None); self.app.config["TESTING"] = True
        create_portal(self.app, enquiry_db=self.enq, environ=env); self.app.config["PORTAL_DB"].migrate()
        @self.app.get("/data/site.json")
        def _x(): return "must not be reachable"            # stand-in: the real app blocks this path; see test_static_exposure
        self.c = self.app.test_client()

    # ---- fixtures
    def user(self, role, email=None, must=0, pw=PW, active=1):
        email = email or f"{role}@example.test"
        with self.app.app_context():
            uid = dbm.insert("INSERT INTO users (email, full_name, role, password_hash, must_change_password, active, created_at) VALUES (?,?,?,?,?,?,?)", (email, role.title(), role, sec.hash_password(pw), must, active, dbm.now()))
        return uid, email
    def patient(self, name="Fictional Patient"):
        with self.app.app_context(): return dbm.insert("INSERT INTO patients (full_name, created_at) VALUES (?,?)", (name, dbm.now()))
    def q(self, sql, args=()):
        with self.app.app_context(): return dbm.many(sql, args)
    def x(self, sql, args=()):
        with self.app.app_context(): dbm.run(sql, args)
    def login(self, client, email, pw=PW, realm="staff"):
        base = "/staff" if realm == "staff" else "/portal"
        tok = CSRF.search(client.get(base + "/login").get_data(as_text=True)).group(1)
        return client.post(base + "/login", data={"email": email, "password": pw, "csrf_token": tok})
    def staff_client(self, role, email=None):
        self.user(role, email); c = self.app.test_client(); r = self.login(c, email or f"{role}@example.test"); self.assertEqual(r.status_code, 302); return c
    def token(self, client, path):
        return CSRF.search(client.get(path).get_data(as_text=True)).group(1)
    def post(self, client, path, page="/staff/", **data):
        data["csrf_token"] = self.token(client, page); return client.post(path, data=data)

class Stage1Staff(Base):
    def test_login_generic_error_and_no_enumeration(self):
        self.user("receptionist"); a = self.login(self.app.test_client(), "receptionist@example.test", "wrong-password-1"); b = self.login(self.app.test_client(), "nobody@example.test", "wrong-password-1")
        self.assertEqual((a.status_code, b.status_code), (401, 401)); self.assertEqual(a.get_data(as_text=True).count("not correct"), b.get_data(as_text=True).count("not correct")); self.assertIn("not correct", a.get_data(as_text=True))
    def test_lockout_applies_even_with_correct_password_and_to_unknown_accounts(self):
        self.user("nurse"); c = self.app.test_client()
        for _ in range(5): self.login(c, "nurse@example.test", "bad-password-123")
        self.assertEqual(self.login(c, "nurse@example.test").status_code, 429)
        d = self.app.test_client()
        for _ in range(5): self.login(d, "ghost@example.test", "bad-password-123")
        self.assertEqual(self.login(d, "ghost@example.test", "x").status_code, 429)
    def test_deactivated_account_cannot_log_in(self):
        self.user("nurse", active=0); self.assertEqual(self.login(self.app.test_client(), "nurse@example.test").status_code, 401)
    def test_sql_injection_in_login_and_search(self):
        self.assertEqual(self.login(self.app.test_client(), "' OR 1=1 --").status_code, 401)
        c = self.staff_client("receptionist"); self.assertEqual(c.get("/staff/patients?q=%27%20OR%201%3D1%20--").status_code, 200)
    def test_private_pages_need_login_and_are_not_cacheable(self):
        r = self.app.test_client().get("/staff/patients"); self.assertEqual(r.status_code, 302); self.assertIn("/staff/login", r.headers["Location"])
        r = self.staff_client("receptionist").get("/staff/patients"); self.assertIn("no-store", r.headers["Cache-Control"]); self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
    def test_forced_password_change_and_policy(self):
        self.user("nurse", must=1); c = self.app.test_client(); self.login(c, "nurse@example.test")
        self.assertIn("/staff/password", c.get("/staff/patients").headers["Location"])
        r = self.post(c, "/staff/password", "/staff/password", current=PW, new="short1", again="short1"); self.assertEqual(r.status_code, 400)
        r = self.post(c, "/staff/password", "/staff/password", current=PW, new="Brand-new-passphrase-7", again="Brand-new-passphrase-7"); self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/staff/patients").status_code, 200)
    def test_csrf_required_on_state_changing_requests(self):
        c = self.staff_client("hospital_admin"); r = c.post("/staff/users/new", data={"email": "x@example.test", "full_name": "X", "role": "nurse"}); self.assertEqual(r.status_code, 400)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM users WHERE email='x@example.test'")[0]["n"], 0)
        r = c.post("/staff/users/new", data={"email": "x@example.test", "full_name": "X", "role": "nurse", "csrf_token": "forged"}); self.assertEqual(r.status_code, 400)
        r = self.post(c, "/staff/users/new", email="x@example.test", full_name="X", role="nurse"); self.assertEqual(r.status_code, 200); self.assertIn("shown only once", r.get_data(as_text=True))
    def test_session_expiry_and_logout_revoke(self):
        c = self.staff_client("receptionist"); self.assertEqual(c.get("/staff/patients").status_code, 200)
        self.x("UPDATE sessions SET last_seen='2000-01-01T00:00:00Z'"); self.assertEqual(c.get("/staff/patients").status_code, 302)
        c2 = self.staff_client("nurse"); cookie = c2.get_cookie("nc_staff", path="/staff").value; self.post(c2, "/staff/logout"); c3 = self.app.test_client(); c3.set_cookie("nc_staff", cookie, path="/staff"); self.assertEqual(c3.get("/staff/patients").status_code, 302)
    def test_absolute_session_lifetime(self):
        c = self.staff_client("receptionist"); self.x("UPDATE sessions SET expires_at='2000-01-01T00:00:00Z'"); self.assertEqual(c.get("/staff/patients").status_code, 302)
    def test_cookie_flags(self):
        self.user("nurse"); c = self.app.test_client(); r = self.login(c, "nurse@example.test"); h = r.headers.get("Set-Cookie", "").lower(); self.assertIn("httponly", h); self.assertIn("samesite=strict", h)
    def test_role_permissions_matrix(self):
        pid = self.patient(); denied = {"receptionist": ["/staff/billing", f"/staff/patients/{pid}/clinical", "/staff/audit", "/staff/users", "/staff/homecare"],
            "system_admin": ["/staff/patients", f"/staff/patients/{pid}", f"/staff/patients/{pid}/clinical", "/staff/billing"], "caregiver": ["/staff/patients", "/staff/homecare", "/staff/billing", f"/staff/patients/{pid}/clinical"],
            "billing_clerk": [f"/staff/patients/{pid}/clinical", "/staff/homecare", "/staff/users"], "nurse": ["/staff/billing", "/staff/users", "/staff/audit"], "homecare_coordinator": [f"/staff/patients/{pid}/clinical", "/staff/billing"]}
        for role, paths in denied.items():
            c = self.staff_client(role)
            for p in paths: self.assertEqual(c.get(p).status_code, 403, f"{role} should be denied {p}")
        for role, paths in {"doctor": [f"/staff/patients/{pid}/clinical"], "billing_clerk": ["/staff/billing"], "system_admin": ["/staff/users", "/staff/audit"], "caregiver": ["/staff/my-visits"]}.items():
            c = self.staff_client(role, f"ok-{role}@example.test")
            for p in paths: self.assertEqual(c.get(p).status_code, 200, f"{role} should open {p}")
    def test_admin_boundaries(self):
        c = self.staff_client("hospital_admin"); r = self.post(c, "/staff/users/new", email="a@example.test", full_name="A", role="system_admin"); self.assertEqual(r.status_code, 403)
        uid, _ = self.user("system_admin", "root@example.test"); self.assertEqual(self.post(c, f"/staff/users/{uid}/deactivate").status_code, 403)
        me = self.q("SELECT id FROM users WHERE role='hospital_admin'")[0]["id"]; self.post(c, f"/staff/users/{me}/deactivate"); self.assertEqual(self.q("SELECT active FROM users WHERE id=?", (me,))[0]["active"], 1)
        s = self.staff_client("system_admin", "sa2@example.test"); only = self.q("SELECT id FROM users WHERE email='root@example.test'")[0]["id"]; self.post(s, f"/staff/users/{only}/deactivate")
        self.assertEqual(self.q("SELECT COUNT(*) n FROM users WHERE role='system_admin' AND active=1")[0]["n"], 1)
    def test_deactivation_ends_sessions(self):
        c = self.staff_client("nurse"); uid = self.q("SELECT id FROM users WHERE role='nurse'")[0]["id"]; a = self.staff_client("hospital_admin"); self.post(a, f"/staff/users/{uid}/deactivate"); self.assertEqual(c.get("/staff/patients").status_code, 302)
    def test_audit_trail_and_tamper_detection(self):
        c = self.staff_client("receptionist"); c.get("/staff/audit"); self.assertTrue(any(r["action"] == "access.denied" for r in self.q("SELECT action FROM audit_events")))
        with self.app.app_context(): ok, _, n = verify_chain()
        self.assertTrue(ok); self.assertGreaterEqual(n, 2)
        self.x("UPDATE audit_events SET action='nothing.happened' WHERE id=2")
        with self.app.app_context(): self.assertFalse(verify_chain()[0])
    def test_audit_detail_holds_no_credentials(self):
        self.login(self.app.test_client(), "nobody@example.test", "Super-secret-pass-1")
        self.assertFalse(any("Super-secret" in r["detail"] for r in self.q("SELECT detail FROM audit_events")))

class Stage3Homecare(Base):
    def setUp(self):
        super().setUp(); self.pid = self.patient(); self.coord = self.staff_client("homecare_coordinator"); self.carer_id, _ = self.user("caregiver", "carer1@example.test"); self.carer = self.app.test_client(); self.login(self.carer, "carer1@example.test")
        self.other_id, _ = self.user("caregiver", "carer2@example.test"); self.other = self.app.test_client(); self.login(self.other, "carer2@example.test")
        self.plan = self.q("SELECT 1")  # placeholder
    def schedule(self, start="2030-01-10T09:00", end="2030-01-10T10:00", plan=""):
        self.post(self.coord, "/staff/homecare/new", "/staff/homecare/new", patient_id=str(self.pid), visit_type="Nursing visit", start=start, end=end, area="Demo Estate", address="Fictional Road 1", care_plan_id=plan)
        return self.q("SELECT id FROM homecare_visits ORDER BY id DESC LIMIT 1")[0]["id"]
    def test_full_visit_workflow_and_privacy(self):
        pl = self.post(self.coord, f"/staff/patients/{self.pid}/careplans", f"/staff/patients/{self.pid}", title="Daily support"); cid = self.q("SELECT id FROM care_plans")[0]["id"]
        self.post(self.coord, f"/staff/careplans/{cid}/tasks", f"/staff/careplans/{cid}", description="Help with breakfast", frequency="daily")
        vid = self.schedule(plan=str(cid)); self.assertEqual(self.carer.get(f"/staff/visits/{vid}").status_code, 403)       # not assigned yet
        self.post(self.coord, f"/staff/homecare/{vid}/assign", f"/staff/visits/{vid}", caregiver_id=str(self.carer_id))
        self.assertEqual(self.other.get(f"/staff/visits/{vid}").status_code, 403)                                            # a different caregiver
        page = self.carer.get(f"/staff/visits/{vid}").get_data(as_text=True); self.assertNotIn("Fictional Road", page)       # address hidden until accepted
        self.post(self.carer, f"/staff/visits/{vid}/accept", f"/staff/visits/{vid}"); self.assertIn("Fictional Road 1", self.carer.get(f"/staff/visits/{vid}").get_data(as_text=True))
        self.post(self.carer, f"/staff/visits/{vid}/complete", f"/staff/visits/{vid}", report="too early"); self.assertEqual(self.q("SELECT status FROM homecare_visits WHERE id=?", (vid,))[0]["status"], "confirmed")
        self.post(self.carer, f"/staff/visits/{vid}/start", f"/staff/visits/{vid}")
        tid = self.q("SELECT id FROM care_plan_tasks")[0]["id"]; self.post(self.carer, f"/staff/visits/{vid}/complete", f"/staff/visits/{vid}", report="Visit went smoothly.", **{f"task_{tid}": "on"})
        self.assertEqual(self.q("SELECT status FROM homecare_visits WHERE id=?", (vid,))[0]["status"], "completed")
        raw = self.q("SELECT report_enc FROM visit_records")[0]["report_enc"]; self.assertNotIn("smoothly", raw)
        self.assertEqual(self.q("SELECT done FROM visit_task_records")[0]["done"], 1)
    def test_overlapping_assignment_refused_and_bad_transitions(self):
        v1 = self.schedule(); v2 = self.schedule("2030-01-10T09:30", "2030-01-10T10:30")
        self.post(self.coord, f"/staff/homecare/{v1}/assign", f"/staff/visits/{v1}", caregiver_id=str(self.carer_id)); self.post(self.coord, f"/staff/homecare/{v2}/assign", f"/staff/visits/{v2}", caregiver_id=str(self.carer_id))
        self.assertEqual(self.q("SELECT status FROM homecare_visits WHERE id=?", (v2,))[0]["status"], "scheduled")
        self.post(self.carer, f"/staff/visits/{v1}/start", f"/staff/visits/{v1}"); self.assertEqual(self.q("SELECT status FROM homecare_visits WHERE id=?", (v1,))[0]["status"], "assigned")   # cannot start before accepting
        self.post(self.coord, f"/staff/homecare/{v2}/status", f"/staff/visits/{v2}", to="missed"); self.assertEqual(self.q("SELECT status FROM homecare_visits WHERE id=?", (v2,))[0]["status"], "scheduled")
    def test_caregiver_cannot_schedule_or_assign(self):
        self.assertEqual(self.carer.get("/staff/homecare/new").status_code, 403); self.assertEqual(self.post(self.carer, "/staff/homecare/1/assign", "/staff/my-visits", caregiver_id="1").status_code, 403)
    def test_invalid_visit_input(self):
        r = self.post(self.coord, "/staff/homecare/new", "/staff/homecare/new", patient_id="999", visit_type="Nope", start="2030-01-10T10:00", end="2030-01-10T09:00"); self.assertEqual(r.status_code, 400)

class Stage4Clinical(Base):
    def setUp(self):
        super().setUp(); self.pid = self.patient(); self.doc = self.staff_client("doctor"); self.nurse = self.staff_client("nurse")
    def enc(self):
        self.post(self.doc, f"/staff/patients/{self.pid}/encounters", f"/staff/patients/{self.pid}/clinical", encounter_type="consultation", occurred_at="2030-01-10T09:00", reason="Fictional reason text"); return self.q("SELECT id FROM clinical_encounters")[0]["id"]
    def test_notes_encrypted_at_rest_and_readable_by_clinicians(self):
        eid = self.enc(); self.post(self.doc, f"/staff/encounters/{eid}/notes", f"/staff/encounters/{eid}", body="Fictional clinical observation alpha")
        raw = sqlite3.connect(f"{self.dir}/portal.db").execute("SELECT body_enc FROM clinical_notes").fetchone()[0]; self.assertNotIn("alpha", raw)
        self.assertIn("Fictional clinical observation alpha", self.nurse.get(f"/staff/encounters/{eid}").get_data(as_text=True))
        raw_reason = sqlite3.connect(f"{self.dir}/portal.db").execute("SELECT reason_enc FROM clinical_encounters").fetchone()[0]; self.assertNotIn("Fictional reason", raw_reason)
    def test_only_doctors_order_medication(self):
        r = self.post(self.nurse, f"/staff/patients/{self.pid}/medications", f"/staff/patients/{self.pid}/clinical", medication_name="Fictional medicine", instructions="As directed by prescriber"); self.assertEqual(r.status_code, 403)
        self.post(self.doc, f"/staff/patients/{self.pid}/medications", f"/staff/patients/{self.pid}/clinical", medication_name="Fictional medicine", instructions="As directed by prescriber")
        self.assertEqual(self.q("SELECT COUNT(*) n FROM medication_orders")[0]["n"], 1); self.assertNotIn("As directed", self.q("SELECT instructions_enc FROM medication_orders")[0]["instructions_enc"])
    def test_observation_validation(self):
        eid = self.enc(); self.post(self.nurse, f"/staff/encounters/{eid}/observations", f"/staff/encounters/{eid}", kind="blood_pressure", value="abc"); self.assertEqual(self.q("SELECT COUNT(*) n FROM observations")[0]["n"], 0)
        self.post(self.nurse, f"/staff/encounters/{eid}/observations", f"/staff/encounters/{eid}", kind="blood_pressure", value="120/80"); self.assertEqual(self.q("SELECT unit FROM observations")[0]["unit"], "mmHg")
    def test_reads_and_writes_are_audited_and_other_roles_blocked(self):
        eid = self.enc(); self.doc.get(f"/staff/encounters/{eid}"); acts = [r["action"] for r in self.q("SELECT action FROM audit_events")]; self.assertIn("encounter.viewed", acts); self.assertIn("encounter.created", acts)
        for role in ("receptionist", "caregiver", "billing_clerk", "hospital_admin"): self.assertEqual(self.staff_client(role, f"{role}@x.test").get(f"/staff/encounters/{eid}").status_code, 403)

class Stage2Portal(Base):
    def register(self, client, email, name="Fictional Family"):
        tok = CSRF.search(client.get("/portal/register").get_data(as_text=True)).group(1)
        return client.post("/portal/register", data={"full_name": name, "email": email, "phone": "0712345678", "password": PW, "again": PW, "consent": "on", "csrf_token": tok})
    def approve(self, email, pid=None, staff=None):
        staff = staff or self.reception; aid = self.q("SELECT id FROM portal_accounts WHERE email=?", (email,))[0]["id"]
        return self.post(staff, f"/staff/portal-accounts/{aid}/review", "/staff/portal-accounts", decision="approve", patient_id=str(pid or ""), verification="Fictional ID checked in person")
    def setUp(self):
        super().setUp(); self.reception = self.staff_client("receptionist"); self.pa, self.pb = self.patient("Patient A"), self.patient("Patient B")
        self.cl = self.app.test_client(); self.register(self.cl, "a@example.test"); self.approve("a@example.test", self.pa); self.login(self.cl, "a@example.test", realm="patient")
    def test_pending_account_sees_nothing(self):
        c = self.app.test_client(); self.register(c, "p@example.test"); self.login(c, "p@example.test", realm="patient")
        self.assertIn("waiting for staff", c.get("/portal/").get_data(as_text=True)); self.assertEqual(c.get("/portal/care-plan").get_data(as_text=True).count("Daily"), 0)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM patient_access WHERE account_id=(SELECT id FROM portal_accounts WHERE email='p@example.test')")[0]["n"], 0)
    def test_registration_does_not_reveal_existing_emails_and_is_rate_limited(self):
        a = self.register(self.app.test_client(), "a@example.test"); b = self.register(self.app.test_client(), "new@example.test"); self.assertEqual(a.status_code, b.status_code); self.assertEqual(a.get_data(as_text=True), b.get_data(as_text=True))
        self.assertEqual(self.q("SELECT COUNT(*) n FROM portal_accounts WHERE email='a@example.test'")[0]["n"], 1)
        c = self.app.test_client(); codes = [self.register(c, f"u{i}@example.test").status_code for i in range(8)]; self.assertIn(429, codes)
    def test_weak_password_rejected_at_registration(self):
        c = self.app.test_client(); tok = CSRF.search(c.get("/portal/register").get_data(as_text=True)).group(1)
        r = c.post("/portal/register", data={"full_name": "X Y", "email": "w@example.test", "password": "short", "again": "short", "consent": "on", "csrf_token": tok}); self.assertEqual(r.status_code, 400)
    def test_patient_sees_only_own_published_care_plan(self):
        coord = self.staff_client("homecare_coordinator")
        for pid, title in ((self.pa, "Plan for A"), (self.pb, "Plan for B")): self.post(coord, f"/staff/patients/{pid}/careplans", f"/staff/patients/{pid}", title=title)
        for row in self.q("SELECT id FROM care_plans"): self.post(coord, f"/staff/careplans/{row['id']}/publish", f"/staff/careplans/{row['id']}")
        page = self.cl.get("/portal/care-plan").get_data(as_text=True); self.assertIn("Plan for A", page); self.assertNotIn("Plan for B", page)
        first = self.q("SELECT id FROM care_plans WHERE title='Plan for A'")[0]["id"]; self.post(coord, f"/staff/careplans/{first}/publish", f"/staff/careplans/{first}"); self.assertNotIn("Plan for A", self.cl.get("/portal/care-plan").get_data(as_text=True))   # unpublished again
    def test_cannot_request_appointment_for_someone_else(self):
        tok = self.token(self.cl, "/portal/appointments"); r = self.cl.post("/portal/appointments", data={"patient_id": str(self.pb), "service": "Laboratory", "csrf_token": tok}); self.assertEqual(r.status_code, 403)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM appointments")[0]["n"], 0)
        r = self.cl.post("/portal/appointments", data={"patient_id": str(self.pa), "service": "Laboratory", "csrf_token": tok}); self.assertEqual(r.status_code, 302); self.assertEqual(self.q("SELECT status FROM appointments")[0]["status"], "requested")
    def test_family_access_requires_staff_grant_and_can_be_revoked(self):
        fam = self.app.test_client(); self.register(fam, "f@example.test"); self.approve("f@example.test", self.pb); self.login(fam, "f@example.test", realm="patient")
        self.assertNotIn("Patient A", fam.get("/portal/").get_data(as_text=True))
        self.post(self.reception, f"/staff/patients/{self.pa}/grants", f"/staff/patients/{self.pa}", email="f@example.test", relationship="Daughter", consent_note="Patient agreed by phone")
        self.assertIn("Patient A", fam.get("/portal/").get_data(as_text=True))
        gid = self.q("SELECT id FROM patient_access WHERE patient_id=? AND relationship='Daughter'", (self.pa,))[0]["id"]; self.post(self.reception, f"/staff/patients/{self.pa}/grants/{gid}/revoke", f"/staff/patients/{self.pa}")
        self.assertNotIn("Patient A", fam.get("/portal/").get_data(as_text=True))
    def test_released_encounter_shows_date_and_type_only(self):
        doc = self.staff_client("doctor"); self.post(doc, f"/staff/patients/{self.pa}/encounters", f"/staff/patients/{self.pa}/clinical", encounter_type="consultation", occurred_at="2030-02-02T09:00", reason="Private reason XYZ")
        eid = self.q("SELECT id FROM clinical_encounters")[0]["id"]; self.post(doc, f"/staff/encounters/{eid}/notes", f"/staff/encounters/{eid}", body="Private note XYZ")
        self.assertNotIn("2030-02-02", self.cl.get("/portal/visits").get_data(as_text=True)); self.post(doc, f"/staff/encounters/{eid}/release", f"/staff/encounters/{eid}")
        page = self.cl.get("/portal/visits").get_data(as_text=True); self.assertIn("2030-02-02", page); self.assertNotIn("XYZ", page)
    def test_portal_user_cannot_open_staff_areas_and_vice_versa(self):
        self.assertEqual(self.cl.get("/staff/patients").status_code, 302); self.assertEqual(self.reception.get("/portal/").status_code, 302)
        c = self.app.test_client(); c.set_cookie("nc_staff", self.cl.get_cookie("nc_portal", path="/portal").value, path="/staff"); self.assertEqual(c.get("/staff/patients").status_code, 302)
    def test_suspended_account_loses_access_immediately(self):
        aid = self.q("SELECT id FROM portal_accounts WHERE email='a@example.test'")[0]["id"]; self.post(self.reception, f"/staff/portal-accounts/{aid}/review", "/staff/portal-accounts", decision="suspend"); self.assertEqual(self.cl.get("/portal/").status_code, 302)
    def test_approval_requires_identity_check_note(self):
        c = self.app.test_client(); self.register(c, "n@example.test"); aid = self.q("SELECT id FROM portal_accounts WHERE email='n@example.test'")[0]["id"]
        self.post(self.reception, f"/staff/portal-accounts/{aid}/review", "/staff/portal-accounts", decision="approve", patient_id=str(self.pa), verification=""); self.assertEqual(self.q("SELECT status FROM portal_accounts WHERE id=?", (aid,))[0]["status"], "pending")
    def test_portal_csrf(self):
        self.assertEqual(self.cl.post("/portal/appointments", data={"patient_id": str(self.pa), "service": "Laboratory"}).status_code, 400)

class Stage5Billing(Base):
    def setUp(self):
        super().setUp(); self.pid = self.patient(); self.bill = self.staff_client("billing_clerk")
        self.post(self.bill, f"/staff/patients/{self.pid}/invoices", f"/staff/billing", description="Consultation fee", amount="1500.00"); self.iid = self.q("SELECT id FROM invoices")[0]["id"]
    def test_payment_rules_and_status(self):
        self.post(self.bill, f"/staff/invoices/{self.iid}/payments", f"/staff/invoices/{self.iid}", amount="2000", method="cash"); self.assertEqual(self.q("SELECT COUNT(*) n FROM payments")[0]["n"], 0)   # over balance
        self.post(self.bill, f"/staff/invoices/{self.iid}/payments", f"/staff/invoices/{self.iid}", amount="500", method="cash"); self.assertEqual(self.q("SELECT status FROM invoices")[0]["status"], "part_paid")
        self.post(self.bill, f"/staff/invoices/{self.iid}/void", f"/staff/invoices/{self.iid}"); self.assertEqual(self.q("SELECT status FROM invoices")[0]["status"], "part_paid")   # has payments
        self.post(self.bill, f"/staff/invoices/{self.iid}/payments", f"/staff/invoices/{self.iid}", amount="1000", method="mpesa_manual", reference="FICT123"); self.assertEqual(self.q("SELECT status FROM invoices")[0]["status"], "paid")
    def test_invalid_amounts_and_methods(self):
        for amt, m in (("-5", "cash"), ("0", "cash"), ("abc", "cash"), ("10.123", "cash"), ("10", "bitcoin")): self.post(self.bill, f"/staff/invoices/{self.iid}/payments", f"/staff/invoices/{self.iid}", amount=amt, method=m)
        self.assertEqual(self.q("SELECT COUNT(*) n FROM payments")[0]["n"], 0)
    def test_only_billing_staff_can_write_and_no_card_data_stored(self):
        nurse = self.staff_client("nurse"); self.assertEqual(nurse.get(f"/staff/invoices/{self.iid}").status_code, 403)
        admin = self.staff_client("hospital_admin"); self.assertEqual(admin.get(f"/staff/invoices/{self.iid}").status_code, 200); self.assertEqual(self.post(admin, f"/staff/invoices/{self.iid}/payments", f"/staff/invoices/{self.iid}", amount="1", method="cash").status_code, 403)
        cols = [r["name"] for r in self.q("PRAGMA table_info(payments)")]; self.assertFalse({"card_number", "cvv", "pan"} & set(cols))
    def test_provider_integration_is_disabled(self):
        from portal import billing_provider
        with self.assertRaises(billing_provider.ProviderNotConfigured): billing_provider.charge(100)

class Stage6DataProtection(Base):
    def test_enquiries_database_is_separate_from_patient_data(self):
        import app as site  # the public site module and its own SQLite file
        self.assertNotEqual(str(site.DB), str(self.app.config["PORTAL_DB"].path))
        with self.app.app_context(): tables = {r["name"] for r in dbm.many("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("enquiries", tables)
    def test_production_refuses_to_start_without_secrets(self):
        from portal import load_settings
        with self.assertRaises(RuntimeError): load_settings({"PORTAL_ENV": "production"})
    def test_encryption_roundtrip_and_key_rotation(self):
        with self.app.app_context():
            tok = sec.encrypt("Fictional secret"); self.assertNotIn("Fictional", tok); self.assertEqual(sec.decrypt(tok), "Fictional secret")
            new = Fernet.generate_key().decode(); old = self.app.config["PORTAL"]["data_keys"]; self.app.config["PORTAL"]["data_keys"] = [new] + old; self.app.config["_FERNET"] = None
            self.assertEqual(sec.decrypt(tok), "Fictional secret")      # old data still readable after adding a newer key
    def test_wrong_key_does_not_crash_or_leak(self):
        with self.app.app_context():
            tok = sec.encrypt("Fictional secret"); self.app.config["PORTAL"]["data_keys"] = [Fernet.generate_key().decode()]; self.app.config["_FERNET"] = None; self.assertIn("unreadable", sec.decrypt(tok))
    def test_password_hashes_are_salted_and_not_plaintext(self):
        self.user("nurse"); h = self.q("SELECT password_hash FROM users")[0]["password_hash"]; self.assertNotIn(PW, h); self.assertTrue(h.startswith("scrypt:"))
        with self.app.app_context(): self.assertNotEqual(sec.hash_password(PW), sec.hash_password(PW))
    def test_private_pages_not_served_as_static_and_error_pages_are_safe(self):
        r = self.app.test_client().get("/staff/nonexistent"); self.assertIn(r.status_code, (404,)); c = self.staff_client("receptionist"); self.assertEqual(c.get("/staff/patients/99999").status_code, 404)

class RealSiteExposure(unittest.TestCase):
    def test_real_app_blocks_data_and_source_paths_and_keeps_portal_off_by_default(self):
        env = dict(os.environ); env.pop("PORTAL_ENABLED", None)
        import subprocess, json
        code = "import sys;sys.path.insert(0,'python');import app;c=app.app.test_client();print(json.dumps([c.get(p).status_code for p in ['/data/site.json','/python/app.py','/python/portal/security.py','/python/instance/enquiries.db','/staff/','/portal/','/']]))"
        out = subprocess.run([sys.executable, "-c", "import json;" + code], capture_output=True, text=True, env=env, cwd=str(Path(__file__).resolve().parents[2])).stdout.strip().splitlines()[-1]
        self.assertEqual(json.loads(out), [404, 404, 404, 404, 404, 404, 200])

if __name__ == "__main__": unittest.main()
