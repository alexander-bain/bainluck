"""#4057: the Kalshi settlement selection's two WHERE clauses, against a REAL PostgreSQL.

## why this gate needs a real server

`_select_kalshi_settlement_tickers()` decides WHICH settled Kalshi markets a
cycle asks the venue about. Everything the ship claims is in those two WHERE
clauses:

    -- band 1, new in #4057; grade test corrected in #5146, DELETED in #6981
    COALESCE(fm.settled_at, fm.resolution_date) BETWEEN NOW() - :floor AND NOW()
    AND EXISTS (an outcome that is neither authoritative nor ungradeable_result)
    ORDER BY MAX(LEAST(fm.settled_at, fm.resolution_date)) DESC LIMIT :fresh

    -- band 2, the pre-existing alphabetical sweep
    fm.external_id > :cursor ... ORDER BY fm.external_id ASC LIMIT :tail

A fake session that answers "any statement mentioning `futures_markets`" with a
canned list agrees with itself: delete the floor, the `ungradeable_result`
exclusion or the upper bound — or put the #6981 winner clause back — and every
unit test in `tests/test_kalshi_settlement_recency_band_4057.py` still passes,
because a row is absent from that list only because the test author left it out.

## #6981 — the band stopped asking "does this market have a winner"

Band 1 carried `NOT EXISTS (an outcome with is_winner IS TRUE)` from #4057 until
2026-09-18, as a proxy for its real subject: what a reader sees as "settled, no
result". The proxy holds for a two-sided market and fails for a FIELD, where one
winner and twenty losers are twenty-one venue contracts that settle at DIFFERENT
TIMES. The winner settles first — the instant the first touchdown is scored — and
that grade was then the very thing that evicted the market, at exactly the moment
its remaining legs became gradeable.

Measured on production 2026-09-18 16:20-16:25Z: last night's Bills 41 - Lions 31
(`/events/14638444`) had all five prop event tickers `finalized` at Kalshi with
per-leg results — 151 markets — while we held 36 grades, and fifteen hours after
the whistle the page printed `Josh Allen Won` above eighteen rows reading `last
quote 1%`. Inside the band's own 3-day window that day, 427 tickers were eligible
and **559 more, carrying 14,405 ungraded legs, were excluded by that clause
alone** — the locked-out cohort larger than the admitted one.

The `EXISTS` clause beneath it already asks the right question, so the ship is a
deletion, and it widens nothing: band 2's `EXISTS` is strictly wider and has never
had a winner clause, so every newly-admitted ticker was already reachable there
and already flowed through the same writer. `FFF`/`FGG` are the both-directions
pair, identical but for their legs.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs; the
`search-recall` job's "Verify the gate is actually armed" step is what stops a
skipped gate reading as a passing one.

## what production says, so the corpus is not invented

Measured through `/api/admin/db-query` on 2026-09-10 11:05–11:40Z:

* the tail band's own population is **71,389 distinct event tickers** — at 2,000
  a cycle, 4 cycles a day, one wrap is **~8.9 days**, and a market that settles
  below the cursor waits for it;
* **37,190** Kalshi markets were observed settling in the last 3 days and
  **29,556 of them (79%)** carry a `resolution_date` older than 3 days or none —
  which is why the recency signal is `COALESCE(settled_at, resolution_date)` and
  not the schedule alone;
* the recency band's population was **2,886** tickers over 3 days, **180** per
  6-hour cycle against a 400-ticker band — 2.2x headroom, so the band could not
  be outrun by ordinary inflow. **That claim is retired; see below.**

### the headroom claim above is DEAD, and it was never the right question (#5152)

Re-measured 2026-09-11 10:45–10:55Z, after #5146 corrected the grade test, running
the shipped band-1 statement itself rather than a paraphrase of it. The 2,886 was
a count of the population the OLD clause could see; under `IS TRUE` the same
window holds **7,625** distinct tickers, so the "2.2x headroom" is not merely
smaller — it is measuring a pool that no longer exists.

But replacing 2.2x with a worse ratio would repeat the original mistake, because
the population is not uniform and a ratio assumes it is. Distinct eligible
tickers by 6-hour cycle-age:

    cycle  -0    73     -6    243
    cycle  -1   282     -7   1523
    cycle  -2    31     -8   1153
    cycle  -3   259     -9   1671
    cycle  -4    58    -10   2074
    cycle  -5   109    -11    149

Two facts follow, and they point opposite ways:

* **Ordinary inflow does not outrun the band.** The two newest cycles hold 355
  tickers against 400 slots. Nothing that settled in the last 12 hours is being
  crowded out, which is what "last night's game is graded by morning" actually
  depends on.
* **84% of the pool is unreachable by construction, not by capacity.** 6,421
  tickers sit in the single 24-hour block at cycles -7..-10. The band is
  newest-first with a hard `LIMIT 400`, and the cumulative count from cycle -0
  crosses 400 inside cycle -3 — so the band reaches back roughly 18–24 hours and
  can never see that block at all. It ages out of `_FRESH_SETTLEMENT_FLOOR_DAYS`
  and falls to band 2's ~11-day alphabetical wrap.

That block is not the cohort the venue has nothing to say about. Bucketing it by
whether a cycle has ever received a venue answer for the ticker: **1,911 never
touched, 4,478 carrying only a non-authoritative source, 180 asked-partial** — so
6,389 of 6,569 have never had an authoritative answer, and 97% have never been
asked at all.

Two consequences a later reader should not have to re-derive:

* `_FRESH_SETTLEMENT_FLOOR_DAYS = 3` is currently **inert**. The `LIMIT` binds at
  ~24 hours, so the 72-hour floor never decides anything. Widening the floor
  would change nothing; only the ordering or the limit can.
* Raising `_FRESH_SETTLEMENT_MAX_SHARE` — #5152's candidate fix — does not
  address this. Doubling the band to 800 would still cover ~12% of that block,
  and it takes the budget from band 2, which is the only thing that ever drains
  it. The defect is a starvation shape, not a capacity shape.

The 400 slots the band does take are healthy and should not be re-aimed on
suspicion: they spread over **197 distinct series** with no series above 4%, and
only 50 of 400 are high-frequency (15-minute / hourly) tickers.

## what this corpus got WRONG for its first day, and why the shape matters (#5146)

Every "blank" row below used to be seeded `is_winner = NULL`, and the graded arm
`is_winner = true`. Production has almost none of the first shape:
`futures_outcomes.is_winner` is `nullable=True, default=False,
server_default=text("false")`, so a leg no grader has touched stores **FALSE**.
NULL is the *rare* state — mostly #1852's retraction.

So the shipped clause `NOT EXISTS (is_winner IS NOT NULL)` read the column's own
DEFAULT as a grade, and one untouched leg hid the whole market from this band.
Measured 2026-09-11 07:30–07:55Z inside the band's own 3-day window: the old
clause made **2,416** tickers eligible, `IS TRUE` makes **7,927** — 5,511 (70%)
of freshly-settled tickers could never enter the fast lane, and waited on band
2's ~11-day wrap. `KXNFLPASSTDS-26SEP10SFLAR` (SF–LA Rams, 2026-09-10) was 9/9
`finalized` at Kalshi with three `yes` results while every stored leg sat at
`is_winner=false, resolution_source=NULL`.

`default_false` and `mixed_default` below are that shape. Both are seeded with
EXPLICIT `False` rather than by omitting the column, so the arm tests the clause
and not the seeding path.

## the corpus, and what each row can fail on

Ten markets for the two bands above, plus six for the early-settled band added
in #6012. Each one is the ONLY row that fails if a particular clause is
deleted, and the two "mutated shape" arms at the bottom execute the deleted
shapes against the same seeded server so a green run cannot mean "the corpus had
nothing discriminating in it".

* **`settled_low`** — settled half an hour ago, ticker `AAA-…` sorts BELOW the
  cursor. The ship: the tail band can never offer it, the recency band must.
* **`settled_high`** — settled two hours ago, `ZZZ-…`, above the cursor. Proves
  the recency band is ordered by TIME, not by the alphabet: it comes LAST here
  while sorting last alphabetically too, which is why `observed_only` below is
  the row that actually separates the two orderings.
* **`schedule_only`** — `settled_at` NULL, `resolution_date` an hour ago. The
  COALESCE's second arm; the pre-column rows.
* **`observed_only`** — `settled_at` 45 minutes ago, `resolution_date` NINE DAYS
  old. The COALESCE's first arm, and 79% of production by measurement. An
  `fm.resolution_date`-only window drops it, and a `resolution_date` ORDERING
  sends it to the back.
* **`stale`** — settled nine days ago. Outside the floor; the tail's job.
* **`future_dated`** — `settled_at` NULL, `resolution_date` twenty days out.
  Excluded by the upper bound. Without it, newest-first ordering parks this row
  at the head of the band forever and the band never grades anything.
* **`already_graded`** — settled an hour ago, one outcome carries
  `is_winner = true`. Not blank, so not this band's work.
* **`ungradeable`** — settled an hour ago, every leg carries
  `ungradeable_result` (#1852's retraction of a fabricated loss). A decision,
  not a gap; in the band it would clog it for three days.
* **`authoritative`** — settled an hour ago, every leg already carries
  `api_settlement`. The pre-existing authority clause.
* **`polymarket`** / **`still_open`** — the source and status clauses.

## #6012 — the third band, and the sentence above that is not true

"Those fall to the tail sweep, which does not care what the date says" (the
`future_dated` note above) holds only for a market we have already flipped to
`resolved`. BOTH bands require `fm.status = 'resolved'`. The same #2644 field
mechanism that puts a future `resolution_date` on an already-settled market also
leaves our row `open` until the settled-events sweep's per-series cursor reaches
it (gotcha #33), so a market that is future-dated AND open is invisible to band 1
by date and to band 2 by status — and the `ungradeable_result` retraction that
`resolution_authority` calls "reversible by evidence" never gets the evidence.

Measured on production 2026-09-14 03:50–04:05Z: Kalshi finalized all 48 legs of
`KXATP-26USO` (US Open Men's Singles Winner) at 22:00:08Z, `-ZVE` = `result:
yes`. Six hours later our row was still `open` with a future `resolution_date`
and Alexander Zverev — the champion — read `current_probability=0.995,
is_winner=FALSE, resolution_source='ungradeable_result'`. The Exacta
(`KXATPWTA-26USO`) printed 84% on the winning pair on the men's-final event page.
**23 tickers** were in the band's window at that moment.

The six rows below are all `status='open'`, so none of them can move
`EXPECTED_FRESH` or the tail assertions:

* **`early_specimen`** (`NNN`) — the shape above: open, future-dated, one tier-3
  leg, one retracted leg, no winner. THE SHIP.
* **`early_later`** (`TTT`) — same shape, due later; the ordering arm.
* **`early_graded`** (`PPP`) — already holds a tier-3 winner; nothing to ask.
* **`early_far_future`** (`QQQ`) / **`early_stale`** (`RRR`) — the two bounds.
* **`early_polymarket`** (`SSS`) — the source clause.
* **`still_open`** (`JJJ`, reused) — open and in-window but no venue settlement:
  the clause that keeps this band off ordinary not-yet-played markets.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres Kalshi settlement "
        "recency band gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: The cursor the corpus is read against: past everything but `ZZZ-…`, which is
#: exactly the production state the ship is about — the sweep is mid-alphabet and
#: tonight's settlements are behind it.
CURSOR = "M"


def _now() -> datetime:
    return datetime.now(UTC)


#: (key, source, status, external_id, settled_at, resolution_date, outcomes)
#: where each outcome is (external_id, is_winner, resolution_source).
def _corpus() -> list[tuple]:
    now = _now()
    # Distinct to the minute on purpose: the ordering arm below asserts an exact
    # list, and two rows sharing a timestamp would make it a coin toss.
    half_hour = now - timedelta(minutes=30)
    # #6981's pair. `FFF` and `FGG` share this stamp deliberately — they are the
    # both-directions control (gotcha #43) and must differ in their LEGS and in
    # nothing else, so neither window position nor ordering can explain the
    # difference between them. Safe as a tie because only one of the two is ever
    # in the band, so the exact-list assertion still has a single answer.
    thirty_five = now - timedelta(minutes=35)
    forty = now - timedelta(minutes=40)
    three_quarters = now - timedelta(minutes=45)
    fifty = now - timedelta(minutes=50)
    hour = now - timedelta(hours=1)
    # `RRR` joined at `hour` with #6012 and tied `BBB` exactly, which the corpus's
    # own opening comment forbids: two rows sharing an ordering key make the
    # exact-list assertions in this file a coin toss that Postgres is free to
    # break either way. Pre-existing and not #6981's doing — found while adding a
    # third row at that stamp, which would have made it a three-way toss — but a
    # flaky gate guarding a settlement ship is worth the one line. Between `BBB`
    # and `ZZZ`, so no expectation in the file moves.
    sixty_five = now - timedelta(minutes=65)
    two_hours = now - timedelta(hours=2)
    nine_days = now - timedelta(days=9)
    ten_days = now - timedelta(days=10)
    five_minutes = now - timedelta(minutes=5)
    future = now + timedelta(days=20)
    # #6012's window, two-sided: `soon`/`tomorrow` sit inside the early band's
    # future reach, `nine_days_ago` below its floor, `future` beyond its reach.
    soon = now + timedelta(hours=1)
    tomorrow = now + timedelta(days=1)
    # #7857 — band 4's distance. Deliberately far past `future` (+20d): the
    # specimen missed band 3's ceiling by 466 days, and a fixture that only just
    # clears it would pass against a build whose ceiling was merely loosened
    # rather than inverted.
    years_out = now + timedelta(days=466)
    # `L4R` alone among band 4's rows is `resolved`, so it is the only one that
    # can enter band 1's statement at all — and `_CEILING_ONLY` drops band 1's
    # upper bound and asserts the FURTHEST-FUTURE row parks at the head. At
    # `years_out` this row displaced `EEE-26DEC31` there and reddened that arm
    # for a reason that has nothing to do with #7857. It is held just past band
    # 3's +2d reach instead: that is the only distance its own clause cares
    # about (it is refused by the inverted band-1 limb, not by the date), and it
    # leaves the neighbouring guard measuring what it was written to measure.
    beyond_reach_short = now + timedelta(days=10)
    nine_days_ago = nine_days
    blank = [("leg-a", None, None), ("leg-b", None, None)]
    return [
        ("settled_low", "kalshi", "resolved", "AAA-26SEP10", half_hour, half_hour, blank),
        ("settled_high", "kalshi", "resolved", "ZZZ-26SEP10", two_hours, two_hours, blank),
        ("schedule_only", "kalshi", "resolved", "BBB-26SEP10", None, hour, blank),
        ("observed_only", "kalshi", "resolved", "CCC-26SEP10", three_quarters, nine_days, blank),
        ("stale", "kalshi", "resolved", "DDD-26SEP01", nine_days, nine_days, blank),
        ("future_dated", "kalshi", "resolved", "EEE-26DEC31", None, future, blank),
        # #6981 — THE FIELD MARKET MID-SETTLEMENT, and the row that changed sides.
        # One graded winner above one leg nobody has spoken for: last night's
        # `Detroit vs Buffalo: 1st Touchdown` in two legs. Josh Allen's contract
        # settles the instant he scores — 25 minutes into the game, `close_time`
        # 00:27:51Z — and the other twenty settle at the whistle, so the winner's
        # grade arrives FIRST and, under the clause this ship deletes, was the very
        # thing that evicted the market at the moment its losers became gradeable.
        # It fell to band 2's ~9-11 day alphabetical wrap and a reader saw `Josh
        # Allen Won` above eighteen rows reading `last quote 1%` fifteen hours after
        # the whistle. Production 2026-09-18: 559 tickers carrying 14,405 ungraded
        # legs were locked out by that clause alone, against 427 admitted.
        (
            "winner_plus_blank", "kalshi", "resolved", "FFF-26SEP10",
            thirty_five, thirty_five,
            [("leg-a", True, "api_settlement"), ("leg-b", None, None)],
        ),
        # #6981's control, and the half that keeps the fix honest in BOTH
        # directions (gotcha #43). Byte-identical to `FFF` except that its second
        # leg IS graded: the same field market AFTER the fast lane has done its
        # work. Nothing is left to ask the venue, so it must stay out — which is
        # what proves the band now keys on "a leg still has no authoritative
        # grade" and not on "this market has no winner". Distinguished from `HHH`,
        # which is fully graded but holds no winner at all and so cannot tell the
        # old clause from the new one.
        (
            "fully_graded", "kalshi", "resolved", "FGG-26SEP10",
            thirty_five, thirty_five,
            [("leg-a", True, "api_settlement"), ("leg-b", False, "api_settlement")],
        ),
        (
            "ungradeable", "kalshi", "resolved", "GGG-26SEP10", hour, hour,
            [("leg-a", None, "ungradeable_result"), ("leg-b", None, "ungradeable_result")],
        ),
        (
            "authoritative", "kalshi", "resolved", "HHH-26SEP10", hour, hour,
            [("leg-a", None, "api_settlement"), ("leg-b", None, "api_settlement")],
        ),
        # #6012 amendment — the early-settled band's ONLY exclusion, and the
        # control that keeps it honest. Resolved, no winner, ONE tier-3 leg (so
        # the band's venue-evidence clause passes) and ONE ordinary ungraded leg
        # (so band 1's own EXISTS passes too). Band 1 has this ticker; the early
        # band must not spend a second venue call on it. Distinguished from
        # `HHH`, which has the tier-3 leg but NO ordinary one and is therefore
        # invisible to every band.
        (
            "band_one_visible", "kalshi", "resolved", "RRR-26SEP10",
            sixty_five, sixty_five,
            [("leg-a", None, "api_settlement"), ("leg-b", False, None)],
        ),
        ("polymarket", "polymarket", "resolved", "III-26SEP10", hour, hour, blank),
        ("still_open", "kalshi", "open", "JJJ-26SEP10", hour, hour, blank),
        # #5146 — the shape 70% of production is actually in. Every leg carries
        # the server default FALSE and no grader has ever spoken. Under the old
        # `is_winner IS NOT NULL` clause this row is invisible to the band, and
        # `KKK` sorts below the cursor so the tail cannot reach it either: it is
        # the row that waits ~11 days while the venue holds the answer.
        (
            "default_false", "kalshi", "resolved", "KKK-26SEP10", forty, forty,
            [("leg-a", False, None), ("leg-b", False, None)],
        ),
        # ONE untouched leg was enough to hide a market — the SF–LA Rams shape,
        # where some legs were retracted and the rest still hold the default.
        # `all_losers` is the dominant source on this cohort in production
        # (11,636 in-window legs) and is non-authoritative, so the second clause
        # still passes and only the grade test decides this row.
        (
            "mixed_default", "kalshi", "resolved", "LLL-26SEP10", fifty, fifty,
            [("leg-a", None, None), ("leg-b", False, "all_losers")],
        ),
        # #1121 — THE CATCH-UP ROW, and the reason the ORDER BY is `LEAST` and
        # not the window's `COALESCE`. The venue settled this TEN DAYS ago; a
        # backlog sweep only reached it five minutes ago and stamped `settled_at`
        # with its own clock. `COALESCE(settled_at, resolution_date)` therefore
        # calls it the freshest market in the book and hands it the head of a
        # capped band, evicting a game that finished tonight.
        #
        # Not hypothetical and not rare: measured on production 2026-09-14 09:25Z,
        # **214 of the 400 fast-lane slots (53.5%) were held by rows of exactly
        # this shape** — the head three were Korean-baseball games from 9 August —
        # while 699 tickers settled inside the last 24 h sat below the cutoff.
        # Sunday night's Cowboys–Giants player props ranked 1161–1172.
        #
        # Its `settled_at` is the NEWEST in the corpus on purpose: under the old
        # ordering it takes the head, under the ship it takes the tail, and no
        # other row can produce that difference.
        (
            "catchup", "kalshi", "resolved", "AAB-26SEP05", five_minutes, ten_days,
            blank,
        ),
        # ---- #6012: the early-settled band's corpus -------------------------
        # Every row below is `status='open'`, so none of them is visible to the
        # two bands above and none of them can move EXPECTED_FRESH or the tail.
        #
        # THE SPECIMEN, in the shape production served it. `KXATP-26USO` (US Open
        # Men's Singles Winner): Kalshi finalized all 48 legs at 22:00:08Z with
        # `-ZVE` = `result: yes`; six hours later our row was still `open` with a
        # FUTURE resolution_date, the champion sat at `is_winner=FALSE,
        # resolution_source='ungradeable_result'`, and no band could ask.
        (
            "early_specimen", "kalshi", "open", "NNN-26SEP14", None, soon,
            [("zve", False, "ungradeable_result"), ("she", False, "api_settlement")],
        ),
        # Ordering arm: same shape, due later. Soonest-due must come first.
        (
            "early_later", "kalshi", "open", "TTT-26SEP15", None, tomorrow,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # NOT selected — we already hold the venue's answer, so there is nothing
        # to ask about. Pins the `NOT EXISTS (is_winner IS TRUE)` clause.
        (
            "early_graded", "kalshi", "open", "PPP-26SEP14", None, soon,
            [("leg-a", True, "api_settlement"), ("leg-b", False, "api_settlement")],
        ),
        # NOT selected — beyond the future reach. Pins the upper bound, without
        # which every open market in the book with one settled leg is in scope.
        (
            "early_far_future", "kalshi", "open", "QQQ-26DEC31", None, future,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # NOT selected — below the floor. Pins the lower bound (gotcha #41: a
        # sweep over an expiring population needs BOTH bounds, not an ordering).
        (
            "early_stale", "kalshi", "open", "RRR-26SEP01", None, nine_days_ago,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # NOT selected — not Kalshi. Pins `source='kalshi'`; Polymarket has its
        # own settlement path and this band must not reach into it.
        (
            "early_polymarket", "polymarket", "open", "SSS-26SEP14", None, soon,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # ------------------------------------------------------------------
        # #7857 — BAND 4's corpus. Every row here is `resolution_date` BEYOND
        # band 3's future reach, which is the one thing that makes it band 4's.
        # `QQQ-26DEC31` above is already such a row and already has an assertion
        # that band 3 refuses it; band 4 must TAKE it, and that pair is the
        # cleanest statement of the ship there is.
        #
        # The `L4…` prefix is chosen so these sort together and AFTER every
        # letter the existing corpus uses for a band-4 member, which is what lets
        # the cursor arms assert an exact walk rather than a set.
        # ------------------------------------------------------------------
        #
        # THE SPECIMEN, in the shape production served it. Kalshi market 112815
        # "Next Fed rate hike?" — a cumulative ladder whose last rung is dated
        # 2028 and which the venue settled `yes` on 2026-09-16, 466 days early.
        # Three legs already carry the venue's tier-3 stamp and none is a winner,
        # so we hold no answer and the page showed a 95% hero over a live chart.
        (
            "longdated_ladder", "kalshi", "open", "L4A-28JAN01", None, years_out,
            [
                ("leg-a", False, "api_settlement"),
                ("leg-b", False, "api_settlement"),
                ("leg-c", False, "api_settlement"),
            ],
        ),
        # Two more members, purely so the cursor has somewhere to walk TO. A
        # one-member band cannot tell "the cursor advanced" from "the statement
        # returned everything it had".
        (
            "longdated_second", "kalshi", "open", "L4B-29JAN01", None, years_out,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        (
            "longdated_third", "kalshi", "open", "L4C-27JUL01", None, years_out,
            [("leg-a", False, "settlement_sync"), ("leg-b", False, None)],
        ),
        # NOT selected — we already hold the venue's answer. Band 3's winner
        # clause, carried into band 4; without it a graded ladder is re-asked
        # about for ever and never leaves the cursor's population.
        (
            "longdated_graded", "kalshi", "open", "L4X-28JAN01", None, years_out,
            [("leg-a", True, "api_settlement"), ("leg-b", False, "api_settlement")],
        ),
        # NOT selected — no tier-3 leg, so nothing says the venue has settled any
        # part of this. This is the clause that keeps the band from becoming "every
        # long-dated Kalshi market in the book", which is most of the book.
        (
            "longdated_untouched", "kalshi", "open", "L4Y-28JAN01", None, years_out,
            blank,
        ),
        # NOT selected — not Kalshi. Same reason as `SSS` above.
        (
            "longdated_polymarket", "polymarket", "open", "L4Z-28JAN01", None,
            years_out,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # NOT selected — BAND 2 IS COMING FOR IT, and this row is why the
        # inverted band-1 clause is correct rather than a hole. It is `resolved`
        # with one ordinary ungraded leg. Band 1's own window is
        # `COALESCE(settled_at, resolution_date) <= NOW()`, so a years-out row
        # fails it — but band 2 has NO date window at all, only `status =
        # 'resolved'` + a non-authoritative leg + the cursor, so it sweeps this
        # up on its alphabetical walk. Band 4 must not duplicate that work.
        (
            "longdated_band_two_owns_it", "kalshi", "resolved", "L4R-28JAN01",
            None, beyond_reach_short,
            [("leg-a", False, "api_settlement"), ("leg-b", False, None)],
        ),
        # ------------------------------------------------------------------
        # #7870 band 5 — the status-sync band. It needs exactly ONE new row.
        # ------------------------------------------------------------------
        #
        # Its two MEMBERS are already here and were seeded as other bands'
        # refusals, which is the cleanest possible statement of why the band
        # exists: `PPP-26SEP14` (`early_graded`) and `L4X-28JAN01`
        # (`longdated_graded`) are both open markets carrying an authoritative
        # WINNER, i.e. we hold the venue's answer and our status still says
        # `open`. Bands 3 and 4 refuse them for having a winner; bands 1 and 2
        # refuse them for not being `resolved`. Until this band they were rows
        # nobody was coming for — the #7857 residue, and `L4X` is `FEDHIKE`'s
        # shape on the day after band 4 graded it.
        #
        # `FGG-26SEP10` (`fully_graded`) is likewise already the status-clause
        # control: resolved, with an authoritative winner. Band 5 must refuse it.
        #
        # THE ONE ROW THE CORPUS LACKS is an open market whose winner is NOT
        # authoritative — the tier-1 `all_losers` guess, which is a thing we
        # decided and not a thing the venue said. Without it, deleting
        # `AND COALESCE(fo.resolution_source,'') IN (…)` from the band's EXISTS
        # changes no result in this file and the authority clause is untested.
        # It is dated `soon` on purpose so that it sits squarely inside band 3's
        # window: it then fails band 3 ONLY on the winner clause and fails band 5
        # ONLY on the authority clause, which makes it discriminating for both.
        (
            "status_sync_guess_winner", "kalshi", "open", "SSY-26SEP14", None,
            soon,
            [("leg-a", True, "all_losers"), ("leg-b", False, None)],
        ),
    ]


#: What the recency band must return, VENUE-newest first, when nothing caps it.
#:
#: #1121 moved the last two. The ordering key is `LEAST(settled_at,
#: resolution_date)` — the earlier of "when we noticed" and "when the venue said
#: it was due" — so the two rows whose venue date is old sink below every row
#: that genuinely settled in the last hour, however recently we stamped them:
#:
#:   * `CCC` observed 45 min ago, venue-dated nine days ago
#:   * `AAB` observed FIVE MINUTES ago, venue-dated ten days ago
#:
#: Both remain MEMBERS — the window is still the `COALESCE` and that is what the
#: 79% measurement in `backfill_winners`' constant block protects. Only their
#: place in a capped band changes, which is the whole ship.
EXPECTED_FRESH = [
    "AAA-26SEP10",
    # #6981 — the field market mid-settlement. It carries a graded winner, which
    # until this ship was disqualifying on its own; it also carries a leg no
    # grader has spoken for, which is the only thing this band is supposed to ask
    # about. Its fully-graded twin `FGG` sits at the SAME timestamp and is absent.
    "FFF-26SEP10",
    "KKK-26SEP10",
    "LLL-26SEP10",
    "BBB-26SEP10",
    # #6012 amendment's control row. It is resolved with one ordinary ungraded
    # leg, so band 1 genuinely owns it — that is the whole point of adding it,
    # and `test_a_resolved_market_band_one_can_see_is_left_to_band_one` asserts
    # both halves (absent from the early band, present here).
    "RRR-26SEP10",
    "ZZZ-26SEP10",
    "CCC-26SEP10",
    "AAB-26SEP05",
]


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _seed(conn)

    yield engine

    await engine.dispose()


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{key: futures_markets.id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status`
    carry a **client-side `default=`** applied by the ORM and invisible to a raw
    INSERT — omitting one raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against live ORM metadata and this file is in its `COVERED` tuple.
    """
    ids: dict[str, int] = {}
    for key, source, status, ext, settled_at, resolution_date, outcomes in _corpus():
        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, settled_at, resolution_date) "
                    "VALUES (:source, :ext, :name, 'championship', true, "
                    "        :status, :settled_at, :resolution_date) RETURNING id"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                    "settled_at": settled_at,
                    "resolution_date": resolution_date,
                },
            )
        ).scalar_one()
        ids[key] = market_id

        for leg_ext, is_winner, resolution_source in outcomes:
            await conn.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, is_winner, resolution_source) "
                    "VALUES (:mid, :ext, :name, :w, :src)"
                ),
                {
                    "mid": market_id,
                    "ext": f"{ext}-{leg_ext}",
                    "name": f"{key} {leg_ext}",
                    "w": is_winner,
                    "src": resolution_source,
                },
            )
    return ids


async def _select(engine, limit: int, cursor: str = CURSOR):
    from app.tasks.backfill_winners import _select_kalshi_settlement_tickers

    async with engine.connect() as conn:
        return await _select_kalshi_settlement_tickers(conn, limit, cursor)


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_a_market_that_settled_below_the_cursor_is_selected_this_cycle(pg_engine):
    """`AAA-…` settled an hour ago and sorts below the cursor.

    The tail band cannot reach it until the cursor wraps — ~8.9 days on the
    measured production population. The recency band must return it now, and
    this is the whole user-visible ship: a settled market stops showing no
    result while the venue has one.
    """
    fresh, tail = await _select(pg_engine, limit=2000)

    assert "AAA-26SEP10" in fresh
    assert "AAA-26SEP10" not in tail, (
        "the tail band is cursor-bound; if it can see AAA the corpus no longer "
        "reproduces the defect and every assertion here is vacuous"
    )


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,shape",
    [
        ("KKK-26SEP10", "every leg carries the server default FALSE"),
        ("LLL-26SEP10", "one leg NULL, one leg the default FALSE + all_losers"),
    ],
)
async def test_an_ungraded_market_whose_legs_hold_the_default_false_is_selected(
    pg_engine, ticker, shape
):
    """#5146 — the ship. `is_winner` defaults to FALSE, so this IS "no result".

    `futures_outcomes.is_winner` is `default=False, server_default=text("false")`,
    so a leg no grader has touched reads FALSE, not NULL. Under the shipped-then
    clause `NOT EXISTS (is_winner IS NOT NULL)` both of these rows were excluded
    from the fast lane — 70% of freshly-settled production tickers — and fell to
    the tail band's ~11-day wrap while the venue already held the answer.

    Both tickers sort BELOW the cursor, so the tail cannot cover for the band;
    without that, a green here would not distinguish the two paths.
    """
    fresh, tail = await _select(pg_engine, limit=2000)

    assert ticker in fresh, shape
    assert ticker not in tail, (
        "the tail band is cursor-bound; if it can reach this ticker the arm no "
        "longer proves the recency band is what selects it"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_recency_band_is_ordered_by_settlement_time_not_by_ticker(pg_engine):
    """VENUE-newest first — not by the alphabet, and not by our own clock.

    `BBB` (schedule-only, an hour ago) must outrank `ZZZ` (two hours ago), so
    this is not `ORDER BY external_id` and not `ORDER BY settled_at` alone — a
    row with no `settled_at` still has to find its place.

    And `CCC`/`AAB`, whose venue dates are nine and ten days old, must rank
    BELOW every genuinely-recent row however recently we stamped them. #1121:
    `AAB`'s `settled_at` is the newest in the corpus.
    """
    fresh, _tail = await _select(pg_engine, limit=2000)
    assert fresh == EXPECTED_FRESH


@needs_postgres
@pytest.mark.asyncio
async def test_a_capped_band_spends_its_budget_on_the_newest(pg_engine):
    """limit=5 -> a 1-ticker band (`_fresh_settlement_budget`), and it takes the newest.

    This is the arm that makes the ordering load-bearing rather than cosmetic:
    with a cap, order decides who is graded tonight and who waits.

    #1121 makes it the ship's narrowest statement. `AAB` was stamped `settled_at`
    five minutes ago — 25 minutes newer than `AAA` — so under the shipped-until-now
    `COALESCE` ordering this single slot went to a market the venue settled TEN
    DAYS ago, and the market that settled tonight waited for the alphabetical
    tail to wrap (~11 days on the production population). The one slot must go to
    `AAA`.
    """
    fresh, tail = await _select(pg_engine, limit=5)
    assert fresh == ["AAA-26SEP10"], (
        "the one fast-lane slot went to a catch-up row: the band is ordered by "
        "OUR observation stamp, not by when the venue settled"
    )
    assert len(tail) <= 4


@needs_postgres
@pytest.mark.asyncio
async def test_the_two_bands_never_exceed_the_cycle_budget(pg_engine):
    """Cost neutrality, proven against the server rather than argued from the split."""
    fresh, tail = await _select(pg_engine, limit=5)
    assert len(fresh) + len(tail) <= 5


@needs_postgres
@pytest.mark.asyncio
async def test_the_fast_lane_returns_the_same_band_1_and_no_band_2(pg_engine):
    """#1121 residual, against the server: the SAME rows, sooner.

    `grade_fresh_kalshi_settlements` runs at `:09/:39` and its entire claim is
    that it asks about exactly what the `:45` omnibus would have asked about in
    band 1 — so the two calls must agree on band 1 EXACTLY, ordering included,
    while band 2 comes back empty.

    The second assertion is what makes the first one worth making: the same
    cursor and budget DO yield a non-empty tail when it is asked for, so the
    empty tail is the skip and not a corpus that happens to have no tail rows.
    """
    from app.tasks.backfill_winners import _select_kalshi_settlement_tickers

    full_fresh, full_tail = await _select(pg_engine, limit=20)
    async with pg_engine.connect() as conn:
        fast_fresh, fast_tail = await _select_kalshi_settlement_tickers(
            conn, 20, CURSOR, include_tail=False
        )

    assert fast_fresh == full_fresh
    assert fast_tail == []
    assert full_tail, "corpus must offer a tail, or the arm above is vacuous"


# ---------------------------------------------------------------------------
# every exclusion, one row each
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,why",
    [
        ("DDD-26SEP01", "settled nine days ago — outside the floor, the tail's job"),
        ("EEE-26DEC31", "future-dated schedule — would park at the head forever"),
        ("FGG-26SEP10", "every leg graded, winner included — nothing left to ask"),
        ("GGG-26SEP10", "every leg is ungradeable_result — a retraction, not a gap"),
        ("HHH-26SEP10", "every leg is already authoritative"),
        ("III-26SEP10", "polymarket, not kalshi"),
        ("JJJ-26SEP10", "still open"),
    ],
)
async def test_the_recency_band_refuses(pg_engine, ticker, why):
    fresh, _tail = await _select(pg_engine, limit=2000)
    assert ticker not in fresh, why


# ---------------------------------------------------------------------------
# two-armed: the deleted clauses, executed
# ---------------------------------------------------------------------------

_MUTATED_BASE = """
    SELECT fm.external_id
    FROM futures_markets fm
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      {window}
      {blank}
      {gradeable}
    GROUP BY fm.external_id
    ORDER BY {order} DESC
    LIMIT {limit}
"""

#: The shipped ordering key (#1121): the earlier of our observation stamp and the
#: venue's own date, which is Postgres `LEAST` because `LEAST` IGNORES NULLs —
#: a row carrying only one of the two keeps exactly the key it had before.
_ORDER = "MAX(LEAST(fm.settled_at, fm.resolution_date))"
#: The ordering as it shipped from #4057 until #1121, kept so the regression is
#: EXECUTED against this server rather than described in a comment.
_ORDER_OBSERVED = "MAX(COALESCE(fm.settled_at, fm.resolution_date))"

_WINDOW = (
    "AND COALESCE(fm.settled_at, fm.resolution_date) >= NOW() - INTERVAL '3 days' "
    "AND COALESCE(fm.settled_at, fm.resolution_date) <= NOW()"
)
_FLOOR_ONLY = "AND COALESCE(fm.settled_at, fm.resolution_date) <= NOW()"
_CEILING_ONLY = (
    "AND COALESCE(fm.settled_at, fm.resolution_date) >= NOW() - INTERVAL '3 days'"
)
_SCHEDULE_ONLY_WINDOW = (
    "AND fm.resolution_date >= NOW() - INTERVAL '3 days' "
    "AND fm.resolution_date <= NOW()"
)
#: #6981 DELETED the winner clause outright, so the shipped band now has NO
#: winner-based membership test and the default below is the empty string. The
#: two constants that follow are the clause's TWO HISTORICAL SHAPES, kept so each
#: regression is EXECUTED against this server rather than described in a comment.
#: Neither may come back: a market and its legs are not the same subject, and
#: both shapes make that mistake — one in each direction.
_NO_WINNER_CLAUSE = ""
#: The clause as it shipped from #5146 until #6981: "this market has no winner",
#: used as a proxy for "this market has no result". True of a two-sided market,
#: false of a FIELD, whose winner settles before its losers.
_WINNER_EXCLUSION = (
    "AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo "
    "WHERE fo.market_id = fm.id AND fo.is_winner IS TRUE)"
)
#: The clause as it shipped from #4057 until #5146: "no leg has been touched",
#: which read the column's own server-default FALSE as a grade.
_BLANK_IS_NOT_NULL = (
    "AND NOT EXISTS (SELECT 1 FROM futures_outcomes fo "
    "WHERE fo.market_id = fm.id AND fo.is_winner IS NOT NULL)"
)
_GRADEABLE = (
    "AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id "
    "AND COALESCE(fo.resolution_source, '') NOT IN "
    "('api_settlement','clob_authoritative','clob_field_repair','clob_never_graded',"
    "'clob_ordinal','datagolf_settlement','settlement_sync') "
    "AND COALESCE(fo.resolution_source, '') <> 'ungradeable_result')"
)
_GRADEABLE_WITHOUT_RETRACTION = (
    "AND EXISTS (SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id "
    "AND COALESCE(fo.resolution_source, '') NOT IN "
    "('api_settlement','clob_authoritative','clob_field_repair','clob_never_graded',"
    "'clob_ordinal','datagolf_settlement','settlement_sync'))"
)


async def _mutated(
    engine,
    *,
    window=_WINDOW,
    blank=_NO_WINNER_CLAUSE,
    gradeable=_GRADEABLE,
    order=_ORDER,
    limit=2000,
):
    sql = _MUTATED_BASE.format(
        window=window, blank=blank, gradeable=gradeable, order=order, limit=limit
    )
    async with engine.connect() as conn:
        rows = await conn.execute(text(sql))
    return [r[0] for r in rows.all()]


@needs_postgres
@pytest.mark.asyncio
async def test_the_authoritative_clauses_reproduce_the_shipped_band(pg_engine):
    """The mutation harness is calibrated on the unmutated shape first.

    Without this, a mutated arm that returns the same list as the ship could
    mean either "the clause does nothing" or "the harness is not running the
    query I think it is".
    """
    assert await _mutated(pg_engine) == EXPECTED_FRESH


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_floor_sweeps_in_a_nine_day_old_settlement(pg_engine):
    assert "DDD-26SEP01" in await _mutated(pg_engine, window=_FLOOR_ONLY)


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_upper_bound_parks_a_future_date_at_the_head(pg_engine):
    """Not merely "included" — FIRST, which is the clog.

    Newest-first ordering hands the head of a capped band to the row with the
    furthest-future schedule, every cycle, forever.
    """
    got = await _mutated(pg_engine, window=_CEILING_ONLY)
    assert got[0] == "EEE-26DEC31"


@needs_postgres
@pytest.mark.asyncio
async def test_a_schedule_only_window_drops_the_row_production_is_made_of(pg_engine):
    """79% of production, in one row: observed an hour ago, scheduled nine days ago."""
    got = await _mutated(pg_engine, window=_SCHEDULE_ONLY_WINDOW)
    assert "CCC-26SEP10" not in got
    assert "AAA-26SEP10" in got, "the schedule-only window is not broken outright"


@needs_postgres
@pytest.mark.asyncio
async def test_restoring_the_winner_clause_hides_the_field_market_mid_settlement(
    pg_engine,
):
    """#6981's regression, EXECUTED — and it moves exactly one row.

    This arm used to run in the other direction: it deleted the clause and
    asserted `FFF` swept in, as the harm the clause prevented. #6981 measured the
    clause on production and found the harm is the clause — 559 tickers carrying
    14,405 ungraded legs locked out against 427 admitted — so the same two states
    are still executed here and only the labels have swapped.

    The exact-list assertion is what makes it a guard rather than an anecdote. A
    future edit that reintroduces a winner-based test in ANY form goes red here,
    and the message says which row it cost. A wider or narrower clause than the
    one deleted fails the same assertion for the opposite reason: it moves
    something other than `FFF`.
    """
    got = await _mutated(pg_engine, blank=_WINNER_EXCLUSION)

    assert "FFF-26SEP10" not in got, (
        "the winner clause did not evict the field market, so the corpus no "
        "longer reproduces #6981 and every assertion about the fix is vacuous"
    )
    assert got == [t for t in EXPECTED_FRESH if t != "FFF-26SEP10"], (
        "the winner clause must cost this band the mid-settlement field market "
        "and NOTHING else — otherwise this arm is measuring some other change "
        "and the 559-vs-427 production split is not what it explains"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_pre_5146_grade_test_hides_the_default_false_rows(pg_engine):
    """The regression, executed — not asserted about.

    Running the OLD clause against this same seeded server must drop exactly the
    two default-FALSE rows and keep everything else. If a later edit reverts the
    grade test, the ship arm above goes red and this arm explains why in one
    line: the column's default was read as a grade.
    """
    got = await _mutated(pg_engine, blank=_BLANK_IS_NOT_NULL)

    assert "KKK-26SEP10" not in got
    assert "LLL-26SEP10" not in got
    # `RRR` joined the corpus with the #6012 amendment and is a default-FALSE row
    # too (`leg-b` is explicitly `False`, the shape 70% of production is in), so
    # the old clause drops it for exactly the reason this arm is about. Seeding it
    # NULL instead would keep this list shorter and make the control less like
    # production, which is the trade #5146 already ruled on.
    assert "RRR-26SEP10" not in got
    # And `FFF` since #6981, for the OTHER reason — `IS NOT NULL` catches a real
    # grade as well as a default, so the oldest shape of this clause costs the
    # band both cohorts at once. Listed apart from the three above because it is
    # a different defect sharing one clause, not a fourth default-FALSE row.
    assert "FFF-26SEP10" not in got
    assert got == [
        t
        for t in EXPECTED_FRESH
        if t not in {"KKK-26SEP10", "LLL-26SEP10", "RRR-26SEP10", "FFF-26SEP10"}
    ], (
        "the old clause must differ from the shipped one on the default-FALSE "
        "rows and the mid-settlement field market and on NOTHING else — "
        "otherwise this arm is measuring some other change and the "
        "2,416-vs-7,927 production split is not what it explains"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_retraction_exclusion_lets_ungradeable_rows_clog_the_band(
    pg_engine,
):
    got = await _mutated(pg_engine, gradeable=_GRADEABLE_WITHOUT_RETRACTION)
    assert "GGG-26SEP10" in got


@needs_postgres
@pytest.mark.asyncio
async def test_the_observation_stamp_ordering_hands_the_head_to_a_ten_day_old_market(
    pg_engine,
):
    """#1121's regression, EXECUTED — the one-slot band, both ways.

    The membership clauses are held identical and only the ORDER BY moves, so
    the difference cannot be anything else. Under the old
    `COALESCE(settled_at, resolution_date)` the single slot goes to `AAB`, which
    the venue settled ten days ago and a backlog sweep stamped five minutes ago;
    under the shipped `LEAST` it goes to `AAA`, which settled half an hour ago.

    This is the production defect in one row: `settled_at` is OUR clock, so a
    catch-up sweep manufactures freshness and evicts tonight's game from a band
    whose only purpose is tonight's game.
    """
    old = await _mutated(pg_engine, order=_ORDER_OBSERVED, limit=1)
    new = await _mutated(pg_engine, order=_ORDER, limit=1)

    assert old == ["AAB-26SEP05"], (
        "the corpus no longer reproduces the defect — if the old ordering does "
        "not promote the catch-up row, every assertion about the fix is vacuous"
    )
    assert new == ["AAA-26SEP10"]


@needs_postgres
@pytest.mark.asyncio
async def test_the_ordering_change_moves_nobody_in_or_out_of_the_band(pg_engine):
    """Reach is the window's job; the ORDER BY may only re-rank.

    #1121 is a re-ranking, and the 79% measurement in `backfill_winners`'
    constant block is why it must stay one: narrowing the WINDOW to the venue's
    own date would lose four settlements in five. Run both orderings uncapped
    and the SETS must be equal.
    """
    old = await _mutated(pg_engine, order=_ORDER_OBSERVED)
    new = await _mutated(pg_engine, order=_ORDER)

    assert sorted(old) == sorted(new)
    assert old != new, (
        "the two orderings returned the identical LIST, so this file is not "
        "exercising the change at all"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_least_ignores_nulls_so_a_one_column_row_keeps_its_old_key(pg_engine):
    """The load-bearing Postgres behaviour, asserted against the server.

    `LEAST` ignoring NULLs is a Postgres-specific rule (most dialects propagate
    the NULL), and the whole safety argument for #1121 rests on it: a row with
    only ONE of the two columns must keep exactly the key it had before. `BBB`
    is that row — `settled_at` NULL, `resolution_date` an hour ago — and it
    stands for the entire pre-`settled_at` cohort, which resolved before the
    column shipped and will never be backfilled. If NULL propagated, every one
    of them would sort to the bottom of the band rather than being re-ranked.
    """
    async with pg_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT LEAST(NULL::timestamptz, NOW()), "
                    "       LEAST(NOW(), NULL::timestamptz), "
                    "       LEAST(NULL::timestamptz, NULL::timestamptz)"
                )
            )
        ).one()

    assert row[0] is not None, "LEAST propagated a NULL — the ordering key is unsafe"
    assert row[1] is not None
    assert row[2] is None, "LEAST of all-NULL must stay NULL"

    # And the consequence on the real band. `BBB`'s key is identical under both
    # orderings, so its order against every OTHER row whose key is also
    # unchanged must be identical too — here `AAA`, `KKK`, `LLL`, `ZZZ`, all of
    # which carry two agreeing timestamps. Asserted as relative order and not as
    # an index, because the catch-up rows moving past `BBB` is the ship.
    unmoved = [
        "AAA-26SEP10",
        "FFF-26SEP10",
        "KKK-26SEP10",
        "LLL-26SEP10",
        "BBB-26SEP10",
        "ZZZ-26SEP10",
    ]
    old = await _mutated(pg_engine, order=_ORDER_OBSERVED)
    new = await _mutated(pg_engine, order=_ORDER)
    assert [t for t in old if t in unmoved] == [t for t in new if t in unmoved] == unmoved


# ---------------------------------------------------------------------------
# the tail band is untouched
# ---------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_the_tail_band_still_walks_the_alphabet_from_the_cursor(pg_engine):
    """The pre-existing sweep keeps its shape, its cursor and its own budget.

    `RRR` and `ZZZ` are the corpus tickers above the cursor that carry a
    non-authoritative outcome, so this also proves the recency band did not
    quietly become the whole selection. `RRR` joined the corpus with the #6012
    amendment and belongs here for the same reason it belongs in
    `EXPECTED_FRESH`: an ordinary ungraded leg is exactly what these two bands
    are for, and the early band's whole job is the markets that have none.
    """
    _fresh, tail = await _select(pg_engine, limit=2000)
    assert tail == ["RRR-26SEP10", "ZZZ-26SEP10"]


@needs_postgres
@pytest.mark.asyncio
async def test_the_tail_band_ignores_recency_entirely(pg_engine):
    """From the start of the alphabet it returns the stale and the future-dated too.

    The two bands answer different questions; this is the row that proves the
    recency clauses did not leak into the sweep that must keep the whole
    population moving.
    """
    _fresh, tail = await _select(pg_engine, limit=2000, cursor="")
    assert "DDD-26SEP01" in tail
    assert "EEE-26DEC31" in tail


# ---------------------------------------------------------------------------
# #6012 — the early-settled band
#
# WHY THIS BAND EXISTS, stated where the next reader will look: the module
# docstring above says a future-dated settled market "falls to the tail sweep,
# which does not care what the date says". That is true only for a market whose
# status we have already flipped. Both bands above require
# `fm.status = 'resolved'`, and the same #2644 field mechanism that puts a future
# `resolution_date` on a settled market also leaves our row `open` until the
# settled-events sweep's per-series cursor reaches it (gotcha #33). A market that
# is BOTH future-dated AND open is invisible to band 1 by date and to band 2 by
# status, so the `ungradeable_result` retraction the design calls "reversible by
# evidence" never gets the evidence.
#
# AMENDED (#6012, 2026-09-14 08:45Z). "Open" was never the property. At 08:15:13Z
# an unrelated sweep flipped BOTH founding specimens to `status='resolved'` —
# status only, no grade — and the band lost them five hours after it was written,
# with the champion still `is_winner=false` against a venue reading `result='yes'`.
# The property is "NO OTHER BAND WILL ASK", and the only exclusion is band 1's two
# gates together: resolved status AND a leg that is neither authoritative nor
# `ungradeable_result`. Testing only the leg half drops every OPEN market with an
# ordinary ungraded leg into the same gap — `TTT-26SEP15` is that guard.
#
# These run against a real server for the same reason the ones above do: delete
# the floor, the future reach, the winner test, the venue-evidence test, the
# source test or either half of the band-1 exclusion, and a fake session that
# answers from a canned list still agrees with itself.
# ---------------------------------------------------------------------------


async def _select_early(engine, limit: int = 50):
    from app.tasks.backfill_winners import _select_kalshi_early_settled_tickers

    async with engine.connect() as conn:
        return await _select_kalshi_early_settled_tickers(conn, limit)


@needs_postgres
@pytest.mark.asyncio
async def test_an_open_market_the_venue_has_settled_is_asked_about(pg_engine):
    """THE SHIP. The champion stops reading 99.5% and "not a winner".

    `NNN` is the production specimen's shape: our row still says `open`, its
    `resolution_date` is still in the future, one leg carries the venue's own
    tier-3 settlement and one carries the retraction — and no leg is a winner.
    Neither band above can see it. This band must.
    """
    early = await _select_early(pg_engine)

    assert "NNN-26SEP14" in early


@needs_postgres
@pytest.mark.asyncio
async def test_the_band_is_ordered_soonest_due_first(pg_engine):
    """Both bounds AND an ordering (gotcha #41), and the ordering is by due date.

    A reader is looking at the market that just finished, not the one that
    finishes tomorrow, so the soonest-due ticker is asked about first when the
    cap binds.
    """
    early = await _select_early(pg_engine)

    assert early.index("NNN-26SEP14") < early.index("TTT-26SEP15")


@needs_postgres
@pytest.mark.asyncio
async def test_a_market_we_already_have_a_winner_for_is_not_asked_about(pg_engine):
    """`PPP` holds a tier-3 winner already — there is nothing to ask.

    Without this clause the band would re-ask the venue about every settled
    market in the window forever, which is the cost the cap exists to bound.
    """
    early = await _select_early(pg_engine)

    assert "PPP-26SEP14" not in early


@needs_postgres
@pytest.mark.asyncio
async def test_an_open_market_with_no_venue_settlement_is_left_alone(pg_engine):
    """`JJJ` is open and in-window, but no leg carries a tier-3 source.

    This is the clause that keeps the band off ordinary open markets: an event
    that has simply not happened yet is not a settlement we are missing. `JJJ`
    is the pre-existing `still_open` corpus row, so this also proves the band
    did not widen to "every open market".
    """
    early = await _select_early(pg_engine)

    assert "JJJ-26SEP10" not in early


@needs_postgres
@pytest.mark.asyncio
async def test_the_window_is_bounded_on_both_sides(pg_engine):
    """`QQQ` is 20 days out, `RRR` is 9 days stale — both carry venue settlements.

    The future reach stops the band swallowing the whole forward book; the floor
    stops it starting on the dead tail (gotcha #41: a sweep over an expiring
    population needs BOTH bounds).
    """
    early = await _select_early(pg_engine)

    assert "QQQ-26DEC31" not in early
    assert "RRR-26SEP01" not in early


@needs_postgres
@pytest.mark.asyncio
async def test_the_band_is_kalshi_only(pg_engine):
    """`SSS` is the specimen's shape on Polymarket, which has its own path.

    This band feeds `GET /events/{ticker}` on Kalshi; handing it a Polymarket
    market would spend a venue call that can never answer.
    """
    early = await _select_early(pg_engine)

    assert "SSS-26SEP14" not in early


@needs_postgres
@pytest.mark.asyncio
async def test_a_resolved_market_band_one_can_see_is_left_to_band_one(pg_engine):
    """`RRR` is resolved AND carries an ordinary ungraded leg — band 1 has it.

    The bands must not double-ask. This is the only exclusion this band applies,
    and it takes BOTH of band 1's gates, because band 1 needs both: resolved
    status AND a leg that is neither authoritative nor `ungradeable_result`.
    """
    early = await _select_early(pg_engine)

    assert "RRR-26SEP10" not in early
    # …and band 1 really does have it, so nothing is dropped on the floor.
    fresh, _tail = await _select(pg_engine, limit=200, cursor="")
    assert "RRR-26SEP10" in fresh


@needs_postgres
@pytest.mark.asyncio
async def test_a_resolved_market_NO_band_can_see_is_asked_about(pg_engine):
    """`HHH` is resolved, every leg authoritative, and NOT ONE BAND CAN SEE IT.

    This assertion is the inverse of the one it replaces, and the inversion is
    the #6012 amendment. The old test read "resolved ⇒ band 2's job"; band 2's
    own `EXISTS` needs a NON-authoritative leg, which `HHH` does not have, so
    band 2 never had it either and the comment was simply wrong. A market with
    no winner that every band skips is precisely what this band is for.

    Production made the point at 08:15:13Z on 2026-09-14: an unrelated sweep
    flipped `KXATP-26USO` from `open` to `resolved` — status only, no grade —
    and under the old clause the champion fell out of the one band written for
    him, five hours after it was written, still `is_winner=false` against a
    venue reading `result='yes'`.
    """
    early = await _select_early(pg_engine)

    assert "HHH-26SEP10" in early
    # Nobody else is coming: neither band above qualifies it.
    fresh, tail = await _select(pg_engine, limit=200, cursor="")
    assert "HHH-26SEP10" not in fresh
    assert "HHH-26SEP10" not in tail


@needs_postgres
@pytest.mark.asyncio
async def test_an_open_market_with_an_ordinary_ungraded_leg_is_still_asked_about(
    pg_engine,
):
    """The half-fix guard. `TTT` is OPEN and carries a null-source leg.

    Excluding on the leg clause ALONE — "band 1 could qualify on that leg" —
    reads correct and silently drops this row into the very gap the band exists
    to close, because band 1 also requires `status = 'resolved'` and `TTT` is
    open. Measured on production before shipping: the leg-only clause selected
    45 tickers, the both-gates clause 53, and the 8 rows between them are this
    shape. The exclusion must test BOTH of band 1's gates or it is not an
    exclusion, it is a new hole.
    """
    early = await _select_early(pg_engine)

    assert "TTT-26SEP15" in early


@needs_postgres
@pytest.mark.asyncio
async def test_the_band_respects_its_own_budget(pg_engine):
    """The cap binds, and it is this band's own — it never borrows from the others.

    gotcha #34: one counter shared across a loop starves the later members. The
    two bands above are pinned to sum to exactly the cycle budget, so this band
    has to be additive or it would silently shrink them.
    """
    early = await _select_early(pg_engine, limit=1)

    # Soonest-due first, so the one ticket goes to `HHH` (an hour ago), not to
    # the ship specimen `NNN` (an hour from now). Asserting the ORDER rather
    # than the name keeps this a budget test: it was `== ["NNN-26SEP14"]` while
    # `HHH` was excluded by status, and that made it quietly double as an
    # ordering test that the #6012 amendment would have reddened for the wrong
    # reason.
    assert len(early) == 1
    assert early == (await _select_early(pg_engine))[:1]
    assert await _select_early(pg_engine, limit=0) == []


# ---------------------------------------------------------------------------
# #7857 — BAND 4: the venue settled it YEARS before its own end date
# ---------------------------------------------------------------------------
#
# THE READER-VISIBLE SHIP. `/futures/112815` "Next Fed rate hike?" served a 95%
# hero, "Resolves Dec 31, 2027" and a live chart over a question Kalshi answered
# `yes` on 2026-09-16T19:08:29Z. Measured on production 2026-09-21 by running the
# SHIPPED band-3 clause against that row: every gate passes except the ceiling,
# which it misses by 466 days.
#
# WHY NO OTHER BAND WAS COMING. The venue RETIRED the `FEDHIKE` series into
# successor `KXFEDHIKE` (read live per notice 26/27: `/markets?series_ticker=
# FEDHIKE` returns 0 markets in EVERY status; `/markets?series_ticker=KXFEDHIKE`
# returns the three finalized rungs with their market and event tickers
# unchanged). Discovery and polling key on the SERIES, so `futures_markets.status`
# never became `'resolved'` and bands 1-2 are blind to it — gotcha #33 one step
# on. The grader, though, knocks on `GET /events/{ticker}` with the EVENT ticker,
# which is what we store, and `/events/FEDHIKE` still answers **200** with the
# three finalized markets. The door was never shut; only the band that uses it
# could not see the row. That is why this fix is a selection clause and not a
# poller change.


async def _select_longdated(engine, limit: int = 50, cursor: str = ""):
    from app.tasks.backfill_winners import (
        _select_kalshi_early_settled_longdated_tickers,
    )

    async with engine.connect() as conn:
        return await _select_kalshi_early_settled_longdated_tickers(
            conn, limit, cursor
        )


@needs_postgres
@pytest.mark.asyncio
async def test_a_ladder_the_venue_settled_years_early_is_selected(pg_engine):
    """THE SHIP. The specimen's shape reaches a band, and it is this one.

    `L4A-28JAN01` is market 112815's shape: open, dated 466 days out, three legs
    carrying the venue's tier-3 stamp and not one of them a winner.
    """
    longdated = await _select_longdated(pg_engine)

    assert "L4A-28JAN01" in longdated


@needs_postgres
@pytest.mark.asyncio
async def test_the_specimen_is_invisible_to_every_other_band(pg_engine):
    """The control that makes the arm above mean anything.

    If any other band could already see this row, the ship is unnecessary and
    every assertion in this section is vacuous. Bands 1 and 2 are asked with a
    budget big enough that only their WHERE clauses can exclude it, and band 3
    with its own.
    """
    fresh, tail = await _select(pg_engine, limit=2000, cursor="")
    early = await _select_early(pg_engine, limit=2000)

    assert "L4A-28JAN01" not in fresh, "band 1 needs status='resolved'"
    assert "L4A-28JAN01" not in tail, "band 2 needs status='resolved'"
    assert "L4A-28JAN01" not in early, "band 3's ceiling is what this ship inverts"


@needs_postgres
@pytest.mark.asyncio
async def test_band_three_and_band_four_are_disjoint_in_both_directions(pg_engine):
    """gotcha #34 + gotcha #43 — neither band may take the other's ticker.

    Both directions, because one is not evidence of the other: a band 4 that
    accidentally widened to band 3's population would still pass "band 3 does not
    hold L4A". `QQQ-26DEC31` is the corpus's pre-existing row asserting band 3
    refuses a far-future market; it is band 4's by construction, and that pairing
    is the ship stated in one line.
    """
    early = set(await _select_early(pg_engine, limit=2000))
    longdated = set(await _select_longdated(pg_engine, limit=2000))

    assert not (early & longdated), (
        f"the bands overlap on {sorted(early & longdated)} — one cycle would ask "
        "the venue about the same ticker twice and the budgets stop being additive"
    )
    # ... and neither is empty, or "disjoint" is true for a band that selects
    # nothing at all.
    assert early and longdated
    assert "QQQ-26DEC31" in longdated
    assert "QQQ-26DEC31" not in early


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,why",
    [
        ("L4X-28JAN01", "a leg is already a winner — we hold the venue's answer"),
        ("L4Y-28JAN01", "no tier-3 leg — nothing says the venue settled any of it"),
        ("L4Z-28JAN01", "not Kalshi"),
        ("L4R-28JAN01", "resolved with an ordinary ungraded leg — band 2 owns it"),
    ],
)
async def test_band_four_refuses_what_it_must(pg_engine, ticker, why):
    """Band 3's refusals, carried into band 4 rather than re-derived.

    The limit is deliberately larger than the corpus so a refusal can only be the
    WHERE clause and never the budget.
    """
    longdated = await _select_longdated(pg_engine, limit=2000)

    assert ticker not in longdated, why


@needs_postgres
@pytest.mark.asyncio
async def test_the_cursor_walks_forward_and_never_repeats(pg_engine):
    """The load-bearing arm — this is why the band is a cursor, not a date sort.

    A market leaves this population only when a leg is graded a WINNER, so a
    ladder the venue has settled only NOes on is permanent. Under `ORDER BY
    resolution_date ASC LIMIT n` such a row would head every cycle for ever and
    everything behind it would starve. Walking the whole population one page at a
    time is the property that makes the band drain; measured on production
    2026-09-21, 1,190 tickers at 50/cycle is a full sweep in ~12 h.
    """
    everything = await _select_longdated(pg_engine, limit=2000)
    assert len(everything) >= 3, "corpus too small to prove a walk"

    page_one = await _select_longdated(pg_engine, limit=2, cursor="")
    page_two = await _select_longdated(pg_engine, limit=2, cursor=page_one[-1])

    assert page_one == everything[:2]
    assert page_two == everything[2:4]
    assert not set(page_one) & set(page_two), "the cursor re-served a ticker"


@needs_postgres
@pytest.mark.asyncio
async def test_the_sweep_runs_dry_at_the_end_so_the_caller_can_wrap(pg_engine):
    """An exhausted cursor returns EMPTY, which is the caller's wrap signal.

    Without this the band walks to `Z` and stops asking for ever, and a market the
    venue settles next month is never revisited. The caller's `elif` deletes the
    key on exactly this result.
    """
    everything = await _select_longdated(pg_engine, limit=2000)

    assert await _select_longdated(pg_engine, cursor=everything[-1]) == []
    assert await _select_longdated(pg_engine, cursor="ZZZZZZZZ") == []


@needs_postgres
@pytest.mark.asyncio
async def test_the_band_respects_its_own_budget_and_zero_means_zero(pg_engine):
    """gotcha #34 again: band 4 is additive, never a borrower.

    `limit=0` returning `[]` without touching the server is what lets the budget
    be turned off in an incident without the statement running at all.
    """
    everything = await _select_longdated(pg_engine, limit=2000)

    assert await _select_longdated(pg_engine, limit=1) == everything[:1]
    assert await _select_longdated(pg_engine, limit=0) == []


# ---------------------------------------------------------------------------
# #7870 — BAND 5, the status-sync band, against the same real server
#
# WHY THIS SECTION EXISTS AT ALL, stated plainly because the first presentation
# of #7870 was BLOCKED for want of it (CERT-3263, 2026-09-21 23:08Z).
#
# That change added the status write — `all_terminal(venue statuses)` ⇒ flip
# `futures_markets.status` to `resolved` — and twelve unit tests which stubbed
# every selector and force-fed the ticker in. They proved the write and said
# NOTHING about who gets asked, and the answer was: not the ship's own specimen.
# Market 112815 `FEDHIKE` was graded by #7857's band 4, and being graded is
# precisely what evicts a market from band 4. On production the morning after,
# the row read `status='open'`, 6 legs, 3 winners, all `api_settlement` — and no
# selector in the product could name it. A correct write on an unreachable row.
#
# So every arm below is asked through the SHIPPED SELECTOR against a real
# PostgreSQL. A fake session answering "any statement mentioning
# futures_markets" with a canned list cannot fail any of them.
#
# ## what production says, so the corpus is not invented
#
# A CENSUS of the band's entire population — not a sample — taken 2026-09-21
# through `/api/admin/db-query` for membership and
# `GET /events/{ticker}?with_nested_markets=true` for the venue, all 736 rows
# probed, zero errors:
#
#   * the band's population is **736** tickers, 1:1 with markets, every one of
#     them `status='open'`;
#   * **13** are all-terminal at the venue and flip. `FEDHIKE` is one, and it
#     sorts FIRST — running the shipped statement with a cold cursor returns it
#     as row 1 of 50, so the specimen is reached on the first cycle after this
#     ships, not eventually;
#   * **298** are mixed — a settled rung on a live ladder, e.g.
#     `KXNFLWINSWEEK-26W8` at 62 finalized + 180 active — and are correctly HELD;
#   * **425** answer 200 with no markets at all and are correctly HELD, because
#     `all_terminal([])` is False on purpose: an absence is not a settlement
#     (gotcha #53).
#
# 13 of 736 is the point of the `mixed`/`empty` majority, not a disappointment:
# the band asks, and the venue — never the band — settles.
# ---------------------------------------------------------------------------


async def _select_status_sync(engine, limit: int = 50, cursor: str = ""):
    from app.tasks.backfill_winners import _select_kalshi_status_sync_tickers

    async with engine.connect() as conn:
        return await _select_kalshi_status_sync_tickers(conn, limit, cursor)


@needs_postgres
@pytest.mark.asyncio
async def test_the_row_whose_grade_landed_and_whose_status_did_not_is_selected(
    pg_engine,
):
    """THE SHIP, and the exact thing CERT-3263 found unreachable.

    `L4X-28JAN01` is `FEDHIKE` as production held it the morning after band 4
    graded it: open, long-dated, an authoritative winner on a leg, and a page
    still rendering a live hero over an answered question. `PPP-26SEP14` is the
    same defect on a short-dated market, so the band is not secretly keyed on
    the long-dated ceiling band 4 uses.
    """
    selected = await _select_status_sync(pg_engine, limit=2000)

    assert "L4X-28JAN01" in selected, (
        "the FEDHIKE shape — graded by band 4, evicted from band 4 by that very "
        "grade, status never flipped — must be reachable by SOME band"
    )
    assert "PPP-26SEP14" in selected


@needs_postgres
@pytest.mark.asyncio
async def test_the_specimen_is_invisible_to_all_four_older_bands(pg_engine):
    """The control without which the arm above proves nothing.

    If any pre-existing band could already reach `L4X`, then #7870 needed no new
    selector and every assertion in this section is vacuous. Each band is asked
    with a budget far larger than the corpus, so a miss can only be its WHERE
    clause and never its limit.
    """
    fresh, tail = await _select(pg_engine, limit=2000, cursor="")
    early = await _select_early(pg_engine, limit=2000)
    longdated = await _select_longdated(pg_engine, limit=2000)

    for band, rows, why in [
        ("band 1", fresh, "requires status='resolved' — the column that is wrong"),
        ("band 2", tail, "requires status='resolved' — the column that is wrong"),
        ("band 3", early, "requires NOT EXISTS(is_winner IS TRUE)"),
        ("band 4", longdated, "requires NOT EXISTS(is_winner IS TRUE)"),
    ]:
        assert "L4X-28JAN01" not in rows, f"{band} {why}"
        assert "PPP-26SEP14" not in rows, f"{band} {why}"

    # ... and none of them is empty, or "invisible" is true of a band that
    # selected nothing at all (gotcha: a vacuous control).
    assert fresh and tail and early and longdated


@needs_postgres
@pytest.mark.asyncio
async def test_band_five_is_disjoint_from_every_other_band_both_directions(
    pg_engine,
):
    """gotcha #34 + gotcha #43 — five bands, one cycle, additive budgets.

    Both directions and all four pairings, because none is evidence of another:
    a band 5 that had quietly widened into band 3's population would still pass
    "band 3 does not hold L4X". The disjointness is structural — `status <>
    'resolved'` against bands 1/2, `EXISTS(authoritative winner)` against bands
    3/4 — and this arm is what stops a later edit making it merely true today.
    """
    fresh, tail = await _select(pg_engine, limit=2000, cursor="")
    early = set(await _select_early(pg_engine, limit=2000))
    longdated = set(await _select_longdated(pg_engine, limit=2000))
    status_sync = set(await _select_status_sync(pg_engine, limit=2000))

    for name, other in [
        ("band 1", set(fresh)),
        ("band 2", set(tail)),
        ("band 3", early),
        ("band 4", longdated),
    ]:
        overlap = status_sync & other
        assert not overlap, (
            f"band 5 overlaps {name} on {sorted(overlap)} — one cycle would ask "
            "the venue about the same ticker twice and the budgets stop being "
            "additive"
        )

    assert status_sync and early and longdated and fresh and tail


@needs_postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker,why",
    [
        (
            "FGG-26SEP10",
            "resolved AND authoritatively graded — the status already agrees "
            "with the grade, so there is nothing for this band to fix",
        ),
        (
            "SSY-26SEP14",
            "its winner is a tier-1 `all_losers` GUESS, not the venue's word — "
            "this band must not re-ask the venue about our own inferences",
        ),
        (
            "L4A-28JAN01",
            "no winner at all — we hold no answer, so this is band 4's work "
            "and taking it here would break the budgets",
        ),
        (
            "L4Y-28JAN01",
            "no winner and no tier-3 leg — nothing says the venue settled any "
            "part of it",
        ),
        (
            "JJJ-26SEP14",
            "open with no venue settlement anywhere — the clause that keeps "
            "this band off ordinary not-yet-played markets",
        ),
    ],
)
async def test_band_five_refuses_what_it_must(pg_engine, ticker, why):
    """The limit is far larger than the corpus, so a refusal is the WHERE clause
    and never the budget."""
    selected = await _select_status_sync(pg_engine, limit=2000)

    assert ticker not in selected, why


@needs_postgres
@pytest.mark.asyncio
async def test_a_polymarket_row_of_the_same_shape_is_not_this_bands_business(
    pg_engine,
):
    """The source clause. The status write this band feeds reads Kalshi's own
    nested market statuses, so selecting a Polymarket row would send a ticker to
    a grader that cannot answer for it."""
    selected = await _select_status_sync(pg_engine, limit=2000)

    assert not [t for t in selected if t.startswith("SSS-")]
    assert not [t for t in selected if t.startswith("L4Z-")]


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_authority_clause_lets_our_own_guess_into_the_band(
    pg_engine,
):
    """The strawman for the clause that has no other witness (gotcha #43).

    Executes the band's statement with `AND COALESCE(fo.resolution_source,'') IN
    (…)` DELETED, against the same seeded server, and asserts the row the shipped
    clause refuses walks straight in. Without this arm the authority clause could
    be removed and every other test in this section would still pass — which is
    the failure mode that produced CERT-3263 in the first place, one layer down.
    """
    mutated = text("""
        SELECT fm.external_id
        FROM futures_markets fm
        WHERE fm.source = 'kalshi'
          AND fm.status <> 'resolved'
          AND fm.external_id > ''
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo
              WHERE fo.market_id = fm.id
                AND fo.is_winner IS TRUE
          )
        GROUP BY fm.external_id
        ORDER BY fm.external_id ASC
        LIMIT 2000
    """)
    async with pg_engine.connect() as conn:
        widened = [r[0] for r in (await conn.execute(mutated)).all()]

    shipped = await _select_status_sync(pg_engine, limit=2000)

    assert "SSY-26SEP14" in widened, (
        "the harness is not running the statement this test thinks it is"
    )
    assert "SSY-26SEP14" not in shipped
    assert set(widened) - set(shipped) == {"SSY-26SEP14"}, (
        "the authority clause should differ from the widened shape on exactly "
        "the guess-graded row and nothing else"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_dropping_the_status_clause_steals_band_ones_rows(pg_engine):
    """The second strawman: the clause that keeps the band off resolved markets.

    Without it the band re-asks about everything bands 1 and 2 already own, the
    budgets stop being additive, and the disjointness arm above becomes the only
    thing standing between us and a doubled venue bill.
    """
    mutated = text("""
        SELECT fm.external_id
        FROM futures_markets fm
        WHERE fm.source = 'kalshi'
          AND fm.external_id > ''
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo
              WHERE fo.market_id = fm.id
                AND fo.is_winner IS TRUE
                AND COALESCE(fo.resolution_source, '') IN
                    ('api_settlement', 'clob_authoritative', 'clob_field_repair',
                     'clob_never_graded', 'clob_ordinal', 'datagolf_settlement',
                     'settlement_sync')
          )
        GROUP BY fm.external_id
        ORDER BY fm.external_id ASC
        LIMIT 2000
    """)
    async with pg_engine.connect() as conn:
        widened = [r[0] for r in (await conn.execute(mutated)).all()]

    shipped = await _select_status_sync(pg_engine, limit=2000)

    assert "FGG-26SEP10" in widened
    assert "FGG-26SEP10" not in shipped
    assert set(shipped) < set(widened)


@needs_postgres
@pytest.mark.asyncio
async def test_band_five_cursor_walks_forward_and_never_repeats(pg_engine):
    """The load-bearing arm, and the reason this band is a cursor and not a sort.

    A member leaves this population only when its status flips, and the census
    says 723 of 736 never will — the venue has not finished them. Under any
    date or score ordering the same permanent head would be re-probed every
    cycle for ever and the 13 rows that need the work would be reached only if
    they happened to sort early. Walking the alphabet one page at a time is what
    makes the band drain.
    """
    everything = await _select_status_sync(pg_engine, limit=2000)
    assert len(everything) >= 2, "corpus too small to prove a walk"

    page_one = await _select_status_sync(pg_engine, limit=1, cursor="")
    page_two = await _select_status_sync(pg_engine, limit=1, cursor=page_one[-1])

    assert page_one == everything[:1]
    assert page_two == everything[1:2]
    assert not set(page_one) & set(page_two), "the cursor re-served a ticker"


@needs_postgres
@pytest.mark.asyncio
async def test_band_five_sweep_runs_dry_at_the_end_so_the_caller_can_wrap(pg_engine):
    """An exhausted cursor returns EMPTY — the caller's wrap signal.

    Without the wrap the band walks to `Z` and stops asking for ever, and a
    market the venue settles next month is never revisited. The caller's `elif`
    deletes the Redis key on exactly this result.
    """
    everything = await _select_status_sync(pg_engine, limit=2000)

    assert await _select_status_sync(pg_engine, cursor=everything[-1]) == []
    assert await _select_status_sync(pg_engine, cursor="ZZZZZZZZ") == []


@needs_postgres
@pytest.mark.asyncio
async def test_band_five_respects_its_own_budget_and_zero_means_zero(pg_engine):
    """gotcha #34 once more: band 5 is additive, never a borrower.

    `limit=0` returning `[]` WITHOUT the statement running is what lets the
    budget be turned off in an incident without touching the server.
    """
    everything = await _select_status_sync(pg_engine, limit=2000)

    assert await _select_status_sync(pg_engine, limit=1) == everything[:1]
    assert await _select_status_sync(pg_engine, limit=0) == []
