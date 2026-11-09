# Browser tests (optional, need Playwright)
```
pip install playwright && playwright install chromium
NEXACARE_DB=/tmp/e2e.db PORT=5056 python python/app.py &        # a throw-away database
python python/tests/browser/e2e_pages.py        # overflow at 360/768/1440, every internal URL returns 200, images load
python python/tests/browser/e2e_journeys.py     # dropdowns, mobile menu, keyboard, branch search, form submissions, branch saved in the database
```
Use a fresh database each time (the API allows 5 submissions per 10 minutes per client). External fonts/icons are blocked by the scripts so they run offline.
