# `calibration_report-2026-05-26.html` — archived 2026-08-24

A **frozen snapshot**, not a live document. It was generated on **2026-05-26** and committed to the
repo root as `calibration_report.html` by `98100ef2` ("Update docs and report: MCE 4.8pp, golf
fixed, progress documented"). It sat at the root for three months, where it read like a current
report because nothing about a bare `.html` file at the top of a tree says how old it is.

Archived under its generation date during the Q-CLEANUP pass so the date is part of the name.

## What it says, and why you should not act on it

Its headline number is the calibration MCE as measured **2026-05-26**. Do not quote it. The whole
calibration picture has moved since — the never-graded Polymarket cohort, the `pass2_loser`
poisoning, the two moneyline sources, and the recoverable-vs-excluded denominator split are all
later findings, and several of them change the number rather than refine it.

**For a current figure, read the live endpoint, not this file:** `GET /api/calibration`
(public, 1 h cache) and the `/calibration` page.

## Why the root path kept filling back up

Three scripts still write to the repo-root `calibration_report.html`:

- `backend/scripts/calibration_analysis.py:955`
- `backend/scripts/build_calibration_report.py:773`
- `backend/scripts/build_calibration_report_svg.py:546`

That is a generated build artifact landing in a tracked location, which is how it got committed the
first time. The root path is now gitignored, so the generators keep working exactly as before and
their output simply stops being commitable by accident. Committing a future snapshot on purpose
means `git add -f` plus a dated filename in this directory — the deliberate act the accident was
imitating.
