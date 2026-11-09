# Test report: multi-branch public website (7 November 2026)

## Automated (run from the project root)
| Command | Result |
|---|---|
| `python python/build.py` | Built 37 pages (30 in sitemap, 7 noindex: six pending branch pages + 404) |
| `python python/check_site.py` | Checked 37 pages. No problems found. |
| `python -m unittest discover -s python/tests -v` | **87 tests, all pass** (45 existing portal/security tests unchanged and passing, 42 new) |

`check_site.py` now also verifies: all internal links and anchors; image files; one h1, unique title and description on every branch page; branch pages match the `noindex` rule; JSON-LD parses and contains no unverified telephone, address, coordinates or hours; no telephone link other than the central line, no WhatsApp, map or iframe unless verified; every page links to the branches page and carries the Request Appointment button; every enquiry form has a branch field whose options equal `data/branches.json`; no inline `style=` attributes (the site CSP would block them); sitemap equals the set of indexable pages; robots.txt disallows `/staff/`, `/portal/`, `/api/`.

New tests: `test_branches.py` (data rules and validator; committed build output; a temporary copy where Eldoret is given verified test data to prove facts flow to the card, page, structured data and sitemap while other branches stay clean; negative tests proving the checker catches a leaked number and a missing branch option; idempotent rebuild) and `test_enquiries.py` (API allow-list, all seven branch values plus `no-preference`, malicious values rejected with nothing stored, all four enquiry kinds, existing validation unchanged, unknown fields ignored, migration of a pre-branch database, retrieval on an unmigrated read-only database, CLI, staff inbox display, filter, HTML escaping, permissions).

## Browser tests (Chromium via Playwright, scripts in `python/tests/browser/`): 38 / 38 checks passed
- No horizontal overflow on all 37 pages at 360, 768 and 1440 px; no JavaScript errors.
- 52 distinct internal URLs found by crawling every link on every page all return HTTP 200; images load on the home, about, branches, a branch and a service page.
- Desktop dropdowns (Services, Our Branches, Health Library) open on hover; keyboard Enter opens, Escape closes; first Tab reaches the skip link; all nine required navigation items present.
- Mobile (390 px) and tablet (820 px) menu opens, branch submenu opens, Escape closes; mobile quick-action bar visible.
- Branch picker on the home page, branch search (match, no-match with central line, clear), `?branch=` pre-selection, appointment branch chips synced with the select.
- Validation: empty submission shows a summary and field errors with a clear branch message. Submissions of appointment, branch-page, contact and homecare forms each showed a reference and branch; the database held the branch in both the column and the payload for all four. A blocked network shows the phone fallback and says nothing was saved.

## Not verified
- Appearance with the live Google font and Font Awesome icons (no internet in the build environment; icons were therefore blank in screenshots, layout was unaffected).
- Safari and Firefox; screen readers; a full WCAG audit; Lighthouse timings; PostgreSQL (the public enquiry store is SQLite only).
- Photographs: the branch visuals are branded graphics, not photos of the branches. The supplied people photos keep the licence caveat in the main README.

## Design notes that affect the owner
- Gatua, Kitale is treated as the main centre, not one of the six (please confirm).
- Branch pages are `noindex` until a branch is `open` with verified details.
- Statements that were true of a single centre ("walk-ins welcome", service availability) are kept but service availability is described as varying by branch.
