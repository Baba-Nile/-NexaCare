#!/usr/bin/env python3
"""Generates the static NexaCare public website from data/*.json so header, footer and templates stay identical on every page.
Run from anywhere:  python python/build.py   (no third-party packages needed)

Data sources:  data/site.json (central contact + facts)   data/branches.json (all branches, verified-only publishing)
               data/services.json   data/health-topics.json   data/staff.json   data/image-manifest.json
Branch details are never typed into templates: every branch fact comes from data/branches.json through python/branches.py,
and appears only when its 'verified' flag is true."""
import hashlib, html, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import branches as BM

ROOT = BM.ROOT
D = ROOT / "data"
load = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
SITE, SERV, TOP, STAFF = load("site.json"), load("services.json"), load("health-topics.json"), load("staff.json")
BDATA = BM.load()
MAIN, BRS = BDATA["main_centre"], BDATA["branches"]
ALLB = [MAIN] + BRS
BB = {b["slug"]: b for b in ALLB}
TEAM = [p for p in STAFF if p.get("published") and p.get("name") and p.get("photo")]   # only verified, approved profiles appear
esc = html.escape
CUR, R = "", ""
PAGES = []                      # (path, indexable)
SV = {s["slug"]: s for s in SERV}
TP = {t["slug"]: t for t in TOP}
PHONE, TEL, MAIL = SITE["phone"], SITE["phone_tel"], SITE["email"]
NB = len(BRS)
LOC = esc(SITE["locality"])
MAIN_BADGE = ' <span class="badge badge--main">Main centre</span>'
NUMWORD = {6: "six", 5: "five", 7: "seven", 4: "four", 8: "eight"}.get(NB, str(NB))

_problems = BM.validate(BDATA, set(SV))
if _problems:
    print("data/branches.json has problems:\n  " + "\n  ".join(_problems)); sys.exit(1)

# ---------- image manifest (editable; set "file" then re-run build) ----------
def default_manifest():
    ph = {"status": "tile fallback", "source": "TBC", "credit": "TBC", "license": "TBC"}
    sup = lambda f, w, h, alt: {"file": f, "w": w, "h": h, "alt": alt, "status": "supplied by client", "source": "Client-supplied photograph; confirm licence and permission to publish", "credit": "NexaCare", "license": "Client-owned (to confirm)"}
    s = {"duo": sup("assets/images/hero/care-team-hero.jpg", 960, 1120, "A doctor and a nurse standing together in a hospital ward"),
         "doctor-corridor": sup("assets/images/doctors/doctor-corridor.jpg", 800, 1005, "A doctor in a white coat holding a clipboard in a hospital corridor"),
         "doctor-clipboard": sup("assets/images/doctors/doctor-clipboard.jpg", 800, 1011, "A doctor in a white coat writing notes on a clipboard"),
         "doctor-studio": sup("assets/images/doctors/doctor-studio.jpg", 800, 1067, "A doctor in a white coat with a stethoscope"),
         "hero-banner (CSS background)": sup("assets/images/hero/hero-banner.jpg", 1920, 520, "Composite made from the corridor photograph")}
    for x in SERV: s["service-" + x["slug"]] = {"file": None, "icon": x["icon"], **ph}
    owner = lambda f, w, h, alt: {**sup(f, w, h, alt), "status": "supplied by site owner", "source": "Supplied by the site owner; licence and permission to publish to be confirmed", "credit": "TBC", "license": "TBC"}
    child = owner("assets/images/services/nurse-child-checkup.jpg", 738, 414, "A smiling nurse listening to a young child's chest with a stethoscope")
    bp = owner("assets/images/services/blood-pressure-check.jpg", 576, 432, "A nurse checking an older man's blood pressure in a clinic room")
    s["photo-nurse-child"], s["photo-blood-pressure"] = child, bp
    for t in TOP: s["topic-" + t["slug"]] = {"file": None, "icon": t["icon"], **ph}
    s["service-outpatient"].update(bp); s["topic-hypertension"].update(bp); s["service-maternal-child-health"].update(child); s["topic-child-health"].update(child)
    for k in ("homecare-hero", "homecare-visit", "homecare-family"): s[k] = {"file": None, "icon": "fa-house-medical", **ph}
    for b in ALLB: s[b["photo_slot"]] = {"file": None, "icon": "fa-location-dot", **ph, "note": "Add a real photograph of this branch (exterior or reception) with permission to publish."}
    return {"_note": "Set 'file' (path from the site root), 'w', 'h', 'alt' to replace a tile with a real photo, then run python/build.py. Never present stock photos as NexaCare staff, patients or premises.", "slots": s}
MF = D / "image-manifest.json"
IMG = json.loads(MF.read_text(encoding="utf-8")) if MF.exists() else default_manifest()
for k, v in default_manifest()["slots"].items(): IMG["slots"].setdefault(k, v)
MF.write_text(json.dumps(IMG, indent=1, ensure_ascii=False), encoding="utf-8")

RATIO = {"1/1": "1x1", "4/3": "4x3", "3/2": "3x2", "16/9": "16x9", "4/5": "4x5", "21/9": "21x9"}
POSN = {"top": "pos-top", "mid": "pos-mid"}

def has_photo(slot):
    m = IMG["slots"].get(slot, {})
    return bool(m.get("file") and (ROOT / m["file"]).exists())

def photo(slot, alt="", ar=None, cls="photo", pos=None, eager=False):
    """Real photo (WebP when available) if the manifest has one, otherwise a brand tile. No inline styles (the site CSP forbids them)."""
    m = IMG["slots"].get(slot, {})
    c = " ".join([cls] + ([f"ar-{RATIO[ar]}"] if ar else []) + ([POSN[pos]] if pos else []))
    if has_photo(slot):
        f = m["file"]; webp = (ROOT / f).with_suffix(".webp")
        attrs = f'class="{c}" src="{R}{f}" alt="{esc(m.get("alt") or alt)}" width="{m.get("w", "")}" height="{m.get("h", "")}"' + (' fetchpriority="high" decoding="async"' if eager else ' loading="lazy" decoding="async"')
        img = f"<img {attrs}>"
        if webp.exists():
            wp = f"{R}{Path(f).with_suffix('.webp').as_posix()}"
            return f'<picture><source type="image/webp" srcset="{wp}">{img}</picture>'
        return img
    return f'<div class="tile {c}" role="img" aria-label="{esc(alt)}"><i class="fa-solid {m.get("icon", "fa-notes-medical")}" aria-hidden="true"></i></div>'

# ---------- helpers ----------
ico = lambda n: f'<i class="fa-solid {n}" aria-hidden="true"></i>'
icon_html = lambda n: f'<i class="{n}" aria-hidden="true"></i>' if n.startswith("fa-brands") else ico(n)
ul = lambda items: "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"
dots = lambda items: '<ul class="dot-list">' + "".join(f'<li>{ico("fa-circle-check")}<span>{esc(i)}</span></li>' for i in items) + "</ul>"
surl = lambda s: R + (s.get("page") or f"services/{s['slug']}.html")
turl = lambda t: f"{R}health-library/{t['slug']}.html"
HUB = "branches/index.html"
def burl(b): return f"{R}{HUB}#{b['slug']}" if b["role"] == "main_centre" else f"{R}branches/{b['slug']}.html"
def bname(b): return b["name"] if b["role"] == "main_centre" else f"NexaCare {b['name']}"
def book_url(b=None): return f"{R}appointments.html" + (f"?branch={b['slug']}" if b else "")
def title_block(h, p="", center=False, kicker=""):
    k = f'<span class="eyebrow">{esc(kicker)}</span>' if kicker else ""
    return f'<div class="section-title{" section-title--center" if center else ""}">{k}<h2>{h}</h2>{f"<p>{p}</p>" if p else ""}</div>'
def sec(inner, cls="", id=""):
    return f'<section class="section {cls}"{f" id={chr(34)}{id}{chr(34)}" if id else ""}><div class="container reveal">{inner}</div></section>'
def crumbs(trail):
    li = "".join(f'<li><a href="{R}{u}">{esc(n)}</a></li>' for n, u in trail[:-1]) + f'<li aria-current="page">{esc(trail[-1][0])}</li>'
    return f'<nav class="breadcrumb" aria-label="Breadcrumb"><ol><li><a href="{R}index.html">Home</a></li>{li}</ol></nav>'
def banner(title, trail, lede=""):
    return f'<section class="page-hero"><div class="container">{crumbs(trail)}<h1>{esc(title)}</h1>{f"<p class={chr(34)}page-hero__lede{chr(34)}>{lede}</p>" if lede else ""}</div></section>'
def cta_strip(text="Need care? Request an appointment at the branch that suits you.", btn="Request appointment", href="appointments.html", alt=True):
    second = f'<a class="btn btn--ghost-light" href="{R}{HUB}">Find a branch</a>' if alt else ""
    return f'<section class="cta-strip"><div class="container"><p>{text}</p><div class="btn-row"><a class="btn btn--white" href="{R}{href}">{btn}</a>{second}</div></div></section>'
DISC = "This page gives general health information in plain language. It does not diagnose, and it does not replace advice from a qualified health professional."
def faq_list(items):
    return '<div class="faq">' + "".join(f"<details><summary>{esc(q)}</summary><div><p>{a}</p></div></details>" for q, a in items) + "</div>"
def central_line(cls="", label=True):
    lab = f'{esc(SITE.get("central_label", "Central line"))}: ' if label else ""
    return f'<a class="{cls}" href="tel:{TEL}">{lab}{PHONE}</a>'

# ---------- forms ----------
def field(f, p):
    n, i = f["name"], f"{p}-{f['name']}"; t = f.get("type", "text"); req = " required" if f.get("req") else ""
    hint = f'<p class="hint" id="{i}-h">{esc(f["hint"])}</p>' if f.get("hint") else ""
    d = f' aria-describedby="{i}-h"' if f.get("hint") else ""
    lab = f'<label for="{i}">{esc(f["label"])}{"" if f.get("req") else " <span class=opt>(optional)</span>"}</label>'
    if t == "select":
        sel = f.get("selected")
        opts = "".join(f'<option value="{esc(v)}"{" selected" if v == sel else ""}>{esc(l)}</option>' for v, l in f["options"])
        ph = f'<option value="">{esc(f.get("ph", "Choose one"))}</option>' if f.get("req") else ""
        c = f'{lab}<select id="{i}" name="{n}"{req}{d}>{ph}{opts}</select>'
    elif t == "textarea":
        c = f'{lab}<textarea id="{i}" name="{n}" maxlength="600"{req}{d}></textarea>'
    elif t == "radio":
        rs = "".join(f'<label><input type="radio" name="{n}" value="{esc(v)}"{" checked" if k == 0 else ""}> {esc(v)}</label>' for k, v in enumerate(f["options"]))
        c = f'<fieldset class="radio-group"><legend>{esc(f["label"])}</legend>{rs}</fieldset>'
    elif t == "check":
        return f'<div class="field check full"><input type="checkbox" id="{i}" name="{n}"{req}{d}><label for="{i}">{f["label"]}</label></div>'
    else:
        pat = ' pattern="[0-9+()\\s\\-]{7,20}" inputmode="tel" autocomplete="tel"' if t == "tel" else ""
        ac = ' autocomplete="name"' if n in ("name", "requester_name") else (' autocomplete="email"' if t == "email" else "")
        c = f'{lab}<input id="{i}" name="{n}" type="{t}"{pat}{ac} maxlength="120"{req}{d}>'
    sh = f' data-showif="{f["showif"]}" hidden' if f.get("showif") else ""
    return f'<div class="field{" full" if f.get("full") else ""}"{sh}>{c}{hint}</div>'
SVC_OPTS = [(s["slug"], s["title"]) for s in SERV] + [("not-sure", "I am not sure")]
TIMES = [("No preference", "No preference"), ("Morning", "Morning"), ("Afternoon", "Afternoon"), ("Evening", "Evening")]
CM = ["Phone call", "Text message", "Email"]
CONSENT = lambda: f'I agree that NexaCare may use these details to respond to my request, as described in the <a href="{R}privacy.html">privacy notice</a>.'
def branch_options(none_label):
    """Every branch, then the main centre, then the 'no preference' choice. Values are slugs from data/branches.json."""
    return [(b["slug"], b["name"]) for b in BRS] + [(MAIN["slug"], f'{MAIN["name"]} (main centre)'), (BM.NO_PREFERENCE, none_label)]
def branch_field(req=False, label="Preferred branch", none_label="No preference", selected=None, hint=None, full=False):
    return dict(name="branch", label=label, type="select", options=branch_options(none_label), req=req, ph="Choose a branch", selected=selected or (None if req else BM.NO_PREFERENCE), hint=hint, full=full)
def form(kind, fields, p, label="Send request", success="", sq=False):
    body = "".join(field(f, p) for f in fields)
    need = ' data-need-one="phone,email"' if kind == "contact" else ""
    return (f'<form class="form" data-enquiry="{kind}" data-success="{esc(success)}" novalidate{need}>{body}'
            f'<div class="hp" aria-hidden="true"><label>Leave this empty<input class="hp-input" type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
            f'<noscript><p class="noscript-note">This form needs JavaScript. Please call <a href="tel:{TEL}">{PHONE}</a> or email <a href="mailto:{MAIL}">{MAIL}</a> instead.</p></noscript>'
            f'<div class="form-status" role="status" aria-live="polite" hidden></div>'
            f'<div class="form__btn"><button class="btn btn--primary btn--lg" type="submit">{ico("fa-paper-plane")} {label}</button></div></form>')
def appt_fields(branch=None):
    return [dict(name="name", label="Full name", req=1), dict(name="phone", label="Telephone number", type="tel", req=1),
            branch_field(req=True, label="Preferred branch", none_label="No preference: help me choose", selected=branch, full=True, hint="Not sure? Choose \u201cNo preference\u201d and the team will help you pick a branch."),
            dict(name="email", label="Email", type="email"), dict(name="service", label="Service needed", type="select", options=SVC_OPTS, req=1),
            dict(name="date", label="Preferred date", type="date"), dict(name="time", label="Preferred time of day", type="select", options=TIMES),
            dict(name="area", label="General area for the home visit", showif="service=homecare", full=1, hint="Town or estate only. We will ask for the exact address when we call."),
            dict(name="contact_method", label="How should we contact you?", type="radio", options=CM, full=1),
            dict(name="message", label="Brief note", type="textarea", full=1, hint="Keep this general. Please do not include medical history, ID numbers or results."),
            dict(name="consent", label=CONSENT(), type="check", req=1)]
HC_TYPES = ["Elderly care and daily living assistance", "Nursing visit", "Post-hospital recovery support", "Mobility assistance and physiotherapy", "Medication support (within professional authorisation)", "Mother and baby visit", "Family caregiver guidance", "General homecare enquiry"]
def homecare_fields():
    return [dict(name="requester_name", label="Your name", req=1), dict(name="phone", label="Telephone number", type="tel", req=1),
            dict(name="contact_method", label="Preferred way to be contacted", type="radio", options=CM, full=1),
            dict(name="contact_time", label="Best time to contact you", type="select", options=TIMES),
            dict(name="relationship", label="Your relationship to the person needing care", hint="For example: daughter, son, neighbour, or myself."),
            dict(name="care_type", label="Type of support you are asking about", type="select", req=1, options=[(c, c) for c in HC_TYPES] + [("Not sure", "I am not sure")], full=1),
            dict(name="age_group", label="Age group of the person needing care", type="select", options=[("Not given", "Prefer not to say"), ("Child", "Child"), ("Adult", "Adult"), ("Older adult", "Older adult (65 or over)")]),
            branch_field(label="Nearest NexaCare branch", none_label="Not sure: help me choose"),
            dict(name="area", label="Location or estate", req=1, hint="Town or estate only. We will ask for the exact address when we speak.", full=1),
            dict(name="message", label="Anything else we should know", type="textarea", full=1, hint="Keep this brief and general. Please do not send medical records or detailed health information."),
            dict(name="consent", label=CONSENT(), type="check", req=1)]
def contact_fields(branch=None, pre="ct"):
    return [dict(name="name", label="Your name", req=1), dict(name="email", label="Your email", type="email"), dict(name="phone", label="Phone", type="tel"),
            branch_field(label="Which branch is this about?", none_label="Not about a specific branch", selected=branch),
            dict(name="message", label="Your message", type="textarea", req=1, full=1, hint="Please do not include medical history or ID numbers."),
            dict(name="consent", label=CONSENT(), type="check", req=1)]


# ---------- shell: navigation, header, footer ----------
def sub(key, label, href, items, allt, active, wide=False):
    cur = ' aria-current="page"' if active == key else ""
    return (f'<li class="has-sub"><div class="nav__row"><a href="{R}{href}"{cur}>{label}</a><button class="sub-toggle" type="button" aria-expanded="false" aria-controls="sub-{key}" aria-label="{label}: open submenu">{ico("fa-chevron-down")}</button></div>'
            f'<ul class="sub{" sub--wide" if wide else ""}" id="sub-{key}">{items}<li class="sub__all"><a href="{R}{href}">{allt} {ico("fa-arrow-right")}</a></li></ul></li>')
def navhtml(active):
    cur = lambda k: ' aria-current="page"' if active == k else ""
    svc = "".join(f'<li><a href="{surl(s)}">{esc(s["title"])}</a></li>' for s in SERV)
    bra = "".join(f'<li><a href="{burl(b)}">{esc(b["name"])}</a></li>' for b in BRS) + f'<li><a href="{burl(MAIN)}">{esc(MAIN["name"])} <span class="sub__tag">Main centre</span></a></li>'
    top = "".join(f'<li><a href="{turl(t)}">{esc(t["title"])}</a></li>' for t in TOP)
    team = f'<li><a href="{R}our-team.html"{cur("team")}>Our Team</a></li>' if TEAM else ""
    return (f'<nav aria-label="Main"><ul class="nav__list"><li><a href="{R}index.html"{cur("home")}>Home</a></li><li><a href="{R}about.html"{cur("about")}>About Us</a></li>'
            f'{sub("services", "Services", "services.html", svc, "All services", active, True)}{sub("branches", "Our Branches", HUB, bra, "All branches", active)}'
            f'<li><a href="{R}homecare.html"{cur("homecare")}>Homecare</a></li>{team}{sub("library", "Health Library", "health-library/index.html", top, "Browse the library", active)}'
            f'<li><a href="{R}faq.html"{cur("faq")}>FAQs</a></li><li><a href="{R}contact.html"{cur("contact")}>Contact Us</a></li></ul></nav>')
def header(active):
    lg = SITE["logo"]["header"]
    return (f'<a class="skip-link" href="#main">Skip to main content</a>'
            f'<div class="topbar"><div class="container topbar__in"><p class="topbar__left"><a href="tel:{TEL}">{ico("fa-phone")}<span class="hide-sm">{esc(SITE.get("central_label", "Central line"))}: </span>{PHONE}</a>'
            f'<a class="hide-sm" href="mailto:{MAIL}">{ico("fa-envelope")}{MAIL}</a></p>'
            f'<p class="topbar__right"><a href="{R}{HUB}">{ico("fa-location-dot")}{NUMWORD.capitalize()} branches: find yours</a></p></div></div>'
            f'<header class="site-header"><div class="container header__in"><a class="brand" href="{R}index.html"><img src="{R}assets/images/logo/nexacare-logo-header.png" alt="NexaCare Health Centre, home" width="{lg[0]}" height="{lg[1]}"></a>'
            f'<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">{ico("fa-bars")}<span class="nav-toggle__label">Menu</span></button>'
            f'<div class="navbar" id="site-nav">{navhtml(active)}<a class="navbar__cta" href="{R}appointments.html">{ico("fa-calendar-check")} Request Appointment</a></div></div></header>')
def footer():
    links = [("About Us", "about.html"), ("Services", "services.html"), ("Our Branches", HUB), ("Homecare", "homecare.html"), ("Health Library", "health-library/index.html"), ("FAQs", "faq.html"), ("Contact Us", "contact.html"), ("Request Appointment", "appointments.html"), ("Privacy and cookies", "privacy.html"), ("Website terms", "terms.html")]
    if TEAM: links.insert(1, ("Our Team", "our-team.html"))
    li = "".join(f'<li><a href="{R}{u}">{n}</a></li>' for n, u in links)
    bl = "".join(f'<li><a href="{burl(b)}">{esc(b["name"])}</a></li>' for b in BRS) + f'<li><a href="{burl(MAIN)}">{esc(MAIN["name"])} <span class="muted-light">(main centre)</span></a></li>'
    ff = form("contact", [dict(name="name", label="Your name", req=1), dict(name="phone", label="Telephone", type="tel", req=1), branch_field(label="Branch", none_label="Not about a specific branch"),
                          dict(name="message", label="Message", type="textarea", req=1, full=1), dict(name="consent", label=CONSENT(), type="check", req=1)], "ft", "Send message", "We will reply using the details you gave.")
    msg = f'<details class="footer__msg"><summary>{ico("fa-envelope-open-text")} Send us a message</summary>{ff}</details>' if CUR not in ("contact.html", "appointments.html", "homecare.html") else ""
    return (f'<footer class="site-footer"><div class="container footer__grid"><div class="footer__brand"><img src="{R}assets/images/logo/nexacare-logo-header.png" alt="" width="{SITE["logo"]["header"][0]}" height="{SITE["logo"]["header"][1]}" loading="lazy">'
            f'<p>{esc(SITE["tagline"])}. NexaCare Health Centre offers outpatient care, maternal and child health, laboratory and pharmacy services, homecare and more across {NUMWORD} branches and a main centre in {esc(SITE["locality"])}.</p>'
            f'<p class="footer__note">In an emergency, go to the nearest emergency facility or call emergency services. Website forms are not for urgent problems.</p></div>'
            f'<div><h2>Our branches</h2><ul class="footer__list">{bl}</ul></div><div><h2>Quick links</h2><ul class="footer__list footer__list--cols">{li}</ul></div>'
            f'<div><h2>Contact</h2><ul class="footer__contact"><li>{ico("fa-phone")}<span>{esc(SITE.get("central_label", "Central line"))}<br><a href="tel:{TEL}">{PHONE}</a></span></li><li>{ico("fa-envelope")}<span>Email<br><a href="mailto:{MAIL}">{MAIL}</a></span></li>'
            f'<li>{ico("fa-location-dot")}<span>Main centre<br>{esc(SITE["locality"])}</span></li></ul><p class="footer__small">Branch telephone numbers and addresses are added to each branch page once published.</p>{msg}</div></div>'
            f'<div class="footer__bar"><div class="container"><p>&copy; {SITE["build_date"][-4:]} {esc(SITE["name"])}. All rights reserved.</p><ul class="footer__legal"><li><a href="{R}privacy.html">Privacy</a></li><li><a href="{R}terms.html">Terms</a></li></ul></div></div></footer>'
            f'<nav class="mobile-bar" aria-label="Quick actions"><a href="tel:{TEL}">{ico("fa-phone")}<span>Call</span></a><a href="{R}{HUB}">{ico("fa-location-dot")}<span>Branches</span></a><a class="mobile-bar__main" href="{R}appointments.html">{ico("fa-calendar-check")}<span>Book</span></a></nav>')

_assets = hashlib.md5(b"".join(p.read_bytes() for p in sorted((ROOT / "assets").glob("css/site.css")) + sorted((ROOT / "assets").glob("js/*.js")))).hexdigest()[:8]
def shell(title, desc, body, active="", index=True, ld="", full_title=False, head_extra=""):
    path = CUR
    t = title if full_title else f"{title} | {SITE['name']}"
    canon = f'<link rel="canonical" href="https://{SITE["domain"]}/{path}">' if SITE["domain"] else ""
    PAGES.append((path, index))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(t)}</title>'
            f'<meta name="description" content="{esc(desc)}">{"" if index else "<meta name=robots content=noindex>"}{canon}<meta name="theme-color" content="#0F766E">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="{esc(SITE["name"])}"><meta property="og:title" content="{esc(t)}"><meta property="og:description" content="{esc(desc)}">'
            f'<meta name="nexacare-api" content="/api/enquiry"><meta name="nexacare-phone" content="{PHONE}"><meta name="nexacare-tel" content="{TEL}">'
            f'<link rel="icon" type="image/png" href="{R}assets/images/logo/favicon.png"><link rel="apple-touch-icon" href="{R}assets/images/logo/apple-touch-icon.png">'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
            f'<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" crossorigin="anonymous" referrerpolicy="no-referrer">'
            f'<link rel="stylesheet" href="{R}assets/css/site.css?v={_assets}">{head_extra}'
            f'<script>document.documentElement.classList.add("js")</script>{ld}</head><body>{header(active)}<main id="main">{body}</main>{footer()}'
            + "".join(f'<script src="{R}assets/js/{j}.js?v={_assets}" defer></script>' for j in ("main", "navigation", "forms", "interactions", "branches")) + '</body></html>')
def out(path, content):
    p = ROOT / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8")
def setr(path):
    global R, CUR; R = "../" * path.count("/"); CUR = path

# ---------- blocks ----------
def svc_card(s):
    return f'<a class="svc" href="{surl(s)}"><span class="svc__icon">{ico(s["icon"])}</span><h3>{esc(s["title"])}</h3><p>{esc(s["short"])}</p><span class="svc__more">Learn more {ico("fa-arrow-right")}</span></a>'
def acard(t, feature=False):
    cls = "acard acard--feature" if feature else "acard"
    return (f'<article class="{cls}"><a class="acard__img" href="{turl(t)}" tabindex="-1" aria-hidden="true">{photo("topic-" + t["slug"], t["title"], "3/2", pos="mid")}</a><div class="acard__body"><span class="tag">{esc(t["tag"])}</span><h3><a href="{turl(t)}">{esc(t["title"])}</a></h3>'
            f'<p>{esc(t["what"].split(". ")[0].rstrip("."))}.</p><span class="acard__meta">{ico("fa-book-medical")} Health guide</span></div></article>')
def staff_card(p):
    return f'<a class="tcard" href="{R}team/{p["slug"]}.html"><img src="{R}{p["photo"]}" alt="{esc(p.get("photo_alt") or p["name"])}" width="800" height="1005" loading="lazy"><div class="tcard__body"><h3>{esc(p["name"])}</h3><p>{esc(p.get("title", ""))}</p></div></a>'
def branch_visual(b):
    if has_photo(b["photo_slot"]): return photo(b["photo_slot"], f"{bname(b)}", "3/2", "bphoto")
    i = ALLB.index(b) % 3
    return f'<div class="bvisual bvisual--{i}" aria-hidden="true"><span class="bvisual__pin">{ico("fa-location-dot")}</span><span class="bvisual__name">{esc(b["name"])}</span></div>'
def svc_titles(slugs_): return [SV[x]["title"] for x in slugs_ if x in SV]
def branch_card(b, hub=False):
    """One consistent card per branch. Only verified facts are shown; otherwise the central line is offered."""
    main = b["role"] == "main_centre"
    loc, addr, ph, hrs, svc, dirs, wa = (BM.value(b, k) for k in ("locality", "address", "phone", "hours", "services", "directions", "whatsapp"))
    row = lambda i, inner: f'<li>{ico(i)}<span>{inner}</span></li>'
    facts = []
    if addr or loc: facts.append(row("fa-location-dot", esc(addr or loc)))
    if ph: facts.append(row("fa-phone", f'<a href="tel:{ph["tel"]}">{esc(ph["display"])}</a>'))
    else: facts.append(row("fa-phone", f'{esc(SITE.get("central_label", "Central line"))}: <a href="tel:{TEL}">{PHONE}</a>'))
    if hrs: facts.append(row("fa-clock", esc(hrs[0])))
    if svc: facts.append(row("fa-stethoscope", esc(", ".join(svc_titles(svc)[:3])) + (" and more" if len(svc) > 3 else "")))
    pend = "" if (addr or ph or hrs) or main else '<p class="bcard__pending">This branch&rsquo;s own address, telephone and hours will appear here once published.</p>'
    acts = [] if main else [f'<a class="btn btn--primary btn--sm" href="{burl(b)}">View branch</a>']
    acts.append(f'<a class="btn btn--outline btn--sm" href="{book_url(b)}">Request appointment</a>')
    if dirs: acts.append(f'<a class="btn btn--ghost btn--sm" href="{esc(dirs)}" target="_blank" rel="noopener">{ico("fa-diamond-turn-right")} Directions<span class="sr-only"> to {esc(bname(b))} (opens in a new tab)</span></a>')
    if wa: acts.append(f'<a class="btn btn--ghost btn--sm" href="https://wa.me/{wa["number"]}" target="_blank" rel="noopener"><i class="fa-brands fa-whatsapp" aria-hidden="true"></i> WhatsApp<span class="sr-only"> {esc(bname(b))} (opens in a new tab)</span></a>')
    blob = " ".join([b["name"], loc or "", addr or "", " ".join(svc_titles(svc or [])), "main centre" if main else "branch"]).lower()
    badge = '<span class="badge badge--main">Main centre</span>' if main else ""
    title = f'<a href="{burl(b)}">{esc(bname(b))}</a>' if not main else esc(bname(b))
    return (f'<article class="bcard{" bcard--main" if main else ""}" id="{b["slug"]}" data-branch data-search="{esc(blob)}"{" data-has-phone" if ph else ""}{" data-has-directions" if dirs else ""}><div class="bcard__media">{branch_visual(b)}{badge}</div>'
            f'<div class="bcard__body"><h3>{title}</h3><p class="bcard__loc">{ico("fa-location-dot")} {esc(loc or addr) if (loc or addr) else "Branch of NexaCare Health Centre"}</p>'
            f'<ul class="bcard__facts">{"".join(facts)}</ul>{pend}<div class="bcard__actions">{"".join(acts)}</div></div></article>')
def branch_chips(skip=None):
    return '<ul class="chips">' + "".join(f'<li><a href="{burl(b)}">{esc(b["name"])}</a></li>' for b in ALLB if b is not skip) + "</ul>"


# ---------- pages ----------
HOME_SERVICES = ("outpatient", "maternal-child-health", "laboratory", "pharmacy", "family-planning", "homecare", "physiotherapy", "telemedicine")
def finder_select(idp="find"):
    opts = "".join(f'<option value="{HUB if b is MAIN else "branches/" + b["slug"] + ".html"}{"#" + b["slug"] if b is MAIN else ""}">{esc(b["name"])}{" (main centre)" if b is MAIN else ""}</option>' for b in BRS + [MAIN])
    return (f'<form class="findbar__form only-js" data-branch-finder action="{R}{HUB}"><label class="sr-only" for="{idp}-branch">Choose a branch</label>'
            f'<select id="{idp}-branch" name="branch"><option value="">Choose a branch</option>{opts}</select><button class="btn btn--primary" type="submit">View branch</button></form>')

def home():
    setr("index.html")
    quick = form("quick", [dict(name="name", label="Your name", req=1), dict(name="phone", label="Telephone", type="tel", req=1), branch_field(req=True, label="Preferred branch", none_label="No preference: help me choose"),
                           dict(name="service", label="Service needed", type="select", options=SVC_OPTS, req=1), dict(name="consent", label=CONSENT(), type="check", req=1)], "q", "Request appointment",
                 "NexaCare will contact you to confirm. This is a request, not a confirmed appointment.")
    hero = (f'<section class="hero"><div class="container hero__in"><div class="hero__copy"><span class="eyebrow eyebrow--light">Healthcare across {NUMWORD} branches</span>'
            f'<h1>Modern medicine, <span>compassionate touch</span>, closer to you</h1>'
            f'<p class="hero__lead">Consultations, laboratory and pharmacy services, maternal and child health and care at home. Find your nearest NexaCare branch and request an appointment online.</p>'
            f'<div class="btn-row"><a class="btn btn--white btn--lg" href="appointments.html">{ico("fa-calendar-check")} Request appointment</a><a class="btn btn--ghost-light btn--lg" href="{HUB}">{ico("fa-location-dot")} Find a branch</a></div>'
            f'<ul class="hero__points"><li>{ico("fa-circle-check")} {NB} branches and a main centre in {esc(SITE["locality"])}</li><li>{ico("fa-circle-check")} Homecare and telemedicine enquiries</li><li>{ico("fa-circle-check")} Plain-language health guides</li></ul></div>'
            f'<div class="hero__media">{photo("duo", "A doctor and a nurse standing together in a hospital ward", "4/5", "hero__img", "top", eager=True)}'
            f'<div class="hero__badge">{ico("fa-location-dot")}<div><strong>{NB} branches</strong><span>Find the one nearest you</span></div></div></div></div></section>')
    find = (f'<section class="findbar" aria-label="Find a branch"><div class="container"><div class="findbar__in"><div class="findbar__text"><h2>Find your nearest branch</h2><p>Pick a location to see its details and request an appointment.</p></div>'
            f'{finder_select()}<a class="findbar__link only-nojs" href="{HUB}">See all branches</a><a class="findbar__link only-js" href="{HUB}">Search all branches {ico("fa-arrow-right")}</a></div></div></section>')
    intro = sec(f'<div class="split split--center"><div class="photo-frame">{photo("doctor-clipboard", "A doctor in a white coat writing notes on a clipboard", "4/5", pos="top")}</div>'
                f'<div>{title_block("One name, several places to get care", kicker="About NexaCare")}<p class="lead">NexaCare Health Centre serves patients from a main centre in {esc(SITE["locality"])} and {NUMWORD} branches. Choose the location that suits you, check its details and request an appointment in a few clicks.</p>'
                f'<p>Every visit starts with a respectful conversation. Not every service is available at every branch, so we confirm this with you when you book.</p>'
                f'<div class="btn-row"><a class="btn btn--primary" href="about.html">About NexaCare</a><a class="btn btn--outline" href="{HUB}">Our branches</a></div></div></div>')
    svcs = sec(f'<div class="section-head">{title_block("Our services", "Everyday healthcare, from a first consultation to support at home. Availability can vary by branch, so please ask when you book.", kicker="What we do")}'
               f'<a class="btn btn--outline" href="services.html">View all services</a></div><div class="grid grid--4">' + "".join(svc_card(SV[k]) for k in HOME_SERVICES) + "</div>", "section--alt")
    brs = sec(f'<div class="section-head">{title_block("Our branches", f"{NUMWORD.capitalize()} branches, plus our main centre in {LOC}. Choose yours to see its details.", kicker="Find care near you")}'
              f'<a class="btn btn--outline" href="{HUB}">Search all branches</a></div><div class="grid grid--3">' + "".join(branch_card(b) for b in BRS) + f'</div><div class="mainstrip">{ico("fa-building-columns")}<p><strong>Main centre:</strong> {esc(SITE["locality"])}. Walk in, or <a href="{book_url(MAIN)}">request an appointment</a>.</p>{central_line("btn btn--ghost btn--sm")}</div>')
    steps = [("Choose your branch", "Pick the NexaCare location that is easiest for you to reach."), ("Tell us what you need", "Share your name, telephone number and the service you are asking about."), ("We contact you", "The team calls to confirm a date and time. Your appointment is confirmed only when we do.")]
    book = sec(f'<div class="split split--center"><div>{title_block("Request an appointment in three steps", "No account needed. Share the basics and we will take it from there.", kicker="Appointments")}'
               f'<ol class="steps">' + "".join(f"<li><h3>{h}</h3><p>{p}</p></li>" for h, p in steps) + f'</ol><div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Urgent problem?</strong> Do not use this form. Go to the nearest emergency facility or call emergency services.</p></div></div>'
               f'<div class="form-card"><h3>Appointment request</h3>{quick}<p class="form-more"><a href="appointments.html">Need to add more details? Use the full appointment form {ico("fa-arrow-right")}</a></p></div></div>', "section--tint", "request")
    whys = [("fa-location-dot", "Choose your branch", f"{NUMWORD.capitalize()} locations to choose from, each with its own page and contact options."), ("fa-house-medical", "Care beyond the clinic", "Homecare and telemedicine enquiries for people who cannot easily travel."),
            ("fa-book-medical", "Clear information", "Plain-language health guides and honest answers about what to expect."), ("fa-phone", "Easy to reach", "Call, email or request an appointment online. The team contacts you to confirm.")]
    why = sec(f'<div class="split split--center"><div>{title_block("Why choose NexaCare", kicker="Our approach")}<div class="features">' + "".join(f'<div class="feature"><span class="feature__icon">{ico(i)}</span><div><h3>{h}</h3><p>{p}</p></div></div>' for i, h, p in whys) + f'</div></div>'
              f'<div class="collage">{photo("photo-nurse-child", "A smiling nurse listening to a young child\'s chest with a stethoscope", "4/3", "collage__a")}{photo("photo-blood-pressure", "A nurse checking an older man\'s blood pressure in a clinic room", "4/3", "collage__b")}</div></div>')
    guides = sec(f'<div class="section-head">{title_block("Patient information and useful links", "Helpful reading for patients and families.", kicker="Health library")}<a class="btn btn--outline" href="health-library/index.html">Browse the library</a></div>'
                 f'<div class="split split--aside"><div class="grid grid--3">' + "".join(acard(TP[k]) for k in ("hypertension", "child-health", "malaria")) + '</div>'
                 f'<aside class="linkbox"><h3>Useful links</h3><ul>' + "".join(f'<li><a href="{u}">{ico(i)} {n}</a></li>' for i, n, u in [("fa-clipboard-list", "Preparing for your visit", "faq.html#preparing"), ("fa-circle-question", "Frequently asked questions", "faq.html"), ("fa-house-medical", "Request homecare", "homecare.html#request"), ("fa-location-dot", "Find a branch", HUB), ("fa-shield-halved", "Privacy and cookies", "privacy.html")]) + '</ul></aside></div>', "section--alt")
    contact = (f'<section class="contact-band" id="contact"><div class="container reveal"><div class="contact-band__in"><div><span class="eyebrow eyebrow--light">Contact</span><h2>Talk to our team</h2><p>Call our central line, send an email or choose a branch. Branch telephone numbers are added to each branch page once published.</p>'
               f'<ul class="contact-lines"><li>{ico("fa-phone")}<span><strong>{esc(SITE.get("central_label", "Central line"))}</strong><a href="tel:{TEL}">{PHONE}</a></span></li><li>{ico("fa-envelope")}<span><strong>Email</strong><a href="mailto:{MAIL}">{MAIL}</a></span></li></ul>'
               f'<div class="btn-row"><a class="btn btn--white" href="contact.html">Contact us</a><a class="btn btn--ghost-light" href="appointments.html">Request appointment</a></div></div>'
               f'<div class="contact-band__branches"><h3>Choose a branch</h3>{branch_chips()}<p class="small-light">In an emergency, go to the nearest emergency facility or call emergency services.</p></div></div></div></section>')
    ld = '<script type="application/ld+json">' + json.dumps(org_ld(), ensure_ascii=False) + "</script>"
    out("index.html", shell(f"{SITE['name']} | {SITE['tagline']}", f"NexaCare Health Centre offers outpatient care, maternal and child health, laboratory, pharmacy, homecare and telemedicine across {NUMWORD} branches, with a main centre in {SITE['locality']}. Find a branch and request an appointment.",
                            hero + find + intro + svcs + brs + book + why + guides + contact, "home", ld=ld, full_title=True))

def abs_url(path): return f"https://{SITE['domain']}/{path}" if SITE["domain"] else None
def org_ld():
    d = {"@context": "https://schema.org", "@type": "MedicalOrganization", "name": SITE["name"], "slogan": SITE["tagline"], "telephone": SITE["phone"], "email": MAIL}
    if SITE["domain"]: d["url"] = abs_url("index.html")
    d["location"] = {"@type": "MedicalClinic", "name": f"{SITE['name']}, {MAIN['name']}", "address": {"@type": "PostalAddress", "addressLocality": "Kitale", "addressCountry": "KE"}}
    d["subOrganization"] = [dict({"@type": "MedicalClinic", "name": bname(b)}, **({"url": abs_url(f"branches/{b['slug']}.html")} if SITE["domain"] else {})) for b in BRS]
    return d

def services_dir():
    setr("services.html")
    b = (banner("Our services", [("Services", "services.html")], "Everyday healthcare under the NexaCare name.") + sec('<div class="notice">' + ico("fa-circle-info") + f'<p>Service availability can vary between branches. Please confirm with your branch when you book. <a href="{HUB}">Find a branch</a>.</p></div><div class="grid grid--4">' + "".join(svc_card(s) for s in SERV) + "</div>")
         + cta_strip("Not sure which service you need? Call us and we will point you in the right direction.", "Contact us", "contact.html"))
    out("services.html", shell("Our services", f"Outpatient consultations, maternal and child health, laboratory, pharmacy, family planning, emergency care, minor procedures, counselling, physiotherapy, homecare and telemedicine at NexaCare Health Centre.", b, "services"))

def service_page(s):
    if s.get("page"): return
    path = f"services/{s['slug']}.html"; setr(path)
    box = lambda i, h, items: f'<div class="aside__box"><h3>{ico(i)} {h}</h3>{dots(items)}</div>'
    em = f'<div class="alert-box"><h2>In an emergency</h2><p>Do not wait for an appointment or use a website form. Go to the nearest emergency facility or call emergency services now.</p></div>' if s.get("emergency") else ""
    rel = "".join(f'<li><a href="{surl(SV[r])}">{esc(SV[r]["title"])}</a></li>' for r in s["related"]) + "".join(f'<li><a href="{turl(TP[t])}">Guide: {esc(TP[t]["title"])}</a></li>' for t in s["topics"])
    intro = sec(f'<div class="split split--aside-img"><div class="photo-frame">{photo("service-" + s["slug"], s["title"], "4/3", pos="top")}</div><div>{title_block("About this service")}<p class="lead">{esc(s["intro"])}</p>{em}'
                f'<div class="btn-row"><a class="btn btn--primary" href="{R}appointments.html">Request appointment</a><a class="btn btn--outline" href="tel:{TEL}">{ico("fa-phone")} {PHONE}</a></div></div></div>')
    three = sec('<div class="grid grid--3">' + box("fa-list-check", "What to expect", s["expect"]) + box("fa-user-group", "Who it may be for", s["for"]) + box("fa-clipboard-check", "How to prepare", s["prepare"]) + "</div>", "section--alt")
    faq = sec(f'<div class="layout-aside"><div>{title_block("Frequently asked questions")}{faq_list(s["faqs"])}<p class="meta-line">{DISC} Specific tests and treatments vary, so please call to ask about your situation.</p></div>'
              f'<aside class="aside"><div class="aside__box"><h3>Related</h3><ul>{rel}</ul></div><div class="aside__box"><h3>Which branch?</h3><p>Availability can vary between branches. Choose the branch you plan to visit when you request an appointment.</p><a class="btn btn--outline btn--sm" href="{R}{HUB}">Find a branch</a></div>'
              f'<div class="aside__box aside__box--accent"><h3>Talk to our team</h3><p>Call <a href="tel:{TEL}">{PHONE}</a> or request an appointment.</p><a class="btn btn--white" href="{R}appointments.html">Request appointment</a></div></aside></div>')
    out(path, shell(s["title"], f'{s["title"]} at NexaCare Health Centre. {s["short"]} Availability can vary by branch.', banner(s["title"], [("Services", "services.html"), (s["title"], path)], esc(s["short"])) + intro + three + faq, "services"))

def homecare():
    setr("homecare.html")
    fh = form("homecare", homecare_fields(), "hc", "Send homecare enquiry", "A member of the team will contact you to talk about the request. A visit is only confirmed after we speak with you and agree the details.")
    hero = (f'<section class="hc-hero"><div class="container hc-hero__in{"" if has_photo("homecare-hero") else " hc-hero__in--solo"}"><div><span class="eyebrow">Homecare</span><h1>Professional healthcare and compassionate support, at home.</h1>'
            f'<p class="lead">For older adults, people recovering from illness, and the families who look after them. Tell us what is needed and the team will talk it through with you.</p>'
            + dots(["Older adults who need help at home", "People recovering after illness or a hospital stay", "Families caring for a sick or dependent relative"]) +
            f'<div class="btn-row"><a class="btn btn--primary btn--lg" href="#request">Request homecare</a><a class="btn btn--outline btn--lg" href="tel:{TEL}">{ico("fa-phone")} Speak to our team</a></div></div>'
            + (f'<div class="hc-hero__media">{photo("homecare-hero", "A caregiver assisting an older person at home", "4/5", pos="top", eager=True)}</div>' if has_photo("homecare-hero") else "") + '</div></section>')
    who = sec(f'<div class="split"><div>{title_block("Who homecare may help")}<p class="lead">Many families reach a point where looking after someone at home becomes difficult. Homecare is for those moments.</p>'
              f'<p>If you are not sure whether a home visit would suit your relative, send an enquiry or call us. The team will ask a few questions and help you decide.</p>' + (photo("homecare-visit", "A nurse visiting a patient at home", "3/2", pos="mid") if has_photo("homecare-visit") else "") + '</div>'
              f'<div>' + dots(["Older adults who need help with daily activities", "People recovering at home after illness, surgery or hospital discharge", "Patients who need ongoing support with daily care", "Families caring for a sick or dependent relative", "People who may benefit from an appropriately assessed home visit"]) + '</div></div>')
    rows = [("fa-person-cane", "Elderly care and daily living", "Help with everyday activities such as washing, dressing, meals and getting around."), ("fa-user-nurse", "Nursing visits", "Nursing care at home, where it is suitable and appropriate for the person."),
            ("fa-bed-pulse", "Recovery after illness or hospital stay", "Support while you recover at home, with follow-up agreed with the team."), ("fa-person-walking", "Mobility and physiotherapy", "Help with moving safely, and physiotherapy visits where suitable."),
            ("fa-pills", "Medication support", "Help to take medicines as prescribed, within professional authorisation."), ("fa-baby", "Mother and baby visits", "Support for new mothers and babies at home, where suitable."),
            ("fa-people-roof", "Guidance for family caregivers", "Practical advice for relatives looking after someone at home.")]
    svc = sec(f'<div class="split"><div>{title_block("What families can ask about")}<p>These are the kinds of support families ask about. Tell us what you need and the team will explain what NexaCare can arrange for your situation, and whether a home visit is suitable.</p>'
              f'<div class="notice">{ico("fa-circle-info")}<p><strong>Personal care and nursing are different.</strong> Help with washing, dressing and getting around is personal care. Nursing and other clinical care are provided by suitably qualified staff. We will tell you which is being proposed.</p></div>'
              f'<p>Prefer to speak to a clinician remotely first? See <a href="{surl(SV["telemedicine"])}">telemedicine</a>.</p></div>'
              f'<ul class="hc-rows">' + "".join(f'<li>{ico(i)}<div><h3>{h}</h3><p>{p}</p></div></li>' for i, h, p in rows) + "</ul></div>", "section--alt")
    steps = [("Contact us", "Call, or send the enquiry form below."), ("We talk it through", "The team asks about the person&rsquo;s needs and your concerns."), ("Assessment or care plan", "Where suitable, the team arranges an assessment and explains a care plan."),
             ("Care is coordinated", "Confirmed visits are agreed with you, including dates and who will visit."), ("Follow-up", "Follow-up is agreed as part of the care plan.")]
    how = sec(title_block("How homecare works", "A simple path from your first call to care at home.") + '<ol class="timeline">' + "".join(f"<li><h3>{h}</h3><p>{p}</p></li>" for h, p in steps) + "</ol>")
    why = (f'<section class="section section--tint"><div class="container reveal"><div class="split"><div>{title_block("Why families choose care at home")}'
           + dots(["Care in a familiar, comfortable place", "Support for dignity and independence", "Easier coordination between the family and the care team", "Fewer journeys, when it is clinically suitable"]) +
           f'<p class="small">Homecare does not replace hospital treatment, and not every patient is suitable for care at home. The team will advise honestly.</p></div>'
           f'<div>' + (photo("homecare-family", "A family with a caregiver at home", "3/2", pos="mid") if has_photo("homecare-family") else "") + f'<h2>For the family</h2><p class="pull">Looking after someone you love can be tiring and worrying. You do not have to work everything out alone.</p><p>Call us, share your concerns, and we will explain the next steps. You may find these guides helpful: '
           f'<a href="{turl(TP["fall-prevention"])}">preventing falls</a>, <a href="{turl(TP["healthy-ageing"])}">healthy ageing</a> and <a href="{turl(TP["medication-safety"])}">medication safety</a>.</p></div></div></div></section>')
    cov = sec(f'<div class="split"><div>{title_block("Where we can help")}<p class="lead">Homecare enquiries are handled through NexaCare&rsquo;s branches.</p><p>Tell us your location or estate and, if you know it, your nearest branch. The team will confirm whether a home visit is possible there. <a href="{R}{HUB}">See our branches</a>.</p></div>'
              f'<div><ul class="contact-block"><li>{ico("fa-phone")}<div><strong>{esc(SITE.get("central_label", "Central line"))}</strong><a href="tel:{TEL}">{PHONE}</a></div></li><li>{ico("fa-envelope")}<div><strong>Email</strong><a href="mailto:{MAIL}">{MAIL}</a></div></li></ul></div></div>', "section--alt")
    req = sec(f'<div class="split"><div class="hc-form-side">{title_block("Request homecare", "Tell us the basics and we will contact you.")}'
              f'<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Emergencies.</strong> This form is not for emergencies and is not monitored around the clock. If someone is in danger, go to the nearest emergency facility or call emergency services.</p></div>'
              f'<div class="notice">{ico("fa-lock")}<p>Please do not send medical records or detailed health information here. Keep the note brief. A clinician will ask for what is needed. Sending an enquiry does not guarantee a visit.</p></div></div>'
              f'<div class="form-card">{fh}</div></div>', "", "request")
    faq = sec(title_block("Homecare questions") + faq_list([("How do I know if homecare is right for my relative?", "Send an enquiry or call us. The team will ask about the person&rsquo;s needs and tell you whether a home visit may be suitable."), ("What happens after I send the form?", "A member of the team contacts you by your preferred method. Nothing is arranged until you have spoken with us."),
            ("Which areas do you visit?", "Please give your location or estate, and your nearest branch if you know it. The team will confirm whether a visit is possible there."), ("How do I ask about fees?", "Please ask when the team contacts you, or call us."), ("Can I be involved in the care?", "Yes. Families are welcome to take part, and the team can explain how to coordinate with the care team."),
            ("What if it is an emergency?", "Do not wait for an enquiry to be answered. Go to the nearest emergency facility or call emergency services."), ("Should I include medical details in the form?", "No. Keep the note brief and general. The team will ask for any further information during a conversation.")]), "section--alt")
    out("homecare.html", shell("Homecare enquiries", "Homecare enquiries for older adults and people recovering from illness at NexaCare Health Centre. Choose your nearest branch and request a call from the care team.", hero + who + svc + how + why + cov + req + faq, "homecare"))

def team():
    if not TEAM: return
    setr("our-team.html")
    side = '<ul class="sidelist">' + "".join(f'<li><a href="{surl(s)}">{esc(s["title"])}</a></li>' for s in SERV) + "</ul>"
    out("our-team.html", shell("Our team", "Meet the healthcare professionals at NexaCare Health Centre.", banner("Our team", [("Our team", "our-team.html")]) +
        sec(f'<div class="team-layout"><aside><h2 class="side-h">Our services</h2>{side}</aside><div><div class="team-grid">' + "".join(staff_card(p) for p in TEAM) + '</div></div></div>'), "team"))
    for p in TEAM:
        pp = f"team/{p['slug']}.html"; setr(pp)
        rows = "".join(f"<h2>{h}</h2>{c}" for h, c in [("Qualifications", ul(p["qualifications"]) if p.get("qualifications") else ""), ("Languages", f"<p>{esc(', '.join(p['languages']))}</p>" if p.get("languages") else ""),
              ("Services", "<ul>" + "".join(f'<li><a href="{surl(SV[x])}">{esc(SV[x]["title"])}</a></li>' for x in p.get("services", []) if x in SV) + "</ul>" if p.get("services") else "")] if c)
        exp = f'<p><strong>{esc(str(p["experience_years"]))} years</strong> of experience</p>' if p.get("experience_years") else ""
        out(pp, shell(p["name"], f'{p["name"]}, {p.get("title", "")} at NexaCare Health Centre.', banner(p["name"], [("Our team", "our-team.html"), (p["name"], pp)]) +
            sec(f'<div class="profile"><img src="{R}{p["photo"]}" alt="{esc(p.get("photo_alt") or p["name"])}" width="800" height="1005"><div class="prose"><h2>{esc(p["name"])}</h2><p>{esc(p.get("title", ""))}</p>{exp}<p>{esc(p.get("bio", ""))}</p>{rows}<p><a class="btn btn--primary" href="{R}appointments.html">Request appointment</a></p></div></div>'), "team"))

def about():
    setr("about.html")
    fac = lambda i, h, t: f'<div class="feature"><span class="feature__icon">{ico(i)}</span><div><h3>{h}</h3><p>{t}</p></div></div>'
    names_ = ", ".join(b["name"] for b in BRS[:-1]) + " and " + BRS[-1]["name"]
    intro = sec(f'<div class="split split--center"><figure class="photo-frame figcap">{photo("duo", "A doctor and a nurse in a hospital ward", "4/3", pos="top")}<figcaption>Modern clinical practice with a respectful, personal approach.</figcaption></figure>'
                f'<div>{title_block("Welcome to NexaCare Health Centre", kicker="About us")}<p class="lead">NexaCare is a health centre with its main centre in {esc(SITE["locality"])} and branches at {esc(names_)}.</p>'
                f'<p>We offer outpatient consultations, maternal and child health, laboratory and pharmacy services, family planning, emergency care, minor procedures and first aid, counselling, physiotherapy, homecare and telemedicine. Service availability can vary by branch, so please check with the branch you plan to visit.</p>'
                f'<div class="mv"><div><h3>{ico("fa-heart-pulse")} Our approach</h3><p>{esc(SITE["tagline"])}. We combine modern clinical practice with a respectful, personal approach.</p></div><div><h3>{ico("fa-door-open")} Walk-in care</h3><p>You can come in without booking, or request an appointment to plan your visit.</p></div></div>'
                f'<div class="btn-row"><a class="btn btn--primary" href="{HUB}">Our branches</a><a class="btn btn--outline" href="services.html">Our services</a></div></div></div>')
    grid = sec('<div class="features features--3">' + fac("fa-vials", "Laboratory and pharmacy", "Tests and medicines, so fewer trips.") + fac("fa-baby", "Maternal and child health", "Support for mothers, babies and children.") + fac("fa-house-medical", "Homecare", "Support at home for older adults and people recovering from illness.") +
               fac("fa-laptop-medical", "Telemedicine", "Speak to a health professional remotely when a visit is not possible.") + fac("fa-hand-holding-heart", "Counselling", "A private space to talk through worries and difficult events.") + fac("fa-person-walking", "Physiotherapy", "Help to move well after injury or illness.") + "</div>", "section--alt")
    gal = "".join(f'<figure class="gallery__item">{photo(k, "", "1/1", pos="top")}</figure>' for k in ("doctor-corridor", "doctor-clipboard", "doctor-studio", "duo"))
    gf = sec(f'<div class="split"><div>{title_block("Photo gallery")}<div class="gallery">{gal}</div><p class="small">Some images are illustrative and may not show NexaCare staff, patients or premises.</p></div><div>{title_block("Frequently asked questions")}' + faq_list([("Where are NexaCare branches?", f'See the <a href="{HUB}">branches page</a>. NexaCare has a main centre in {esc(SITE["locality"])} and branches at {esc(names_)}.'), ("Do I need an appointment?", "No. Walk-ins are welcome, and you can also request an appointment."), ("Is homecare available?", "Please see the <a href='homecare.html'>homecare page</a> or call us to discuss your situation."), ("How can I contact the team?", f"Call <a href='tel:{TEL}'>{PHONE}</a> or email <a href='mailto:{MAIL}'>{MAIL}</a>.")]) + "</div></div>")
    out("about.html", shell("About us", f"About NexaCare Health Centre: a main centre in {SITE['locality']} and {NUMWORD} branches offering compassionate, modern healthcare.", banner("About us", [("About us", "about.html")], "Modern medicine with a compassionate touch.") + intro + grid + cta_strip() + gf, "about"))

def appointments():
    setr("appointments.html")
    f = form("appointment", appt_fields(), "ap", "Send request", "NexaCare will contact you to confirm a date and time. Your appointment is not confirmed until we do.")
    pick = f'<div class="pick" role="group" aria-labelledby="pick-h"><h3 id="pick-h">1. Choose your branch</h3><ul class="chips chips--pick">' + "".join(f'<li><button type="button" class="chip" data-pick-branch="{b["slug"]}" aria-pressed="false">{esc(b["name"])}{" (main centre)" if b is MAIN else ""}</button></li>' for b in BRS + [MAIN]) + '</ul></div>'
    b = banner("Request an appointment", [("Appointments", "appointments.html")], "Choose a branch, tell us what you need and we will contact you to confirm.") + sec(
        f'<div class="split"><div>{pick}<h3 class="step-h">2. Tell us what you need</h3><p>Share the basics in the form. Add a preferred date and time if you have one.</p><h3 class="step-h">3. We contact you</h3>{dots(["This is a request. Your appointment is confirmed only when NexaCare contacts you.", "Walk-ins are also welcome.", "Share the basics only. Do not include medical history or ID numbers."])}'
        f'<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Urgent problem?</strong> Do not use this form. Go to the nearest emergency facility or call emergency services.</p></div><p>Prefer to talk? Call our central line on <a href="tel:{TEL}">{PHONE}</a>.</p></div><div class="form-card" id="appointment-form">{f}</div></div>')
    out("appointments.html", shell("Request an appointment", f"Request an appointment at a NexaCare Health Centre branch. Choose your preferred branch, share the basics and the team will contact you to confirm.", b, "appointments"))

def contact_card(b):
    ph, em, hrs = BM.value(b, "phone"), BM.value(b, "email"), BM.value(b, "hours")
    loc = BM.value(b, "address") or BM.value(b, "locality")
    rows = []
    if loc: rows.append(f'<li>{ico("fa-location-dot")}<span>{esc(loc)}</span></li>')
    rows.append(f'<li>{ico("fa-phone")}<span>' + (f'<a href="tel:{ph["tel"]}">{esc(ph["display"])}</a>' if ph else f'{esc(SITE.get("central_label", "Central line"))}: <a href="tel:{TEL}">{PHONE}</a>') + "</span></li>")
    rows.append(f'<li>{ico("fa-envelope")}<span><a href="mailto:{em or MAIL}">{esc(em or MAIL)}</a>{"" if em else " (central email)"}</span></li>')
    if hrs: rows.append(f'<li>{ico("fa-clock")}<span>{esc(hrs[0])}</span></li>')
    main = b["role"] == "main_centre"
    return (f'<article class="ccard"><h3>{esc(bname(b))}{MAIN_BADGE if main else ""}</h3><ul class="ccard__rows">{"".join(rows)}</ul>'
            f'<div class="btn-row"><a class="btn btn--primary btn--sm" href="{R}contact.html?branch={b["slug"]}#message">Message this branch</a><a class="btn btn--outline btn--sm" href="{book_url(b)}">Request appointment</a>' + ("" if main else f'<a class="btn btn--ghost btn--sm" href="{burl(b)}">Branch page</a>') + "</div></article>")

def contact():
    setr("contact.html")
    f = form("contact", contact_fields(), "ct", "Send message", "We will reply using the details you gave.")
    b = (banner("Contact us", [("Contact", "contact.html")], "Call, email or send a message. Tell us which branch your message is about.") + sec(
        f'<div class="contactcards"><div class="contactcard">{ico("fa-phone")}<h3>{esc(SITE.get("central_label", "Central line"))}</h3><p><a href="tel:{TEL}">{PHONE}</a></p></div><div class="contactcard">{ico("fa-envelope")}<h3>Email</h3><p><a href="mailto:{MAIL}">{MAIL}</a></p></div>'
        f'<div class="contactcard contactcard--warn">{ico("fa-triangle-exclamation")}<h3>Emergencies</h3><p>Go to the nearest emergency facility or call emergency services. Do not use this page.</p></div></div>')
        + sec(title_block("Contact a branch", "Each branch&rsquo;s own telephone, email and hours appear here once published. Until then, the central line and email reach the NexaCare team.", kicker="Our locations") + '<div class="grid grid--3">' + "".join(contact_card(x) for x in BRS + [MAIN]) + "</div>", "section--alt")
        + sec(f'<div class="split"><div>{title_block("Send us a message", "Choose the branch your message is about so it reaches the right team.", kicker="Message")}<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p>For emergencies, do not use this form. Go to the nearest emergency facility or call emergency services.</p></div>'
              f'<p>Prefer to talk? Call <a href="tel:{TEL}">{PHONE}</a>.</p></div><div class="form-card" id="message">{f}</div></div>'))
    out("contact.html", shell("Contact us", f"Contact NexaCare Health Centre by telephone, email or message, and choose the branch you want to reach.", b, "contact"))

def faq():
    setr("faq.html")
    g = lambda h, items, id_="": f'<h2{f" id={chr(34)}{id_}{chr(34)}" if id_ else ""}>{h}</h2>{faq_list(items)}'
    body = "".join([g("Branches", [("Where are NexaCare branches?", f'NexaCare has a main centre in {esc(SITE["locality"])} and {NUMWORD} branches. See the <a href="branches/index.html">branches page</a> to find yours.'), ("How do I choose a branch?", "Use the branch search on the <a href='branches/index.html'>branches page</a>, or choose your preferred branch when you request an appointment. If you are not sure, choose &ldquo;No preference&rdquo; and the team will help."), ("Do all branches offer the same services?", "Not necessarily. Service availability can vary between branches. Each branch page lists services once they are confirmed, and the team will tell you what your branch offers when you book.")]),
        g("Appointments", [("Do I need an appointment?", "NexaCare welcomes walk-in patients. You can also <a href='appointments.html'>request an appointment</a> to plan your visit. A request is not confirmed until the team contacts you."), ("How will I know my appointment is confirmed?", "The team will contact you by your preferred method to agree a date and time.")]),
        g("Services", [("Which services are offered?", "See the <a href='services.html'>services page</a>. If you need a specific test or procedure, please call your branch and ask."), ("Is emergency care available 24 hours?", "Please confirm current emergency hours by phone before travelling. In a life-threatening emergency, go to the nearest emergency facility or call emergency services.")]),
        g("Homecare", [("How do I ask about homecare?", "Use the <a href='homecare.html#request'>homecare request form</a> or call us. A visit is only confirmed after we speak with you and check availability."), ("How do I ask about fees?", "Please ask when we contact you, or call. Prices are confirmed by NexaCare.")]),
        g("Preparing for a visit", [("What should I bring?", "Your medicines or a list of them, earlier medical records or test results, and a list of questions."), ("Can I bring someone with me?", "Many patients do. Please tell the team if you need extra support.")], "preparing"),
        g("Contacting us", [("How can I reach NexaCare?", f"Call the central line on <a href='tel:{TEL}'>{PHONE}</a> or email <a href='mailto:{MAIL}'>{MAIL}</a>. See the <a href='contact.html'>contact page</a> for every branch."), ("Is the online form for emergencies?", "No. Forms are not monitored around the clock. For urgent problems go to the nearest emergency facility or call emergency services.")]),
        g("Billing", [("What do services cost?", "Fees are confirmed by NexaCare. Please call or ask at your branch.")])])
    out("faq.html", shell("Frequently asked questions", "Answers about NexaCare branches, appointments, services, homecare, preparing for a visit and contacting NexaCare Health Centre.", banner("Frequently asked questions", [("FAQs", "faq.html")]) + sec(f'<div class="layout-aside"><div class="prose">{body}</div><aside class="aside"><div class="aside__box aside__box--accent"><h3>Still have a question?</h3><p>Call us or send a message.</p><a class="btn btn--white" href="contact.html">Contact us</a></div><div class="aside__box"><h3>Find a branch</h3><p>See every NexaCare location.</p><a class="btn btn--outline btn--sm" href="{HUB}">Our branches</a></div></aside></div>'), "faq"))

def topic_page(t):
    path = f"health-library/{t['slug']}.html"; setr(path)
    S = lambda i, h, items: f'<h2 id="{i}">{esc(h)}</h2>{ul(items)}' if items else ""
    toc = [("overview", "Overview"), ("symptoms", t["symptoms_title"])] + ([("causes", t["causes_title"])] if t["causes"] else []) + [("prevention", t.get("prevention_title") or "Prevention and staying well"), ("seek", "When to seek a health assessment"), ("urgent", "Urgent warning signs"), ("sources", "Sources")]
    urgent = f'<div class="alert-box" id="urgent"><h2>{ico("fa-triangle-exclamation")} Get urgent medical help if you notice</h2>{ul(t["urgent"])}<p>Go to the nearest emergency facility or call emergency services. Do not wait for an appointment.</p></div>'
    refs = "<ol class=refs>" + "".join(f'<li><a href="{u}" rel="noopener" target="_blank">{esc(n)}<span class="sr-only"> (opens in a new tab)</span></a></li>' for n, u in t["refs"]) + "</ol>"
    pic = ('<figure class="topic-photo">' + photo("topic-" + t["slug"], t["title"], "16/9", pos="mid") + '</figure>') if has_photo("topic-" + t["slug"]) else ""
    art = (f'<article class="prose"><div class="topic-meta"><span class="tag">{esc(t["tag"])}</span></div>{pic}<h2 id="overview">Overview</h2><p class="lead">{esc(t["what"])}</p>{S("symptoms", t["symptoms_title"], t["symptoms"])}{S("causes", t.get("causes_title", ""), t["causes"])}'
           f'{S("prevention", t.get("prevention_title") or "Prevention and staying well", t["prevention"])}{S("seek", "When to seek a health assessment", t["seek"])}{urgent}'
           f'<div class="notice">{ico("fa-circle-info")}<p>{DISC} This page is education only and does not mean NexaCare provides specialist care for this condition. Call us to ask what is available.</p></div>'
           f'<h2 id="sources">Sources</h2>{refs}<p class="meta-line">Prepared on {SITE["build_date"]} from the sources listed above.</p></article>')
    svcs = "".join(f'<li><a href="{surl(SV[x])}">{esc(SV[x]["title"])}</a></li>' for x in t["services"]); rel = "".join(f'<li><a href="{turl(TP[x])}">{esc(TP[x]["title"])}</a></li>' for x in t["topics"])
    aside = (f'<aside class="aside"><div class="aside__box"><h3>On this page</h3><ul>' + "".join(f'<li><a href="#{i}">{esc(n)}</a></li>' for i, n in toc) + f'</ul></div><div class="aside__box aside__box--accent"><h3>Talk to our team</h3><p>If you are worried, you do not need to wait.</p><a class="btn btn--white" href="{R}appointments.html">Request appointment</a></div>'
             f'<div class="aside__box"><h3>Related services</h3><ul>{svcs}</ul></div><div class="aside__box"><h3>Related reading</h3><ul>{rel}</ul></div></aside>')
    out(path, shell(t["title"], f'{t["title"]}: plain-language health information with warning signs and sources, from NexaCare Health Centre.', banner(t["title"], [("Health library", "health-library/index.html"), (t["title"], path)]) + sec(f'<div class="layout-aside">{art}{aside}</div>'), "library"))

def library():
    setr("health-library/index.html")
    tags = {}
    for t in TOP: tags[t["tag"]] = tags.get(t["tag"], 0) + 1
    cats = '<ul class="catlist">' + "".join(f"<li><span>{esc(k)}</span><span>({n})</span></li>" for k, n in tags.items()) + "</ul>"
    pop = '<ul class="poplist">' + "".join(f'<li><a href="{turl(TP[k])}" tabindex="-1" aria-hidden="true">{photo("topic-" + k, TP[k]["title"], "1/1")}</a><a href="{turl(TP[k])}">{esc(TP[k]["title"])}<small>{esc(TP[k]["tag"])}</small></a></li>' for k in ("hypertension", "child-health", "malaria")) + "</ul>"
    b = banner("Health library", [("Health library", "health-library/index.html")], "Plain-language guides for patients and families.") + sec(f'<div class="news"><div><div class="notice">{ico("fa-circle-info")}<p>{DISC} Having a guide here does not mean NexaCare offers specialist care for every condition.</p></div><div class="news__list">' + "".join(acard(t, i == 0) for i, t in enumerate(TOP)) + f'</div></div><aside class="sidebar"><h2>Categories</h2>{cats}<h2>Start here</h2>{pop}</aside></div>')
    out("health-library/index.html", shell("Health library", "Plain-language health guides on blood pressure, diabetes, malaria, ageing, falls, maternal and child health, medicines and respiratory illness.", b, "library"))

def legal():
    for path, title, intro, secs in [
        ("privacy.html", "Privacy and cookies", "How NexaCare Health Centre handles the details you send through this website.",
         [("Who we are", f"{SITE['name']}, with a main centre in {SITE['locality']} and branches listed on our branches page. Contact: {MAIL}."),
          ("What we collect", "Only what you type into our forms: name, telephone, optional email, the branch you choose, the service you ask about, preferred date and time, general location for home visits, a brief note and your contact preference. Please do not send medical history, ID numbers or test results through the website."),
          ("Why we use it", "To reply to your request and to arrange or discuss care. The branch you choose helps us route your request to the right team. We do not use these details for advertising."), ("Who can see it", "Authorised NexaCare staff who handle enquiries."),
          ("How long we keep it", "We keep enquiries only as long as needed to respond and to arrange care, and then delete them."),
          ("Your rights", f"You may ask to see, correct or delete your information, or object to its use, by contacting {MAIL}. You may also complain to the Office of the Data Protection Commissioner."),
          ("Cookies and third parties", "This site sets no analytics, advertising or tracking cookies. Fonts and icons load from Google Fonts and Font Awesome&rsquo;s content network, so your browser contacts those providers when a page loads.")]),
        ("terms.html", "Website terms", "The terms for using the NexaCare Health Centre website.",
         [("Information only", "Content on this website is general information. It does not diagnose, treat or replace advice from a qualified health professional."), ("Emergencies", "Do not use this website, forms or email in an emergency. Go to the nearest emergency facility or call emergency services."),
          ("Requests are not bookings", "Sending a form is a request. An appointment or visit exists only when NexaCare confirms it to you."), ("Services, branches and prices", "Service availability, branch details and prices are confirmed by NexaCare and may change. Not every service is offered at every branch."),
          ("Links and images", "External links lead to sites we do not control. Some images are illustrative and do not necessarily show NexaCare staff, patients or facilities.")])]:
        setr(path)
        out(path, shell(title, f"{title} for NexaCare Health Centre.", banner(title, [(title, path)]) + sec(f'<div class="prose"><p class="lead">{intro}</p>' + "".join(f"<h2>{h}</h2><p>{p}</p>" for h, p in secs) + "</div>"), ""))

def notfound():
    global R
    setr("404.html"); R = "/"
    out("404.html", shell("Page not found", "This page could not be found.", f'<section class="container error-page"><h1>We could not find that page</h1><p class="lead">The link may be out of date. Try one of these instead.</p><div class="btn-row btn-row--center"><a class="btn btn--primary" href="/index.html">Go to the homepage</a><a class="btn btn--outline" href="/branches/index.html">Find a branch</a><a class="btn btn--outline" href="/services.html">See our services</a></div></section>', "", index=False))

# ---------- branches ----------
def branches_hub():
    setr(HUB)
    any_pending = any(BM.pending(b) for b in BRS)
    has = lambda k: any(BM.value(b, k) for b in ALLB)
    flt = ""
    if has("phone") or has("directions"):
        flt = '<fieldset class="finder__filters"><legend class="sr-only">Show only</legend>' + ('<label><input type="checkbox" data-filter="phone"> Has its own telephone</label>' if has("phone") else "") + ('<label><input type="checkbox" data-filter="directions"> Directions available</label>' if has("directions") else "") + "</fieldset>"
    finder = (f'<div class="finder only-js" data-finder><div class="finder__search"><label for="branch-search">Search branches</label><div class="finder__input">{ico("fa-magnifying-glass")}<input id="branch-search" type="search" placeholder="Branch name, area or service" autocomplete="off" enterkeyhint="search">'
              f'<button class="finder__clear" type="button" hidden>Clear</button></div></div>{flt}<p class="finder__count" role="status" aria-live="polite"></p></div>')
    pending_note = (f'<div class="notice">{ico("fa-circle-info")}<p>We are adding each branch&rsquo;s own address, telephone, opening hours and services as they are published. Until then, the central line (<a href="tel:{TEL}">{PHONE}</a>) can direct you, and you can request an appointment at any branch below.</p></div>') if any_pending else ""
    steps = [("fa-magnifying-glass-location", "Find your branch", "Search by name or browse the cards."), ("fa-address-card", "Check its details", "Open the branch page for contact options, hours and services once published."), ("fa-calendar-check", "Request an appointment", "Choose the branch in the form and we will contact you to confirm.")]
    body = (banner("Our branches", [("Our Branches", HUB)], f"{NUMWORD.capitalize()} branches and a main centre in {LOC}. Find the one nearest to you.") +
            sec(f'{finder}{pending_note}<div class="bgrid-main">{branch_card(MAIN, True)}</div><div class="bgrid" data-branch-list>' + "".join(branch_card(b, True) for b in BRS) +
                f'</div><div class="finder__empty" data-empty hidden><h3>No branch matches your search</h3><p>Try a different word, or <a href="tel:{TEL}">call the central line on {PHONE}</a> and the team will point you to the nearest branch.</p></div>') +
            sec('<div class="features features--3">' + "".join(f'<div class="feature"><span class="feature__icon">{ico(i)}</span><div><h3>{h}</h3><p>{p}</p></div></div>' for i, h, p in steps) + "</div>", "section--alt") +
            cta_strip("Not sure which branch is closest? Call us or request an appointment and the team will help.", "Request appointment", "appointments.html", alt=False))
    out(HUB, shell("Our branches", f"Find a NexaCare Health Centre branch: {', '.join(b['name'] for b in BRS)}, plus our main centre in {SITE['locality']}. Contact options and appointment requests.", body, "branches"))

HOURS_RE = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(-(Mo|Tu|We|Th|Fr|Sa|Su))?( \d\d:\d\d-\d\d:\d\d)$")
def branch_ld(b):
    """Structured data limited to verified facts. Nothing is inferred."""
    d = {"@context": "https://schema.org", "@type": "MedicalClinic", "name": bname(b), "parentOrganization": {"@type": "MedicalOrganization", "name": SITE["name"]}}
    if SITE["domain"]: d["url"] = abs_url(f"branches/{b['slug']}.html")
    addr, loc, ph, em, dirs = (BM.value(b, k) for k in ("address", "locality", "phone", "email", "directions"))
    if addr: d["address"] = {"@type": "PostalAddress", "streetAddress": addr, "addressCountry": "KE"}
    elif loc: d["address"] = {"@type": "PostalAddress", "addressLocality": loc, "addressCountry": "KE"}
    if ph: d["telephone"] = ph["tel"]
    if em: d["email"] = em
    xy = BM.coordinates(b)
    if xy: d["geo"] = {"@type": "GeoCoordinates", "latitude": xy[0], "longitude": xy[1]}
    if dirs: d["hasMap"] = dirs
    if BM.value(b, "hours"): d["openingHours"] = [h for h in (b.get("hours_schema") or []) if HOURS_RE.match(h)] or None
    if d.get("openingHours") is None: d.pop("openingHours", None)
    crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home"}, {"@type": "ListItem", "position": 2, "name": "Our Branches"}, {"@type": "ListItem", "position": 3, "name": bname(b)}]}
    if SITE["domain"]:
        for item, p in zip(crumbs_ld["itemListElement"], ("index.html", HUB, f"branches/{b['slug']}.html")): item["item"] = abs_url(p)
    return "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False) + "</script>" for x in (d, crumbs_ld))

def branch_page(b):
    path = f"branches/{b['slug']}.html"; setr(path)
    loc, addr, ph, wa, em, hrs, svc, dirs = (BM.value(b, k) for k in ("locality", "address", "phone", "whatsapp", "email", "hours", "services", "directions"))
    soon = '<span class="soon">Coming soon</span>'
    fact = lambda i, lab, val: f'<div class="fact"><dt>{icon_html(i)} {lab}</dt><dd>{val}</dd></div>'
    rows = [fact("fa-location-dot", "Location", esc(addr or loc) if (addr or loc) else soon),
            fact("fa-phone", "Branch telephone", f'<a href="tel:{ph["tel"]}">{esc(ph["display"])}</a>' if ph else soon)]
    if wa: rows.append(fact("fa-brands fa-whatsapp", "WhatsApp", f'<a href="https://wa.me/{wa["number"]}" target="_blank" rel="noopener">{esc(wa["display"])}<span class="sr-only"> (opens in a new tab)</span></a>'))
    rows += [fact("fa-envelope", "Branch email", f'<a href="mailto:{em}">{esc(em)}</a>' if em else soon), fact("fa-clock", "Opening hours", "<br>".join(esc(h) for h in hrs) if hrs else soon)]
    rows.append(fact("fa-diamond-turn-right", "Directions", f'<a class="btn btn--primary btn--sm" href="{esc(dirs)}" target="_blank" rel="noopener">Get directions<span class="sr-only"> to {esc(bname(b))} (opens in a new tab)</span></a>' if dirs else soon))
    intro_p = (f"{esc(bname(b))} is one of NexaCare Health Centre&rsquo;s branches" + (f", located in {esc(loc)}." if loc else ".") +
               ("" if (addr or ph or hrs) else " This branch&rsquo;s own address, telephone number and opening hours will appear on this page once they are published."))
    details = (f'<div class="card-panel"><h3>Branch details</h3><dl class="facts">{"".join(rows)}</dl>'
               f'<div class="central-note">{ico("fa-circle-info")}<p>{"For anything not listed here, " if (addr or ph or hrs) else "Until then, "}call NexaCare&rsquo;s central line: <a href="tel:{TEL}">{PHONE}</a> or email <a href="mailto:{MAIL}">{MAIL}</a>.</p></div></div>')
    if svc:
        services = '<ul class="svc-list">' + "".join(f'<li><a href="{surl(SV[x])}">{ico(SV[x]["icon"])} {esc(SV[x]["title"])}</a></li>' for x in svc) + "</ul>"
        svc_block = f'{title_block("Services at this branch")}{services}<p class="small">Please check with the branch before travelling for a specific test or procedure.</p>'
    else:
        svc_block = (f'{title_block("Services")}<p>NexaCare&rsquo;s services are listed on our <a href="{R}services.html">services page</a>. Availability can differ between branches, so the team will tell you what {esc(bname(b))} offers when you book.</p>'
                     f'<a class="btn btn--outline" href="{R}services.html">View all services</a>')
    fm = form("appointment", appt_fields(b["slug"]), "bp", "Send request", "NexaCare will contact you to confirm a date and time. Your appointment is not confirmed until we do.")
    body = (banner(bname(b), [("Our Branches", HUB), (b["name"], path)], "A branch of NexaCare Health Centre") +
            sec(f'<div class="split split--branch"><div class="branch-intro">{branch_visual(b)}<p class="lead">{intro_p}</p><div class="btn-row"><a class="btn btn--primary" href="#book">{ico("fa-calendar-check")} Request appointment here</a>' +
                (f'<a class="btn btn--outline" href="{esc(dirs)}" target="_blank" rel="noopener">{ico("fa-diamond-turn-right")} Directions<span class="sr-only"> (opens in a new tab)</span></a>' if dirs else f'<a class="btn btn--outline" href="tel:{TEL}">{ico("fa-phone")} Call central line</a>') + f'</div></div>{details}</div>') +
            sec(svc_block, "section--alt") +
            sec(f'<div class="split"><div>{title_block("Request an appointment at " + esc(bname(b)), "Share the basics and the team will contact you to confirm a date and time.")}{dots(["This is a request. Your appointment is confirmed only when NexaCare contacts you.", "Do not include medical history or ID numbers."])}'
                f'<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Urgent problem?</strong> Do not use this form. Go to the nearest emergency facility or call emergency services.</p></div></div><div class="form-card">{fm}</div></div>', "", "book") +
            sec(f'{title_block("Other NexaCare locations")}{branch_chips(b)}<p><a class="more" href="{R}{HUB}">See all branches {ico("fa-arrow-right")}</a></p>', "section--alt"))
    out(path, shell(b["seo_title"], b["seo_description"], body, "branches", index=BM.indexable(b), ld=branch_ld(b), full_title=True))

def seo_files():
    dom = SITE["domain"] or "REPLACE-WITH-DOMAIN"
    urls = "".join(f"<url><loc>https://{dom}/{p}</loc><lastmod>{SITE['site_updated']}</lastmod></url>" for p, ix in PAGES if ix)
    out("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    out("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /staff/\nDisallow: /portal/\nDisallow: /api/\nSitemap: https://{dom}/sitemap.xml\n")

def report():
    print(f"Built {len(PAGES)} pages ({sum(1 for _, i in PAGES if i)} in sitemap, {sum(1 for _, i in PAGES if not i)} noindex).")
    pend = {b["name"]: BM.pending(b) for b in BRS if BM.pending(b)}
    if pend:
        print("Branch details not yet published (add to data/branches.json and mark verified):")
        for n, f in pend.items(): print(f"  - {n}: {', '.join(f)}")
    noidx = [b["name"] for b in BRS if not BM.indexable(b)]
    if noidx: print("Branch pages marked noindex until the branch is open with verified details:", ", ".join(noidx))

if __name__ == "__main__":
    home(); services_dir(); [service_page(s) for s in SERV]; homecare(); team(); about(); branches_hub(); [branch_page(b) for b in BRS]; appointments(); contact(); faq(); library(); [topic_page(t) for t in TOP]; legal(); notfound(); seo_files(); report()
