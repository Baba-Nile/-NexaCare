from e2e_common import *
with sync_playwright() as p:
    b=p.chromium.launch(); errs=[]
    for w in (360,768,1440):
        pg=page(b,viewport={"width":w,"height":800}); pg.on("pageerror",lambda e:errs.append(str(e))); over=[]
        for u in PAGES:
            pg.goto(f"{B}/{u}",wait_until="domcontentloaded")
            if pg.evaluate("document.documentElement.scrollWidth>innerWidth+1"): over.append(u)
        ok(f"no horizontal overflow @{w} on {len(PAGES)} pages",not over,over); pg.close()
    ok("no JS errors",not errs,errs)
    pg=page(b); seen={}; bad=[]
    for u in PAGES:
        pg.goto(f"{B}/{u}",wait_until="domcontentloaded")
        for h in pg.evaluate("[...document.querySelectorAll('a[href]')].map(a=>a.href)"):
            if not h.startswith(B): continue
            path=h.split('#')[0]
            if path in seen: continue
            try: seen[path]=urllib.request.urlopen(path).status
            except Exception as e: seen[path]=getattr(e,'code',0); bad.append(h)
    ok(f"all {len(seen)} distinct internal URLs return 200",not bad,bad)
    for u in ("index.html","about.html","branches/index.html","branches/eldoret.html","services/outpatient.html"):
        pg.goto(f"{B}/{u}"); H=pg.evaluate("document.body.scrollHeight")
        for y in range(0,H,400): pg.evaluate(f"scrollTo(0,{y})"); pg.wait_for_timeout(50)
        pg.wait_for_timeout(200); br=pg.evaluate("[...document.images].filter(i=>i.complete&&i.naturalWidth==0).map(i=>i.src)"); ok(f"images load {u}",not br,br)
    b.close()
print("SUMMARY A",sum(v for _,v in res),"/",len(res))
