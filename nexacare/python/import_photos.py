#!/usr/bin/env python3
"""Import approved stock photos listed in data/stock-photos.json into the site.
Needs: pip install Pillow (and internet access when 'url' is used).  Run:  python python/import_photos.py [--build]
For each entry with a 'url' or 'local' file it: requires page/credit/license to be filled in, downloads and checks the image, rejects images that are
too small or near-duplicates of a photo already on the site, crops to the slot's aspect ratio, saves an optimised JPEG under assets/images/<folder>/,
and records file, size, alt, source, credit and licence in data/image-manifest.json."""
import json, shutil, sys, urllib.request
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
MIN_WIDTH = 1000          # reject small images that would look soft
MAX_WIDTH = 1600
UA = {"User-Agent": "NexaCareSiteBuilder/1.0 (+image import)"}

def ahash(im):
    g = im.convert("L").resize((16, 16), Image.LANCZOS); px = list(g.tobytes()); avg = sum(px) / len(px)
    return int("".join("1" if p > avg else "0" for p in px), 2)
def dist(a, b): return bin(a ^ b).count("1")

def load(entry):
    if entry.get("local"):
        return Image.open(ROOT / entry["local"] if not Path(entry["local"]).is_absolute() else entry["local"])
    req = urllib.request.Request(entry["url"], headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        if not r.headers.get("Content-Type", "").startswith("image/"): raise ValueError("URL did not return an image")
        return Image.open(BytesIO(r.read()))

def crop(im, aspect, focus):
    w, h = map(float, aspect.split(":")); target = w / h; iw, ih = im.size
    fy = 0.3 if "30" in focus else (0.25 if "25" in focus else 0.5)
    if iw / ih > target:
        nw = int(ih * target); x = (iw - nw) // 2; return im.crop((x, 0, x + nw, ih))
    nh = int(iw / target); y = int((ih - nh) * fy); return im.crop((0, y, iw, y + nh))

def main():
    cfg = json.loads((D / "stock-photos.json").read_text(encoding="utf-8")); mf = json.loads((D / "image-manifest.json").read_text(encoding="utf-8"))
    hashes = {}
    for k, v in mf["slots"].items():
        f = v.get("file")
        if f and (ROOT / f).exists():
            try: hashes[k] = ahash(Image.open(ROOT / f))
            except Exception: pass
    done = failed = 0
    for e in cfg["photos"]:
        if not (e.get("url") or e.get("local")): continue
        slot = e["slot"]
        miss = [k for k in ("page", "credit", "license", "alt") if not e.get(k)]
        if miss: print(f"SKIP {slot}: fill in {', '.join(miss)} first"); failed += 1; continue
        try:
            im = ImageOps.exif_transpose(load(e)).convert("RGB")
            if im.width < MIN_WIDTH: raise ValueError(f"only {im.width}px wide (need {MIN_WIDTH}+)")
            h = ahash(im); twin = [k for k, v in hashes.items() if k != slot and dist(v, h) <= 12]
            if twin: raise ValueError(f"looks like the photo already used for {twin[0]}; use a different photo")
            im = crop(im, e["aspect"], e.get("focus", "")); im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS) if im.width > MAX_WIDTH else im
            out = ROOT / "assets" / "images" / e["folder"] / f"{slot}.jpg"; out.parent.mkdir(parents=True, exist_ok=True)
            im.save(out, quality=82, optimize=True, progressive=True)
            mf["slots"][slot] = {**mf["slots"].get(slot, {}), "file": f"assets/images/{e['folder']}/{slot}.jpg", "w": im.width, "h": im.height, "alt": e["alt"], "status": "stock photo",
                                 "source": e["page"], "credit": e["credit"], "license": e["license"]}
            hashes[slot] = h; done += 1; print(f"OK   {slot}: {im.width}x{im.height}")
        except Exception as ex:
            print(f"FAIL {slot}: {ex}"); failed += 1
    (D / "image-manifest.json").write_text(json.dumps(mf, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Imported {done}, problems {failed}.")
    if "--build" in sys.argv and done:
        import subprocess; subprocess.run([sys.executable, str(ROOT / "python" / "build.py")], check=True)
    return 1 if failed else 0
if __name__ == "__main__": sys.exit(main())
