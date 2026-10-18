"""Checks the built site: internal links and anchors, image files, titles, descriptions, one h1, alt text.  Run: python python/check_site.py"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
ROOT = Path(__file__).resolve().parent.parent
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
pages = {f: P() for f in ROOT.rglob("*.html")}
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
print(f"Checked {len(pages)} pages.")
print("\n".join(bad) if bad else "No problems found.")
sys.exit(1 if bad else 0)
