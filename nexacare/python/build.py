#!/usr/bin/env python3
"""Generates the static NexaCare site from data/*.json so header, footer and templates stay identical on every page.
Run from anywhere:  python python/build.py   (no third-party packages needed)"""
import html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
load = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
SITE, SERV, TOP, STAFF = load("site.json"), load("services.json"), load("health-topics.json"), load("staff.json")
TEAM = [p for p in STAFF if p.get("published") and p.get("name") and p.get("photo")]   # only verified, approved profiles appear on the site
esc = html.escape
CUR, R = "", ""
PAGES = []
SV = {s["slug"]: s for s in SERV}
TP = {t["slug"]: t for t in TOP}

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
    for t in TOP: s["topic-" + t["slug"]] = {"file": None, "icon": t["icon"], **ph}
    s["service-outpatient"].update(bp); s["topic-hypertension"].update(bp); s["service-maternal-child-health"].update(child); s["topic-child-health"].update(child)
    for k in ("homecare-hero", "homecare-visit", "homecare-family"): s[k] = {"file": None, "icon": "fa-house-medical", **ph}
    return {"_note": "Set 'file' (path from the site root), 'w', 'h', 'alt' to replace a tile with a real photo, then run python/build.py. Never present stock photos as NexaCare staff, patients or premises.", "slots": s}
MF = D / "image-manifest.json"
IMG = json.loads(MF.read_text()) if MF.exists() else default_manifest()
for k, v in default_manifest()["slots"].items(): IMG["slots"].setdefault(k, v)
MF.write_text(json.dumps(IMG, indent=1, ensure_ascii=False), encoding="utf-8")

def photo(slot, alt="", ar=None, cls="photo", pos=None):
    """Real photo if the manifest has one, otherwise a solid brand tile with the service icon."""
    m = IMG["slots"].get(slot, {})
    st = []
    if ar: st.append(f"--ar:{ar}")
    if pos: st.append(f"object-position:{pos}")
    style = f' style="{";".join(st)}"' if st else ""
    if m.get("file") and (ROOT / m["file"]).exists():
        return f'<img class="{cls}"{style} src="{R}{m["file"]}" alt="{esc(m.get("alt") or alt)}" width="{m.get("w","")}" height="{m.get("h","")}" loading="lazy" decoding="async">'
    c = ["navy", "blue", "green"][sum(map(ord, slot)) % 3]
    return f'<div class="tile tile--{c}"{style} role="img" aria-label="{esc(alt)}"><i class="fa-solid {m.get("icon","fa-notes-medical")}" aria-hidden="true"></i></div>'

def has_photo(slot):
    m = IMG["slots"].get(slot, {})
    return bool(m.get("file") and (ROOT / m["file"]).exists())

# ---------- helpers ----------
ico = lambda n: f'<i class="fa-solid {n}" aria-hidden="true"></i>'
ul = lambda items: "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"
dots = lambda items: '<ul class="dot-list">' + "".join(f'<li>{ico("fa-circle-check")}<span>{esc(i)}</span></li>' for i in items) + "</ul>"
surl = lambda s: R + (s.get("page") or f"services/{s['slug']}.html")
turl = lambda t: f"{R}health-library/{t['slug']}.html"
PHONE, TEL, MAIL = SITE["phone"], SITE["phone_tel"], SITE["email"]
def title_block(h, p="", center=False):
    return f'<div class="section-title{" section-title--center" if center else ""}"><h2>{h}</h2>{f"<p>{p}</p>" if p else ""}</div>'
def sec(inner, cls="", id=""):
    return f'<section class="section {cls}"{f" id={chr(34)}{id}{chr(34)}" if id else ""}><div class="container reveal">{inner}</div></section>'
def crumbs(trail):
    li = "".join(f'<li><a href="{R}{u}">{esc(n)}</a></li>' for n, u in trail[:-1]) + f'<li aria-current="page">{esc(trail[-1][0])}</li>'
    return f'<nav class="breadcrumb" aria-label="Breadcrumb"><ol><li><a href="{R}index.html">Home</a></li>{li}</ol></nav>'
def banner(title, trail):
    return f'<section class="banner"><h1>{esc(title)}</h1><div class="banner__crumbs"><div class="container">{crumbs(trail)}</div></div></section>'
def cta_strip(text="Need care? Request an appointment and the team will contact you.", btn="Request appointment", href="appointments.html"):
    return f'<section class="cta-strip"><div class="container"><p>{text}</p><a class="btn btn--white" href="{R}{href}">{btn}</a></div></section>'
DISC = "This page gives general health information in plain language. It does not diagnose, and it does not replace advice from a qualified health professional."
def faq_list(items):
    return '<div class="faq">' + "".join(f"<details><summary>{esc(q)}</summary><div><p>{a}</p></div></details>" for q, a in items) + "</div>"
# ---------- forms ----------
def field(f, p):
    n, i = f["name"], f"{p}-{f['name']}"; t = f.get("type", "text"); req = " required" if f.get("req") else ""
    hint = f'<p class="hint" id="{i}-h">{esc(f["hint"])}</p>' if f.get("hint") else ""
    d = f' aria-describedby="{i}-h"' if f.get("hint") else ""
    lab = f'<label for="{i}">{esc(f["label"])}{"" if f.get("req") else " <span class=opt>(optional)</span>"}</label>'
    if t == "select":
        opts = "".join(f'<option value="{esc(v)}">{esc(l)}</option>' for v, l in f["options"])
        c = f'{lab}<select id="{i}" name="{n}"{req}{d}><option value="">Choose one</option>{opts}</select>' if f.get("req") else f'{lab}<select id="{i}" name="{n}"{d}>{opts}</select>'
    elif t == "textarea":
        c = f'{lab}<textarea id="{i}" name="{n}" maxlength="600"{req}{d}></textarea>'
    elif t == "radio":
        rs = "".join(f'<label><input type="radio" name="{n}" value="{esc(v)}"{" checked" if k == 0 else ""}> {esc(v)}</label>' for k, v in enumerate(f["options"]))
        c = f'<fieldset class="radio-group"><legend>{esc(f["label"])}</legend>{rs}</fieldset>'
    elif t == "check":
        return f'<div class="field check{" full" if True else ""}"><input type="checkbox" id="{i}" name="{n}"{req}{d}><label for="{i}">{f["label"]}</label></div>'
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
def form(kind, fields, p, label="Send request", success="", sq=False):
    body = "".join(field(f, p) for f in fields)
    need = ' data-need-one="phone,email"' if kind == "contact" else ""
    return (f'<form class="form" data-enquiry="{kind}" data-success="{esc(success)}" novalidate{need}>{body}'
            f'<div class="hp" aria-hidden="true"><label>Leave this empty<input class="hp-input" type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
            f'<noscript><p class="noscript-note">This form needs JavaScript. Please call <a href="tel:{TEL}">{PHONE}</a> or email <a href="mailto:{MAIL}">{MAIL}</a> instead.</p></noscript><div class="form-status" role="status" aria-live="polite" hidden></div><div class="form__btn"><button class="btn btn--primary{" btn-sq" if sq else ""}" type="submit"{f" aria-label={chr(34)}{label}{chr(34)}" if sq else ""}>{ico("fa-paper-plane")}{"" if sq else " " + label}</button></div></form>')
def appt_fields():
    return [dict(name="name", label="Full name", req=1), dict(name="phone", label="Telephone number", type="tel", req=1),
            dict(name="email", label="Email", type="email"), dict(name="service", label="Service needed", type="select", options=SVC_OPTS, req=1),
            dict(name="date", label="Preferred date", type="date"), dict(name="time", label="Preferred time of day", type="select", options=TIMES),
            dict(name="area", label="General area for the home visit", showif="service=homecare", full=1, hint="Town or estate only. We will ask for the exact address when we call."),
            dict(name="contact_method", label="How should we contact you?", type="radio", options=CM, full=1),
            dict(name="message", label="Brief note", type="textarea", full=1, hint="Keep this general. Please do not include medical history, ID numbers or results."),
            dict(name="consent", label=CONSENT(), type="check", req=1)]
def homecare_fields():
    return [dict(name="requester_name", label="Your name", req=1), dict(name="phone", label="Telephone number", type="tel", req=1),
            dict(name="contact_method", label="Preferred way to be contacted", type="radio", options=CM, full=1),
            dict(name="contact_time", label="Best time to contact you", type="select", options=TIMES),
            dict(name="relationship", label="Your relationship to the person needing care", hint="For example: daughter, son, neighbour, or myself."),
            dict(name="care_type", label="Type of support you are asking about", type="select", req=1, options=[(c, c) for c in HC_TYPES] + [("Not sure", "I am not sure")], full=1),
            dict(name="age_group", label="Age group of the person needing care", type="select", options=[("Not given", "Prefer not to say"), ("Child", "Child"), ("Adult", "Adult"), ("Older adult", "Older adult (65 or over)")]),
            dict(name="area", label="Location or estate", req=1, hint="Town or estate only. We will ask for the exact address when we speak."),
            dict(name="message", label="Anything else we should know", type="textarea", full=1, hint="Keep this brief and general. Please do not send medical records or detailed health information."),
            dict(name="consent", label=CONSENT(), type="check", req=1)]
HC_TYPES = ["Elderly care and daily living assistance", "Nursing visit", "Post-hospital recovery support", "Mobility assistance and physiotherapy", "Medication support (within professional authorisation)", "Mother and baby visit", "Family caregiver guidance", "General homecare enquiry"]


# ---------- shell ----------
def navhtml(active):
    cur = lambda k: ' aria-current="page"' if active == k else ""
    svc = "".join(f'<li><a href="{surl(s)}">{esc(s["title"])}</a></li>' for s in SERV)
    top = "".join(f'<li><a href="{turl(t)}">{esc(t["title"])}</a></li>' for t in TOP)
    sub = lambda label, items, allp, allt, wide="": (f'<li class="has-sub"><button class="sub-toggle" type="button" aria-expanded="false" aria-haspopup="true">{label} {ico("fa-chevron-down")}</button>'
          f'<ul class="sub {wide}">{items}<li><a href="{R}{allp}"><strong>{allt}</strong></a></li></ul></li>')
    team = f'<li><a href="{R}our-team.html"{cur("team")}>Our team</a></li>' if TEAM else ""
    return (f'<nav aria-label="Main"><ul class="nav__list"><li><a href="{R}index.html"{cur("home")}>Home</a></li><li><a href="{R}about.html"{cur("about")}>About us</a></li>'
            f'{sub("Services", svc, "services.html", "All services", "sub--wide")}<li><a href="{R}homecare.html"{cur("homecare")}>Homecare</a></li>{team}'
            f'{sub("Health library", top, "health-library/index.html", "Browse the library")}'
            f'<li><a href="{R}faq.html"{cur("faq")}>FAQs</a></li><li><a href="{R}contact.html"{cur("contact")}>Contact us</a></li></ul></nav>')
def header(active):
    lg = SITE["logo"]["header"]
    ib = lambda i, h, t: f'<li class="infoblock">{ico(i)}<div><strong>{h}</strong><span>{t}</span></div></li>'
    return (f'<a class="skip-link" href="#main">Skip to main content</a><div class="topbar"><div class="container"><span>{ico("fa-location-dot")}{esc(SITE["locality"])}</span>'
            f'<span><span class="hide-sm"><a href="mailto:{MAIL}">{ico("fa-envelope")}{MAIL}</a> &nbsp;&nbsp;</span><a href="tel:{TEL}">{ico("fa-phone")}{PHONE}</a></span></div></div>'
            f'<header class="site-header"><div class="headmain"><div class="container headmain__in"><a class="brand" href="{R}index.html"><img src="{R}assets/images/logo/nexacare-logo-header.png" alt="NexaCare Health Centre, home" width="{lg[0]}" height="{lg[1]}"></a>'
            f'<ul class="infoblocks">{ib("fa-mobile-screen-button", "Call us now", f"<a href=tel:{TEL}>{PHONE}</a>")}{ib("fa-location-dot", "Visit us", esc(SITE["locality"]))}{ib("fa-envelope", "Email us", f"<a href=mailto:{MAIL}>{MAIL}</a>")}</ul>'
            f'<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">{ico("fa-bars")}<span class="sr-only">Menu</span></button></div></div>'
            f'<div class="navbar" id="site-nav"><div class="container navbar__in">{navhtml(active)}<a class="navbar__cta" href="{R}appointments.html">{ico("fa-calendar-check")} Request appointment</a></div></div></header>')

def footer():
    links = [("About us", "about.html"), ("Services", "services.html"), ("Homecare", "homecare.html"), ("Health library", "health-library/index.html"), ("Appointments", "appointments.html"), ("FAQs", "faq.html"), ("Contact us", "contact.html"), ("Privacy and cookies", "privacy.html"), ("Website terms", "terms.html")]
    if TEAM: links.insert(1, ("Our team", "our-team.html"))
    li = "".join(f'<li><a href="{R}{u}">{n}</a></li>' for u, n in [(u, n) for n, u in links])
    li = "".join(f'<li><a href="{R}{u}">{n}</a></li>' for n, u in links)
    if CUR in ("contact.html", "appointments.html", "homecare.html"):
        last = f'<div><h2>How can we help?</h2><div class="btn-row"><a class="btn btn--primary" href="{R}appointments.html">Request appointment</a><a class="btn btn--white" href="{R}homecare.html#request">Request homecare</a></div><p class="footer__note">In an emergency, go to the nearest emergency facility or call emergency services.</p></div>'
    else:
        ff = form("contact", [dict(name="name", label="Your name", req=1), dict(name="phone", label="Telephone", type="tel", req=1), dict(name="message", label="Message", type="textarea", req=1, full=1), dict(name="consent", label=CONSENT(), type="check", req=1)], "ft", "Submit", "We will reply using the details you gave.")
        last = f'<div><h2>Send us a message</h2>{ff}</div>'
    return (f'<footer class="site-footer"><div class="container footer__grid"><div><h2>About NexaCare</h2><p>NexaCare Health Centre offers outpatient care, maternal and child health, laboratory and pharmacy services, family planning, emergency care, counselling, physiotherapy, homecare and telemedicine in {esc(SITE["locality"])}.</p>'
            f'<p><a class="footer__more" href="{R}about.html">Know more &rsaquo;</a></p><p class="footer__note">In an emergency, go to the nearest emergency facility or call emergency services. Website forms are not for urgent problems.</p></div>'
            f'<div><h2>Useful links</h2><ul class="footer__cols">{li}</ul></div>'
            f'<div><h2>Contact details</h2><ul class="footer__contact"><li>{ico("fa-location-dot")}<span>{esc(SITE["locality"])}</span></li><li>{ico("fa-envelope")}<a href="mailto:{MAIL}">{MAIL}</a></li><li>{ico("fa-phone")}<a href="tel:{TEL}">{PHONE}</a></li></ul></div>{last}</div>'
            f'<div class="footer__bar"><div class="container"><p>&copy; {SITE["build_date"][-4:]} {esc(SITE["name"])}. All rights reserved.</p><ul class="footer__legal"><li><a href="{R}privacy.html">Privacy</a></li><li><a href="{R}terms.html">Terms</a></li></ul></div></div></footer>')

def shell(title, desc, body, active="", index=True, ld="", full_title=False):
    path = CUR
    t = title if full_title else f"{title} | {SITE['name']}"
    canon = f'<link rel="canonical" href="https://{SITE["domain"]}/{path}">' if SITE["domain"] else ""
    PAGES.append((path, index))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(t)}</title>'
            f'<meta name="description" content="{esc(desc)}">{"" if index else "<meta name=robots content=noindex>"}{canon}'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="{esc(SITE["name"])}"><meta property="og:title" content="{esc(t)}"><meta property="og:description" content="{esc(desc)}">'
            f'<meta name="nexacare-api" content="/api/enquiry"><meta name="nexacare-phone" content="{PHONE}"><meta name="nexacare-tel" content="{TEL}">'
            f'<link rel="icon" type="image/png" href="{R}assets/images/logo/favicon.png"><link rel="apple-touch-icon" href="{R}assets/images/logo/apple-touch-icon.png">'
            f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Hind:wght@300;400;500&display=swap" rel="stylesheet">'
            f'<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" crossorigin="anonymous" referrerpolicy="no-referrer">'
            + "".join(f'<link rel="stylesheet" href="{R}assets/css/{c}.css">' for c in ("variables", "base", "layout", "components", "pages", "responsive")) +
            f'<script>document.documentElement.classList.add("js")</script>{ld}</head><body>{header(active)}<main id="main">{body}</main>{footer()}'
            + "".join(f'<script src="{R}assets/js/{j}.js" defer></script>' for j in ("main", "navigation", "forms", "interactions")) + '</body></html>')
def out(path, content):
    p = ROOT / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8")
def setr(path):
    global R, CUR; R = "../" * path.count("/"); CUR = path

# ---------- blocks ----------
def dept(s): return f'<a class="dept" href="{surl(s)}"><span class="dept__icon">{ico(s["icon"])}</span><h3>{esc(s["title"])}</h3><p>{esc(s["short"])}</p><span class="more">Read more</span></a>'
def acard(t, feature=False):
    cls = "acard acard--feature" if feature else "acard"
    return (f'<article class="{cls}"><a class="acard__img" href="{turl(t)}" tabindex="-1" aria-hidden="true">{photo("topic-" + t["slug"], t["title"], "3/2", pos="center 30%")}</a><div class="acard__body"><h3><a href="{turl(t)}">{esc(t["title"])}</a></h3>'
            f'<p>{esc(t["what"].split(". ")[0])}.</p><div class="acard__meta">{ico("fa-book-medical")} Health guide &middot; {esc(t["tag"])}</div></div></article>')

def staff_card(p):
    nm = esc(p["name"]); tl = esc(p.get("title", ""))
    return f'<a class="tcard" href="{R}team/{p["slug"]}.html" style="text-decoration:none;color:inherit"><img src="{R}{p["photo"]}" alt="{esc(p.get("photo_alt") or p["name"])}" width="800" height="1005" loading="lazy"><div class="tcard__body"><h3>{nm}</h3><p>{tl}</p></div></a>'

def dcard(s):
    face = photo("service-" + s["slug"], s["title"], None, "dcard__photo", pos="center 30%") if has_photo("service-" + s["slug"]) else ico(s["icon"])
    return f'<a class="dcard" href="{surl(s)}"><span class="dcard__img">{face}</span><h3>{esc(s["title"])}</h3><p>{esc(s["short"])}</p><div class="dcard__foot"><span>Read more</span></div></a>'

def glance():
    nums = [("fa-notes-medical", len(SERV), "Services at one centre"), ("fa-book-medical", len(TOP), "Patient health guides"), ("fa-house-medical", 2, "Care beyond the clinic: homecare and telemedicine"), ("fa-phone", 3, "Ways to reach us: walk in, call or email")]
    items = "".join(f'<div class="stats__item">{ico(i)}<span class="stats__num">{n}</span><span class="stats__lab">{l}</span></div>' for i, n, l in nums)
    return f'<section class="stats"><div class="container"><h2>NexaCare at a glance</h2><p class="lead">Care for everyday health in {esc(SITE["locality"])}, from a first consultation to support at home.</p><div class="stats__grid">{items}</div></div></section>'

# ---------- pages ----------
def home():
    setr("index.html")
    quick = form("quick", [dict(name="name", label="Your name", req=1), dict(name="phone", label="Telephone", type="tel", req=1), dict(name="service", label="Service needed", type="select", options=SVC_OPTS, req=1),
                           dict(name="date", label="Preferred date", type="date"), dict(name="consent", label=CONSENT(), type="check", req=1)], "q", "Send request", "NexaCare will contact you to confirm. This is a request, not a confirmed appointment.", sq=True)
    hero = (f'<section class="hero"><div class="container"><div class="hero__panel"><h1>Modern Medicine, <span>Compassionate Touch</span></h1>'
            f'<p>Outpatient care, maternal and child health, laboratory and pharmacy services, and care at home in {esc(SITE["locality"])}. Walk in, or request an appointment.</p>'
            f'<div class="btn-row"><a class="btn btn--primary" href="services.html">Our services</a><a class="btn btn--outline" href="homecare.html">Explore homecare</a></div></div></div></section>')
    appt = (f'<section class="apptbar" aria-label="Request an appointment"><div class="container"><div class="apptbar__in"><div class="apptbar__label">{ico("fa-calendar-check")}<span>Make an Appointment</span></div><div class="apptbar__form">{quick}</div></div></div></section>')
    carousel = sec(f'<div data-carousel><div class="carousel__head">{title_block("Our services")}<div class="carousel__btns"><button type="button" data-prev aria-label="Previous services">{ico("fa-chevron-left")}</button><button type="button" data-next aria-label="Next services">{ico("fa-chevron-right")}</button></div></div>'
                   f'<div class="carousel__track" tabindex="0" aria-label="Services">' + "".join(dept(s) for s in SERV) + "</div></div>")
    thumbs = "".join(f'<a href="{surl(SV[k])}">{photo("service-" + k, SV[k]["title"], "4/3")}{esc(SV[k]["title"])}</a>' for k in ("maternal-child-health", "laboratory", "pharmacy", "homecare"))
    best = sec(f'<div class="best"><figure class="figcap" style="margin:0">{photo("doctor-clipboard", "A doctor in a white coat writing notes on a clipboard", "4/5.2", pos="center 10%")}<figcaption>Walk in for compassionate care in a modern setting.</figcaption></figure>'
               f'<div>{title_block("Welcome to NexaCare")}<p>NexaCare Health Centre is a health centre in {esc(SITE["locality"])}. You can see a clinician, have tests done and collect medicines in one place, and ask about care at home or by telemedicine.</p>'
               f'<div class="best__feature"><div><h3><a href="{surl(SV["outpatient"])}">Outpatient consultations</a></h3><p>{esc(SV["outpatient"]["intro"])}</p><a class="btn btn--outline btn--sm" href="{surl(SV["outpatient"])}">Read more</a></div>{photo("service-outpatient", "Outpatient consultation", "4/3", pos="center 30%")}</div>'
               f'<div class="best__thumbs">{thumbs}</div></div></div>', "section--alt")
    arts = sec(title_block("Health guides for patients and families") + '<div class="grid grid--3">' + "".join(acard(TP[k]) for k in ("hypertension", "child-health", "malaria")) + "</div>")
    fac = lambda i, h, t: f'<div class="infoitem"><span class="infoitem__icon">{ico(i)}</span><div><h3>{h}</h3><p>{t}</p></div></div>'
    facs = sec(f'<div class="fac"><div>{title_block("Our facilities")}<div class="infogrid" style="grid-template-columns:1fr 1fr">' + fac("fa-vial", "Laboratory", "Tests that support diagnosis and monitoring.") + fac("fa-pills", "Pharmacy", "Medicines with guidance on using them safely.") +
               fac("fa-truck-medical", "Emergency care", "For sudden, serious illness or injury.") + fac("fa-bandage", "Minor procedures and first aid", "Treatment of minor injuries, with aftercare advice.") +
               f'</div></div><aside class="aside"><div class="aside__box aside__box--blue"><h3>Need help choosing a service?</h3><p style="font-size:.95rem">Call us and the team will point you in the right direction.</p><a class="btn btn--white" href="tel:{TEL}">{ico("fa-phone")} {PHONE}</a></div></aside></div>', "section--alt")
    band = (f'<section class="band"><div class="container reveal"><div class="split"><div><h2>You&rsquo;re in good hands</h2><p>NexaCare brings consultations, laboratory and pharmacy services, maternal and child health, counselling and physiotherapy together in {esc(SITE["locality"])}. Walk-ins are welcome, and you can also request an appointment.</p>'
            f'<div class="btn-row"><a class="btn btn--white" href="appointments.html">Request appointment</a><a class="btn btn--white" href="contact.html">Contact us</a></div></div>'
            f'<div><h2>Care at home</h2><p>Homecare supports older adults, people recovering from illness and the families who care for them. The team talks through every request before anything is arranged.</p><div class="btn-row"><a class="btn btn--white" href="homecare.html#request">Request homecare</a><a class="btn btn--white" href="homecare.html">About homecare</a></div></div></div></div></section>')
    ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "MedicalClinic", "name": SITE["name"], "slogan": SITE["tagline"], "telephone": SITE["phone"], "email": MAIL, "address": {"@type": "PostalAddress", "addressLocality": "Kitale", "addressCountry": "KE"}}) + "</script>"
    out("index.html", shell(f"{SITE['name']} | {SITE['tagline']}, Gatua, Kitale", "NexaCare Health Centre in Gatua, Kitale offers outpatient consultations, maternal and child health, laboratory, pharmacy, homecare and telemedicine.",
                            hero + appt + carousel + best + glance() + arts + facs + band, "home", ld=ld, full_title=True))

def services_dir():
    setr("services.html")
    b = banner("Our services", [("Services", "services.html")]) + sec('<div class="grid grid--4">' + "".join(dcard(s) for s in SERV) + "</div>") + cta_strip("Not sure which service you need? Call us and we will point you in the right direction.", "Contact us", "contact.html")
    out("services.html", shell("Our services", "Outpatient consultations, maternal and child health, laboratory, pharmacy, family planning, emergency care, minor procedures, counselling, physiotherapy, homecare and telemedicine in Kitale.", b, "services"))

def service_page(s):
    if s.get("page"): return
    path = f"services/{s['slug']}.html"; setr(path)
    box = lambda i, h, items: f'<div class="aside__box"><h3>{ico(i)} {h}</h3>{dots(items)}</div>'
    em = f'<div class="alert-box"><h2>In an emergency</h2><p>Do not wait for an appointment or use a website form. Go to the nearest emergency facility or call emergency services now.</p></div>' if s.get("emergency") else ""
    rel = "".join(f'<li><a href="{surl(SV[r])}">{esc(SV[r]["title"])}</a></li>' for r in s["related"]) + "".join(f'<li><a href="{turl(TP[t])}">Guide: {esc(TP[t]["title"])}</a></li>' for t in s["topics"])
    intro = sec(f'<div class="intro-split intro-split--aside"><div>{photo("service-" + s["slug"], s["title"], "4/3", pos="center 12%")}</div><div>{title_block("About this service")}<p class="lead">{esc(s["intro"])}</p>{em}'
                f'<div class="btn-row"><a class="btn btn--primary" href="{R}appointments.html">Request appointment</a><a class="btn btn--outline" href="tel:{TEL}">{ico("fa-phone")} {PHONE}</a></div></div></div>')
    three = sec('<div class="grid grid--3">' + box("fa-list-check", "What to expect", s["expect"]) + box("fa-user-group", "Who it may be for", s["for"]) + box("fa-clipboard-check", "How to prepare", s["prepare"]) + "</div>", "section--alt")
    faq = sec(f'<div class="layout-aside"><div>{title_block("Frequently asked questions")}{faq_list(s["faqs"])}<p class="meta-line">{DISC} Specific tests and treatments vary, so please call to ask about your situation.</p></div>'
              f'<aside class="aside"><div class="aside__box"><h3>Related</h3><ul>{rel}</ul></div><div class="aside__box aside__box--blue"><h3>Talk to our team</h3><p style="font-size:.92rem">Call <a href="tel:{TEL}">{PHONE}</a> or request an appointment.</p><a class="btn btn--white" href="{R}appointments.html">Request appointment</a></div></aside></div>')
    out(path, shell(s["title"], f'{s["title"]} at NexaCare Health Centre, Gatua, Kitale. {s["short"]}', banner(s["title"], [("Services", "services.html"), (s["title"], path)]) + intro + three + faq, "services"))

def homecare():
    setr("homecare.html")
    fh = form("homecare", homecare_fields(), "hc", "Send homecare enquiry", "A member of the team will contact you to talk about the request. A visit is only confirmed after we speak with you and agree the details.")
    hero = (f'<section class="hc-hero"><div class="container hc-hero__in{"" if has_photo("homecare-hero") else " hc-hero__in--solo"}"><div><span class="kicker">Homecare in {esc(SITE["locality"])}</span><h1>Professional healthcare and compassionate support, at home.</h1>'
            f'<p class="lead">For older adults, people recovering from illness, and the families who look after them. Tell us what is needed and the team will talk it through with you.</p>'
            + dots(["Older adults who need help at home", "People recovering after illness or a hospital stay", "Families caring for a sick or dependent relative"]) +
            f'<div class="btn-row"><a class="btn btn--green" href="#request">Request homecare</a><a class="btn btn--outline" href="tel:{TEL}">{ico("fa-phone")} Speak to our team</a></div></div>'
            + (f'<div class="hc-hero__media">{photo("homecare-hero", "A caregiver assisting an older person at home", "4/4.6", pos="center 20%").replace("loading=\"lazy\" ", "")}</div>' if has_photo("homecare-hero") else "") + '</div></section>')
    who = sec(f'<div class="split"><div>{title_block("Who homecare may help")}<p class="lead">Many families reach a point where looking after someone at home becomes difficult. Homecare is for those moments.</p>'
              f'<p>If you are not sure whether a home visit would suit your relative, send an enquiry or call us. The team will ask a few questions and help you decide.</p>' + (photo("homecare-visit", "A nurse visiting a patient at home", "3/2", pos="center 30%") if has_photo("homecare-visit") else "") + '</div>'
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
    why = (f'<section class="section hc-warm"><div class="container reveal"><div class="split"><div>{title_block("Why families choose care at home")}'
           + dots(["Care in a familiar, comfortable place", "Support for dignity and independence", "Easier coordination between the family and the care team", "Fewer journeys, when it is clinically suitable"]) +
           f'<p class="small" style="margin-top:1rem">Homecare does not replace hospital treatment, and not every patient is suitable for care at home. The team will advise honestly.</p></div>'
           f'<div>' + (photo("homecare-family", "A family with a caregiver at home", "3/2", pos="center 30%") if has_photo("homecare-family") else "") + f'<h2>For the family</h2><p class="pull">Looking after someone you love can be tiring and worrying. You do not have to work everything out alone.</p><p>Call us, share your concerns, and we will explain the next steps. You may find these guides helpful: '
           f'<a href="{turl(TP["fall-prevention"])}">preventing falls</a>, <a href="{turl(TP["healthy-ageing"])}">healthy ageing</a> and <a href="{turl(TP["medication-safety"])}">medication safety</a>.</p></div></div></div></section>')
    cov = sec(f'<div class="split"><div>{title_block("Where we can help")}<p class="lead">NexaCare is based in {esc(SITE["locality"])}.</p><p>Tell us your location or estate in the enquiry form and the team will confirm whether a home visit is possible there.</p></div>'
              f'<div><ul class="contact-block"><li>{ico("fa-phone")}<div><strong>Telephone</strong><a href="tel:{TEL}">{PHONE}</a></div></li><li>{ico("fa-envelope")}<div><strong>Email</strong><a href="mailto:{MAIL}">{MAIL}</a></div></li></ul></div></div>', "section--alt")
    req = sec(f'<div class="split"><div class="hc-form-side">{title_block("Request homecare", "Tell us the basics and we will contact you.")}'
              f'<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Emergencies.</strong> This form is not for emergencies and is not monitored around the clock. If someone is in danger, go to the nearest emergency facility or call emergency services.</p></div>'
              f'<div class="notice">{ico("fa-lock")}<p>Please do not send medical records or detailed health information here. Keep the note brief. A clinician will ask for what is needed. Sending an enquiry does not guarantee a visit.</p></div></div>'
              f'<div class="form-card">{fh}</div></div>', "", "request")
    faq = sec(title_block("Homecare questions") + faq_list([("How do I know if homecare is right for my relative?", "Send an enquiry or call us. The team will ask about the person&rsquo;s needs and tell you whether a home visit may be suitable."), ("What happens after I send the form?", "A member of the team contacts you by your preferred method. Nothing is arranged until you have spoken with us."),
            ("Which areas do you visit?", "Please give your location or estate in the form. The team will confirm whether a visit is possible there."), ("How do I ask about fees?", "Please ask when the team contacts you, or call us."), ("Can I be involved in the care?", "Yes. Families are welcome to take part, and the team can explain how to coordinate with the care team."),
            ("What if it is an emergency?", "Do not wait for an enquiry to be answered. Go to the nearest emergency facility or call emergency services."), ("Should I include medical details in the form?", "No. Keep the note brief and general. The team will ask for any further information during a conversation.")]), "section--alt")
    out("homecare.html", shell("Homecare in Kitale", "Homecare enquiries for older adults and people recovering from illness at NexaCare Health Centre, Gatua, Kitale. Request a call from the care team.", hero + who + svc + how + why + cov + req + faq, "homecare"))

def team():
    if not TEAM: return
    setr("our-team.html")
    side = '<ul class="sidelist">' + "".join(f'<li><a href="{surl(s)}">{esc(s["title"])}</a></li>' for s in SERV) + "</ul>"
    out("our-team.html", shell("Our team", "Meet the healthcare professionals at NexaCare Health Centre, Gatua, Kitale.", banner("Our team", [("Our team", "our-team.html")]) +
        sec(f'<div class="team-layout"><aside><h2 style="font-size:1.15rem">Our services</h2>{side}</aside><div><div class="team-grid">' + "".join(staff_card(p) for p in TEAM) + '</div></div></div>'), "team"))
    for p in TEAM:
        pp = f"team/{p['slug']}.html"; setr(pp)
        rows = "".join(f"<h2>{h}</h2>{c}" for h, c in [("Qualifications", ul(p["qualifications"]) if p.get("qualifications") else ""), ("Languages", f"<p>{esc(', '.join(p['languages']))}</p>" if p.get("languages") else ""),
              ("Services", "<ul>" + "".join(f'<li><a href="{surl(SV[x])}">{esc(SV[x]["title"])}</a></li>' for x in p.get("services", []) if x in SV) + "</ul>" if p.get("services") else "")] if c)
        exp = f'<p><strong>{esc(str(p["experience_years"]))} years</strong> of experience</p>' if p.get("experience_years") else ""
        out(pp, shell(p["name"], f'{p["name"]}, {p.get("title","")} at NexaCare Health Centre.', banner(p["name"], [("Our team", "our-team.html"), (p["name"], pp)]) +
            sec(f'<div class="profile"><img src="{R}{p["photo"]}" alt="{esc(p.get("photo_alt") or p["name"])}" width="800" height="1005"><div class="prose"><h2>{esc(p["name"])}</h2><p>{esc(p.get("title",""))}</p>{exp}<p>{esc(p.get("bio",""))}</p>{rows}<p><a class="btn btn--primary" href="{R}appointments.html">Request appointment</a></p></div></div>'), "team"))

def about():
    setr("about.html")
    fac = lambda i, h, t: f'<div class="infoitem"><span class="infoitem__icon">{ico(i)}</span><div><h3>{h}</h3><p>{t}</p></div></div>'
    intro = sec(f'<div class="intro-split intro-split--aside"><figure class="figcap" style="margin:0">{photo("duo", "A doctor and a nurse in a hospital ward", "4/3.4", pos="center 15%")}<figcaption>Walk in for compassionate care in a modern setting.</figcaption></figure>'
                f'<div>{title_block("Welcome to NexaCare Health Centre")}<p>NexaCare is a health centre serving {esc(SITE["locality"])} and the surrounding community. We offer outpatient consultations, maternal and child health, laboratory and pharmacy services, family planning, emergency care, minor procedures and first aid, counselling, physiotherapy, homecare and telemedicine.</p>'
                f'<div class="mv"><div><h3>{ico("fa-heart-pulse")} Our approach</h3><p>{esc(SITE["tagline"])}. We combine modern clinical practice with a respectful, personal approach.</p></div><div><h3>{ico("fa-door-open")} Walk-in care</h3><p>You can come in without booking, or request an appointment to plan your visit.</p></div></div>'
                f'<p style="margin-top:1.5rem"><a class="btn btn--outline" href="services.html">Our services</a></p></div></div>')
    grid = sec('<div class="infogrid">' + fac("fa-vials", "Laboratory and pharmacy", "Tests and medicines at the centre, so fewer trips.") + fac("fa-baby", "Maternal and child health", "Support for mothers, babies and children.") + fac("fa-house-medical", "Homecare", "Support at home for older adults and people recovering from illness.") +
               fac("fa-laptop-medical", "Telemedicine", "Speak to a health professional remotely when a visit is not possible.") + fac("fa-hand-holding-heart", "Counselling", "A private space to talk through worries and difficult events.") + fac("fa-person-walking", "Physiotherapy", "Help to move well after injury or illness.") + "</div>", "section--alt")
    gal = "".join(f'<figure style="margin:0">{photo(k, "", "1/1", pos="center 15%")}</figure>' for k in ("doctor-corridor", "doctor-clipboard", "doctor-studio", "duo"))
    gf = sec(f'<div class="split"><div>{title_block("Photo gallery")}<div class="gallery">{gal}</div></div><div>{title_block("Frequently asked questions")}' + faq_list([("Where is NexaCare located?", f"{esc(SITE['locality'])}. Call us for directions."), ("Do I need an appointment?", "No. Walk-ins are welcome, and you can also request an appointment."), ("Is homecare available?", "Please see the <a href='homecare.html'>homecare page</a> or call us to discuss your situation."), ("How can I contact the team?", f"Call <a href='tel:{TEL}'>{PHONE}</a> or email <a href='mailto:{MAIL}'>{MAIL}</a>.")]) + "</div></div>")
    out("about.html", shell("About us", "About NexaCare Health Centre in Gatua, Kitale: our services and our approach to compassionate, modern healthcare.", banner("About us", [("About us", "about.html")]) + intro + grid + cta_strip() + gf, "about"))

def appointments():
    setr("appointments.html")
    f = form("appointment", appt_fields(), "ap", "Send request", "NexaCare will contact you to confirm a date and time. Your appointment is not confirmed until we do.")
    b = banner("Request an appointment", [("Appointments", "appointments.html")]) + sec(f'<div class="split"><div>{title_block("Before you send", "Tell us what you need and we will contact you to confirm.")}{dots(["This is a request. Your appointment is confirmed only when NexaCare contacts you.", "Walk-ins are also welcome.", "Share the basics only. Do not include medical history or ID numbers."])}'
        f'<div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p><strong>Urgent problem?</strong> Do not use this form. Go to the nearest emergency facility or call emergency services.</p></div><p>Prefer to talk? Call <a href="tel:{TEL}">{PHONE}</a>.</p></div><div class="form-card">{f}</div></div>')
    out("appointments.html", shell("Request an appointment", "Request an appointment at NexaCare Health Centre, Gatua, Kitale. Share the basics and the team will contact you to confirm.", b, "appointments"))

def contact():
    setr("contact.html")
    f = form("contact", [dict(name="name", label="Your name", req=1), dict(name="email", label="Your email", type="email"), dict(name="phone", label="Phone", type="tel"), dict(name="message", label="Your message", type="textarea", req=1, full=1, hint="Please do not include medical history or ID numbers."), dict(name="consent", label=CONSENT(), type="check", req=1)], "ct", "Send message", "We will reply using the details you gave.")
    f = f.replace('class="btn btn--primary"', 'class="btn btn--primary btn--block btn--pill"')
    qc = lambda i, h, t: f'<li>{ico(i)}<div><strong>{h}</strong> {t}</div></li>'
    b = banner("Contact us", [("Contact", "contact.html")]) + sec(f'<div class="gtitle"><h2>Get in touch with us</h2></div><div class="cform"><div class="panel"><h3>Send us a message</h3>{f}</div>'
        f'<div class="panel"><h3>Quick contact</h3><p>If you have any questions, simply use the contact details below.</p><ul class="qc">' + qc("fa-location-dot", "Location:", esc(SITE["locality"])) + qc("fa-phone", "Phone:", f'<a href="tel:{TEL}">{PHONE}</a>') + qc("fa-envelope", "Email:", f'<a href="mailto:{MAIL}">{MAIL}</a>') +
        f'</ul><div class="notice notice--warn">{ico("fa-triangle-exclamation")}<p>For emergencies, do not use this form. Go to the nearest emergency facility or call emergency services.</p></div></div></div>')
    out("contact.html", shell("Contact us", "Contact NexaCare Health Centre in Gatua, Kitale by telephone, email or message.", b, "contact"))

def faq():
    setr("faq.html")
    g = lambda h, items: f'<h2>{h}</h2>{faq_list(items)}'
    body = "".join([g("Appointments", [("Do I need an appointment?", "NexaCare welcomes walk-in patients. You can also <a href='appointments.html'>request an appointment</a> to plan your visit. A request is not confirmed until the team contacts you."), ("How will I know my appointment is confirmed?", "The team will contact you by your preferred method to agree a date and time.")]),
        g("Services", [("Which services are offered?", "See the <a href='services.html'>services page</a>. If you need a specific test or procedure, please call and ask."), ("Is emergency care available 24 hours?", "Please confirm current emergency hours by phone before travelling. In a life-threatening emergency, go to the nearest emergency facility or call emergency services.")]),
        g("Homecare", [("How do I ask about homecare?", "Use the <a href='homecare.html#request'>homecare request form</a> or call us. A visit is only confirmed after we speak with you and check availability."), ("How do I ask about fees?", "Please ask when we contact you, or call. Prices are confirmed by NexaCare.")]),
        g("Preparing for a visit", [("What should I bring?", "Your medicines or a list of them, earlier medical records or test results, and a list of questions."), ("Can I bring someone with me?", "Many patients do. Please tell the team if you need extra support.")]),
        g("Contacting us", [("How can I reach the clinic?", f"Call <a href='tel:{TEL}'>{PHONE}</a> or email <a href='mailto:{MAIL}'>{MAIL}</a>. See the <a href='contact.html'>contact page</a> for contact details and location."), ("Is the online form for emergencies?", "No. Forms are not monitored around the clock. For urgent problems go to the nearest emergency facility or call emergency services.")]),
        g("Billing", [("What do services cost?", "Fees are confirmed by NexaCare. Please call or ask at the centre.")])])
    out("faq.html", shell("Frequently asked questions", "Answers about appointments, services, homecare, preparing for a visit and contacting NexaCare Health Centre.", banner("Frequently asked questions", [("FAQs", "faq.html")]) + sec(f'<div class="layout-aside"><div class="prose">{body}</div><aside class="aside"><div class="aside__box aside__box--blue"><h3>Still have a question?</h3><p style="font-size:.93rem">Call us or send a message.</p><a class="btn btn--white" href="contact.html">Contact us</a></div></aside></div>'), "faq"))

def topic_page(t):
    path = f"health-library/{t['slug']}.html"; setr(path)
    S = lambda i, h, items: f'<h2 id="{i}">{esc(h)}</h2>{ul(items)}' if items else ""
    toc = [("overview", "Overview"), ("symptoms", t["symptoms_title"])] + ([("causes", t["causes_title"])] if t["causes"] else []) + [("prevention", t.get("prevention_title") or "Prevention and staying well"), ("seek", "When to seek a health assessment"), ("urgent", "Urgent warning signs"), ("sources", "Sources")]
    urgent = f'<div class="alert-box" id="urgent"><h2>{ico("fa-triangle-exclamation")} Get urgent medical help if you notice</h2>{ul(t["urgent"])}<p style="margin-top:.75rem">Go to the nearest emergency facility or call emergency services. Do not wait for an appointment.</p></div>'
    refs = "<ol class=refs>" + "".join(f'<li><a href="{u}" rel="noopener" target="_blank">{esc(n)}</a></li>' for n, u in t["refs"]) + "</ol>"
    art = (f'<article class="prose"><div class="topic-meta"><span class="tag">{esc(t["tag"])}</span></div>{('<figure class="topic-photo">' + photo("topic-" + t["slug"], t["title"], "16/9", pos="center 30%") + '</figure>') if has_photo("topic-" + t["slug"]) else ""}<h2 id="overview">Overview</h2><p class="lead">{esc(t["what"])}</p>{S("symptoms", t["symptoms_title"], t["symptoms"])}{S("causes", t.get("causes_title", ""), t["causes"])}'
           f'{S("prevention", t.get("prevention_title") or "Prevention and staying well", t["prevention"])}{S("seek", "When to seek a health assessment", t["seek"])}{urgent}'
           f'<div class="notice">{ico("fa-circle-info")}<p>{DISC} This page is education only and does not mean NexaCare provides specialist care for this condition. Call us to ask what is available.</p></div>'
           f'<h2 id="sources">Sources</h2>{refs}<p class="meta-line">Prepared on {SITE["build_date"]} from the sources listed above.</p></article>')
    svcs = "".join(f'<li><a href="{surl(SV[x])}">{esc(SV[x]["title"])}</a></li>' for x in t["services"]); rel = "".join(f'<li><a href="{turl(TP[x])}">{esc(TP[x]["title"])}</a></li>' for x in t["topics"])
    aside = (f'<aside class="aside"><div class="aside__box"><h3>On this page</h3><ul>' + "".join(f'<li><a href="#{i}">{esc(n)}</a></li>' for i, n in toc) + f'</ul></div><div class="aside__box aside__box--blue"><h3>Talk to our team</h3><p style="font-size:.92rem">If you are worried, you do not need to wait.</p><a class="btn btn--white" href="{R}appointments.html">Request appointment</a></div>'
             f'<div class="aside__box"><h3>Related services</h3><ul>{svcs}</ul></div><div class="aside__box"><h3>Related reading</h3><ul>{rel}</ul></div></aside>')
    out(path, shell(t["title"], f'{t["title"]}: plain-language health information with warning signs and sources, from NexaCare Health Centre.', banner(t["title"], [("Health library", "health-library/index.html"), (t["title"], path)]) + sec(f'<div class="layout-aside">{art}{aside}</div>'), "library"))

def library():
    setr("health-library/index.html")
    tags = {}
    for t in TOP: tags[t["tag"]] = tags.get(t["tag"], 0) + 1
    cats = '<ul class="catlist">' + "".join(f"<li><span>{esc(k)}</span><span>({n})</span></li>" for k, n in tags.items()) + "</ul>"
    pop = '<ul class="poplist">' + "".join(f'<li><a href="{turl(TP[k])}" tabindex="-1" aria-hidden="true">{photo("topic-" + k, TP[k]["title"], "1/1")}</a><a href="{turl(TP[k])}">{esc(TP[k]["title"])}<small>{esc(TP[k]["tag"])}</small></a></li>' for k in ("hypertension", "child-health", "malaria")) + "</ul>"
    b = banner("Health library", [("Health library", "health-library/index.html")]) + sec(f'<div class="news"><div><div class="notice">{ico("fa-circle-info")}<p>{DISC} Having a guide here does not mean NexaCare offers specialist care for every condition.</p></div><div class="news__list">' + "".join(acard(t, i == 0) for i, t in enumerate(TOP)) + f'</div></div><aside class="sidebar"><h2>Categories</h2>{cats}<h2>Start here</h2>{pop}</aside></div>')
    out("health-library/index.html", shell("Health library", "Plain-language health guides on blood pressure, diabetes, malaria, ageing, falls, maternal and child health, medicines and respiratory illness.", b, "library"))

def legal():
    for path, title, intro, secs in [
        ("privacy.html", "Privacy and cookies", "How NexaCare Health Centre handles the details you send through this website.",
         [("Who we are", f"{SITE['name']}, {SITE['locality']}. Contact: {MAIL}."),
          ("What we collect", "Only what you type into our forms: name, telephone, optional email, the service you ask about, preferred date and time, general location for home visits, a brief note and your contact preference. Please do not send medical history, ID numbers or test results through the website."),
          ("Why we use it", "To reply to your request and to arrange or discuss care. We do not use these details for advertising."), ("Who can see it", "Authorised NexaCare staff who handle enquiries."),
          ("How long we keep it", "We keep enquiries only as long as needed to respond and to arrange care, and then delete them."),
          ("Your rights", f"You may ask to see, correct or delete your information, or object to its use, by contacting {MAIL}. You may also complain to the Office of the Data Protection Commissioner."),
          ("Cookies and third parties", "This site sets no analytics, advertising or tracking cookies. Fonts and icons load from Google Fonts and Font Awesome&rsquo;s content network, so your browser contacts those providers when a page loads.")]),
        ("terms.html", "Website terms", "The terms for using the NexaCare Health Centre website.",
         [("Information only", "Content on this website is general information. It does not diagnose, treat or replace advice from a qualified health professional."), ("Emergencies", "Do not use this website, forms or email in an emergency. Go to the nearest emergency facility or call emergency services."),
          ("Requests are not bookings", "Sending a form is a request. An appointment or visit exists only when NexaCare confirms it to you."), ("Services and prices", "Service availability and prices are confirmed by NexaCare and may change."),
          ("Links and images", "External links lead to sites we do not control. Some images are illustrative and do not necessarily show NexaCare staff, patients or facilities.")])]:
        setr(path)
        out(path, shell(title, f"{title} for NexaCare Health Centre.", banner(title, [(title, path)]) + sec(f'<div class="prose"><p class="lead">{intro}</p>' + "".join(f"<h2>{h}</h2><p>{p}</p>" for h, p in secs) + "</div>"), ""))

def notfound():
    global R
    setr("404.html"); R = "/"
    out("404.html", shell("Page not found", "This page could not be found.", f'<section class="container error-page"><h1>We could not find that page</h1><p class="lead" style="margin-inline:auto">The link may be out of date. Try one of these instead.</p><div class="btn-row" style="justify-content:center"><a class="btn btn--primary" href="/index.html">Go to the homepage</a><a class="btn btn--outline" href="/services.html">See our services</a></div></section>', "", index=False))

def seo_files():
    dom = SITE["domain"] or "REPLACE-WITH-DOMAIN"
    urls = "".join(f"<url><loc>https://{dom}/{p}</loc></url>" for p, ix in PAGES if ix)
    out("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    out("robots.txt", f"User-agent: *\nAllow: /\nSitemap: https://{dom}/sitemap.xml\n")

if __name__ == "__main__":
    home(); services_dir(); [service_page(s) for s in SERV]; homecare(); team(); about(); appointments(); contact(); faq(); library(); [topic_page(t) for t in TOP]; legal(); notfound(); seo_files()
    print(f"Built {len(PAGES)} pages.")
