# Managing NexaCare branches

All branch information lives in **`data/branches.json`**. Pages, forms, navigation, footer, sitemap and the backend all read it. Nothing about a branch is typed into a template.

## Decisions to confirm with the owner
1. **Gatua, Kitale.** The original site had this single location. It is kept as the **main centre** (`main_centre` in the data file) and shown separately from the six branches, with the existing central telephone and email. It appears in the branch dropdown of every form as "Gatua, Kitale (main centre)". If it should instead be an ordinary branch, move the object into the `branches` list, give it `"role": "branch"`, and rebuild: it will then get its own page.
2. **Branch details.** None were supplied, so every branch is `details_pending` and publishes only its name, a labelled link to the central line, and appointment actions.

## What is shown, and when
A value is public only if it is filled in **and** its flag under `verified` is `true`. Otherwise the page shows "Coming soon" (or omits the row) and the visitor is offered the central line, which is clearly labelled "Central line".

| Fact | Where it appears once verified |
|---|---|
| `locality`, `address` | Branch card, branch page, contact page, structured data |
| `phone` | Click-to-call on card, page, contact page; `telephone` in structured data |
| `whatsapp` | WhatsApp button (never shown otherwise) |
| `email` | Branch page and contact card (central email is used until then) |
| `hours` (+ optional `hours_schema`, e.g. `"Mo-Fr 08:00-17:00"`) | Card and page; `openingHours` only when `hours_schema` is given |
| `services` (service slugs) | "Services at this branch" list with links |
| `directions` + `directions_url` / `coordinates` / address | "Directions" button, `hasMap` and `geo` |

## Completing a branch
1. Fill the values, for example `"phone": {"display": "0700 000 000", "tel": "+254700000000"}`.
2. Set the matching `verified` flags to `true`.
3. When the owner confirms it operates, set `"status": "open"`.
4. `python python/build.py` then `python python/check_site.py`.

`build.py` refuses to build if a flag is true without a value, a slug is invalid, a phone number is malformed, a service slug does not exist, or `status` is `open` with no verified address, phone or hours. It prints which details are still pending for each branch.

## Search engines
Branch pages are generated for every branch (so links, forms and navigation work) but carry `noindex` and stay out of `sitemap.xml` until the branch is `open` **with** at least one verified address, phone or hours. This avoids publishing thin pages that say nothing factual. The branches hub page is always indexed.

## Photographs
Each branch card uses a branded location visual. To show a real photo, set `file`, `w`, `h`, `alt` for the slot `branch-<slug>` in `data/image-manifest.json`, run `python python/optimize_images.py`, then rebuild. Use only photos of the actual branch, with permission.

## Enquiries and branches
Forms send `branch` (a slug, or `no-preference`). The backend accepts only slugs listed in `branches.json` (reloaded when the file changes), stores the value in a `branch` column and in the payload, and the staff inbox (`/staff/enquiries`) shows the branch name and can filter by branch. `python python/app.py list 20 eldoret` filters on the command line. Databases created before this change are upgraded automatically (a column is added; no rows are touched) and their enquiries show "Not specified". The backend still accepts submissions with no branch, so pages cached by browsers before the update keep working.
