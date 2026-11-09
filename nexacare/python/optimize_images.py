#!/usr/bin/env python3
"""Creates a .webp next to every .jpg/.png photo under assets/images (not logos), so build.py can serve smaller files with <picture>.
The original files are never modified or deleted.  Needs Pillow:  pip install Pillow   then:  python python/optimize_images.py"""
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parent.parent
made = 0
for f in sorted((ROOT / "assets" / "images").rglob("*")):
    if f.suffix.lower() not in (".jpg", ".jpeg", ".png") or "logo" in f.parts: continue
    out = f.with_suffix(".webp")
    if out.exists() and out.stat().st_mtime >= f.stat().st_mtime: continue
    with Image.open(f) as im:
        im.convert("RGB").save(out, "WEBP", quality=80, method=6)
    made += 1
    print(f"{f.relative_to(ROOT)}  {f.stat().st_size // 1024} KB -> {out.stat().st_size // 1024} KB")
print(f"Created {made} WebP file(s).")
