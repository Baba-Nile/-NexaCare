"""Public enquiry API and staff inbox: branch selection is allow-listed, stored, retrieved and shown; old databases keep working.
Run:  python -m unittest discover -s python/tests -v   (from the project root)"""
import json, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
PY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PY)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as webapp, branches as BM, enquiry_store
from test_portal import Base

GOOD = {"kind": "appointment", "name": "Test Person", "phone": "0712 345 678", "service": "outpatient", "consent": True}
LEGACY_SCHEMA = """CREATE TABLE enquiries(id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, kind TEXT NOT NULL,
                 name TEXT, phone TEXT, email TEXT, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new')"""

def make_legacy(path):
    """A database exactly as the previous version of the site created it (no branch column)."""
    c = sqlite3.connect(path); c.execute(LEGACY_SCHEMA)
    c.execute("INSERT INTO enquiries(reference,created_at,kind,name,phone,payload) VALUES('NC-OLD00001','2026-01-01T09:00:00+00:00','appointment','Old Patient','0711111111',?)", (json.dumps({"name": "Old Patient", "service": "laboratory"}),))
    c.commit(); c.close()

class Api(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); webapp.DB = Path(self.dir) / "enq.db"; webapp.RATE_MAX = 1000
        self.c = webapp.app.test_client()
    def post(self, **over):
        d = {**GOOD, **over}; d = {k: v for k, v in d.items() if v is not None}
        return self.c.post("/api/enquiry", json=d, headers={"Origin": "http://localhost"})
    def row(self, ref):
        c = sqlite3.connect(webapp.DB); c.row_factory = sqlite3.Row
        try: return dict(c.execute("SELECT * FROM enquiries WHERE reference=?", (ref,)).fetchone())
        finally: c.close()

    def test_branch_is_in_the_field_allowlist(self):
        self.assertIn("branch", webapp.FIELDS)
    def test_every_branch_is_accepted_stored_and_kept_in_payload(self):
        for slug in BM.slugs():
            r = self.post(branch=slug); self.assertEqual(r.status_code, 201, slug)
            row = self.row(r.get_json()["reference"]); self.assertEqual(row["branch"], slug); self.assertEqual(json.loads(row["payload"])["branch"], slug)
    def test_six_required_branches_are_selectable(self):
        names = {b["name"] for b in BM.load()["branches"]}
        self.assertEqual(names, {"Maili Saba", "Manor House", "Meru Farm", "Tiwani", "Eldoret", "Nairobi"})
    def test_unknown_or_malicious_branch_is_rejected_and_nothing_is_saved(self):
        for bad in ("atlantis", "ELDORET ", "eldoret'; DROP TABLE enquiries;--", "<script>alert(1)</script>", "../etc/passwd"):
            r = self.post(branch=bad); self.assertEqual(r.status_code, 400, bad); self.assertIn("branch", r.get_json()["error"].lower())
        with webapp.db() as c: self.assertEqual(c.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0], 0)
    def test_branch_is_optional_so_older_cached_pages_still_work(self):
        r = self.post(); self.assertEqual(r.status_code, 201); self.assertIsNone(self.row(r.get_json()["reference"])["branch"])
    def test_all_enquiry_kinds_accept_a_branch(self):
        for kind, extra in (("appointment", {}), ("quick", {}), ("contact", {"phone": None, "email": "a@b.co"}), ("homecare", {"requester_name": "Req", "name": None, "care_type": "Nursing visit", "area": "Estate"})):
            r = self.post(kind=kind, branch="meru-farm", **extra); self.assertEqual(r.status_code, 201, kind); self.assertEqual(self.row(r.get_json()["reference"])["branch"], "meru-farm")
    def test_existing_validation_still_works(self):
        self.assertEqual(self.post(consent=False).status_code, 400); self.assertEqual(self.post(phone="abc").status_code, 400)
        self.assertEqual(self.post(name=None).status_code, 400); self.assertEqual(self.post(website="bot").status_code, 400)
        self.assertEqual(self.c.post("/api/enquiry", json=GOOD).status_code, 403)       # no Origin header
        self.assertEqual(self.post(branch="eldoret").status_code, 201)
    def test_unknown_fields_are_still_ignored(self):
        r = self.post(branch="eldoret", is_admin="yes", payload="x"); row = self.row(r.get_json()["reference"]); self.assertNotIn("is_admin", json.loads(row["payload"]))
    def test_branch_list_follows_branches_json_without_restart(self):
        self.assertEqual(self.post(branch="gatua-kitale").status_code, 201); self.assertEqual(self.post(branch="no-preference").status_code, 201)
    def test_old_database_is_migrated_without_losing_rows(self):
        make_legacy(webapp.DB)
        r = self.post(branch="tiwani"); self.assertEqual(r.status_code, 201)
        c = sqlite3.connect(webapp.DB)
        try:
            self.assertIn("branch", enquiry_store.columns(c)); self.assertEqual(c.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0], 2)
            self.assertIsNone(c.execute("SELECT branch FROM enquiries WHERE reference='NC-OLD00001'").fetchone()[0])
        finally: c.close()
    def test_retrieval_shows_branch_and_handles_old_rows(self):
        make_legacy(webapp.DB); self.post(branch="eldoret"); self.post(branch="nairobi")
        with webapp.db() as c:
            allr = enquiry_store.rows(c, 50); by = {r["reference"]: r for r in allr}
            self.assertEqual(len(allr), 3); self.assertEqual(by["NC-OLD00001"]["branch_name"], "Not specified")
            self.assertEqual([r["branch_name"] for r in enquiry_store.rows(c, 50, "eldoret")], ["Eldoret"])
            self.assertEqual([r["reference"] for r in enquiry_store.rows(c, 50, enquiry_store.UNSPECIFIED)], ["NC-OLD00001"])
            self.assertEqual(enquiry_store.branch_counts(c), {"eldoret": 1, "nairobi": 1, "unspecified": 1})
    def test_retrieval_on_unmigrated_database_opened_read_only(self):
        make_legacy(webapp.DB); c = sqlite3.connect(f"file:{webapp.DB}?mode=ro", uri=True)
        try: r = enquiry_store.rows(c, 10); self.assertEqual(r[0]["branch_name"], "Not specified"); self.assertEqual(enquiry_store.rows(c, 10, "eldoret"), [])
        finally: c.close()
    def test_cli_list_shows_branch(self):
        self.post(branch="manor-house")
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): webapp.cli(["list", "5"])
        self.assertIn("Manor House", buf.getvalue())

class StaffInbox(Base):
    def seed(self, legacy=False):
        if legacy: make_legacy(self.enq)
        webapp.DB = self.enq; webapp.RATE_MAX = 1000; c = webapp.app.test_client()
        for slug, name in (("eldoret", "Ellie Eldoret"), ("nairobi", "Nora Nairobi"), (None, "No Branch")):
            r = c.post("/api/enquiry", json={**GOOD, "name": name, **({"branch": slug} if slug else {}), "message": "Hello <b>x</b>"}, headers={"Origin": "http://localhost"}); self.assertEqual(r.status_code, 201)
    def test_staff_see_the_selected_branch(self):
        self.seed(); r = self.staff_client("receptionist").get("/staff/enquiries"); h = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200); self.assertIn("Eldoret", h); self.assertIn("Nairobi", h); self.assertIn("Not specified", h); self.assertIn("<th>Branch</th>", h)
    def test_branch_filter(self):
        self.seed(); c = self.staff_client("receptionist"); h = c.get("/staff/enquiries?branch=eldoret").get_data(as_text=True)
        self.assertIn("Ellie Eldoret", h); self.assertNotIn("Nora Nairobi", h); self.assertNotIn("No Branch", h)
        h = c.get("/staff/enquiries?branch=unspecified").get_data(as_text=True); self.assertIn("No Branch", h); self.assertNotIn("Ellie Eldoret", h)
        self.assertEqual(c.get("/staff/enquiries?branch=bogus").status_code, 200)       # unknown filter is ignored, not an error
    def test_inbox_works_on_a_database_from_before_branches(self):
        self.seed(legacy=True); h = self.staff_client("hospital_admin").get("/staff/enquiries").get_data(as_text=True)
        self.assertIn("Old Patient", h); self.assertIn("Ellie Eldoret", h)
    def test_inbox_escapes_visitor_text(self):
        self.seed(); h = self.staff_client("receptionist").get("/staff/enquiries").get_data(as_text=True)
        self.assertNotIn("<b>x</b>", h); self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
    def test_inbox_permissions_unchanged(self):
        self.seed(); self.assertEqual(self.staff_client("billing_clerk").get("/staff/enquiries").status_code, 403)
        self.assertEqual(self.app.test_client().get("/staff/enquiries").status_code, 302)
    def test_empty_inbox_and_missing_database(self):
        r = self.staff_client("receptionist").get("/staff/enquiries"); self.assertEqual(r.status_code, 200); self.assertIn("None.", r.get_data(as_text=True))

if __name__ == "__main__": unittest.main()
