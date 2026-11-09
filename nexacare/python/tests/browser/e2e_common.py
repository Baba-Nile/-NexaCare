import re, sqlite3, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
B="http://127.0.0.1:5056"; ROOT=Path(__file__).resolve().parents[3]; res=[]
def ok(n,c,x=""): res.append((n,bool(c))); print(("PASS" if c else "FAIL"),n,x,flush=True)
def page(b,**k):
    pg=b.new_page(**k); pg.route(re.compile(r'^https?://(?!127\.0\.0\.1).*'),lambda r:r.abort()); pg.set_default_timeout(8000); return pg
PAGES=[str(f.relative_to(ROOT)) for f in ROOT.rglob("*.html") if "python" not in f.parts]
