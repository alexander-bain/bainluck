# #11158 Vassell Under: retained served points (NOT stored rows)

`served-points.json` holds VALUES and TIMES copied from the retained served
payload `artifacts/release-1.0.4-pickup-20261011/futures-history-31519211/history-all.json`
(`GET /api/futures/31519211/history` "All" read, captured 2026-10-12T22:16:23Z,
sha256 `312906e7093457fe889100dead0ef4100e0150b2dc55a21340bd73895932f4a5`):

- the 16 whole-second Under points (the old history rail's shape, June 3 15:00:07Z
  to June 4 06:00:04Z);
- the 10 Over points that fall within 60 minutes of any of them (the rail's
  `NEAR_WINDOW_MIN`). The payload's other 153 non-settlement Over points
  (including the July 12 poll) are all further than 60 minutes from every Under
  point, so they cannot pair with any of them.

Excluded: the July 12 sub-second Under poll and both settlement points, which
are not history-shape rows.

What it is NOT: these are served-derived observations, not raw production
rows. The served payload carries no snapshot ids, token, writer or insertion
time. Every id the tests attach is SYNTHETIC. Nothing here establishes current
stored rows, token/writer identity, run identity or insertion chronology.
