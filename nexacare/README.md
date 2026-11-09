# NexaCare Health Centre website

## Multi-branch public website (latest round)
The public site now presents NexaCare as a multi-branch organisation: six branches (Maili Saba, Manor House, Meru Farm, Tiwani, Eldoret, Nairobi) plus the existing Gatua, Kitale location kept as the **main centre**. **See `docs/BRANCHES.md`** (how to manage branches, what is verified-only, SEO rules) and `docs/TEST-REPORT.md` (what was tested).
- `data/branches.json` is the single source for branches; `python/branches.py` loads and validates it; `python/build.py` generates the hub page `branches/index.html`, six `branches/<slug>.html` pages, navigation, footer, forms and structured data from it.
- No branch address, telephone, WhatsApp, email, hours, services or map data was supplied, so none is shown. Pages say so plainly and offer the central line, labelled as such.
- Forms (appointment, quick request, contact, homecare, footer message) have a branch selector; `python/app.py` allow-lists, validates and stores it (`python/enquiry_store.py`), and the staff inbox shows and filters by it. Old enquiry databases are migrated in place.
- The public design is a new self-contained stylesheet, `assets/css/site.css`. The older `variables/base/components.css` remain only because the staff dashboard and patient portal use them. Icons still come from Font Awesome on cdnjs and the font from Google Fonts.
- Photos: `python python/optimize_images.py` (Pillow) creates `.webp` copies that `build.py` serves with `<picture>`.
- Tests: `python -m unittest discover -s python/tests -v` (87 tests) and the optional browser scripts in `python/tests/browser/`.

Static multipage website generated from JSON data and Python templates, plus a small Flask service that stores enquiry forms.


# Secure healthcare platform (staff dashboard, patient portal, homecare, clinical records, billing)

**Status: built and tested on SQLite with fictional data. NOT approved for real patient data.** It is off by default (`PORTAL_ENABLED` unset), so the public website behaves exactly as before. Do not deploy it or migrate real patient data without explicit owner approval, a security review and the legal checks below.

## What was found first (gap analysis)
The existing Flask app had one public enquiry endpoint, a SQLite inbox and a development static server. It had no accounts, sessions, roles, CSRF protection, templates, relational schema, migrations, encryption, audit trail, backup or retention tooling, and no PostgreSQL path. Public enquiries stay in their own SQLite database; the platform uses a separate database and nothing links them.

## Completed (tested: 45 automated tests, plus a browser login smoke test)
| Stage | Built |
|---|---|
| 1 Staff dashboard | Login with scrypt-hashed passwords, 12+ character policy, forced first-login password change, generic login error, lockout after 5 failures per account and per address (also for unknown accounts), server-side revocable sessions (20 min idle, 8 h absolute), HttpOnly SameSite=Strict cookies (Secure in production), CSRF on every POST, role-based permissions enforced on the server, staff account management (create, role change, deactivate, reset; temp passwords shown once), tamper-evident audit log (hash chain) with a viewer |
| 2 Patient and family portal | Registration stays "pending" until staff verify identity and link a patient record (the check is recorded); family access needs an explicit staff-granted, revocable link with a consent note; appointment requests (never confirmed automatically); published care plans; released visit dates and types; invoices. Every query is limited to patients the account has an active grant for. Clinical notes are never shown |
| 3 Homecare | Care plans and tasks, encrypted assessments, visit scheduling, caregiver assignment with overlap check, offer/accept/decline, enforced status transitions, visit documentation with encrypted report and per-task records. Caregivers see only their own assigned visits; address appears only after acceptance |
| 4 Clinical | Encounters, validated observations (fixed measurement types, units and formats), append-only encrypted notes, medication orders (doctors only; the system never suggests or checks doses), release of an encounter's date/type to the patient |
| 5 Billing | Invoices, manual payment records (cash, M-Pesa reference, bank, card machine), over-payment and invalid-amount rejection, status from payments, void only when unpaid. No card data is stored. Payment-provider integration is **not implemented** (`billing_provider.py` is a disabled stub) |
| 6 Data protection | Field encryption (Fernet, key rotation supported) for clinical text, addresses, visit reports; audit of reads, writes and denials; encrypted backups with a restore check; purge of expired sessions, old login attempts and stale registrations; strict CSP and no-store on private pages; no private data in static folders or public URLs; production refuses to start without secrets |

## Roles (what each can open)
| Role | Access |
|---|---|
| System administrator | Staff accounts, audit log. **No patient or clinical data** |
| Hospital administrator | Staff accounts (not admins), audit, patients, portal accounts, appointments, visits, care plans (read), invoices (read), enquiries. No clinical records |
| Receptionist | Patients, portal registrations and grants, appointments, enquiries |
| Homecare coordinator | Patients, visits and assignment, care plans (read/write), enquiries. No clinical records |
| Nurse | Patients, care plans, clinical records (read/write), own visits. Cannot order medication |
| Doctor | Patients, care plans, clinical records, medication orders |
| Caregiver | Only their own assigned visits and linked care-plan tasks |
| Billing clerk | Patients (demographics), invoices and payments |

## Run it locally (SQLite, fictional data)
```
pip install -r python/requirements.txt
set PORTAL_ENABLED=1                        (PowerShell: $env:PORTAL_ENABLED="1")
python python/manage.py migrate
python python/manage.py seed-demo           # prints fictional demo logins once (development only)
python python/app.py                        # http://127.0.0.1:5000/staff/login  and  /portal/login
python -m unittest discover -s python/tests -v
```
First real administrator: `python python/manage.py create-admin` (prompts for a password; no default accounts exist).

## Production (PostgreSQL): required before any real use
1. Copy `.env.example`, generate secrets with `python python/manage.py gen-keys`, set them in the server environment (never in code or git). Back up `PORTAL_DATA_KEY` separately from the database: without it encrypted text cannot be read.
2. Create a PostgreSQL database and a low-privilege application user; use TLS; run `python python/manage.py migrate`. **The PostgreSQL code path was written but could not be run in the build environment**: run the whole test suite against a PostgreSQL test database (adapt `Base.setUp` to a PostgreSQL `DATABASE_URL`) and fix any dialect differences first.
3. Serve over HTTPS only (HSTS at the proxy), behind a reverse proxy, with gunicorn; set `NEXACARE_TRUSTED_PROXIES`, `NEXACARE_ALLOWED_ORIGINS`. The login limiter is stored in the database, so several workers are fine. Add proxy-level rate limiting too.
4. Backups: `python python/manage.py backup` (SQLite) or `pg_dump` (PostgreSQL), encrypted, copied off-site, restore tested regularly (`restore-check`). Set a recovery-time target and rehearse it. Database disk encryption and OS hardening are the hosting provider's/your responsibility.
5. Retention: `manage.py purge` only removes operational data. **Retention periods for clinical, billing and audit records are not set and nothing deletes them**; the owner must decide them with counsel. Data-subject requests (access, correction, erasure) have no tooling yet.
6. Monitoring and incident response: run `manage.py verify-audit` on a schedule; alert on repeated `access.denied`/`auth.failed`; write a breach-response plan.
7. Update the public privacy notice and terms for the portal (they currently describe only website enquiries) and obtain legal review. This build does not claim compliance with the Kenya Data Protection Act, 2019 or health regulations: the owner must confirm obligations (registration with the Data Protection Commissioner, lawful basis and consent wording, health-data hosting and transfer rules, retention, breach notification) with qualified counsel.

## NOT done / limitations (be clear with the client)
- Not tested on PostgreSQL; not load-tested; not penetration-tested; no independent security review.
- No multi-factor authentication for staff (strongly recommended before real use). No email/SMS channel, so no self-service password reset or notifications: staff issue temporary passwords after verifying the person.
- Patient identity verification is a manual staff step; no automated identity checks.
- Payment-provider integration, online payments, receipts and refunds: not implemented.
- No mobile app, no health-information-exchange adapter, no lab or pharmacy modules, no file uploads, no care-plan versions history beyond a counter, no break-glass emergency access, no per-clinician care-relationship restriction (clinical roles can open any patient's record, and every access is logged).
- Operational diagram items from the architecture sketch that are absent: SMS/email provider, payment integration, health information exchange adapter, separate API tier (the app is a single Flask service).
- Browser testing covered a Chromium login smoke test, not every page or screen reader.

## Previous design reference (superseded by site.css; kept for history)
The visual layer follows the supplied "Hospitals" template screenshots: top bar; white header with call / visit / email blocks; navigation row with an active-item top line and a blue appointment button; photographic hero with a white text panel; appointment bar (blue label, 2x2 fields, tall send button); services carousel; editorial welcome section; blue "at a glance" banner; guide cards; facilities with a help box; blue information band; charcoal four-column footer. Inner pages use a photographic banner with breadcrumbs. The Services page uses the Departments card grid, the Health library uses the News layout (cards plus Categories and Start here sidebar), and Contact uses the form + Quick contact layout. Fonts: Poppins (headings, UI) and Hind (body), as in the reference.

Template sections that were NOT reproduced because they need content NexaCare has not supplied: team of consultants and doctor directory (no verified staff), testimonials, awards and recognition, years-of-experience/patient counts, blog dates and comments, social links, Instagram/Facebook feeds, search box, map, photo-only thumbnails for services. The "at a glance" banner uses real counts from this project. Header search is omitted because there is no search feature behind it.

## Photos supplied by the site owner (latest round)
`assets/images/services/nurse-child-checkup.jpg` (maternal and child health service, child health guide) and `blood-pressure-check.jpg` (outpatient service, hypertension guide) were supplied by the site owner. Their licence and permission to publish are NOT confirmed: confirm them or replace the files (edit the slot in `data/image-manifest.json`, then rebuild). Alt text describes the scene only and does not present the people as NexaCare staff or patients. The BP photo is 576px wide, so it is shown at moderate sizes; supply larger originals if available.

## Adding stock photography (Homecare and service pages)
Stock photos could not be downloaded when the site was built (no internet access in the build environment), so these slots show brand tiles or are left out: the Homecare hero, "who homecare helps" and "for the family" photos, and most service and guide images. The mismatched doctor portrait that used to sit on the Homecare hero was removed.
To add real photos: pick them yourself from Unsplash or Pexels (free commercial licences; read the licence on each photo page, avoid visible brands or text, prefer Black African and East African subjects, natural light, no AI-generated images), then fill in an entry in `data/stock-photos.json` (`url` or `local`, `page`, `credit`, `license`, `alt`). The file lists, per slot, the scene wanted and the crop. Run:
```
pip install Pillow
python python/import_photos.py --build
```
The importer refuses entries without page/credit/licence, images under 1000px wide, and near-duplicates of a photo already on the site. It crops to the slot's aspect ratio, optimises, records the source and licence in `data/image-manifest.json`, and rebuilds. Then run `python python/check_site.py` and look at each page on desktop and mobile. Do not describe stock people as NexaCare staff or patients.

## Structure
```
python/build.py        SOURCE: page templates and shared header/footer. Generates every HTML page.
python/app.py          SOURCE: Flask enquiry service (also serves the site for local development)
python/check_site.py   Checker: links, anchors, images, titles, descriptions, one h1, alt text, leftover placeholder wording
data/site.json         Central contact details and business facts (phone, email, locality, logo sizes, domain)
data/branches.json     All branches: details, verified flags, status, SEO text (see docs/BRANCHES.md)
python/branches.py     Loads/validates branch data; the only code that decides what is public
python/enquiry_store.py Enquiry schema migration and retrieval (shared by app.py and the staff inbox)
python/optimize_images.py Creates WebP copies of photos
data/services.json     Service pages     data/health-topics.json  Health guides
data/staff.json        Staff (only entries with "published": true, a name and a photo appear)
data/image-manifest.json  Image slots: file, size, alt, source, licence
assets/css|js|images   Source assets (public CSS: site.css; variables/base/components/portal.css serve the staff portal)
*.html, services/, health-library/, sitemap.xml, robots.txt   GENERATED. Do not edit by hand; run build.py.
```
Do not hand-edit generated pages: change `python/build.py` or a file in `data/`, then rebuild.

## Run
```
pip install -r python/requirements.txt
python python/build.py          # regenerate the site
python python/check_site.py     # must print "No problems found."
python python/app.py            # http://127.0.0.1:5000
python python/app.py list 20    # view recent enquiries (add a branch slug or 'unspecified' to filter)
python python/app.py purge 90   # delete enquiries older than 90 days
```

## How enquiries work
Forms (appointment, quick request, homecare, contact, footer message) POST JSON (including the chosen `branch`) to `/api/enquiry`. The server checks the Origin header, validates and length-limits fields, ignores unknown fields, applies a honeypot and a rate limit (5 per 10 minutes per client, stored in SQLite so it works across workers), and stores the enquiry in `python/instance/enquiries.db` (mode 600, git-ignored). Logs contain references only, never names, phone numbers or messages. The browser shows success only after the server confirms storage; otherwise it shows the phone number and email. Without JavaScript, each form shows a call/email fallback. No notification email is sent: someone must check the inbox (`app.py list`). Adding email alerts needs an SMTP account stored in server environment variables, never in the frontend.

## Maintain content
- Service or health page: edit `data/services.json` / `data/health-topics.json` (keys are documented by the existing entries), then rebuild. A new service needs a slug, icon, text and related slugs.
- Staff: add an entry with `"published": true`, name, title, photo and verified details. Until at least one is published, the Our team page and its links do not exist.
- Images: put the file in `assets/images/...`, set `file`, `w`, `h`, `alt`, `source`, `license` for its slot in `data/image-manifest.json`, rebuild. Slots without a photo show a brand-colour tile.
- Domain: set `domain` in `data/site.json` to enable canonical tags and a correct sitemap/robots.txt.

## Production requirements
Serve over HTTPS; run `app.py` with gunicorn behind a reverse proxy; set `NEXACARE_TRUSTED_PROXIES` (number of proxies) so the client address is read safely, `NEXACARE_ALLOWED_ORIGINS` (https://your-domain), and a random `NEXACARE_HASH_SALT`; keep the database outside the web root with restricted permissions and backups; add the CSP header the app sends (see `app.py`) to the web server if it serves static files; run Lighthouse and axe. Fonts and icons load from Google Fonts and cdnjs: self-host them if privacy or speed requires.

## Status
Complete: public site, homecare page with enquiry form, enquiry storage, sticky header, checker.
Not built (separate secure phase): staff login, caregiver assignment, patient tracking, clinical records, booking management. A portal needs authentication, role-based access, audit logs, privacy controls, encrypted storage, defined workflows and legal review. Do not store clinical information in the enquiry database. NexaCare should confirm its obligations under the Kenya Data Protection Act, 2019 (registration, retention, data-subject requests, hosting) with qualified counsel; the privacy notice does not by itself make the site compliant.

## PRIVATE LAUNCH CHECKLIST (not shown to visitors)
Confirm and then add to `data/` or the templates:
1. Opening hours: the poster says 8:00am to 10:00pm daily, the banner says "24/7 service". Hours are therefore not shown on the site.
2. Full street address, directions and map location.
3. Emergency arrangements: line, hours, ambulance. Until confirmed, pages only direct people to the nearest emergency facility or emergency services.
4. Which homecare services NexaCare actually provides, coverage area, fees. Homecare wording is framed as "what families can ask about".
5. Which tests, procedures and family-planning methods are offered; telemedicine method.
6. Staff: names, titles, qualifications, registration, portraits and consent to publish. The supplied doctor photographs are used as images only; confirm they show NexaCare staff, or replace them.
7. A genuine photograph of homecare for the homecare hero (an older adult being cared for at home, taken or licensed with consent). The current hero uses a supplied portrait. Other wanted photos: consultation, nurse and patient, laboratory, pharmacy, mother-and-baby clinic, physiotherapy, building exterior.
8. Mission, vision and values (removed because they were unconfirmed), WhatsApp number, social links, domain name.
9. Data controller details, retention period, who reads enquiries, registration with the Data Protection Commissioner.
10. Clinical review and live check of the health-library source links; no article is claimed as medically reviewed.

## Test record (16 October 2026)
Done (latest round): 30 pages build; checker clean; viewport screenshots of header, hero and Services grid reviewed against the references by eye; all four widths re-tested (no overflow, sticky header, anchors, forms, failure handling, keyboard, reduced motion). Earlier: 30 pages build; checker clean (including banned-placeholder scan); Chromium at 390, 768, 1024 and 1440 px: no horizontal overflow on 13 pages, no JavaScript errors, no failed local requests; sticky header stays at top with scroll shadow at all four widths; in-page anchors (#request) clear the header; desktop dropdown hover/click and mobile menu with Escape; homecare form invalid, success and simulated backend failure; first Tab focuses the skip link; reduced-motion shows content; API: valid, missing/foreign Origin, no consent, honeypot, bad phone, non-JSON, rate limit (including spoofed X-Forwarded-For), private folders return 404, CSP header present.
Not verified: appearance with the real Open Sans font and Font Awesome icons (blocked in the test sandbox); Safari/Firefox; screen-reader testing and full WCAG audit; live external source links; multi-worker production deployment.
