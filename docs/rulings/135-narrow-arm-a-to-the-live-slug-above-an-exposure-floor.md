# RULING 135 — A release narrows the window; it does not disqualify the day — above a minimum-exposure floor

date: 2026-08-24
author: Alex
issues: #2107, #2143
supersedes: partially amends ruling 130
superseded-by: **ruling 136 (2026-08-26) retires this ruling's arm A for #2107.**
The 6 h floor below was itself unrunnable — ~41 % per attempt, ~868 days expected wait for seven
consecutive banked days — and the gate banked zero days in the three days it was live. The
reasoning about attribution was also aimed at the wrong object: #2107's subject is a code change
present in every deployed slug, not a slug. Read 136 for what is in force. What survives here is
the served-requests floor and the general shape of the argument (an unrunnable falsifier grades
INCONCLUSIVE forever, which reads as "not yet proven"), which 136 quotes back at this ruling.

Ruling 130 said a window straddling a release is INCONCLUSIVE, because its errors
cannot be attributed to a slug. That is correct about attribution and it turned
out to be **unschedulable**, which is a different kind of wrong.

LAT-P087 measured the rule against the deploy cadence it has to live on. Across
96 production releases in the twelve days 2026-08-12 → 2026-08-24 (95 intervals,
median gap 0.67 h, p90 11.03 h, max 51.19 h; gaps ≥ 24 h = 1 of 95), the number
of UTC dates that could host a window whose arm-A lookback is deploy-free:

| lookback the day must keep clear | dates that qualify | longest CONSECUTIVE run |
|---|---|---|
| 24 h (ruling 130 as written) | 2 of 12 | **2** |
| 12 h | 9 of 12 | **4** |
| 6 h | 12 of 12 | **12** |
| 2–4 h | 12 of 12 | 12 |

#2107's falsifier requires **seven consecutive** clean days. Under ruling 130 the
longest run production could offer was two. The falsifier was not strict — it was
**unrunnable**, and an unrunnable falsifier grades INCONCLUSIVE forever, which
reads to every future reader as *not yet proven* rather than *broken*. Nobody
goes looking at "not yet closed". That is the `_detect_restart` failure again
(#2107's own predicate was unconditionally true for eight days and nobody
noticed) with a new name and a ruling behind it.

## The ruling

**Arm A scopes its count to the live slug instead of disqualifying the day.**
Where a release lands inside the lookback, the count is taken from
`max(deploy_time, window_start)` forward rather than over a flat 24 h.

**And a day counts toward the seven only above a minimum-exposure floor.** Two
floors, both fail-closed to INCONCLUSIVE and never to CLEAN:

- **exposure duration ≥ 6 h** since the live slug took over. Below it the verdict
  stays STRADDLED, because "no failures in the 40 minutes since the deploy" is
  not evidence about the deploy — it is evidence about 40 minutes.
- **served requests ≥ 50** in the window. Six deploy-free hours in which nothing
  was asked of `/api/feed` is six hours of nothing observed; a bug that never had
  a chance to fire did not fail to fire.

6 h is **derived, not chosen**: from the table above it is the most conservative
floor that still admits a seven-day run, with five days of headroom. 12 h is not
a stricter version of this criterion, it is an unrunnable one — and the whole
point of the ruling is that unrunnable and strict are not the same thing.

## Why the relaxation is also a sharpening

These are the same edit, and that is the part worth keeping.

An **unnarrowed** count spanning two slugs cannot refute anything: the events may
belong to the retired slug, so the only honest verdict is INCONCLUSIVE. A
**narrowed** count is attributable to the running slug, so a non-zero one is a
genuine FAILED. Scoping the interval is what turns arm A from a criterion that
can only ever shrug into one that can actually refute the fix.

Which is why narrowing has to be checked rather than declared. A NARROWED verdict
whose count was not in fact narrowed is refused, not trusted; so is one that
carries no exposure number, because a claim about how much exposure it narrowed
to is unfalsifiable without the number. Both go to INCONCLUSIVE.

## Two things this does NOT do

- **It does not touch arm B.** 500s observed on a window that ran end to end on
  one slug are that slug's, whatever arm A is scoped to. Both floors and the
  narrowing sit behind the 5xx check in the cascade, deliberately: a volume floor
  that swallowed a real refutation would be a hole, not a floor.
- **It does not credit unobserved time.** Without `--last-release-at`, the
  takeover is bounded by the oldest recorded window that answered on the current
  slug, and an observation gap is not filled in. Under-crediting exposure costs a
  re-run tomorrow; over-crediting banks a day nobody watched. Only one of those
  two errors is recoverable.

Implemented in `backend/scripts/watch_2107_feed_500s.py` (verdict `NARROWED`,
`MIN_POST_RELEASE_EXPOSURE_HOURS`, `MIN_SERVED_REQUESTS`, `sum_buckets_since`),
pinned by `backend/tests/test_watch_2107_exposure_floor.py`.

**Amendment 2026-08-26 (ruling 136).** `NARROWED`, `MIN_POST_RELEASE_EXPOSURE_HOURS` and
`test_watch_2107_exposure_floor.py` no longer exist. The retirement is pinned in
`backend/tests/test_watch_2107_blast_window.py::TestRetiredCriteriaStayRetired`, which fails if any
of them comes back — the next lane to hit a stuck gate will reach for exactly these, because they
read as the strict option. `MIN_SERVED_REQUESTS` and `sum_buckets_since` survive: the floor is now
counted in requests outside a deploy blast band, and the bucket sum is arm A's truncation fallback.
