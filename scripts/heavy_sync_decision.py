#!/usr/bin/env python3
"""#5470 — may the heavy app be synced to the main app's live commit RIGHT NOW?

**The failure this closes.** Since the heavy split (9/11 ~1pm PT) the main site
deploys itself and ``bainluck-heavy`` does not. At 12:48am Sat it sat 84 commits
behind; seven hours after Alex's manual redeploy it was **158 commits / 42
``backend/app`` files** behind again. Every background-job fix merged in between
is "live" on the website and NOT running — #5505 shipped GREEN with 109 published
Polymarket legs waiting on a worker that never got the code. ``/health``, the main
app's release list and a LOOK at the page are all blind to it.

**Why this is not "deploy heavy with every main-site release."** Notice 48 names
that mechanism in a parenthetical; it is a design, and it re-breaks ship 2. A
heavy release cycles ``worker-heavy.1``, and a dyno cycle kills whatever it is
mid-way through — which is the precise failure moving the worker into its own app
was meant to end. There were **31 backend deploys in 24h** (measured 2026-09-12),
so per-release means 31 heavy cycles a day, for code that mostly does not change
what heavy runs.

**And not "whenever a cron happens to fire" either — that was the first design and
it is the one that failed.** A schedule is uncorrelated with the thing it is
chasing: drift is CREATED by main-app deploys, so the rate you need to sync at is
the rate they happen at, and a clock cannot know that. Worse, GitHub does not
deliver the slots — measured 2026-09-13 05:15Z over every run this workflow has
ever had, **4 runs against 17 nominal hourly slots**, the last of them 3h48m
earlier, while heavy sat 7h33m and 98 commits behind with four launch ships dark
on it. Buying more lottery tickets (``34,42,50``, latency/362) raises the expected
rate and leaves the tail exactly as heavy-tailed.

So the primary trigger is ``workflow_run`` on CI completing on ``master``: the
event that CREATES the drift is the event that clears it, and the opportunity rate
tracks the deploy rate for free — including the case that matters most, a quiet
night, where no deploys means no drift means nothing is owed. The cron stays as a
backstop for the one thing the event cannot cover: a sync that was HELD (out of
band, or under the floor below) while no further deploy arrives to re-offer it.

**Which makes the trigger rate stop being the cycle rate, so the floor below is
what keeps the price honest.** ~31 CI-success runs a day against a 25-minute band
is ~13 cycles/day, and this file already rejected that rate at the top. The
``ACCEPTED_CYCLES_PER_DAY`` floor holds the cost at the budget the cron raise was
priced against, and it binds only when triggers are plentiful — at today's ~2.5
cycles/day it never fires at all.

**And not "push at a quiet minute" either.** 31 beats route to ``queue: heavy`` on
one dyno at concurrency 2 — ``*/15``, ``*/20``, ``*/30``, two 15-minute cluster
beats, plus hourly singles. No minute of the hour is reliably free of all of them.

**So what makes a window derivable at all** is a measurement the two rejected
designs did not have: what a cycle actually COSTS. It is one unit, not a pass.

* The curve is **published before** the rebuild runs (D45's publish-first reorder),
  so a kill costs a reader nothing.
* :func:`save_staged_cursor` is called **per unit, immediately after the commit**
  (``precompute_calibration.py`` "COMMIT, then advance"), so a kill costs exactly
  the in-flight unit — ``staged:unit_ms_mean`` = **119,456 ms ≈ 2 min** on
  production, against a 22-minute pass.
* Banked units survive across beats by design: a beat banks ~10 of 128
  (``staged:units_this_beat`` = 10, ``staged:units_banked`` = 120), so a full
  census intentionally spans ~13 beats.

That inverts the cost model. The job is therefore **not** to dodge all 31 beats —
impossible — but to dodge the ONE long, expensive stretch and lean on the measured
per-item durability for the rest. The band below is exactly that.

**The bank is discarded by the CONTENT of a deploy, not its timing.** The
``staged-unit/v1`` fingerprint hashes ``CALIBRATION_POPULATION_VERSION``, the tie
authority and the unit statement, so a deploy that edits the calibration statement
throws away every banked unit whenever it lands, and one that does not touch it
costs a single unit whenever it lands. Timing is the small term in both branches —
which is why a wide, cheap band beats a precise idle probe.

**AND THE BAND IS DERIVED AGAINST ONE OF THREE RESIDENTS, WHICH IS WHY IT IS NOT
THE LAST GATE (#5886).** ``worker-heavy`` runs at concurrency 2 and the rebuild is
only one of the jobs scheduled on it. The first unattended convergence
(2026-09-13T09:53:58Z) landed 19m44s clear of the rebuild — the band did its job —
and cycled ``prediction_market_match`` 3m58s in and ``rebuild_typeahead_index``
58s in, both of which are scheduled INSIDE the band by construction: the matcher
fires ``:05/:20/:35/:50`` and runs 154-552s, so it occupies 19 of the band's 25
minutes, and the typeahead fires ``:53``. There is no 25-minute window that clears
all three (matcher-free minutes are ``:14-:20``, ``:29-:35``, ``:44-:50``,
``:59-:05``), so narrowing the band cannot fix this and would only cost triggers.

So the clock stops being the last word: :func:`inflight_verdict` ASKS the fleet
what it is running instead of predicting it, from the ``active`` set the main
app's ``/api/admin/celery/inspect`` already broadcasts, and holds while a
``HEAVY_TASKS`` job is in flight. The band stays — it is the fallback for the runs
where that answer cannot be read, and a cost gate that cannot read its fact must
never take the sync down (the polarity rule in :func:`decide`).

**AND ONE READING OF THAT PROBE CANNOT SEE ITS OWN BLIND SPOT**, which the first
sync under it demonstrated rather than risked: at v15 the gate printed IDLE at
16:57:10Z while ``matching_reconciliation`` had been running since 16:56:59.9Z.
The reply is a snapshot of unknown age — 5 s of endpoint cache, a 25.6 s
measured broadcast, two retries — so :data:`IDLE_CONFIRMATIONS` readings are
required before the push, and the derivation of that number is on the constant.

What is STILL not covered, stated so nobody reads any of this as a proof:

* a job shorter than the SEPARATION between two readings — ~56 s, not the 30 s
  poll; the arithmetic and its measurement are on
  :data:`INFLIGHT_POLL_SECONDS` — that both starts and ends inside the confirm.
  One resident still qualifies, and still only one: ``matching_reconciliation``
  at 11-36 s measured. The next shortest heavy resident is
  ``rebuild_typeahead_index`` at 90 s, so the wider bound does not widen the
  set. It is also the cheapest to lose and re-fires every 15 min;
* a job on ``worker-heavy`` that is not in ``HEAVY_TASKS``. This is no longer
  hypothetical and it has a name: ``app.tasks.build_cohort_market_type``
  declares ``queue="heavy"`` on its own decorator and
  ``routes/admin_cohort.py`` sends it there explicitly, while sitting outside
  the set ruling 110 governs. It has no beat — only an admin call reaches it —
  so the gate is blind to it exactly when a person triggers it. Widening
  ``HEAVY_TASKS`` is a change to a ruled set and is not made here (#5886).

The inspect reply is keyed by an opaque ``celery@<uuid>`` hostname, which is why
membership of a task set, rather than a worker identity, is the only available
channel. Every residual above is narrower than the one it replaced, and none of
them is silent: the verdict names what it saw.

Usage (the workflow gathers facts, this judges, the workflow acts on the code)::

    python3 scripts/heavy_sync_decision.py decide \\
        --main-live "$MAIN_LIVE" --heavy-live "$HEAVY_LIVE" \\
        --heavy-is-ancestor true [--heavy-release-age-min N] [--dispatched]
    python3 scripts/heavy_sync_decision.py inflight \\
        --inspect-json /tmp/inspect.json [--dispatched]
    python3 scripts/heavy_sync_decision.py band-seconds-left

Exit codes: ``0`` PUSH · ``1`` HOLD (a benign result, not an error — gotcha #124) ·
``2`` REFUSE (unsafe; somebody should look) · ``3`` usage. ``inflight`` uses the
same two benign codes: ``0`` proceed (IDLE, or UNKNOWN — see the polarity rule) ·
``1`` HOLD.

There is deliberately **no ``--now`` flag**. authority/114 checked its window three
times and pushed 29 minutes early because it computed the time from its own
``sleep`` durations instead of reading a clock (#4997) — arithmetic that can only
drift ahead, so it can never report "outside". The clock is read here, in the same
process as the verdict; tests drive the ``now=`` keyword seam instead (gotcha #44).
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# ── the window, derived from measurements — never typed in ─────────────────────

#: The accuracy rebuild's beat. Hourly at :15 (beat schedule is the authority).
REBUILD_START_MIN = 15
#: MEASURED on production, and this constant is a CEILING on the rebuild, not its
#: typical length — the band is only safe if no rebuild outlives it. latency/350
#: read one run at 22m13s (`elapsed_ms = 1,332,567`); latency/372 then read the
#: task-metrics ring of 30 consecutive runs (2026-09-12T17:14Z .. 09-13T09:15Z)
#: and the MAX was 22m31s (09-12 19:14:59 -> 19:37:30), i.e. 22 understated the
#: observed ceiling by 31s. 23 covers every run in that ring. The sibling guard
#: `push_window_guard.py` still carries 7 — see #5470's note; correcting it there
#: without also retiring notice 29 would narrow THAT band to three minutes.
REBUILD_DURATION_MIN = 23
#: Push -> heavy release. A Heroku build with NO CI in front of it, so both ends
#: are well under the main app's CI-queue-dependent lag. These were ESTIMATES —
#: named as constants precisely so the first real reading could move the band
#: instead of being argued about.
#:
#: MIN IS NOW READ FROM EVERY SYNC THIS WORKFLOW HAS EVER COMPLETED, not from
#: one of them (latency/374, `Pushing ...` -> `remote: Released vN` in the run
#: logs, cross-checked against the release records):
#:
#:     v14  run 34750397765  09:52:01.518Z -> 09:53:59.010Z   117.5s
#:     v13  run 34743071282  06:34:38.837Z -> 06:35:15.077Z    36.2s  <- the floor
#:     v12  run 34720427451  21:37:14.249Z -> 21:38:10.096Z    55.8s
#:     v11  run 34714692872  19:37:36.353Z -> 19:38:15.612Z    39.3s
#:
#: `opens` SUBTRACTS this, so only a LOWER bound on the real lag makes the
#: opening edge safe, and the single 1m57.5s reading it was set from was the
#: SLOWEST of the four — three times the real floor. 1 is therefore still not a
#: lower bound: 36.2s is 0.60 min, so the honest floored value is 0 and the band
#: opens at the rebuild's own ceiling rather than a minute inside it. Headroom
#: against the worst observed rebuild goes from **5 seconds** to 1m05s
#: (`test_the_opening_edge_clears_the_worst_rebuild_at_the_fastest_real_lag`).
#: MAX stays an estimate at 12 and is deliberately NOT moved down to the 1m57.5s
#: ceiling these four readings give: it sits on the CLOSING edge, where the band
#: shrinks as the number grows, so over-estimating buys safety and costs only
#: opportunity. The four readings are recorded here anyway, because the day
#: something wants a real upper bound (an imminent-fire gate would) they are the
#: measurement, and re-deriving it from one log line is how 1 got here.
#:
#: Cost of the move, measured rather than assumed (latency/372): CI completions
#: on master cluster at :40-:59 with ZERO in :30-:40, so :34 -> :37 -> :38 loses
#: no triggers at all — 8/13 in band at every one of the three edges.
MIN_RELEASE_LAG_MIN = 0
MAX_RELEASE_LAG_MIN = 12
#: Slack on the closing edge so a lag at the top of the range still lands clear of
#: the NEXT hour's rebuild.
CLOSE_MARGIN_MIN = 5


#: The cycle budget this file has ALREADY priced and accepted, in heavy releases
#: per day. It is not a new number: the raise to three cron attempts an hour
#: (latency/362) was justified at "~7.5 heavy cycles a day against today's ~2.5",
#: and the same paragraph rejects N=6's "~15/day" as too many. 8 is that accepted
#: rate, rounded up so the floor never forbids what the cron was licensed to do.
#: A cycle costs ONE calibration unit (~2 min measured), so this prices at ~16
#: min/day of recomputation.
ACCEPTED_CYCLES_PER_DAY = 8


def min_cycle_interval_min() -> int:
    """The floor between two heavy releases, derived from the accepted budget.

    Derived and not typed in for the same reason as :func:`window_bounds`: moving
    the budget must move the floor, or the two drift apart and the comment above
    becomes a story about a number nothing enforces
    (``test_moving_the_accepted_budget_moves_the_floor``).
    """
    return round(24 * 60 / ACCEPTED_CYCLES_PER_DAY)


def window_bounds() -> tuple[int, int]:
    """The (open, close) minutes past the hour, derived — never asserted.

    ``opens`` is the earliest push whose EARLIEST possible cycle still lands after
    the rebuild has finished; ``closes`` the latest push whose LATEST possible
    cycle still lands clear of the next one. Both edges therefore move on their
    own if any measured input moves, which is the property
    ``test_moving_a_measured_constant_moves_the_band`` pins.
    """
    opens = REBUILD_START_MIN + REBUILD_DURATION_MIN - MIN_RELEASE_LAG_MIN
    closes = REBUILD_START_MIN + 60 - MAX_RELEASE_LAG_MIN - CLOSE_MARGIN_MIN
    return opens, closes


def inside_window(now: datetime) -> bool:
    """Both bounds inclusive — the margin that makes them safe is in the bounds."""
    opens, closes = window_bounds()
    return opens <= now.astimezone(timezone.utc).minute <= closes


#: How often the in-flight read is repeated while worker-heavy is busy.
#:
#: NOT a threshold — no verdict turns on its value, only how many chances one run
#: gets to observe an idle fleet — which is why it is a plain number and the
#: band's edge, which IS a verdict, stays derived. Its two bounds, so the next
#: reader does not have to re-derive them: an idle gap SHORTER than the push ->
#: release lag is not an opportunity at all (the fastest of the four measured
#: lags is 36.2 s), so sampling much finer than that buys precision this job
#: cannot spend; and the endpoint is our own production API, which returned HTTP
#: 500 on two of eight calls when it was measured, so the rate is also a load
#: choice. 30 s gives <=40 reads across the widest possible band.
#:
#: IT IS A SLEEP, NOT THE SEPARATION. The read itself costs ~25.6 s (five 5 s
#: broadcasts — see :data:`IDLE_CONFIRMATIONS`), so two consecutive readings
#: sit ~56 s apart, and 56 s is the width of the confirm's blind window.
#: Lowering this number is how a later reader will try to narrow that window;
#: below `_INSPECT_TTL_S` (5 s) it stops being an instrument at all, because
#: the endpoint's memo would serve ONE snapshot as both confirmations — a
#: confirm that cannot fail, which is the failure. `test_the_confirm_poll_can
#: _never_be_served_two_copies_of_one_snapshot` pins that floor; LAT-P071 (on
#: :data:`IDLE_CONFIRMATIONS`) is why the ceiling is not raised either.
INFLIGHT_POLL_SECONDS = 30

#: How many CONSECUTIVE idle readings are needed before the push (#5886).
#:
#: ONE IDLE READING CANNOT SEE ITS OWN BLIND SPOT, and the v15 sync is the
#: specimen rather than the worry. `matching_reconciliation` started
#: 2026-09-13T16:56:59.9Z; the gate printed IDLE at 16:57:10Z and pushed;
#: heavy released at 16:57:47Z. The job survived only because it is short — it
#: succeeded at 16:57:26, 21 s ahead of the release — but the gate never saw
#: it, and the same sequence around the `:50` matcher (154-552 s, measured)
#: kills a pass.
#:
#: The reading is a SNAPSHOT of unknown age, not a live fact: the endpoint
#: caches for 5 s (`_INSPECT_TTL_S`), the inspect broadcast itself measures
#: 25.6 s, and the workflow retries twice with a 3 s delay. So "IDLE" honestly
#: means "no heavy job was running up to ~31 s ago", against a kill window that
#: runs another 36-118 s past the push.
#:
#: 25.6 s, not the 18.4 s this comment carried until latency/381, and the
#: correction is structural rather than a re-measurement: `_inspect_snapshot`
#: makes FIVE broadcasts in one handler — ping, active, reserved, registered,
#: stats — each `inspect(timeout=5)`, and celery's inspect waits out its
#: timeout whenever it cannot know that every worker has answered. 5 x 5 s is
#: the floor, and eight production reads on 2026-09-13 21:38-21:43Z landed at
#: 25.6-29.6 s (the one exception, 0.22 s, was served by the 5 s memo).
#:
#: A second reading one poll later closes that gap for any job that outlives
#: the SEPARATION of the two readings, because the two snapshots cannot both
#: miss it. That separation is the read plus the sleep — ~25.6 + 30 = ~56 s —
#: and NOT the 30 s poll, which is the number the first version of this comment
#: implied. Stated as a bound rather than a promise: every heavy resident
#: measured on production outlives 56 s — matcher 154-552 s,
#: `futures_price_refresh` 151-296 s, the rebuild 4-22 min,
#: `rebuild_typeahead_index` 90 s (its own budget) — EXCEPT
#: `matching_reconciliation` at 11-36 s, which can still start and finish
#: inside the confirm. So the wider bound does not widen the residual set: the
#: one job it covered at 30 s is the same one job it covers at 56 s. That one
#: is also the cheapest to lose and re-fires every 15 min.
#:
#: 🔴 DO NOT CLOSE THE GAP BY POLLING FASTER. It is the obvious fix and it is
#: the one that took production down: LAT-P071, 2026-08-19 05:00-05:03Z, two
#: read-only samplers on this same endpoint (20 s and 8 s) drove the whole API
#: to HTTP 503 at the 30 s H12 ceiling, `/api/health` included, for ~10 min.
#: The gap is accepted; the poll rate is not the lever (`_INSPECT_TTL_S`).
#:
#: 2 and not 3: each extra confirmation costs a poll of the band for a blind
#: spot that is already covered, and the band is the budget the whole ship
#: spends. The confirm can only ever WAIT, and only inside the band — at the
#: edge it degrades to the single read this gate used before, which is why it
#: cannot cost a cycle (`test_the_confirm_degrades_to_a_single_read_at_the_edge`).
IDLE_CONFIRMATIONS = 2

#: What ONE more turn of the wait loop costs in band, measured end to end.
#:
#: The broadcast half of it: ~25.6 s, eight production reads on 2026-09-13
#: 21:38-21:43Z landing at 25.6-29.6 s, rounded UP to a whole 26 so the
#: derivation below can never under-state the turn. This is the same number
#: :data:`IDLE_CONFIRMATIONS` derives the confirm's blind window from — one
#: measurement, named once, rather than a figure that lives only in prose.
INFLIGHT_READ_SECONDS = 26

#: THE BAND'S EDGE, AND IT IS A TURN OF THE LOOP AND NOT A SLEEP (#6283).
#:
#: The wait loop breaks at the edge so that an unconfirmed IDLE still pushes,
#: which is the reading this gate used before the confirm existed. The whole
#: claim above it — "the confirm can only WAIT, never refuse … so it cannot
#: cost a cycle, only the band can" — is TRUE only if the edge is at least what
#: one more turn costs. It was not: the workflow carried a hand-typed `30`,
#: which is :data:`INFLIGHT_POLL_SECONDS` alone, while a turn is the sleep PLUS
#: the read it ends on.
#:
#: The specimen is run 117, 2026-09-15, and it is the whole reason this constant
#: exists. The gate reached PUSH at 00:49:35Z, waited out a busy worker-heavy
#: for nine minutes, and read IDLE at 00:58:23Z with 36 s of band left. 36 > 30,
#: so it took the confirm branch — and the turn took 55.7 s, so the band shut
#: mid-read and the run ended `HOLD — the band closed while the fleet was being
#: read`. `bainluck-heavy` then sat another 60 minutes on `c1b52e9c3` while the
#: main app served `f880e45da`, which is precisely the cycle the confirm was
#: promised never to cost. The turn cost is not an estimate either: the same
#: hour's run 122 printed `Confirming in 30s` at 01:46:55.5Z and `Pushing` at
#: 01:47:51.2Z — 55.7 s, again.
#:
#: So any band remainder in (`INFLIGHT_POLL_SECONDS`, this] is a remainder the
#: loop can spend but cannot finish inside, and every second of it is a lost
#: hour. Derived, never typed: two copies of one number is how a comment becomes
#: a story about a value nothing enforces, and the YAML's literal is pinned to
#: this one by `test_the_bands_edge_is_a_whole_turn_of_the_wait_loop`.
CONFIRM_SEPARATION_SECONDS = INFLIGHT_POLL_SECONDS + INFLIGHT_READ_SECONDS

#: WHAT THE RUN STILL OWES THE BAND AT THE INSTANT IT WAKES — the wake to the
#: VERDICT (#5470's residual, found by authority/909).
#:
#: :func:`wait_seconds` authorises a sleep by asking :func:`decide` about the
#: moment the run WAKES. Nothing is decided at that moment. The run has to
#: re-read every fact first — `read_facts` again: two `ls-remote`s, two
#: `fetch`es, `cat-file`, `merge-base`, and the `age` call to the Platform API —
#: and the verdict it was authorised on is taken AFTER that read. So the sleep
#: was validated with less margin than the work it must still do, and the margin
#: it was short by is this.
#:
#: Measured end to end, wake instant to the verdict line, over every sleeping
#: run in this workflow's last 100 (14 of them, 2026-09-19..09-20):
#: 9.72 / 10.24 / 10.47 / 10.62 / 10.73 / 10.78 / 10.86 / 11.50 / 11.57 / 11.75
#: / 12.04 / 12.19 / 13.02 / 16.41 s. Rounded UP FROM THE MAXIMUM rather than
#: from the median, because the two errors are not the same size: under-stating
#: authorises a sleep that cannot finish, which is the hour this constant exists
#: to stop, while over-stating declines one whose remaining band was going to be
#: spent for nothing anyway. The wake is computed, not read — a log line is
#: printed by the first thing that finishes, and the two `ls-remote`s ahead of it
#: cost ~5 s that reading the first line would charge to nobody.
#:
#: The specimen is run 35518945494, 2026-09-20, and it is the 13.02 in that list.
#: The gate reached PUSH at 15:14:47Z and slept 2640 s for the 180-min cycle
#: floor, landing 15:58:47Z — 13 s inside a band that closes at 15:59:00. It woke,
#: spent 13.02 s re-reading, and printed `HOLD: :59 is outside the :38-:58
#: heavy-sync window`. Forty-four minutes of runner for the verdict it already
#: held, and heavy stayed on `704cdc47` while main served `d0555293`.
POST_WAKE_READ_SECONDS = 17

def wake_to_push_seconds() -> int:
    """The band a run must still hold at the instant it wakes, to reach a push.

    THE WAKE TO THE PUSH, WHICH IS WHAT THE SLEEP'S DEADLINE IS ACTUALLY ABOUT.
    ``decide`` is not the last gate. The in-flight read stands between it and the
    push, and then the band is asked ONE more time (``HOLD — the band closed while
    the fleet was being read``). So a sleep landing with only the re-read's worth
    of band left still loses the cycle, one gate further down: PUSH at :58:5x,
    ~26 s of broadcast, a final ``band-seconds-left`` of 0, exit. Charging only the
    re-read would fix the specimen and leave its neighbours — a wake with 20 s of
    band is as doomed as one with 13, and for the next reason along.

    This is the SLEEP path's statement of the rule the confirm loop's edge already
    lives by: a remainder of band the run can SPEND but cannot FINISH inside is a
    remainder it must not spend, because the fallback — HOLD now and let the next
    trigger re-judge — is the run this file has always been and costs nothing but
    the attempt.

    A FUNCTION AND NOT A CONSTANT, for the reason :func:`min_cycle_interval_min`
    is one. The fleet read here is the same broadcast, on the same endpoint, in the
    same run that :data:`INFLIGHT_READ_SECONDS` already measures, so it is derived
    from that rather than measured again — and a derived CONSTANT is only derived
    at import. ``= 43`` behaves identically today and silently stops tracking the
    moment either measurement is corrected, which is the drift this file has paid
    for before; that mutant survives every test that patches the total instead of
    the inputs
    (``test_the_two_charges_are_derived_from_measurements_and_are_what_decline_it``).
    """
    return POST_WAKE_READ_SECONDS + INFLIGHT_READ_SECONDS


def band_seconds_left(now: datetime | None = None) -> int:
    """Whole seconds until the band's closing edge; ``0`` once it has passed.

    THE WAIT HAS NO DEADLINE OF ITS OWN, AND MUST NOT (#5470). ``window_bounds``
    already answers "how late may a push be and still clear the next rebuild",
    so the moment it stops being safe to push is exactly the moment it stops
    being worth waiting. A second constant here would be a second answer to one
    question, free to drift from the first
    (``test_the_wait_deadline_is_the_band_and_never_a_number_of_its_own``).

    ``inside_window`` is minute-INCLUSIVE, so the edge is the end of ``closes``,
    not its start; ``timedelta`` carries the hour (and the day) when ``closes``
    is 59. Zero outside the band, which the caller reads as "stop waiting" — so
    an unreadable or crashed deadline degrades toward not waiting, never toward
    waiting forever.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not inside_window(now):
        return 0
    _, closes = window_bounds()
    edge = now.replace(minute=closes, second=0, microsecond=0) + timedelta(minutes=1)
    return max(0, int((edge - now).total_seconds()))


def seconds_until_window_opens(now: datetime | None = None) -> int:
    """Whole seconds until the band's OPENING edge; ``0`` once inside it.

    The mirror of :func:`band_seconds_left`, and derived from the same bounds for
    the same reason: "how long until it is safe to push" and "how long it stays
    safe" are two readings of one band, and a second constant for either is a
    second answer free to drift from the first
    (``test_the_two_edges_are_one_band_read_from_both_sides``).

    Zero INSIDE the band — the caller reads that as "no wait is needed", which is
    the same polarity :func:`band_seconds_left` uses for "stop waiting": both
    degrade toward acting now rather than toward sleeping.

    IT ROUNDS UP, AND THE REAL CLOCK IS WHY. ``int()`` truncates, and a real
    ``now`` carries microseconds, so 13:30:20.84 -> :38 is 459.16 s and
    truncating it lands the sleeper at 13:37:59.84 — one second OUTSIDE the band
    it waited eight minutes to reach, where ``decide`` then HOLDs and the whole
    wait is spent on the verdict it started with. Found by running the
    subcommand against the wall clock rather than against a fixed anchor, which
    is the one thing a ``now=``-seam test cannot do for itself
    (``test_a_wait_computed_from_a_real_clock_lands_inside_the_band``).
    ``band_seconds_left`` truncates for the same reason in the other direction:
    there, short is the safe end.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if inside_window(now):
        return 0
    opens, _ = window_bounds()
    edge = now.replace(minute=opens, second=0, microsecond=0)
    if edge <= now:
        edge += timedelta(hours=1)
    return max(0, math.ceil((edge - now).total_seconds()))


def band_seconds_left_at_open(now: datetime | None = None) -> int:
    """Seconds from ``now`` to the closing edge of the band we would push in.

    The band occurrence meant is the one we are standing in, or — outside it —
    the next one to open. It is the DEADLINE for any wait: a target beyond it is
    not a longer sleep, it is a sleep into a different hour, which is how a
    3-hour cycle floor could otherwise buy a 2h50m runner (:func:`wait_seconds`).

    Derived from the two edges the rest of the file already reads rather than
    from a duration of its own, so a moved band moves it
    (``test_the_wait_deadline_is_the_band_and_never_a_number_of_its_own``).
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    opens_in = seconds_until_window_opens(now)
    if opens_in == 0:
        return band_seconds_left(now)
    return opens_in + band_seconds_left(
        (now + timedelta(seconds=opens_in)).replace(second=0, microsecond=0)
    )


def seconds_until_floor_clears(heavy_release_age_min: int | None) -> int:
    """Seconds until the cycle floor stops forbidding a push; ``0`` when it does not.

    ``None`` — the age could not be read — is ZERO and not "wait", for the reason
    :func:`decide` gives for proceeding on an unreadable age: a gate that cannot
    read its fact must not become a gate of its own. Whole minutes in, because
    ``age`` reports whole floored minutes, so the wait this returns lands at or
    after the true clear and never before it.
    """
    if heavy_release_age_min is None:
        return 0
    return max(0, (min_cycle_interval_min() - heavy_release_age_min) * 60)


# ── the verdict ────────────────────────────────────────────────────────────────

PUSH, HOLD, REFUSE, USAGE = 0, 1, 2, 3

_VALID_SHA_LEN = 40


@dataclass(frozen=True)
class Decision:
    """One sync reading. ``code`` is the process exit code the workflow gates on."""

    code: int
    verdict: str
    reason: str


def _is_sha(value: str | None) -> bool:
    """A full 40-char hex sha and nothing else.

    An abbreviation is refused rather than accepted: notice 28's amendment is the
    precedent — a short sha makes an API answer EMPTY rather than wrong, and an
    empty answer here would read as "nothing to do" (gotcha #53).
    """
    return bool(
        value
        and len(value) == _VALID_SHA_LEN
        and all(c in "0123456789abcdef" for c in value.lower())
    )


def decide(
    *,
    main_live: str | None,
    heavy_live: str | None,
    heavy_is_ancestor: bool | None,
    dispatched: bool = False,
    heavy_release_age_min: int | None = None,
    now: datetime | None = None,
) -> Decision:
    """Judge one sync opportunity. Pure apart from the clock it reads itself.

    Order is the safety order, not the narrative one:

    1. **Unreadable facts REFUSE.** A missing or abbreviated sha cannot be
       reasoned about, and "cannot prove" is never permission.
    2. **Already in sync HOLDS** — checked before the window so the overwhelmingly
       common run reports "up to date" rather than a window skip it never needed.
    3. **Divergence REFUSES**, and does so BEFORE the window and regardless of
       ``--dispatched``: an attended run may overrule a clock, never a
       never-backwards guard. This is the one that must not be forceable.
    4. Only then do the two COST gates — the clock, then the cycle floor — get a
       say, and they fail in the OPPOSITE direction to the guards above them. A
       safety guard that cannot read its fact refuses; a cost gate that cannot
       read its fact proceeds. ``heavy_release_age_min=None`` is therefore not a
       hold: an unreadable release age means we do not know that heavy was
       disturbed recently, and the harm of one extra cycle (~2 min of
       recomputation) is not the harm of missing the sync this ship exists for.
    """
    if not _is_sha(main_live):
        return Decision(REFUSE, "REFUSE", f"main live ref unreadable: {main_live!r}")
    if not _is_sha(heavy_live):
        return Decision(REFUSE, "REFUSE", f"heavy live ref unreadable: {heavy_live!r}")

    if main_live == heavy_live:
        return Decision(HOLD, "HOLD", f"heavy is already on {main_live[:9]} — nothing to do")

    if heavy_is_ancestor is not True:
        # Not an ancestor, or an ancestry we could not establish. A push in either
        # state can rewind the heavy app, so both fail closed (ci.yml's deploy
        # guard reasons identically about its own `HAVE_LIVE`).
        return Decision(
            REFUSE,
            "REFUSE",
            f"heavy {heavy_live[:9]} is not a proven ancestor of main {main_live[:9]} — "
            "refusing rather than rewinding heavy",
        )

    now = now or datetime.now(timezone.utc)
    opens, closes = window_bounds()
    if not dispatched and not inside_window(now):
        return Decision(
            HOLD,
            "HOLD",
            f":{now.astimezone(timezone.utc).minute:02d} is outside the :{opens}-:{closes} "
            f"heavy-sync window (the :{REBUILD_START_MIN} accuracy rebuild runs "
            f"{REBUILD_DURATION_MIN} min) — the next scheduled run retries",
        )

    floor = min_cycle_interval_min()
    if not dispatched and heavy_release_age_min is not None and heavy_release_age_min < floor:
        return Decision(
            HOLD,
            "HOLD",
            f"heavy was released {heavy_release_age_min} min ago, inside the {floor}-min "
            f"cycle floor ({ACCEPTED_CYCLES_PER_DAY} cycles/day) — a release cycles "
            "worker-heavy, so the trigger rate is not the cycle rate",
        )

    why_now = "attended run: window bypassed" if dispatched else f"inside :{opens}-:{closes}"
    return Decision(
        PUSH,
        "PUSH",
        f"heavy {heavy_live[:9]} -> main's live {main_live[:9]} ({why_now})",
    )


def wait_seconds(
    *,
    main_live: str | None,
    heavy_live: str | None,
    heavy_is_ancestor: bool | None,
    dispatched: bool = False,
    heavy_release_age_min: int | None = None,
    now: datetime | None = None,
) -> int:
    """Seconds to sleep so THIS run reaches the band; ``0`` when waiting cannot help.

    OUTSIDE THE BAND IS "NOT YET", NOT "NOT TODAY" — the sentence the in-flight
    loop already lives by, applied to the other clock (#5470).

    WHAT IT COSTS, MEASURED, AND NOT THE THING IT WAS REPORTED AS. lane1/324
    read four consecutive runs (:00, :10, :36, :43, one sync) and called the
    deploy trigger phase-locked against the band; int355 read heavy three
    releases behind at 12:55Z. Neither survives the whole population: over all
    85 runs this workflow has had (2026-09-12T19:37Z .. 09-14T12:35Z, read
    2026-09-14) **34 of 73 `workflow_run` fires landed in band, 47%**, and 29 of
    the last 24 hours' 65. Deploys are spread across the hour, not stacked on
    it, and at 12:55Z heavy was 72 min old — inside its own 180-min cycle floor,
    where being behind is the priced design and not a defect.

    THE REAL COST IS THE RESIDUAL AFTER THE FLOOR CLEARS, and it is visible in
    heavy's own release record. Six consecutive releases, v15..v20
    (2026-09-13 09:57 PDT .. 09-14 04:43): 3h47, 3h06, 4h01, 4h06, 3h47 —
    **mean 3h45 against a 3h00 floor**. That 45-minute residual is this: the
    floor clears at some minute of the hour, and nothing may push until a
    trigger happens to arrive while the band is open. A trigger arrives every
    ~22 min and is in band 47% of the time, which is 45 minutes of expected
    wait — the arithmetic and the reading agree to the minute.

    AND THE TAIL IS THE PART THAT HURT. When deploys stop — a quiet night, a
    frozen tray — the only trigger left is the cron, which this repo measured at
    19-359 min late and which landed in band **2 of 11 times** here. That is the
    7h06m and 7h33m episodes recorded in this file's header, with merged launch
    fixes dark on a worker that never got the code. A cron fire that sleeps to
    the edge converges; a cron fire that HOLDs waits for another lottery.

    A run that HOLDs at :10 and a run that sleeps 28 minutes and pushes at :38
    differ only in whether the opportunity is taken; the alternative was never
    "push at :10". So this CANNOT weaken any gate, and deliberately answers none
    of their questions itself: the wait is authorised only when ``decide``, asked
    about the moment the band opens with the release age it will have by then,
    says PUSH. Every safety guard is re-asked for real after the sleep, against
    refs re-read then — the sha pushed is the one main is serving when it is
    pushed, never the one it was serving when the run started.

    Three reasons it is affordable, none of them "runner time is cheap":

    * ``bainluck`` is a PUBLIC repository, where GitHub-hosted standard runners
      are free — so this spends no money, and is not the spend call D100 is;
    * it spends one of the 20 free concurrent job slots, and only ever one: the
      ``heavy-deploy`` group cancels a PENDING duplicate rather than the running
      sleeper, so a burst of deploys collapses into the single run that is
      already waiting — which then reads their newest sha when it wakes;
    * it can only happen when there is real drift, a proven ancestry and a
      cleared cycle floor. The ~8-cycles-a-day floor bounds the waits at 8, not
      at one per deploy (``test_a_run_inside_the_cycle_floor_never_sleeps``).

    The projected age is the one thing read forward rather than measured: heavy
    released 160 min ago at :00 is past the 180-min floor by :38, so asking the
    floor about NOW would refuse a wait the floor itself will permit. Projecting
    is safe in the direction that matters — the real age at the push is at or
    ABOVE the projection, because the push happens at or after the target, and
    ``age`` floors its minutes (so the reported age understates the real one).

    THE TARGET IS THE LATER OF TWO EDGES, AND THE SECOND ONE IS WHERE THE
    RESIDUAL ACTUALLY LIVES. Sleeping only to the band's opening edge fixes the
    quiet-night tail and leaves the 45-minute residual almost untouched, because
    of a property of this system the first version of this function did not use:
    **the cycle floor USUALLY clears INSIDE the band — 9 of heavy's last 12
    releases, and not a law.** A push may only happen between :38 and :58 and
    the floor is exactly 3 h, so the floor clears at the same minute past the
    hour as the RELEASE that started it — and the release completes ~12 min
    after the push that triggered it, so the clear minute is in band for a push
    before ~:46 and past :58 for a later one. Heavy's own record: v17..v20
    clear at :49, :50, :56 and :43, and **v21 at :59 — one minute past the
    band's close**, which is the case this function's own first production run
    met and correctly declined (v13 :35 and v10 :10 are the other two). The
    tendency is what the sleep is FOR; the exceptions are what the deadline in
    the next paragraph is for, and a reader who takes the tendency for a law
    will mis-derive which runs are even eligible to sleep. So in the one hour
    that matters — the hour the floor clears — asking only about :38 refuses every
    trigger that arrives before the clear: at 14:20 with a floor clearing at
    14:43:49, the projected age at :38 is 174 min and the run HOLDs, having been
    eight minutes short of a window it could have slept into. The measured
    trigger rate is ~1 per 22 min, so that hour is where most of the residual is
    (``test_a_trigger_before_a_floor_that_clears_inside_this_band_sleeps_to_the_clear``).

    Waiting past the CLOSING edge of the band occurrence we are aiming at is the
    one thing this must never do: a floor clearing 2 h 50 m from now is not a
    long sleep, it is a sleep into a different hour's band, and it would hold a
    runner for the length of a cycle. The deadline is the band's own closing edge
    — the same "how late may a push be" the rest of the file reads, never a
    second number (``test_a_floor_clearing_after_this_bands_close_never_sleeps``).

    AND THE DEADLINE IS THE WAKE PLUS EVERYTHING THE RUN STILL OWES, NOT THE WAKE.
    The deadline used to be measured to the wake instant, which is the one instant
    at which this run does nothing: it re-reads every fact first
    (:data:`POST_WAKE_READ_SECONDS`), and after the verdict it still has an
    in-flight read and a final band check to clear before it may push
    (:func:`wake_to_push_seconds`). Run 35518945494 slept 2640 s to land 13 s
    inside the band and spent 13.02 s waking up, so it HOLDed on the clock it had
    just waited 44 minutes for — a sleep authorised with less margin than the work
    it had left. So the deadline is asked about the PUSH, which is the last thing
    the sleep is for, and ``decide`` is then safe to ask about the wake (see the
    comment at the call).

    IT IS A NARROW CUT, and that is measured rather than hoped: replayed over the
    14 sleeps in this workflow's last 100 runs, it declines exactly one — run
    35518945494, the only one of the 14 that HOLDed. The next-closest survivor woke
    with 459 s of band against a 43 s charge
    (``test_a_sleep_that_cannot_afford_its_own_re_read_is_not_taken``).

    Declining costs nothing that was there to lose. The alternative to a sleep that
    cannot finish is not a later push, it is the same HOLD 44 minutes earlier, with
    the runner and the ``heavy-deploy`` slot handed back — and that slot is the
    part that matters, because the group cancels a PENDING duplicate rather than
    the running sleeper, so a doomed sleeper also swallows every trigger that
    arrives while it waits.

    The cycle budget is untouched by either edge: the target is never EARLIER
    than the floor permits, so a sleeping run pushes at the first instant an
    awake one could have.
    """
    now = now or datetime.now(timezone.utc)
    if dispatched:
        return 0
    opens_in = seconds_until_window_opens(now)
    secs = max(opens_in, seconds_until_floor_clears(heavy_release_age_min))
    if secs <= 0:
        return 0
    # `>=` and not `>`: the deadline is the band's closing EDGE, and the final band
    # check the push has to clear reads `band_seconds_left`, which is 0 AT the edge
    # rather than at the second after it. A sleep that fits exactly therefore lands
    # the push on a zero and HOLDs — the same lost cycle, one second wide and one
    # gate further down (`test_a_sleep_that_fits_exactly_lands_the_push_on_a_zero`).
    if secs + wake_to_push_seconds() >= band_seconds_left_at_open(now):
        return 0
    # The projected age stays on `secs` alone, and deliberately: the floor's
    # question is how old heavy is at the moment we would push, and the push is
    # LATER than the target by everything above, so this under-states it. An
    # under-stated age can only refuse a cycle, never buy one — the direction a
    # cost gate is allowed to be wrong in, and the one
    # `test_the_projection_can_never_land_under_the_floor` reads.
    projected_age = (
        None if heavy_release_age_min is None else heavy_release_age_min + (secs + 59) // 60
    )
    # ASKED ABOUT THE WAKE, AND THAT IS SOUND ONLY BECAUSE OF THE LINE ABOVE.
    # The verdict is really taken `POST_WAKE_READ_SECONDS` after this instant, so
    # judging the wake is judging a moment the run never occupies — which is the
    # whole defect, and which the deadline has just closed: it proved the band is
    # still open all the way to the PUSH, so it is open at the verdict too and the
    # two readings cannot disagree. Charging the re-read here as well would be a
    # branch nothing can reach; the equivalence is pinned instead, so weakening the
    # deadline fails a test rather than silently re-opening this
    # (`test_judging_the_wake_is_sound_only_because_the_deadline_covers_the_re_read`).
    at_target = decide(
        main_live=main_live,
        heavy_live=heavy_live,
        heavy_is_ancestor=heavy_is_ancestor,
        dispatched=False,
        heavy_release_age_min=projected_age,
        now=now + timedelta(seconds=secs),
    )
    return secs if at_target.code == PUSH else 0


# ---------------------------------------------------------------------------
# IN FLIGHT — ask the fleet what it is running instead of predicting it (#5886)
# ---------------------------------------------------------------------------
#
# THE BAND PROTECTS ONE OF THREE RESIDENTS. The header states the measurement;
# this is the mechanism. Three facts make it cheap:
#
#   * only `worker-heavy` consumes the `heavy` queue, and `HEAVY_TASKS` is the
#     single source of what routes there (`task_routes` and every beat entry's
#     `options["queue"]` are both written from it, in `app/tasks/__init__.py`).
#     So "a HEAVY_TASKS task is active ANYWHERE" and "worker-heavy is busy" are
#     the same reading, and no worker identity is needed — which matters,
#     because `inspect` names workers `celery@<uuid>` with no app or dyno in it;
#   * the set is READ FROM THAT FILE rather than copied here. A second copy is
#     the drift this repo has already paid for twice (the `ß`/`æ` normaliser
#     tables of #5878), and a list of 28 task names would rot in a week.
#     `test_the_heavy_task_set_is_the_one_the_app_routes_on` asserts the parse
#     equals the imported `app.tasks.HEAVY_TASKS`, both directions;
#   * the payload is gathered by the workflow, not fetched here. Our own host
#     must carry `x-bainluck-origin` (notice 39) and this script cannot import
#     the carrier — it runs on a bare runner before any `pip install`, which is
#     the exemption `test_agent_origin_outbound_tag.py` grants it for the Heroku
#     reads. A `curl -H` in the workflow tags the call without the import.

#: The name of the assignment this module reads the heavy fleet's task set from.
HEAVY_TASKS_NAME = "HEAVY_TASKS"
#: Where that assignment lives, relative to the repo root.
HEAVY_TASKS_SOURCE = "backend/app/tasks/__init__.py"

BUSY, IDLE = 1, 0


def heavy_task_names(source: str) -> frozenset | None:
    """The `HEAVY_TASKS` string set, parsed out of `source`, or ``None``.

    ``None`` — never ``frozenset()`` — when the assignment is missing, is not a
    set/list of plain strings, or the file does not parse. An empty set would
    make every reading IDLE: the worker would be declared free precisely when
    this module has lost the ability to tell, which is gotcha #53's failure
    written as a gate. The caller treats ``None`` as UNKNOWN.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == HEAVY_TASKS_NAME for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return None
        names = {
            e.value for e in value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        }
        # A set literal that parsed but yielded nothing usable is unknown, not
        # empty — same reason as above.
        return frozenset(names) or None
    return None


#: The queue `worker-heavy` consumes, as the beat literals spell it.
HEAVY_QUEUE = "heavy"
#: The assignment carrying the beat literals, read from the same file.
BEAT_SCHEDULE_ATTR = "beat_schedule"


def heavy_queue_beat_tasks(source: str) -> frozenset | None:
    """Tasks of every beat entry AUTHORED ``options={"queue": "heavy"}``.

    **`HEAVY_TASKS` IS NOT THE LIST OF WHAT RUNS ON `worker-heavy`, AND THREE
    JOBS LIVE IN THE GAP.** Membership routes a task there
    (`task_routes[t] = {"queue": "heavy"}`, `app/tasks/__init__.py`), but a beat
    entry can send its own task there without being a member, by carrying the
    queue in its `options` — `apply_async(queue=…)` overrules `task_routes`.
    Measured on this tree, three entries do exactly that:

        refresh-linked-polymarket-books-hourly  crontab(minute=38)
        refresh-linked-game-books-hourly        crontab(minute=20)
        refresh-dated-fixture-starts            crontab(minute=7, hour='1-23/2')

    That is #5886's second residual with names on it, and the first of the three
    is the one with teeth: **:38 is the first minute of the push band**
    (:func:`window_bounds`), and both book refreshers exist to give a LINKED
    market its price (#3518 Kalshi, #3613 Polymarket). A sync that cycles
    worker-heavy on top of one leaves those markets priceless on the page until
    the next hourly fire — which is the half of "releases preserve incoming
    prices" this gate was supposed to cover and could not see.

    The existing guard cannot catch this: `test_heavy_beat_literals_match_their_
    effective_queue` asserts that every HEAVY_TASKS entry SAYS heavy, which is
    the other direction. Nothing asked whether something says heavy without
    being a member.

    Cost of closing it, measured before it was built rather than assumed
    (`task-metrics`, 2026-09-14 07:1xZ, 50-run ring): the only one of the three
    that fires inside the band runs **4.9-10.6 s**. So the gate waits at most
    one `INFLIGHT_POLL_SECONDS` for it, in the one hour-minute it fires, and
    never refuses — busy is "not yet" (#5377).

    ``None`` when the `beat_schedule` assignment is missing or does not parse —
    the caller falls back to the declared set and says so. ``frozenset()`` is a
    REAL answer here and is not folded into ``None``, unlike
    :func:`heavy_task_names`: no beat authored onto the heavy queue is a
    perfectly ordinary state of this file, while an empty `HEAVY_TASKS` means
    the parse has lost its subject.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(t, ast.Attribute) and t.attr == BEAT_SCHEDULE_ATTR
            for t in node.targets
        ):
            continue
        names = set()
        for entry in node.value.values:
            if not isinstance(entry, ast.Dict):
                continue
            fields = {
                k.value: v
                for k, v in zip(entry.keys, entry.values)
                if isinstance(k, ast.Constant)
            }
            task = fields.get("task")
            options = fields.get("options")
            if not isinstance(task, ast.Constant) or not isinstance(task.value, str):
                continue
            if not isinstance(options, ast.Dict):
                continue
            for ok, ov in zip(options.keys, options.values):
                if (
                    isinstance(ok, ast.Constant)
                    and ok.value == "queue"
                    and isinstance(ov, ast.Constant)
                    and ov.value == HEAVY_QUEUE
                ):
                    names.add(task.value)
        return frozenset(names)
    return None


def heavy_worker_task_names(
    declared: frozenset | None, authored: frozenset | None
) -> frozenset | None:
    """Every task that RUNS on worker-heavy, by either route.

    The two arms are composed here rather than inside either parse so the caller
    can tell WHICH one went missing and say so: an unreadable `beat_schedule`
    narrows the gate back to exactly the set it used before this function
    existed, which is a quieter failure than an unreadable `HEAVY_TASKS` and
    must not be printed as the same thing.
    """
    if declared is None:
        return None
    return declared if authored is None else declared | authored


def active_task_names(payload) -> list | None:
    """Every task name the inspect payload reports as ACTIVE, or ``None``.

    ``None`` when the payload names no worker at all. That is the reading a
    failed broadcast produces — `/api/admin/celery/inspect` composes its reply
    from `registered`/`active`/`reserved`, so a broker that answered nothing
    returns a body carrying only `_cache` — and it is indistinguishable in shape
    from a genuinely idle fleet. It is NOT indistinguishable in meaning: three
    workers have replied to every reading this repo has taken, so no worker keys
    means the instrument failed, and "the instrument failed" must not read as
    "nothing is running" (gotcha #53).
    """
    if not isinstance(payload, dict):
        return None
    names = []
    workers = 0
    for key, value in payload.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        workers += 1
        for task in value.get("active") or []:
            if isinstance(task, dict) and task.get("name"):
                names.append(str(task["name"]))
    if not workers:
        return None
    return names


def inflight_verdict(
    *,
    active: list | None,
    heavy: frozenset | None,
    dispatched: bool = False,
) -> Decision:
    """Is a heavy job in flight, so that a release would kill it mid-run?

    The polarity is :func:`decide`'s, for the same reason: this is a COST gate,
    not a safety one. A killed heavy job self-heals on its next beat — the
    09:53:58Z matcher restarted at 10:05 and succeeded at 10:09:37, and the cost
    was one lost pass — while a sync that cannot happen is #5470 itself, silent
    and unbounded. So an unreadable fact PROCEEDS, and says that it is doing so.

    ``--dispatched`` bypasses it, exactly as it bypasses the clock and the cycle
    floor: an attended run is a person accepting one lost pass to get the code
    onto the worker now. It never bypasses the never-backwards guard.
    """
    if dispatched:
        return Decision(IDLE, "BYPASSED", "attended run: the in-flight veto is bypassed")
    if heavy is None:
        return Decision(
            IDLE, "UNKNOWN",
            f"the {HEAVY_TASKS_NAME} set could not be read from {HEAVY_TASKS_SOURCE} — "
            "proceeding, because a cost gate that cannot read its fact must not be "
            "able to stop the sync",
        )
    if active is None:
        return Decision(
            IDLE, "UNKNOWN",
            "the inspect reply named no worker, so the fleet did not answer — "
            "proceeding (an unreadable cost gate never holds the sync)",
        )
    busy = sorted({name for name in active if name in heavy})
    if busy:
        short = ", ".join(n.rsplit(".", 1)[-1] for n in busy)
        return Decision(
            BUSY, "BUSY",
            f"worker-heavy is running {short} — a release cycles the dyno and kills "
            "it mid-run (#5886); the next trigger re-reads and re-judges",
        )
    return Decision(IDLE, "IDLE", "no heavy job is in flight")


# ---------------------------------------------------------------------------
# READBACK — did the push actually become the release heavy is running? (#5722)
# ---------------------------------------------------------------------------
#
# THE GIT REF IS NOT THE ANSWER, AND ASKING IT COST US THE FIRST EVER SYNC.
#
# Run 34714692872 (2026-09-12 19:37Z) pushed `10c0ee5cd` to bainluck-heavy,
# Heroku built it, printed `Released v11`, and ran the release command clean.
# The workflow then read `git ls-remote heroku-heavy refs/heads/master` and got
# `87a095b4` — the PRE-PUSH sha — and failed the job. Heavy was, and is, on the
# new code: `heroku releases -a bainluck-heavy` showed `v11 Deploy 10c0ee5c`.
#
# A Heroku git endpoint is a push endpoint that triggers a build, not a plain
# git server, and the ref it advertises advances asynchronously after the
# release. So the readback raced it and lost.
#
# Why that is worth a script rather than a retry loop in YAML: #5470 exists
# because heavy drift is SILENT, and #5662's repair existed because a job that
# looks fine while doing nothing is the failure mode. A job that reports failure
# every time it succeeds is the same corrosion pointed the other way — within a
# day nobody reads the red, and the run that fails for a real reason becomes
# invisible. So the readback asks the RELEASE record, which is what notice 48
# already means by "heavy carries the sha", and it distinguishes three outcomes
# where the old line had two.

CONFIRMED = 0
MISMATCH = 1
UNREADABLE = 2


def readback_verdict(*, expected: str | None, observed: str | None) -> Decision:
    """Is the release heavy is running built from ``expected``?

    ``UNREADABLE`` is deliberately NOT folded into ``MISMATCH`` (gotcha #53).
    "the API did not answer" and "heavy is on a different commit" call for
    opposite responses — the first is retried, the second is a genuine stop —
    and the old one-line check could not tell them apart, so an unreadable
    answer and a wrong one both printed the same false claim about heavy's sha.
    """
    if not _is_sha(expected):
        return Decision(REFUSE, "REFUSE", f"expected sha unreadable: {expected!r}")
    if not observed:
        return Decision(UNREADABLE, "UNREADABLE", "the release API did not name a commit")
    if not _is_sha(observed):
        return Decision(
            UNREADABLE, "UNREADABLE", f"the release API named something that is not a sha: {observed!r}"
        )
    if observed.lower() == expected.lower():
        return Decision(CONFIRMED, "CONFIRMED", f"heavy's release is built from {expected[:9]}")
    return Decision(
        MISMATCH,
        "MISMATCH",
        f"heavy's release is built from {observed[:9]}, not the {expected[:9]} just pushed",
    )


def poll_readback(
    *,
    expected: str | None,
    fetch,
    attempts: int = 10,
    delay_s: float = 6.0,
    sleep=None,
) -> Decision:
    """Re-ask until the release record catches up, or the budget runs out.

    ``fetch`` returns the commit of the app's current release, or ``None`` if it
    could not be read. It is injected so the classification above is testable
    without a network, a credential, or a clock.

    A MISMATCH is retried rather than trusted immediately, because the race this
    exists for PRESENTS as a mismatch: the first read returns the previous
    release. Only a mismatch that survives the whole budget is reported as one.
    """
    import time

    sleep = sleep or time.sleep
    verdict = readback_verdict(expected=expected, observed=None)
    for attempt in range(1, max(1, attempts) + 1):
        try:
            observed = fetch()
        except Exception as exc:  # noqa: BLE001 - any read failure is UNREADABLE, not a mismatch
            observed = None
            print(f"  attempt {attempt}: release read failed ({type(exc).__name__}: {exc})")
        verdict = readback_verdict(expected=expected, observed=observed)
        if verdict.code in (CONFIRMED, REFUSE):
            return verdict
        print(f"  attempt {attempt}/{attempts}: {verdict.verdict} — {verdict.reason}")
        if attempt < attempts:
            sleep(delay_s)
    return verdict


def _heroku_get(path: str, token: str, extra: dict | None = None):
    """One Platform API read. Stdlib only — this script imports nothing external
    and must stay that way so it runs on a bare runner before any `pip install`.
    """
    import json
    import urllib.request

    # The trailing `/` in the literal is load-bearing, not a tidy-up target:
    # `backend/tests/test_agent_origin_outbound_tag.py` proves statically that
    # this call is third-party (so the origin carrier would be a no-op here,
    # and this file can stay importless), and it can only prove that while the
    # literal prefix CLOSES the authority. `f"...heroku.com{path}"` would leave
    # the host open to whatever `path` holds, and is correctly reported.
    req = urllib.request.Request(
        f"https://api.heroku.com/{path}",
        headers={
            "Accept": "application/vnd.heroku+json; version=3",
            "Authorization": f"Bearer {token}",
            **(extra or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _current_release(app: str, token: str) -> dict | None:
    """The app's CURRENT release record, or ``None`` if the API named none."""
    releases = _heroku_get(
        f"apps/{app}/releases", token, {"Range": "version ..; order=desc, max=1"}
    )
    if not releases:
        return None
    return releases[0] or None


def heroku_release_age_min(app: str, token: str, now: datetime | None = None) -> int | None:
    """Minutes since the app's current release, or ``None`` if unreadable.

    A CONFIG-ONLY release counts here, and that is the difference between this
    question and :func:`heroku_release_commit`'s. That function reads a slugless
    release as unreadable because it cannot say which commit is running; this one
    wants to know when heavy was last DISTURBED, and a config change cycles the
    dyno exactly as a deploy does. Two questions, two right answers — the failure
    would be to reuse one reader for both (gotcha #53).
    """
    release = _current_release(app, token)
    created = (release or {}).get("created_at")
    if not created:
        return None
    stamp = str(created).strip().replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    # A release stamped in the FUTURE (clock skew between the API and the runner)
    # reads as age 0, never as a negative that would sail under the floor.
    return max(0, int((now - when).total_seconds() // 60))


def heroku_release_commit(app: str, token: str) -> str | None:
    """The commit the app's CURRENT release was built from, via the Platform API."""
    release = _current_release(app, token)
    if not release:
        return None
    slug = release.get("slug") or {}
    slug_id = slug.get("id")
    if not slug_id:
        # A release with no slug is a config change, not a deploy — it cannot
        # tell us which commit is running, and saying "no" would be a lie.
        return None
    return (_heroku_get(f"apps/{app}/slugs/{slug_id}", token) or {}).get("commit")


def _age_arg(value: str | None) -> int | None:
    """Minutes, or ``None`` for "the workflow could not read it".

    Deliberately NOT ``type=int``. The workflow computes this from an API read
    that is allowed to fail, so the empty string is a legitimate value here —
    and argparse would turn it into a usage exit, which the workflow reads as a
    story about the harness and refuses on (gotcha #54). An unreadable age is a
    fact about a COST gate, and it proceeds; it must never take the sync down.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _bool_arg(value: str) -> bool | None:
    """`true`/`false` only. Anything else is UNKNOWN, which refuses upstream."""
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="heavy_sync_decision.py",
        description="May bainluck-heavy be synced to the main app's live commit now?",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("decide", help="print the verdict and exit on its code")
    d.add_argument("--main-live", required=True, help="the MAIN app's live sha (40 hex)")
    d.add_argument("--heavy-live", required=True, help="the HEAVY app's live sha (40 hex)")
    d.add_argument(
        "--heavy-is-ancestor",
        required=True,
        help="true|false — is the heavy sha a proven ancestor of the main one? "
        "Anything else is treated as unknown and refuses.",
    )
    d.add_argument(
        "--dispatched",
        action="store_true",
        help="an attended workflow_dispatch run: bypasses the CLOCK only, never the "
        "never-backwards guard",
    )
    d.add_argument(
        "--heavy-release-age-min",
        default="",
        help="minutes since heavy's current release. Empty or unparseable means "
        "UNREADABLE, which does not hold — see the cost-gate polarity in decide().",
    )
    f = sub.add_parser(
        "inflight",
        help="hold while a job is running on worker-heavy — HEAVY_TASKS plus any "
        "beat authored onto the heavy queue without being a member (#5886)",
    )
    f.add_argument(
        "--inspect-json",
        required=True,
        help="path to the body of /api/admin/celery/inspect, as the workflow "
        "fetched it. Missing, empty or unparseable is UNKNOWN, which PROCEEDS.",
    )
    f.add_argument(
        "--tasks-source",
        default="",
        help=f"override the path to the file carrying {HEAVY_TASKS_NAME} "
        f"(default: <repo>/{HEAVY_TASKS_SOURCE})",
    )
    f.add_argument(
        "--dispatched",
        action="store_true",
        help="an attended workflow_dispatch run: bypasses the in-flight veto, "
        "never the never-backwards guard",
    )
    sub.add_parser(
        "band-seconds-left",
        help="print how many seconds of the sync band are left (0 outside it) — "
        "the deadline for waiting out a busy worker-heavy",
    )
    w = sub.add_parser(
        "wait-plan",
        help="print how many seconds to sleep so this run reaches the band (0 when "
        "waiting cannot help) — the same facts `decide` gets, asked about the "
        "moment the band opens",
    )
    w.add_argument("--main-live", required=True, help="the MAIN app's live sha (40 hex)")
    w.add_argument("--heavy-live", required=True, help="the HEAVY app's live sha (40 hex)")
    w.add_argument(
        "--heavy-is-ancestor",
        required=True,
        help="true|false — anything else is unknown, and an unknown ancestry is "
        "never worth waiting for: it refuses on arrival",
    )
    w.add_argument(
        "--dispatched",
        action="store_true",
        help="an attended run never waits — it is exempt from the band it would "
        "be waiting for",
    )
    w.add_argument(
        "--heavy-release-age-min",
        default="",
        help="minutes since heavy's current release. Projected forward to the "
        "band's opening edge before the cycle floor is asked about it.",
    )
    a = sub.add_parser(
        "age", help="print minutes since the app's current release (empty if unreadable)"
    )
    a.add_argument("--app", required=True, help="the Heroku app, e.g. bainluck-heavy")
    v = sub.add_parser(
        "verify", help="confirm heavy's CURRENT RELEASE is built from the sha just pushed"
    )
    v.add_argument("--app", required=True, help="the Heroku app, e.g. bainluck-heavy")
    v.add_argument("--expect", required=True, help="the sha that was just pushed (40 hex)")
    v.add_argument("--attempts", type=int, default=10)
    v.add_argument("--delay-s", type=float, default=6.0)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # READ THE VALUE, don't catch the class (gotcha #54). argparse raises
        # SystemExit(0) for `--help` and SystemExit(2) for a bad argument, and
        # folding both into USAGE made `--help` exit 3 — the code the workflow
        # and notice 10's dry-run clause both read as "the script is broken".
        if not exc.code:
            raise
        return USAGE

    if args.command == "inflight":
        import json
        import os

        # EVERY read here is wrapped, and the wrap is the gate's polarity, not
        # defensive habit: a crash would exit 1 from argparse-land or a
        # traceback, and the workflow reads 1 as HOLD. A gate that holds the
        # sync because it could not open a file is the failure #5470 is.
        def _read(path: str) -> str | None:
            try:
                with open(path, encoding="utf-8") as handle:
                    return handle.read()
            except OSError:
                return None

        source_path = args.tasks_source or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            *HEAVY_TASKS_SOURCE.split("/"),
        )
        source = _read(source_path)
        declared = heavy_task_names(source) if source is not None else None
        authored = heavy_queue_beat_tasks(source) if source is not None else None
        heavy = heavy_worker_task_names(declared, authored)
        # STDERR, deliberately: the workflow reads the VERDICT off stdout
        # (`${INFLIGHT_OUT%%:*}`) and leaves stderr alone so a real problem
        # reaches the log in place. A silent narrowing is the thing worth
        # saying — the gate still vetoes, on a set that has quietly lost an arm.
        if declared is not None and authored is None:
            import sys as _sys

            print(
                f"the {BEAT_SCHEDULE_ATTR} literal could not be read from "
                f"{HEAVY_TASKS_SOURCE}, so the in-flight set is {HEAVY_TASKS_NAME} "
                "alone — a beat authored onto the heavy queue is invisible to this "
                "reading (#5886)",
                file=_sys.stderr,
            )

        raw = _read(args.inspect_json)
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = None
        active = active_task_names(payload) if payload is not None else None

        decision = inflight_verdict(active=active, heavy=heavy, dispatched=args.dispatched)
        print(f"{decision.verdict}: {decision.reason}")
        return decision.code

    if args.command == "wait-plan":
        # The NUMBER ALONE on stdout and always exit 0 — `age`'s contract, for a
        # reason of its own: this is the cheapest gate in the file, and a wait
        # that cannot compute itself must degrade to NOT waiting (0), never to a
        # non-zero the workflow would have to interpret. The WHY goes to stderr,
        # where it reaches the run log without becoming the number.
        secs = wait_seconds(
            main_live=args.main_live,
            heavy_live=args.heavy_live,
            heavy_is_ancestor=_bool_arg(args.heavy_is_ancestor),
            dispatched=args.dispatched,
            heavy_release_age_min=_age_arg(args.heavy_release_age_min),
        )
        opens, closes = window_bounds()
        if secs:
            # WHICH EDGE IT IS WAITING FOR, because the two have different
            # remedies if this ever looks wrong in a run log: the band is a
            # clock fact, the floor is a fact about heavy's last release.
            # The floor's remainder is arithmetic on an age and carries no clock
            # of its own, so comparing against IT cannot be raced by the second
            # that passes between two readings the way re-asking the band would.
            edge = (
                f"the {min_cycle_interval_min()}-min cycle floor to clear inside "
                f"the :{opens}-:{closes} band"
                if secs == seconds_until_floor_clears(_age_arg(args.heavy_release_age_min))
                else f"the :{opens}-:{closes} band"
            )
            print(
                f"waiting {secs // 60}m{secs % 60:02d}s for {edge} "
                "rather than losing this opportunity to a scheduler measured 19-359 min "
                "late — the facts are all re-read after the sleep",
                file=sys.stderr,
            )
        else:
            print(
                "not waiting: either the band is open, this is an attended run, or "
                "the same judge says this run would not push when it opens either",
                file=sys.stderr,
            )
        print(secs)
        return 0

    if args.command == "band-seconds-left":
        # The NUMBER ALONE on stdout, and always exit 0 — `age`'s contract, for
        # `age`'s reason: the caller captures the string, and a non-zero here
        # would let the wait's own deadline fail a job that has nothing wrong
        # with it. The clock is read in this process (there is no `--now`).
        print(band_seconds_left())
        return 0

    if args.command == "age":
        import os

        # Prints the NUMBER ALONE on stdout so the workflow can capture it with
        # `$(...)`, and every diagnostic goes to stderr. Always exits 0: the
        # caller's contract is the string, and an empty string already carries
        # "unreadable" — a non-zero here would make a cost gate able to fail a
        # job that has nothing wrong with it.
        token = os.environ.get("HEROKU_API_KEY", "")
        if not token:
            print("HEROKU_API_KEY is not set, so no release age can be read", file=sys.stderr)
            return 0
        try:
            age = heroku_release_age_min(args.app, token)
        except Exception as exc:  # noqa: BLE001 - any read failure is "unreadable"
            print(f"release age unreadable ({type(exc).__name__}: {exc})", file=sys.stderr)
            return 0
        if age is None:
            print(f"{args.app}: the release API named no usable created_at", file=sys.stderr)
            return 0
        print(age)
        return 0

    if args.command == "verify":
        import os

        token = os.environ.get("HEROKU_API_KEY", "")
        if not token:
            # Gotcha #9: checked here, never in a step-level `if`.
            print("UNREADABLE: HEROKU_API_KEY is not set, so no release can be read")
            return UNREADABLE
        decision = poll_readback(
            expected=args.expect,
            fetch=lambda: heroku_release_commit(args.app, token),
            attempts=args.attempts,
            delay_s=args.delay_s,
        )
        print(f"{decision.verdict}: {decision.reason}")
        return decision.code

    decision = decide(
        main_live=args.main_live,
        heavy_live=args.heavy_live,
        heavy_is_ancestor=_bool_arg(args.heavy_is_ancestor),
        dispatched=args.dispatched,
        heavy_release_age_min=_age_arg(args.heavy_release_age_min),
    )
    print(f"{decision.verdict}: {decision.reason}")
    return decision.code


if __name__ == "__main__":
    sys.exit(main())
