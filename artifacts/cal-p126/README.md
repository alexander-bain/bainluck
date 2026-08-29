# CAL-P126 artifacts

`FINDING-16-CAL-whole-curve.md` is the report. `render-results.py` regenerates its §4 and the
handoff report's §4 from whatever `cell-*.json` files are present, so a later session can add a
cell and refresh both without re-measuring anything.

**`roster-*.json` are DELIBERATELY NOT COMMITTED.** Stage A rosters for the twelve measured cells
came to 7.5 MB, and a roster is a cache with a 24-hour shelf life — `load_or_freeze` prints its age
on every reuse and warns past a day, because markets resolve into a cell continuously. Committing
an expiring 7.5 MB cache buys a later session nothing it should want to use. Re-freeze with
`--roster-cache`; Stage A costs ~21 ms per resolved market.

`payload-q268.json` IS committed and must stay: it is the live proof that the served payload's own
buckets reproduce its own headline, and `test_cohort_mce_reproduces_a_served_payload` skips itself
without it. Refresh it when the population version moves off `q268`.
