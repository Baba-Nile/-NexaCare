"""Checks the built site: internal links and anchors, image files, titles, descriptions, one h1, alt text.  Run: python python/check_site.py"""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import branches as BM
class P(HTMLParser):
    def __init__(s): super().__init__(); s.links, s.ids, s.h1, s.title, s.desc, s.noalt, s.imgs = [], set(), 0, "", "", 0, []; s._t = False
    def handle_starttag(s, t, a):
        a = dict(a)
        if "id" in a: s.ids.add(a["id"])
        if t == "a" and a.get("href"): s.links.append(a["href"])
        if t in ("link", "script", "img") and (a.get("href") or a.get("src")): s.imgs.append(a.get("href") or a.get("src"))
        if t == "img" and "alt" not in a: s.noalt += 1
        if t == "h1": s.h1 += 1
        if t == "title": s._t = True
        if t == "meta" and a.get("name") == "description": s.desc = a.get("content", "")
    def handle_endtag(s, t):
        if t == "title": s._t = False
    def handle_data(s, d):
        if s._t: s.title += d
pages = {f: P() for f in ROOT.rglob("*.html") if "python" not in f.relative_to(ROOT).parts}   # python/portal/templates are server templates, not public pages
for f, p in pages.items(): p.feed(f.read_text(encoding="utf-8"))
BANNED = ["to be confirmed", "being confirmed", "more profiles", "data/staff", "tbc", "todo", "lorem", "draft wording", "photo to be added", "clinical review"]
bad = []
for f, p in pages.items():
    rel = f.relative_to(ROOT)
    if rel.name != "404.html" and p.h1 != 1: bad.append(f"{rel}: {p.h1} h1 elements")
    if not p.title.strip() or not p.desc.strip(): bad.append(f"{rel}: missing title or description")
    txt = f.read_text(encoding="utf-8").lower()
    bad += [f"{rel}: public placeholder wording '{w}'" for w in BANNED if w in txt]
    if p.noalt: bad.append(f"{rel}: {p.noalt} img without alt")
    for l in p.links + p.imgs:
        u = urlparse(l)
        if u.scheme in ("http", "https", "mailto", "tel") or not (u.path or u.fragment): continue
        tgt = (ROOT / u.path.lstrip("/")) if u.path.startswith("/") else (f.parent / unquote(u.path)) if u.path else f
        if not tgt.exists(): bad.append(f"{rel}: broken link {l}"); continue
        if u.fragment and tgt.suffix == ".html" and u.fragment not in pages[tgt.resolve() if tgt.resolve() in pages else tgt].ids: bad.append(f"{rel}: missing anchor {l}")

# ---------- branch rules ----------
data = BM.load(); site = json.loads((ROOT / "data" / "site.json").read_text(encoding="utf-8"))
bad += [f"data/branches.json: {x}" for x in BM.validate(data)]
nav_links = lambda f: pages[f].links
hub = ROOT / "branches" / "index.html"
central_tel = "tel:" + site["phone_tel"]
if not hub.exists(): bad.append("branches/index.html is missing")
titles, descs = {}, {}
for b in data["branches"]:
    f = ROOT / "branches" / f"{b['slug']}.html"
    if not f.exists(): bad.append(f"branch page missing: branches/{b['slug']}.html"); continue
    txt = f.read_text(encoding="utf-8"); p = pages[f]
    if p.title in titles: bad.append(f"duplicate title: {f.name} and {titles[p.title]}")
    if p.desc in descs: bad.append(f"duplicate description: {f.name} and {descs[p.desc]}")
    titles[p.title], descs[p.desc] = f.name, f.name
    if BM.indexable(b) == ('name=robots content=noindex' in txt.replace('"', '')): bad.append(f"{f.name}: robots meta does not match branch status")
    ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', txt, re.S)
    if len(ld) < 2: bad.append(f"{f.name}: structured data missing")
    for blob in ld:
        try: j = json.loads(blob)
        except ValueError: bad.append(f"{f.name}: structured data is not valid JSON"); continue
        if j.get("@type") == "MedicalClinic":
            if not BM.value(b, "phone") and "telephone" in j: bad.append(f"{f.name}: structured data shows an unverified telephone")
            if not BM.value(b, "address") and "streetAddress" in json.dumps(j): bad.append(f"{f.name}: structured data shows an unverified address")
            if not BM.coordinates(b) and "geo" in j: bad.append(f"{f.name}: structured data shows unverified coordinates")
            if not BM.value(b, "hours") and "openingHours" in j: bad.append(f"{f.name}: structured data shows unverified opening hours")
    # nothing unverified may be published on the branch's own page
    if not BM.value(b, "phone") and [l for l in p.links if l.startswith("tel:") and l != central_tel]: bad.append(f"{f.name}: a telephone link other than the central line")
    if not BM.value(b, "whatsapp") and ("wa.me" in txt or "whatsapp" in txt.lower().replace("fa-whatsapp", "")): bad.append(f"{f.name}: WhatsApp shown without a verified number")
    if not BM.value(b, "directions") and ("google.com/maps" in txt or "<iframe" in txt): bad.append(f"{f.name}: map or directions shown without verification")
    if not BM.value(b, "services") and "Services at this branch" in txt: bad.append(f"{f.name}: unverified services listed")
    rel = f"branches/{b['slug']}.html"
    for src in ("index.html", "branches/index.html", "contact.html", "appointments.html"):
        if src == "appointments.html": continue
        if not any(l.endswith(rel) or l.endswith(f"/{b['slug']}.html") for l in nav_links(ROOT / src)): bad.append(f"{src} does not link to {rel}")
    if not any(l.endswith(f"appointments.html?branch={b['slug']}") for l in nav_links(hub)): bad.append(f"branches/index.html has no appointment link for {b['slug']}")
# every page: main navigation includes the branches page and the appointment button; no inline styles (CSP); branch dropdown complete
want_opts = [b["slug"] for b in data["branches"]] + [data["main_centre"]["slug"], BM.NO_PREFERENCE]
for f, p in pages.items():
    rel = f.relative_to(ROOT); txt = f.read_text(encoding="utf-8")
    if rel.name != "404.html":
        if not any(l.endswith("branches/index.html") for l in p.links): bad.append(f"{rel}: no link to the branches page")
        if "Request Appointment" not in txt: bad.append(f"{rel}: navigation lacks the Request Appointment button")
    if re.search(r'\sstyle="', txt): bad.append(f"{rel}: inline style attribute (blocked by the site CSP)")
    for form_html in re.findall(r'<form class="form".*?</form>', txt, re.S):
        sel = re.search(r'<select id="[^"]+" name="branch".*?</select>', form_html, re.S)
        if not sel: bad.append(f"{rel}: enquiry form without a branch field"); continue
        vals = re.findall(r'<option value="([^"]*)"', sel.group(0))
        if [v for v in vals if v] != want_opts: bad.append(f"{rel}: branch options differ from data/branches.json")
# sitemap lists exactly the indexable pages
sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
listed = set(re.findall(r"<loc>https://[^/]+/(.*?)</loc>", sm))
expect = {str(f.relative_to(ROOT)).replace("\\", "/") for f, p in pages.items() if f.name != "404.html" and "noindex" not in f.read_text(encoding="utf-8")[:3000]}
if listed != expect: bad.append(f"sitemap.xml differs from indexable pages: only in sitemap {sorted(listed - expect)}; missing {sorted(expect - listed)}")
rb = (ROOT / "robots.txt").read_text(encoding="utf-8")
for need in ("Sitemap:", "Disallow: /staff/", "Disallow: /portal/"):
    if need not in rb: bad.append(f"robots.txt lacks '{need}'")
print(f"Checked {len(pages)} pages.")
print("\n".join(bad) if bad else "No problems found.")
sys.exit(1 if bad else 0)
