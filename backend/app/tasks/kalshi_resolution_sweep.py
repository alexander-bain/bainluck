"""The Kalshi resolution-window sweep — the repair, in the app, on a beat.

CAL-P998 / D47. Moved verbatim out of
``backend/scripts/backfill_kalshi_resolution_window.py``; that script is now the
attended CLI over this module and restates nothing. The move is what makes the
last open line of #2771 buildable:

    > **The sweep is scheduled, not attended.** The population refills daily; a
    > one-off cannot hold it. That half is NOT in this branch.

A Celery task cannot import from ``scripts/`` — it is not on the dyno's path —
so as long as the repair lived there the only way to run it was for a human to
run it, and the measurement says nobody did: 5,143 sealed rows on 2026-09-03
05:00Z, **5,137** at 22:0xZ the same day. The population is not draining, and
every one of those rows renders a dead last-trade price as a live probability
the moment the venue finalizes it (gotcha #33, #2660's card).

WHAT THE SWEEP IS FOR, in one sentence: settled-at-the-venue is a fact
regardless of what date we are holding, and the row we hold must converge onto
the venue's ``close_time`` rather than sit forever on its legal backstop.

Everything about the predicate, the ordering, the retention floor and the
zero-yield discipline is documented at its definition below and was ratified by
CERT-766 / CAL-P992 — none of it is re-argued here, because none of it changed
in this move. What is NEW in this module is only :func:`run_sweep`: the bound,
unattended entry point the beat calls, and the terminal truth it returns.

CAL-P1019 / #2722 — THE SWEEP NOW READS THE VENUE'S STATUS, NOT ONLY ITS DATES.
Every candidate's event is already fetched with its nested markets, and every
leg of that payload carries the venue's own ``status``. It was being discarded.
That is the only signal that reaches the 20% of the settled cohort Kalshi
finalises EARLY — measured at the venue 2026-09-02, 10 of 49 sampled settled
markets still hold a FUTURE ``close_time``, so no date field and no date
predicate can ever select them, and the row goes on claiming to be open. The
write is at :data:`UPDATE_SQL`: ``status`` and ``settled_at``, on the venue's
word only, and never a grade (#1852's line is unchanged).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import text

# `KalshiAPIService` — NOT `KalshiAPIClient`, which has never existed in
# `app.services.kalshi_api`. CERT-766 caught the wrong name as an ImportError
# raised before argparse ran, so the script could not select a row, let alone
# write one, and the catch-up this whole ship depends on was a no-op.
from app.services.kalshi_api import KalshiAPIService
from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE
from app.utils.kalshi_resolution_window import (
    derive_resolution_window,
    derive_venue_settlement,
    derive_venue_void,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

# The band's calendar. Reused rather than restated: this is the SAME Eastern
# reading the ticker parser uses, so the day the band asks for and the day the
# ticker names cannot drift apart into a second implementation.
from app.utils.market_identity import eastern_game_date

#: What ONE unattended beat run may touch.
#:
#: 500 is the limit every attended run of this repair has used (CAL-P989's
#: catch-up, CAL-P992's re-runs), so the beat inherits a batch size whose venue
#: cost and wall time are already observed rather than picking a fresh one on
#: the day it becomes unattended. At 500/day against the 6,302 rows eligible on
#: 2026-09-03 the population is reached in ~13 runs — and because the ordering
#: is `updated_at ASC` and every write refreshes that stamp, the sweep rotates
#: rather than re-reading the same head (the starvation CAL-P992 measured).
SWEEP_BATCH_LIMIT = 500

#: Concurrent venue reads. Matches the attended default; Kalshi's rate limit has
#: never been the binding constraint at this width and a beat is not the place
#: to find out where it is.
SWEEP_CONCURRENCY = 6

#: How far back the played-game band reaches, in days — #3284 / CAL-P1016.
#:
#: It is `PROVABLY_PURGED_AGE_DAYS`, READ and not retuned (the same discipline
#: #3257 kept on the sibling drain). The band exists to rank rows the venue can
#: still answer for, and beyond this age the venue answers for nothing, so a
#: wider band would only promote rows that cannot be written. It is deliberately
#: the same constant the purge floor already uses rather than a second number
#: that could drift away from it.
PAST_EVENT_BAND_DAYS = PROVABLY_PURGED_AGE_DAYS

#: How far back the EVENT-DRIVEN arm looks for finished games — #4655.
#:
#: Six hours, and the number is a re-check budget rather than a reach. A game's
#: legs are selected the moment our own event goes `completed` and stay selected
#: until the venue finalizes them and the write drops them out, so the window is
#: "how long do we keep asking", not "how far back do we sweep". Six hours
#: covers the measured gap on the specimen (our final 03:26:32Z, Kalshi's
#: settlement 03:28:38Z — two minutes) with three orders of magnitude of slack
#: for a venue that settles late, and it bounds the population: measured on
#: production 2026-09-10 05:35Z, 29 events / 603 open legs in six hours, against
#: the 12,244 rows the population sweep is walking at 500 a night.
RECENT_FINAL_WINDOW_HOURS = 6

#: How far back the LIVE arm's band reaches, in hours — #5024.
#:
#: Bounded for one reason only: a row stuck in `status='live'` long after its
#: game ended would otherwise sit in this selection forever, asking the venue
#: every 10 minutes about a game nobody is playing. 12 hours clears the longest
#: real live windows we carry (a Test-match day, a five-set match, a full esports
#: series) with slack, against a measured 2026-09-11 02:4xZ population whose
#: OLDEST live event had started 3h45m earlier. It is a leash on stale liveness,
#: not a claim about how long games last.
LIVE_EVENT_WINDOW_HOURS = 12

#: How long a LIVE event's leg may go untouched by the price poller before the
#: row is treated as one the venue has stopped serving — #5024, second reach.
#:
#: WHAT THIS SCREEN ASSERTS, AND WHY IT IS CAUSAL RATHER THAN CIRCUMSTANTIAL.
#: `FuturesOutcome.last_updated` is the unconditional TOUCH stamp — the model
#: says so out loud ("poller alive", as against `price_changed_at`'s "price
#: fresh") — so it advances on every price-writing poll whether or not the number
#: moved. Kalshi drops a finalized market from the scan the live poller reads, so
#: the stamp stops advancing the moment the venue stops trading it. A live game's
#: still-traded market is touched every beat; a decided one is not touched again,
#: ever. That is a fact about the VENUE's listing, not an inference from a price.
#:
#: 5 MINUTES AGAINST A MEASURED 2-MINUTE CADENCE. Production 2026-09-20 22:1xZ,
#: all 328 live open KX rows: 262 touched inside 3 minutes, then a tail — 16 in
#: [3,5), 20 in [5,10), 7 in [10,15), 12 in [15,30), 11 past 30. The healthy bulk
#: and the tail are separated by that gap, and 5 minutes is two missed beats of
#: slack so ordinary poll jitter cannot manufacture a candidate.
#:
#: THE TOUCH AGE IS THE TIME SINCE THE VENUE CLOSED THE MARKET, MEASURED. This
#: is the evidence that the screen reads the settlement rather than correlating
#: with it. 2026-09-20 22:34Z, the 16 oldest rows this screen takes that the
#: empty book does not, each asked at the venue by ticker and its `close_time`
#: read back::
#:
#:     ticker                          touch age   venue verdict   closed for
#:     KXNFL1HTEAMTOTAL-26SEP20SEAARI    20 min    all-terminal      20 min
#:     KXNFL1H-26SEP20SEAARI             19 min    all-terminal      20 min
#:     KXNFL1HSPREAD-26SEP20WASDAL       16 min    all-terminal      17 min
#:     KXNFL3QSPREAD-26SEP20JACDEN       13 min    all-terminal      14 min
#:
#: The two columns agree to the poll cadence on all ten all-terminal rows. The
#: six that were still open are the shape you would predict — markets that stay
#: open until the whistle and are simply quiet (4th-quarter BTTS, safety,
#: defensive touchdown) — and each costs exactly one venue question and no
#: write, because `derive_venue_settlement` still decides.
#:
#: MEASURED PRECISION — 54% AND 63% ON TWO INDEPENDENT SAMPLES, NOT THE
#: SUSPENDED ARM'S 87%, AND THE NUMBERS ARE STATED BECAUSE THEY ARE LOWER.
#: 24 selected rows at 22:19Z: 13 all-terminal. The 16 above at 22:34Z: 10. A
#: CONTROL of 8 rows touched inside the minute returned 0 all-terminal, so the
#: screen is doing real work rather than selecting a slate at random.
#:
#: WHY NOT REUSE THE SUSPENDED ARM'S FROZEN-BOOK PREDICATE, WHICH IS ALREADY
#: WRITTEN. Measured on this population rather than inherited: on live events it
#: selects 218 of 328 rows at 25% precision (24 asked at the venue, 6
#: all-terminal). Its 87% was measured on SUSPENDED rows, where the game is over
#: and every book is a relic; during play a wide book beside a moved probability
#: is what a live market NORMALLY looks like. Widening on it would spend four
#: reads in five on healthy markets. This screen takes 50 rows instead of 218 and
#: is right about twice as often.
#:
#: THE RESIDUAL, NAMED. The aggregate is per MARKET — a row is stale only when
#: NO leg has been touched — so one still-served leg keeps a part-settled market
#: fresh and out of this band. That is deliberate (`derive_venue_settlement`
#: refuses a part-settled event anyway, so selecting it would buy a read and no
#: write) but it does mean an event whose venue keeps quoting a dormant leg is
#: reached by the completed arm at the whistle, not by this one.
LIVE_STALE_TOUCH_MINUTES = 5

#: How far back the SUSPENDED arm's band reaches, in hours — #5596.
#:
#: 14 days, and the number is a leash rather than a claim. A `suspended` event
#: never reaches a terminal status on its own (#5881: 59 finished MLB games have
#: been frozen there since Sep 2), so unlike `completed_at` there is no clock
#: ticking that would retire a row from this band by itself — without a floor a
#: stuck event would be re-asked at the venue every 10 minutes forever. 14 days
#: covers the whole live population with slack: measured on production
#: 2026-09-14 05:17Z the OLDEST suspended open KX market commenced 2026-09-03
#: 18:50Z, ten days back.
SUSPENDED_EVENT_WINDOW_HOURS = 336

#: How far a leg's stored probability may sit from the midpoint of its OWN
#: two-sided book before the row is treated as frozen — #5596.
#:
#: This is the second freeze signature, and it is the complement of #5024's
#: empty book rather than a variation on it. When Kalshi finalizes a market the
#: book can be left behind in either of two states, and which one we keep is an
#: accident of when the last poll landed: BOTH sides gone (`yes_bid = 0 AND
#: yes_ask = 1`, #5024's screen), or the last live two-sided quote frozen in
#: place while `current_probability` has already run to the settlement tail. The
#: second is invisible to every existing screen precisely because it looks
#: healthy — a tight, plausible book.
#:
#: The row REFUTES ITSELF, so no ground truth is needed to select it: market
#: 60790861 leg `KXEPLSCORE-26SEP12SUNARS-SUN0ARS2` served `current_probability`
#: 0.99 against its own `0.1300 / 0.1400` book, whose midpoint agrees with both
#: `opening_probability` 0.135 and `current_american_odds` +641. One of those two
#: numbers is a lie and the row says so unaided.
#:
#: AND THE LIE IS THE BOOK, NOT THE 0.99 — worth stating, because the obvious
#: reading of "99% against a 13% book" is that the 99% must be withdrawn. Asked at
#: the venue, that leg (`Arsenal wins 2-0`) settled **`result='yes'`**, and #5596's
#: own headline specimen settled the same way (`KXJLEAGUEGAME-26SEP12MACMAR-TIE`,
#: `result='yes'` — the J-League match really did end a draw). The probability had
#: converged on the truth; the two-sided quote beside it is the relic, frozen by
#: the last poll before close. So this arm exists to stop the pair being presented
#: as a LIVE price, not to suppress the number — which is also why it is safe for
#: the write to leave every price exactly where it is.
#:
#: 0.10 measured, not chosen: over the 30 sampled suspended markets carrying this
#: signature on 2026-09-14 05:16Z, 26 (87%) were `finalized` at the venue. It is a
#: SCREEN, NOT A VERDICT — `derive_venue_settlement` still decides, and the other
#: 4 cost one question and no write (`UPDATE_SQL`'s `ELSE status`).
FROZEN_BOOK_GAP = 0.10

#: What ONE run of the event-driven arm may touch.
#:
#: 200 against a measured 603-leg six-hour population, ordered freshest-final
#: first, so the newest finished game is always inside the first batch — which
#: is the only ordering that can meet #4655's bar (a finished game's tickers
#: reached within 30 minutes of the venue settling). It is deliberately NOT
#: sized to drain the window in one run: the arm runs every 10 minutes, so the
#: window drains at 1,200 legs/hour against a population that refills at the
#: rate games finish.
RECENT_FINAL_BATCH_LIMIT = 200

#: What ONE run of the ALREADY-RESOLVED void arm may ask the venue — #7035,
#: CERT-3324's required repair.
#:
#: 🔴 WHY THIS ARM HAD TO EXIST AT ALL, and the reason is a reachability failure
#: rather than a tuning one. Both selections above open with `fm.status = 'open'`
#: — that screen IS the drain, and it is right for them. But the fixture #7035
#: was filed for is already `resolved`: measured on production 2026-09-23 04:2xZ,
#: all four Levante–Bilbao legs (60481773, 60636796, 60636798, 60636800) read
#: `status='resolved'` with `settled_at` set, on an event still `suspended`, with
#: `venue_voided` NULL. The sweep marked them over and never recorded WHY, so the
#: page has nothing to say but "No result reported". No batch size reaches them:
#: the capture ran on a population its own selection excluded.
#:
#: 60 AGAINST A MEASURED 489. Production, same minute, the exact predicate below:
#: 489 rows over 324 events in the 14-day band, 0 of them legless. At 60 a run
#: and a 10-minute beat the standing population is drained inside two hours, and
#: it does not refill at that rate — a postponement is rare against the rate
#: games finish. It is deliberately small: this arm rides #4655's beat and must
#: never be the reason that beat misses its 30-minute bar.
RESOLVED_VOID_BATCH_LIMIT = 60

#: The already-resolved void selection — #7035.
#:
#: FOUR SCREENS, AND EACH ONE IS A MEASUREMENT RATHER THAN A GUESS.
#:
#: 1. `e.status = 'suspended'` is what separates a postponed fixture from a
#:    played one, and it is the screen that REFUSES THE PLAYED CONTROL the cert
#:    asked for. Same minute, same band: `completed` events hold 11,512 resolved
#:    rows with a graded leg and **2,843 with none** — that second bucket is
#:    "played, we simply have not graded it yet", it is identical to this arm's
#:    population on every other axis, and stamping one of them `venue_voided`
#:    would put "no result was ever reported" on a game that WAS played. The
#:    event status is the only thing that tells them apart before the venue is
#:    asked, so it is a screen and not an ordering.
#: 2. The ungraded test, `NOT EXISTS (... is_winner IS TRUE)`: a row we have
#:    already graded had its result reported, so there is nothing to capture.
#: 3. The legs test, `EXISTS (...)`: without it a row with NO outcomes satisfies
#:    the ungraded test vacuously, and "we never priced this" is not "nobody
#:    reported a result" (#5024's own note, one screen up, for the same reason).
#:    Measured 0 such rows today; it is here because 0 is a reading, not a law.
#: 4. THE IDEMPOTENCY SCREEN, and it is load-bearing rather than hygiene. 🔴 A
#:    14-ticker venue sample of this exact population answered **4 voided / 10
#:    graded** — so 71% of the selection is a row the venue WILL name a result
#:    for, which this arm must refuse and must then never ask about again. With
#:    no stamp those ~350 rows would be re-read every 10 minutes for 14 days.
#:    That is precisely the jam CAL-P998 measured one screen below: a row that
#:    gets no write never rotates, and 500 of them are enough to wedge a beat.
#:    So a terminal answer is RECORDED either way — `venue_voided` when the venue
#:    declined to grade, `venue_void_checked_at` when it did grade — and both
#:    spellings drop the row out of this selection permanently. A NON-terminal
#:    answer is stamped with neither, so a market the venue has not finished is
#:    re-asked, which is the one case that must stay open.
#:
#: The band is `SUSPENDED_EVENT_WINDOW_HOURS`, READ and not retuned — the same
#: 14 days the suspended arm above already reaches over the same population,
#: rather than a second number that could drift away from it.
#:
#: Ordered oldest-commence first: a postponement that has sat unexplained the
#: longest is the one a reader has been staring at the longest.
RESOLVED_VOID_SELECT_SQL = """
    SELECT fm.id, fm.external_id, fm.resolution_date, fm.commence_time,
           fm.market_tier
    FROM futures_markets fm
    JOIN events e ON e.id = fm.event_id
    WHERE fm.source = 'kalshi'
      AND fm.status = 'resolved'
      AND fm.external_id LIKE 'KX%'
      AND fm.market_metadata->>'venue_voided' IS NULL
      AND fm.market_metadata->>'venue_void_checked_at' IS NULL
      AND e.status = 'suspended'
      AND e.commence_time IS NOT NULL
      AND e.commence_time >= :suspended_floor
      AND EXISTS (
            SELECT 1 FROM futures_outcomes fo WHERE fo.market_id = fm.id
      )
      AND NOT EXISTS (
            SELECT 1
              FROM futures_outcomes fo
             WHERE fo.market_id = fm.id
               AND fo.is_winner IS TRUE
      )
    ORDER BY e.commence_time ASC, fm.id ASC
    LIMIT :limit
"""

#: The event-driven selection — #4655.
#:
#: WHY THIS EXISTS BESIDE `SELECT_SQL` RATHER THAN REPLACING IT. The population
#: sweep asks "which rows have I not looked at recently"; this asks "which game
#: just finished". They are different questions and the second one cannot be
#: expressed as an ordering of the first: `updated_at ASC` puts the freshest
#: final LAST, because a game that just finished was being polled until minutes
#: ago and therefore carries the NEWEST stamp in the population. The opener's 61
#: legs were frozen at `updated_at = 00:51:04Z` — newer than thousands of rows
#: ahead of them in the sweep's queue — so no batch size of the population sweep
#: reaches a fresh final in time. That is the whole defect (#4655): both existing
#: arms are population sweeps, and neither is keyed on the event.
#:
#: THE KEY IS OUR OWN EVENT, not a ticker date. `events.completed_at` is the
#: instant an authority told us the game was over, and the legs are already tied
#: to it by `futures_markets.event_id` — verified on the specimen before this was
#: built: all 61 of the opener's legs carry `event_id = 14780138`, whose
#: `completed_at` is 2026-09-10 03:26:32Z. A ticker-date band cannot do this job
#: (it resolves to a DAY, and a Sunday slate finishes across six hours), and
#: `commence_time` cannot either — #2771's 4,954 sealed rows carry the poisoned
#: future backstop there.
#:
#: `status = 'open'` IS THE DRAIN. A leg the venue confirms settled is written to
#: `'resolved'` by `UPDATE_SQL`, so it leaves this select permanently on the run
#: that fixes it. The window therefore self-drains and re-asking is free: a leg
#: still selected an hour after its game ended is a leg the venue has not
#: finalized yet, which is exactly the row we want to keep asking about.
#:
#: `LIKE 'KX%'` mirrors `SELECT_SQL`'s prefix for the same reason it does — the
#: derivation downstream reads Kalshi event tickers and nothing else.
#:
#: THE LIVE ARM — #5024, and the reason `e.status = 'completed'` alone was not
#: enough. Kalshi markets `can_close_early`: "This market will close and expire
#: early if the event occurs." So a question can be DECIDED an hour before the
#: whistle, and keying settlement on our own `completed_at` cannot reach it —
#: not late, but not at all until the game ends.
#:
#: THE DATED SPECIMEN (standing notice 26/27), live SF@LAR 2026-09-11: Kyren
#: Williams scored at 01:20Z; Kalshi closed his leg at 01:20:26Z and finalized it
#: `result='yes'` with `settlement_ts=01:22:33Z`, and finalized the 25 losing
#: legs by 01:45Z. At 02:32Z — 70 minutes later, mid-second-quarter — our row was
#: still `status='open'` and the page drew an open 26-rung ladder summing to
#: 124%, Kyren Williams at 99% and Brock Purdy still listed at 1% to score a
#: touchdown someone else had already scored. Measured over all 48 live-event
#: rows carrying the empty-book signature that minute: 38 were ALL-terminal at
#: the venue, 3 more were terminal-past-dormant-legs, 6 genuinely part-settled
#: and 1 genuinely open — so 41 of 48 were decided and unreachable.
#:
#: WHY THE `EXISTS` AND NOT SIMPLY `e.status = 'live'`. A live game's every leg
#: is a candidate, so the bare predicate would put ~97 rows per NFL night — and
#: on a Sunday slate several hundred — through a venue read every 10 minutes,
#: most of them markets that are still trading normally. `yes_bid = 0 AND
#: yes_ask = 1` is the EMPTY BOOK: both sides gone, which is what a venue leaves
#: behind when it stops trading a market. It is the same signature the reader
#: sees as a stuck 99%/1% ladder, because `_kalshi_yes_probability` falls through
#: an empty book to the last trade. Measured precision on the 48 above: 41/48.
#: It is a screen, not a verdict — the venue read still decides, and a market
#: whose book is merely thin costs one question and no write.
#:
#: FINALS STILL WIN THE BATCH. `completed_at DESC NULLS LAST` sorts every
#: finished game ahead of every live one, so the live arm can only ever consume
#: batch capacity a final did not want. #4655's 30-minute bar is unchanged.
#:
#: THE SUSPENDED ARM — #5596, and the reason the two arms above reach NONE of it.
#: Both are keyed on our own event reaching a terminal-ish status, and a
#: `suspended` event never does. Measured over #5596's whole Kalshi population on
#: 2026-09-14 05:16Z — 51 markets / 114 legs, every one of them `finalized` at the
#: venue (114/114, asked by ticker) — the linked events read `suspended` (44) or
#: `scheduled` (7), `completed_at` NULL on all 51. Run against those ids the
#: completed arm selects 0, the live arm selects 0, and PR #5913's pre-kick-off
#: scope selects 0. Not late: unreachable.
#:
#: WHAT THE READER SEES WITHOUT IT. `Machida Z vs Marinos`, a J-League game that
#: had already been played: `Tie` served at **99%** with both teams at **1%**,
#: over a coherent book naming Marinos the ~70% favourite — three numbers summing
#: to 101% on a page presenting a finished match as live (#5596, filed by ux/1213).
#:
#: WHY `suspended` AND NOT ALSO `scheduled` OR THE UNLINKED ROWS. Precision,
#: measured the same minute by asking Kalshi about 30 markets per bucket carrying
#: the frozen signature: `suspended` **26/30 finalized (87%)**, `scheduled` 7/28
#: (25%), and markets with NO linked event **1/26 (4%)** — 485 of them, nearly all
#: genuinely trading. Widening past `suspended` would spend a venue read every 10
#: minutes, forever, on markets that are perfectly healthy, because a row that is
#: never settled never leaves the selection. The unlinked rows are a real gap
#: (`JOIN events` cannot see them at all) and they are NOT this ship.
#:
#: FINALS STILL WIN, unchanged: a suspended event has `completed_at` NULL, so
#: `NULLS LAST` keeps every one of these behind every genuine final.
RECENT_FINAL_SELECT_SQL = """
    SELECT fm.id, fm.external_id, fm.resolution_date, fm.commence_time,
           fm.market_tier
    FROM futures_markets fm
    JOIN events e ON e.id = fm.event_id
    WHERE fm.source = 'kalshi'
      AND fm.status = 'open'
      AND fm.external_id LIKE 'KX%'
      AND (
            (
              e.status = 'completed'
              AND e.completed_at IS NOT NULL
              AND e.completed_at >= :final_floor
            )
         OR (
              e.status = 'live'
              AND e.commence_time IS NOT NULL
              AND e.commence_time >= :live_floor
              AND (
                    EXISTS (
                          SELECT 1
                            FROM futures_outcomes fo
                           WHERE fo.market_id = fm.id
                             AND fo.current_yes_bid = 0
                             AND fo.current_yes_ask = 1
                    )
                    -- #5024's second reach: the venue has stopped serving this
                    -- market to the price poller. See LIVE_STALE_TOUCH_MINUTES.
                    -- The EXISTS guard is not ceremony — without it a row with
                    -- no legs at all satisfies the NOT EXISTS vacuously, and
                    -- "we have never priced this" is not "the venue dropped it".
                 OR (
                      EXISTS (
                            SELECT 1
                              FROM futures_outcomes fo
                             WHERE fo.market_id = fm.id
                      )
                      AND NOT EXISTS (
                            SELECT 1
                              FROM futures_outcomes fo
                             WHERE fo.market_id = fm.id
                               AND fo.last_updated >= :stale_touch_floor
                      )
                    )
              )
            )
         OR (
              e.status = 'suspended'
              AND e.commence_time IS NOT NULL
              AND e.commence_time >= :suspended_floor
              AND EXISTS (
                    SELECT 1
                      FROM futures_outcomes fo
                     WHERE fo.market_id = fm.id
                       AND (
                             -- #5024's signature: both sides gone.
                             (fo.current_yes_bid = 0 AND fo.current_yes_ask = 1)
                             -- #5596's: a tight two-sided book frozen beside a
                             -- probability that has already run to the tail.
                             -- The row refutes itself; see FROZEN_BOOK_GAP.
                          OR (
                               fo.current_yes_bid > 0
                               AND fo.current_yes_ask < 1
                               AND fo.current_probability IS NOT NULL
                               AND ABS(
                                     fo.current_probability
                                     - (fo.current_yes_bid + fo.current_yes_ask) / 2
                                   ) > CAST(:frozen_gap AS numeric)
                             )
                           )
              )
            )
      )
    ORDER BY e.completed_at DESC NULLS LAST, e.commence_time DESC, fm.updated_at ASC
    LIMIT :limit
"""


def default_session_maker():
    """The session factory both entry points fall back to when none is injected.

    #4699 — THIS MUST BE LOOP-SCOPED, AND IT USED TO BE THE APP'S GLOBAL ENGINE.

    Both entry points are driven by `_tracked_run` -> `run_async` ->
    `asyncio.run(coro)`, which builds a fresh event loop per invocation and
    CLOSES it on return. The module-level `async_session_maker` keeps its pool
    across invocations, so on the second run its pooled connections are bound to
    the first run's dead loop; `pool_pre_ping=True` then pings one on the new
    loop and raises `RuntimeError`.

    Measured on production the night #4655 shipped: `settle_kalshi_recent_finals`
    succeeded on the 07:10Z run — the first after v4395 cycled the dynos, when
    the global pool was empty — and then failed on 07:20Z (80 ms) and 07:30Z
    (8 ms), 0 successes against 3 starts. `app/tasks/base.py` says exactly this
    in `_get_task_engine`'s docstring: it exists for "avoiding the 'attached to a
    different loop' errors when reusing the module-level engine across Celery
    task invocations". The new arm simply did not use it.

    `get_task_session` builds an engine bound to the current loop and disposes
    it in a `finally`. It is called in three bounded places per run — the two
    reads and the one batched write — never per market, so an engine per call is
    cheap at this cadence.

    ONE function rather than the same fallback expression at each call site: the
    two entry points had identical defaults and only one of them was reachable
    often enough to reveal the bug.
    """
    from app.tasks.base import get_task_session

    return get_task_session


@dataclass
class _Leg:
    close_time: Optional[datetime]
    expiration_time: Optional[datetime]
    # #2644 (CAL-P1127). This sweep is the SECOND writer of `resolution_date` —
    # the poller is the first — and both derive it through
    # `derive_resolution_window`. Teaching only the poller would leave the two
    # writers applying different rules to the same column.
    #
    # Stated precisely, because the failure is narrower than "it would revert
    # the fix": the row selector (`resolution_date IS NULL OR resolution_date >=
    # expiration_time`) stops selecting a row once #2644 has pulled its date
    # below the backstop, so a corrected row is not re-stamped. What an untaught
    # sweep WOULD do is stamp the pad on the rows it does still reach — a row
    # with a NULL `resolution_date`, or one the poller has not re-polled since
    # this shipped — leaving them on 2029 until the poller happens to touch
    # them. The write is unconditional (`moved_earlier` is a counter, not a
    # guard), so that is a real write of a known-wrong date, not a no-op.
    #
    # Defaulted so no other construction site has to change.
    expected_expiration_time: Optional[datetime] = None


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


#: A row is a candidate while the date we hold for it is still PROVISIONAL, i.e.
#: while the venue has not yet told us when trading actually stopped.
#:
#: `expiration_time IS NULL` alone — the original marker — is "have I ever touched
#: this row", and CAL-P992 measured what that costs. Kalshi sets `close_time` equal
#: to the backstop while a market is ACTIVE and rewrites it to the settlement
#: instant on finalize. So a row swept while its market was still trading is written
#: with `resolution_date == expiration_time`, which stamps the backstop column and
#: makes the row permanently unselectable — and then the market finalizes and the
#: open-market poll can never re-enumerate it (gotcha #33). The row keeps a future
#: date forever and no run of this script can reach it. Measured on production
#: 2026-09-02: 5,143 `status='open'` rows already sealed this way, five of them
#: (US Open `KXWTASETWINNER` / `KXATPEXACTMATCH` legs) finalized at the venue within
#: an hour of the sweep that sealed them.
#:
#: `resolution_date >= expiration_time` is the provisional test and it is a
#: PROVENANCE read, not a proxy: it is true exactly while `resolution_date` is still
#: a backstop. Once the venue rewrites `close_time`, `resolution_date` moves strictly
#: earlier, the row converges out, and it stays out — the same convergence the old
#: marker gave, keyed on the fact that makes the row done rather than on the fact
#: that we looked at it.
#:
#: `LIKE 'KX%'` rather than `~ '^KX'`: identical semantics for a left-anchored
#: literal prefix, sargable, and executable by the guard in
#: `tests/test_kalshi_resolution_backfill_script_989.py`, which runs this exact
#: string against a seeded table. A regex operator would have made the starvation
#: guard un-runnable, and an un-runnable guard is how the post-LIMIT floor shipped
#: in the first place. (It also excludes 211 legacy non-`KX` rows — all measured as
#: genuinely-future 2027-2032 political/macro markets, so not a dead-card source
#: today; named in #2773 rather than widened here.)
#:
#: ORDERING — `updated_at ASC`, NOT `market_tier ASC`. Tier-first is what the
#: original backlog wanted, but on the provisional population it starves: measured
#: 2026-09-02, tier 1+2 hold 2,951 provisional rows and tier 5 holds 2,038, so a
#: `--limit 500` run ordered by tier never reaches tier 5 at all — and tier 5 is
#: where the settled prop legs live. `updated_at ASC` is not a tie-break dressed up:
#: on a `status='open'` Kalshi row the 2h poller bumps `updated_at` only while the
#: venue still enumerates the market as open, so the moment Kalshi finalizes it the
#: stamp FREEZES (gotcha #33 read forwards). Least-recently-enumerated first is
#: therefore a direct observation of "most likely already settled", and it rotates,
#: so no row can be starved behind a prefix. `commence_time` cannot do this job:
#: 4,954 of the 5,143 sealed rows carry `commence_time = expiration_time`, the same
#: poisoned backstop, so a "has it commenced" gate would have missed all five of the
#: rows that motivated this change.
SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY updated_at ASC NULLS FIRST,
             market_tier ASC NULLS LAST,
             commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

# ---------------------------------------------------------------------------
# The played-game band — #3284 / CAL-P1016
# ---------------------------------------------------------------------------
#
# WHAT THE BEAT'S FIRST UNATTENDED RUN MEASURED (2026-09-05 04:20Z, production,
# `task-metrics?task=kalshi_resolution_window`): 500 candidates, 125 written,
# 121 of those `unchanged` because the venue still reports the backstop, and
# **`newly_past = 4`**. Five hundred venue reads bought four corrected dead
# prices. At a 500-row batch against ~7,000 eligible rows the cycle is ~14
# nights, so a market that finalises just after its slot keeps a live-looking
# price and a fabricated future date for up to a fortnight. That is #2660's card
# ("a golf round that settled five days ago") as a standing mechanism.
#
# WHY `updated_at ASC` ALONE CANNOT FIND THEM. CAL-P992 chose that ordering on
# the argument that the 2h open-market poll bumps `updated_at` only while the
# venue still lists a market, so a frozen stamp detects finalisation. Measured
# 2026-09-05: of 8,879 `status='open'` KX rows only 237 were touched in the last
# 3 hours and 1,428 in the last 26 — the poller's COVERAGE, not the venue's
# listing, dominates the stamp. Four rows sampled from the stale band and
# checked against Kalshi's own API were two genuinely active (2027 midterms,
# Hannover mayor) and two finalised days ago. The stamp does not separate them.
#
# THE SIGNAL THAT DOES is already in the row and gotcha #14 already prefers it
# over `commence_time`: the ticker's own `YYMONDD` segment
# (`app/utils/market_identity.py:ticker_game_date`). `commence_time` cannot do
# this job — 4,954 of the 5,143 sealed rows carry `commence_time` equal to the
# same poisoned backstop (#2771).
#
# MEASURED YIELD, at the venue (12 rows sampled from the band, Kalshi public
# API, 2026-09-05): **8 finalised with a `close_time` months earlier than the
# date we store** — they converge on read — 3 purged/no markets (#2723's
# stranded cohort), 1 genuinely active. ~67% against the beat's measured 0.8%.
#
# IT IS AN ORDER, NEVER A PREDICATE, and the 12th sample is why: `KXMYSLGAME-
# 26SEP04BRUJOH` is a season market whose ticker date is its opener, so a FILTER
# on the band would wrongly promote-and-exclude it while a SORT merely
# mis-orders it. :func:`banded_select_sql` therefore reuses `SELECT_SQL`'s own
# text and rewrites only its ORDER BY — `test_the_band_changes_only_the_order`
# proves the predicate is byte-identical rather than asserting it in prose.
#
# PORTABLE ON PURPOSE. The band is a bounded list of literal day tokens built in
# Python, matched with plain `LIKE`, because the guards for this SQL execute it
# against SQLite and Postgres has no shared regex/`strpos` spelling with it. The
# bound is what makes the list finite: only days the venue can still answer for
# are worth ranking, so the token list is at most `PAST_EVENT_BAND_DAYS` long.

_BAND_MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def past_event_band_tokens(
    now: datetime, *, days: int = PAST_EVENT_BAND_DAYS
) -> list[str]:
    """`LIKE` patterns for every ticker day-stamp whose game has been played.

    Strictly BEFORE today and no older than ``days``. Strictly-before matches
    the measured cohort (604 rows on 2026-09-05) and keeps a game that is being
    played right now out of the band, where it would only spend a venue read to
    be told the backstop again.

    TODAY IS THE VENUE'S DAY, NOT UTC's — #3293 / CAL-P1017, CERT-1939's named
    follow-up, and it is not cosmetic. The ticker's ``YYMONDD`` is a US Eastern
    trading day
    (:func:`app.utils.market_identity.ticker_game_date`), while the beat fires at
    04:20Z. Under EDT that instant is 00:20 ET on the SAME calendar day and the
    two readings agree, which is why the 2026-09-05 measurement could not see
    this. Under EST it is 23:20 ET on the day BEFORE, so a UTC reading of
    "strictly before today" admits the Eastern day still in progress. Measured on
    production 2026-09-05, that day is the *largest* cohort in the whole band —
    785 eligible rows on `26SEP05` against 212 on the finished `26SEP04` — so at
    rank 0 it would fill the entire 500-row batch with games that have not
    finished, and the batch would never reach a played day at all. The band
    would invert into the starvation it was built to end, on 2026-11-01, with no
    code change to blame.

    ``purge_floor`` deliberately stays on the UTC clock: it is an age in absolute
    time, not a position in the venue's calendar.

    Newest first, so the caller can also read the list as the order in which the
    band's days became answerable.
    """
    today = eastern_game_date(now)
    if today is None:
        raise TypeError(
            "past_event_band_tokens needs a datetime to read the venue's day; "
            f"got {type(now).__name__}"
        )
    tokens: list[str] = []
    for back in range(1, max(0, int(days)) + 1):
        d = today - timedelta(days=back)
        tokens.append(f"%-{d.year % 100:02d}{_BAND_MONTHS[d.month - 1]}{d.day:02d}%")
    return tokens


def band_bind_params(tokens: list[str]) -> dict:
    """``{'band_0': '%-26SEP04%', ...}`` — one bind per token, never interpolated.

    The tokens are machine-built from a clock and could not carry an injection
    today, but a SQL string that concatenates values is a habit that outlives
    the day its inputs were safe.
    """
    return {f"band_{i}": tok for i, tok in enumerate(tokens)}


def band_rank_sql(n_tokens: int) -> str:
    """The leading sort key: DAYS SINCE THE GAME, and ``n_tokens`` for the rest.

    Graded rather than binary, and the grading is not a refinement — it is what
    makes the band's head answerable. Measured on production 2026-09-05: under a
    binary rank the band's first 14 rows probed at the venue as 4 convergeable,
    3 still active and **7 purged**, because the inherited `updated_at ASC`
    tie-break sorts the oldest — hence deadest — stamps to the front of the
    band. A random sample from the same band was 8 convergeable of 12. The
    difference is entirely the within-band order.

    :func:`past_event_band_tokens` yields newest-first, so the token's own index
    IS its age in days and one `CASE` expresses both facts. Non-band rows take
    ``n_tokens`` — strictly larger than every band rank, so they follow the
    whole band and their inherited ordering is untouched among themselves.

    ``n_tokens == 0`` yields ``NULL``, not ``0``: an empty band must leave the
    inherited ordering exactly as it was, a `CASE` with no arms is not valid
    SQL, and a bare integer in an ORDER BY is an ORDINAL COLUMN REFERENCE in
    both SQLite and Postgres — `ORDER BY 0` is "term out of range", which is how
    the zero case would have failed in production rather than in a guard.
    """
    if n_tokens <= 0:
        return "NULL"
    arms = " ".join(
        f"WHEN external_id LIKE :band_{i} THEN {i}" for i in range(n_tokens)
    )
    return f"CASE {arms} ELSE {n_tokens} END"


# ---------------------------------------------------------------------------
# The fully-retracted band — #7000
# ---------------------------------------------------------------------------
#
# A SECOND ORDER TERM, ranked BELOW the played-game band and above everything
# else, for the one cohort in this population that NO grading band can ever ask
# about. A market whose every leg carries `ungradeable_result` is invisible to
# all three bands in `backfill_winners`: band 1 excludes retracted legs by name
# ("it is a decision, not a gap"), band 2 requires `status = 'resolved'`, and
# band 3 requires at least one leg carrying an AUTHORITATIVE source — which this
# cohort, by definition, has none of. So if the venue has finalised it, nothing
# in the product will ever find out. This sweep is the only rail that can, and
# until now it ranked them by the inherited `updated_at ASC`, i.e. by the
# poller's coverage.
#
# WHY THE RETRACTION IS EVIDENCE AND NOT NOISE. `repair_kalshi_fabricated_loss`
# writes `ungradeable_result` over a leg that was carrying `api_settlement` and
# nothing else ("Every target leg carries ``api_settlement`` and is a loss"), so
# a retracted leg is a FORMER venue grade: we read a settlement for that exact
# ticker once. The retraction says the venue's `result` was `scalar`/empty at
# that moment, and `resolution_authority` calls it "reversible by evidence and
# by nothing else" — but no rail ever goes back for the evidence. This order
# term is that visit.
#
# MEASURED ON PRODUCTION 2026-09-18 20:45-21:05Z. The cohort is **3,464 open
# families** (4,696 including already-resolved ones), 2,902 of them tier 1-3.
# Probed at Kalshi itself (notice 26/27), 25 tickers drawn pseudo-randomly
# across staleness bands: **3 finalised with a full set of per-leg results**
# (`KXEMMYCOUNT-26WID` 19/19, `KXVOTEPRIMARY-CTPRIMARY01D26LBRO` 9/9,
# `KXPRIMARYMOV-CTPRIMARY01D26` 9/9), the rest genuinely `active` — 2027 NFL and
# NCAAF seeding, December hurricanes, midterms. So the cohort's yield is ~12%,
# against **the beat's own measured base-order yield of 0.8%** (4 `newly_past`
# from 500 reads, 2026-09-05). Fifteen times the corrections per venue read, on
# a budget that is already being spent.
#
# IT RANKS SECOND, NOT FIRST, AND THAT IS THE MEASUREMENT TALKING: the
# played-game band probed at ~67% and this one at ~12%, so promoting this above
# it would spend the batch's head on the weaker signal. Non-cohort rows keep
# their inherited order among themselves exactly as before.
#
# A STALENESS GATE WAS TRIED AND REJECTED, because the rejection is the useful
# part. "Every leg retracted AND not price-polled for a day" looks like "it has
# left the venue's open listing" (gotcha #33), and the split is even cleanly
# bimodal — 1,747 rows unseen for >12h against 1,135 seen inside 6h, with
# nothing in between. It is still wrong: the head of that stale cohort probed as
# `KXSWEDENPARLI-26`, `KXHOUSERACE-DCAL-26` and eight 2027 `KXNFLSEED` tickers,
# every one of them `active` at the venue. This module already says why in its
# own words — "the poller's COVERAGE, not the venue's listing, dominates the
# stamp" — and the measurement reproduced it. Membership is therefore the
# retraction ALONE; no date, no stamp.
#
# SQLite-compatible on purpose, like the band above: the guards execute this SQL
# against SQLite, so this is a correlated `EXISTS` pair and nothing cleverer.
RETRACTED_COHORT_RANK_SQL = f"""CASE WHEN EXISTS (
                     SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = futures_markets.id
                        AND COALESCE(fo.resolution_source, '') = '{RETRACTION_SOURCE}'
                 ) AND NOT EXISTS (
                     SELECT 1 FROM futures_outcomes fo
                      WHERE fo.market_id = futures_markets.id
                        AND COALESCE(fo.resolution_source, '') <> '{RETRACTION_SOURCE}'
                 ) THEN 0 ELSE 1 END"""


def banded_select_sql(n_tokens: int) -> str:
    """`SELECT_SQL` with the two band ranks prefixed onto its ORDER BY, nothing else.

    Built by surgery on `SELECT_SQL` itself rather than by restating it, so the
    two cannot drift: if the predicate changes, this changes with it, and if
    this ever stops being a pure re-ordering the guard that compares the two
    heads fails.

    #7000 adds the fully-retracted rank as a SECOND term, after the played-game
    band and before the inherited ordering — see
    :data:`RETRACTED_COHORT_RANK_SQL` for the two yields that fix that position.
    """
    head, sep, tail = SELECT_SQL.partition("ORDER BY")
    if not sep:  # pragma: no cover — a SELECT_SQL with no ORDER BY is a bug
        raise ValueError("SELECT_SQL has no ORDER BY to prefix")
    return (
        f"{head}ORDER BY {band_rank_sql(n_tokens)},\n"
        f"             {RETRACTED_COHORT_RANK_SQL},\n"
        f"             {tail.lstrip()}"
    )


def row_is_in_band(external_id: Optional[str], tokens: list[str]) -> bool:
    """The Python reading of the same membership, for the run's own report.

    The batch's band count is computed here rather than by a second query: one
    selection, one answer. The tokens carry `LIKE`'s ``%`` wildcards, so strip
    them to get the literal the ticker must contain.
    """
    if not external_id:
        return False
    return any(tok.strip("%") in external_id for tok in tokens)


#: What the batch does NOT cover. Reported every run so a bounded sweep can never
#: read as a complete one. `never_swept` / `provisional_recheck` split the eligible
#: population by which of the two selection reasons put the row there, because they
#: behave differently: the never-swept tail can only shrink (the poller writes
#: `expiration_time` on every upsert), while the provisional set refills every time
#: a market is swept before it settles.
COUNT_SQL = f"""
    SELECT
        count(*) AS eligible_total,
        count(*) FILTER (
            WHERE commence_time IS NOT NULL AND commence_time < :purge_floor
        ) AS excluded_purged,
        count(*) FILTER (WHERE expiration_time IS NULL) AS never_swept,
        count(*) FILTER (
            WHERE expiration_time IS NOT NULL
              AND (resolution_date IS NULL OR resolution_date >= expiration_time)
        ) AS provisional_recheck,
        -- #7000: how big the promoted cohort still is. APPENDED, never inserted:
        -- `totals` is read positionally, so a new column may only go last.
        -- Population-level rather than per-batch because the batch's rows are a
        -- fixed 5-tuple that `handle()` unpacks by position, and widening that
        -- to report a counter would be a row-contract change for a log line.
        count(*) FILTER (
            WHERE EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                       WHERE fo.market_id = futures_markets.id
                         AND COALESCE(fo.resolution_source, '') = '{RETRACTION_SOURCE}'
                  )
              AND NOT EXISTS (
                      SELECT 1 FROM futures_outcomes fo
                       WHERE fo.market_id = futures_markets.id
                         AND COALESCE(fo.resolution_source, '') <> '{RETRACTION_SOURCE}'
                  )
        ) AS fully_retracted_total
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
"""

#: `updated_at` is BOUND, not `now()`: the two date columns and the stamp then come
#: from one instant the caller controls, so the guard can assert on the exact
#: parameters that reach the driver instead of on a value the database invents.
#:
#: THE STATUS HALF — CAL-P1019 / #2722. Until this change the only way a Kalshi row
#: could stop claiming to be open was a DATE predicate going past
#: (`status <> 'resolved' AND resolution_date < now()`, #1818's repair). Measured at
#: the venue 2026-09-02: of 49 sampled markets Kalshi had already settled, **10 (20%)
#: still carry a future `close_time`** because they finalised EARLY, so no date field
#: reaches them — ever. Meanwhile this sweep was reading `status` off every leg of
#: every candidate and throwing it away.
#:
#: So the write is conditional on the VENUE's own word (`derive_venue_settlement`),
#: never on a clock: `venue_settled` is true only when the event has legs and every
#: one of them is `settled`/`finalized`. `ELSE status` — not a plain assignment —
#: because this statement also runs for the rows the venue still lists as open, and
#: those must come out of it byte-identical.
#:
#: IT WRITES `status` AND `settled_at`, AND NOTHING THAT IS A GRADE. #1852's line is
#: unchanged and #2722 restates it: `is_winner`, prices and probabilities are a
#: different defect with a different rail, and moving a date and a grade in one pass
#: is how #1852 happened. `test_the_update_never_writes_a_grade` holds that boundary
#: against the statement text.
#:
#: The two dates became COALESCE for one reason: a settled row the venue gives no
#: derivable date for must still be able to stop looking open. Its write arrives with
#: `resolution_date = None`, and a plain assignment would blank a date we already
#: hold in order to record a status. For every row that HAS a derived date the two
#: spellings are identical, so no existing behaviour moves.
UPDATE_SQL = """
    UPDATE futures_markets
    SET resolution_date = COALESCE(:resolution_date, resolution_date),
        expiration_time = COALESCE(:expiration_time, expiration_time),
        status = CASE WHEN :venue_settled THEN 'resolved' ELSE status END,
        settled_at = CASE WHEN :venue_settled
                          THEN COALESCE(settled_at, :updated_at)
                          ELSE settled_at END,
        updated_at = :updated_at
    WHERE id = :id
"""


#: The void fact, #7035 — a SECOND statement rather than two more columns on the
#: one above, and the separation is deliberate on three counts.
#:
#: 1. :data:`UPDATE_SQL` runs for EVERY row in the batch and must come out
#:    byte-identical for the rows the venue still lists as open; its bind set is
#:    pinned by ``tests/integration/test_kalshi_sweep_settlement_bind_pg.py``.
#:    This one runs only for the rows that voided — 77 events in 14 days,
#:    measured — so the hot path is untouched.
#: 2. :data:`UPDATE_SQL` is deliberately SQLite-drivable, because the band
#:    guards execute it against ``sqlite://``. ``jsonb`` is not, and forcing the
#:    merge into that statement would either break those guards or push the
#:    write into Python, where gotcha #4 (a JSONB ORM assignment that silently
#:    does nothing) is waiting.
#: 3. It writes ``market_metadata`` and nothing else — no status, no date, and
#:    above all no grade. #1852's line holds: a void says the venue named NO
#:    outcome, which is the opposite of a winner, and nothing here may be read
#:    as one.
#:
#: MERGED, NOT ASSIGNED. ``COALESCE(...) || jsonb_build_object(...)`` so a row
#: already carrying ``market_metadata["shape"]`` keeps it. A plain assignment
#: would blank the side-kind metadata the serializers read in order to record a
#: status fact, which is the same class of loss the COALESCEd dates above exist
#: to avoid.
VOID_UPDATE_SQL = """
    UPDATE futures_markets
    SET market_metadata = COALESCE(market_metadata, '{}'::jsonb)
                          || jsonb_build_object(
                                 'venue_voided', true,
                                 'venue_voided_at', CAST(:updated_at AS text)
                             )
    WHERE id = :id
"""


#: The NEGATIVE half of the same fact — #7035, CERT-3324's repair.
#:
#: "We asked the venue about this row and it named a result." Written ONLY by the
#: already-resolved arm (:data:`RESOLVED_VOID_SELECT_SQL`), and it exists because
#: that arm's refusals must be as durable as its findings: 10 of 14 sampled rows
#: are graded at the venue, and a refusal that leaves no trace is re-asked every
#: 10 minutes forever.
#:
#: 🔴 IT IS NOT A GRADE AND MUST NEVER BE READ AS ONE. It records that a QUESTION
#: was answered, not what the answer was — no winner, no price, no status.
#: #1852's line is unchanged: the row stays exactly as ungraded as it was, and
#: the rail that grades it is band 1 of `_backfill_kalshi_winners`, untouched
#: here. The only thing this stamp may ever do is stop THIS arm asking again.
#:
#: Merged, not assigned, for :data:`VOID_UPDATE_SQL`'s reason: a plain assignment
#: would blank the side-kind metadata the serializers read in order to record a
#: bookkeeping fact.
VOID_CHECKED_UPDATE_SQL = """
    UPDATE futures_markets
    SET market_metadata = COALESCE(market_metadata, '{}'::jsonb)
                          || jsonb_build_object(
                                 'venue_void_checked_at', CAST(:updated_at AS text)
                             )
    WHERE id = :id
"""


async def run_backfill(
    *,
    session_maker: Callable,
    client_factory: Callable[[], object],
    limit: int = 200,
    offset: int = 0,
    apply: bool = False,
    concurrency: int = 6,
    now: Optional[datetime] = None,
    rows: Optional[list] = None,
    void_capture_only: bool = False,
) -> dict:
    """Select, derive and (optionally) write. Every dependency is a parameter.

    `session_maker` and `client_factory` are injected rather than imported at the
    call site so the composed guard can drive this whole path — selection,
    derivation, and the two-column UPDATE — against a seeded table and a faked
    venue. `now` is a parameter for the same reason the derivation takes no clock
    (gotcha #44): the retention floor must not move under a test.

    `rows` (#4655) SUPPLIES the batch instead of selecting it, and exists so the
    event-driven arm can share this function's derivation and write byte for byte
    rather than growing a second copy of them. The caller has already decided
    WHICH rows; everything after that decision — the venue read, the settlement
    read, the window derivation, `UPDATE_SQL` — is the same code on the same
    tuple shape `(id, external_id, resolution_date, commence_time, market_tier)`.
    The population counters are the one thing that cannot be shared, because
    "how many rows are still eligible" is a question about the population sweep's
    predicate and a targeted batch is not a page of it; they report `-1`, the
    module's existing "not measured" value, rather than a number from the wrong
    denominator.

    `void_capture_only` (#7035, CERT-3324's repair) is the already-resolved arm's
    write policy, and it is a SUBTRACTION from this function rather than an
    addition to it: the batch is read and classified exactly as any other, and
    then `UPDATE_SQL` is not run for it.

    🔴 THE FLAG EXISTS TO BOUND A BLAST RADIUS, NOT TO SAVE A STATEMENT. Those
    rows are already `resolved`, so `UPDATE_SQL`'s status and `settled_at` arms
    are no-ops on them by construction — but its two date columns are NOT:
    `resolution_date = COALESCE(:resolution_date, resolution_date)` OVERWRITES a
    stored date whenever the venue yields one. That is right for a row this sweep
    is closing and wrong for a row it is only explaining. #7035 ships one fact and
    writes one fact; a capture that quietly re-dated 489 settled rows would be a
    different change wearing this one's name.

    It also turns the refusals durable: with the flag set, a row the venue has
    SETTLED but GRADED is stamped `venue_void_checked_at`
    (:data:`VOID_CHECKED_UPDATE_SQL`) so this arm never asks again. Without it,
    that stamp is never written — the open-row population must stay re-askable,
    and marking thousands of healthy rows "checked" to record a question nobody
    asked of them is exactly the silent widening this flag prevents.
    """
    now = now or datetime.now(timezone.utc)
    purge_floor = now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
    band_tokens = past_event_band_tokens(now)

    supplied = rows is not None
    if supplied:
        rows = list(rows)
        eligible_total = excluded_purged = never_swept = provisional_recheck = -1
        fully_retracted_total = -1
    else:
        async with session_maker() as session:
            rows = (
                await session.execute(
                    text(banded_select_sql(len(band_tokens))),
                    {
                        "purge_floor": purge_floor,
                        "limit": limit,
                        "offset": offset,
                        **band_bind_params(band_tokens),
                    },
                )
            ).all()
            totals = (
                await session.execute(text(COUNT_SQL), {"purge_floor": purge_floor})
            ).first()

        eligible_total = int(totals[0]) if totals else -1
        excluded_purged = int(totals[1]) if totals else -1
        never_swept = int(totals[2]) if totals else -1
        provisional_recheck = int(totals[3]) if totals else -1
        fully_retracted_total = int(totals[4]) if totals else -1

    stats = {
        "eligible_total": eligible_total,
        "excluded_purged": excluded_purged,
        # The two selection reasons, reported apart. `never_swept` is the original
        # backlog and can only shrink; `provisional_recheck` is the population that
        # refills whenever a market is swept before the venue settles it, and is the
        # reason this sweep is not a one-off (CAL-P992).
        "never_swept": never_swept,
        "provisional_recheck": provisional_recheck,
        # #7000: the cohort promoted to second rank — every leg retracted, so no
        # grading band in `backfill_winners` can ever ask about it. Unlike
        # `candidates_in_band` this is the POPULATION, not the batch (the batch's
        # rows are a fixed 5-tuple). It should fall as the sweep walks the cycle;
        # a flat number across a full wrap means the promotion is not reaching
        # them and is the thing to re-measure.
        "fully_retracted_total": fully_retracted_total,
        "candidates": len(rows),
        # #3284: how much of this batch the played-game band actually supplied.
        # The band is an ORDER, so this is the number that says whether it is
        # working: a batch that is mostly band is a batch of rows the venue can
        # answer for, and when the band drains this falls and the sweep is back
        # to walking the population — which is the correct steady state, not a
        # regression. Reported beside `newly_past` so the yield is auditable run
        # to run without re-deriving the cohort.
        "band_days": len(band_tokens),
        "candidates_in_band": sum(1 for r in rows if row_is_in_band(r[1], band_tokens)),
        "moved_earlier": 0,
        "unchanged": 0,
        "newly_past": 0,
        "fallback_no_close_time": 0,
        "unresolvable_at_venue": 0,
        "errors": 0,
        # #2722, the settlement half. `venue_settled` is the yield that matters
        # now: rows this batch stopped calling open because Kalshi says they are
        # over. `venue_partially_settled` is reported beside it so an event
        # settling leg by leg reads as the expected state it is rather than as a
        # miss, and `settled_without_date` counts the rows that could only be
        # reached this way — the date columns had nothing to say about them.
        "venue_settled": 0,
        "venue_partially_settled": 0,
        "settled_without_date": 0,
        # #7035, the void half. A SUBSET of `venue_settled`, never a sibling of
        # it: a void is a settlement the venue declined to grade, so every row
        # counted here is already counted above. Reported apart because the two
        # need opposite repairs downstream — a graded settlement wants its
        # winner backfilled, a void wants the fixture to stop claiming a result
        # nobody ever reported.
        "venue_voided": 0,
        # The refusals, so a run that voids nothing is legible. `void_refused`
        # is dominated by `graded` on a healthy population; a run where it is
        # dominated by `result_absent` is reading a payload shape that has
        # moved, which is the failure this counter exists to make loud
        # (gotcha #53 — "it returned" is not "it worked").
        "void_refused_result_absent": 0,
        # #7035 / CERT-3324. The already-resolved arm's OTHER terminal answer:
        # the venue settled this row and named a result. Counted because it is
        # the majority answer on that population (10 of 14 sampled) and a run
        # where it is 0 while `venue_voided` is also 0 means the arm asked
        # nothing, which is a different fact from "nothing voided".
        "void_refused_graded": 0,
    }
    samples: list[dict] = []
    void_samples: list[dict] = []
    void_ids: list[int] = []
    void_checked_ids: list[int] = []

    if not rows:
        # Not a success. Either the migration has not run, or the floor has
        # excluded everything left — two very different facts, so print both
        # numbers rather than one word.
        stats["writes_prepared"] = 0
        stats["writes_applied"] = 0
        return {
            "mode": "APPLY" if apply else "DRY_RUN",
            "measured_at": now.isoformat(),
            "purge_floor": purge_floor.isoformat(),
            "zero_yield": True,
            "zero_yield_reason": (
                # #4655: a supplied batch has no offset and no population
                # denominator, so the population sentence would be four numbers
                # of `-1` dressed up as a diagnosis. Say the one true thing.
                "no rows supplied: the caller's selection matched nothing"
                if supplied
                else f"no candidates at offset {offset}: {eligible_total} rows still "
                f"eligible ({never_swept} never swept, {provisional_recheck} holding "
                f"a provisional date), {excluded_purged} of them past the purge "
                "floor. If eligible_total is 0 the migration may not have run; if it "
                "equals excluded_purged the recoverable population is exhausted."
            ),
            "stats": stats,
            "newly_past_samples": [],
            # Same keys as the full report below. An empty batch and a batch
            # that voided nothing must be the same SHAPE to a reader, or every
            # consumer grows a `.get`.
            "venue_voided_samples": [],
        }

    sem = asyncio.Semaphore(concurrency)
    client = client_factory()

    # #8586: the same single-contest rule the poller uses, so the two writers of
    # `resolution_date` cannot disagree. Lazy — `app.tasks.kalshi` is heavy and
    # this module is imported by scripts.
    from app.tasks.kalshi import _is_dated_fixture_ticker, _is_kalshi_game_ticker

    async def handle(row) -> Optional[dict]:
        market_id, ticker, stored_rd, commence, tier = row

        async with sem:
            try:
                event = await client.get_event(ticker, with_nested_markets=True)
            except Exception:
                stats["errors"] += 1
                return None

        markets = (event or {}).get("markets") or []
        if not markets:
            # 200-with-no-markets and 404 are NOT the same fact, but neither
            # yields a date. Counted apart from errors so a zero-yield run
            # cannot read as a clean one.
            stats["unresolvable_at_venue"] += 1
            return None

        # #2722 — the venue's own word, off the payload we already have. Read
        # BEFORE the date derivation and independently of it, because that is
        # the whole point: settlement must not be reachable only through a date.
        settlement = derive_venue_settlement([m.get("status") for m in markets])
        if settlement.settled:
            stats["venue_settled"] += 1
        elif settlement.reason == "partially_settled":
            stats["venue_partially_settled"] += 1

        # #7035 — off the SAME payload, for no extra venue call, exactly as the
        # settlement read above was added to the date read before it. `result`
        # is the one field that separates "the venue decided this" from "the
        # venue retired it at a fair price", and we were discarding it: a
        # postponed fixture stored as `status='resolved'` with every leg
        # ungraded, indistinguishable from a played game we had simply not
        # graded yet, and so it sat under "No result reported" forever.
        #
        # `.get("result")` and not `["result"]`: a payload that omits the key
        # reaches `derive_venue_void` as None and is REFUSED there, which is the
        # answer we want. A leg we did not read is not a leg the venue declined
        # to grade.
        void = derive_venue_void(
            [m.get("status") for m in markets],
            [m.get("result") for m in markets],
        )
        if void.voided:
            stats["venue_voided"] += 1
            void_ids.append(market_id)
            if len(void_samples) < 15:
                void_samples.append(
                    {
                        "id": market_id,
                        "ticker": ticker,
                        "tier": tier,
                        "legs": void.legs_total,
                    }
                )
        elif void.reason == "result_absent":
            stats["void_refused_result_absent"] += 1
        elif void.reason == "graded" and void_capture_only:
            # #7035 / CERT-3324 — the refusal that must be remembered. `graded`
            # is TERMINAL at the venue: a finalized leg carrying yes/no does not
            # later become ungraded, so this row will never be a void and asking
            # it again can only cost a call. Recorded here and written below.
            #
            # Deliberately NOT `else`. The other refusals — `not_settled`,
            # `result_absent`, `mismatched_inputs` — are all "we could not tell
            # yet", and stamping one of those would retire a row the venue has
            # simply not finished. Only the answer that cannot change is durable.
            stats["void_refused_graded"] += 1
            void_checked_ids.append(market_id)

        window = derive_resolution_window(
            [
                _Leg(
                    _parse(m.get("close_time")),
                    _parse(m.get("expiration_time")),
                    _parse(m.get("expected_expiration_time")),
                )
                for m in markets
            ],
            single_contest=bool(_is_kalshi_game_ticker(ticker or ""))
            or _is_dated_fixture_ticker(ticker),
        )
        if window.resolution_date is None:
            stats["unresolvable_at_venue"] += 1
            if not settlement.settled:
                return None
            # Settled at the venue with no date we can derive. The row still
            # stops claiming to be open: "Kalshi says this is over" is a fact
            # about the market, not about our date columns, and the COALESCEd
            # UPDATE leaves whatever date we hold exactly where it is.
            stats["settled_without_date"] += 1
            return {
                "id": market_id,
                "resolution_date": None,
                "expiration_time": None,
                "venue_settled": True,
                "updated_at": now,
            }
        if window.used_expiration_fallback:
            stats["fallback_no_close_time"] += 1

        if stored_rd is not None and window.resolution_date < stored_rd:
            stats["moved_earlier"] += 1
            if stored_rd > now >= window.resolution_date:
                stats["newly_past"] += 1
                if len(samples) < 15:
                    samples.append(
                        {
                            "id": market_id,
                            "ticker": ticker,
                            "tier": tier,
                            "was": stored_rd.isoformat(),
                            "now": window.resolution_date.isoformat(),
                        }
                    )
        else:
            stats["unchanged"] += 1

        return {
            "id": market_id,
            "resolution_date": window.resolution_date,
            "expiration_time": window.expiration_time,
            "venue_settled": settlement.settled,
            "updated_at": now,
        }

    try:
        results = await asyncio.gather(*(handle(r) for r in rows))
    finally:
        # `BaseAPIClient` exposes `close()` and no `__aenter__`, so `async with`
        # on the service raises AttributeError. Explicit try/finally instead.
        close = getattr(client, "close", None)
        if close is not None:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe

    writes = [r for r in results if r]
    stats["writes_prepared"] = len(writes)

    if apply and writes and not void_capture_only:
        async with session_maker() as session:
            for chunk_start in range(0, len(writes), 500):
                chunk = writes[chunk_start : chunk_start + 500]
                for w in chunk:
                    await session.execute(text(UPDATE_SQL), w)
                await session.commit()
        stats["writes_applied"] = len(writes)
    else:
        stats["writes_applied"] = 0

    # #7035. Its own pass, after the settlement writes have committed, so a
    # failure here can never leave a row stamped "the venue voided this" that
    # is not also stamped "the venue settled this" — the void is a refinement
    # of the settlement and must not be able to outrun it. Chunked and
    # committed on the same 500 boundary as the loop above, for the same
    # reason (gotcha #13: long transactions on this table deadlock).
    if apply and void_ids:
        async with session_maker() as session:
            for chunk_start in range(0, len(void_ids), 500):
                for market_id in void_ids[chunk_start : chunk_start + 500]:
                    await session.execute(
                        text(VOID_UPDATE_SQL),
                        {"id": market_id, "updated_at": now.isoformat()},
                    )
                await session.commit()
        stats["void_writes_applied"] = len(void_ids)
    else:
        stats["void_writes_applied"] = 0

    # #7035 / CERT-3324 — the refusal stamp, LAST of the three passes and after
    # the void write has committed. The ordering is the same argument the void
    # pass makes against the settlement write one level up: these two statements
    # are mutually exclusive per row by construction (`voided` and `graded` are
    # different branches of one classifier), so the order cannot matter for
    # correctness — but if it ever did, the fact worth keeping is the finding,
    # not the bookkeeping, so the bookkeeping goes last and a failure here costs
    # a re-ask rather than a lost void.
    if apply and void_checked_ids:
        async with session_maker() as session:
            for chunk_start in range(0, len(void_checked_ids), 500):
                for market_id in void_checked_ids[chunk_start : chunk_start + 500]:
                    await session.execute(
                        text(VOID_CHECKED_UPDATE_SQL),
                        {"id": market_id, "updated_at": now.isoformat()},
                    )
                await session.commit()
        stats["void_checked_writes_applied"] = len(void_checked_ids)
    else:
        stats["void_checked_writes_applied"] = 0

    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "purge_floor": purge_floor.isoformat(),
        "offset": offset,
        "zero_yield": len(writes) == 0,
        "stats": stats,
        "newly_past_samples": samples,
        # #7035. Named tickers rather than a bare count, because the claim
        # "the venue voided this" is checkable at the venue in one request
        # (`/events/{ticker}?with_nested_markets=true`) and a report that only
        # carries a number cannot be audited that way.
        "venue_voided_samples": void_samples,
    }
    if stats["unresolvable_at_venue"] == len(rows) and not writes:
        # Every slot in the batch went to a row this script may not write. Those
        # rows keep their slot, so an unattended re-run selects them again.
        report["batch_fully_unresolvable"] = (
            f"all {len(rows)} selected rows were unresolvable at the venue and "
            "none can be written (a missing date is not a status change). "
            f"Re-running at --offset {offset} selects the same rows; advance the "
            "offset to reach the recoverable tail."
        )
    return report


# ---------------------------------------------------------------------------
# The rotating cursor — CAL-P998, measured on the first unattended-shaped run
# ---------------------------------------------------------------------------

#: Where the next batch starts. A ROTATING cursor, and it exists because the
#: first production run of this sweep under CAL-P998 selected 500 rows and wrote
#: zero.
#:
#: WHAT WAS MEASURED (2026-09-03 16:17 PT, `heroku run:detached`, `--limit 500
#: --apply`). Before and after on the exact selected batch: 411 rows with a NULL
#: `expiration_time` before and 411 after, 89 sealed before and 89 after, 0
#: converged. `pg_stat_statements` confirms the run happened and what it did:
#: `SELECT_SQL` **1 call, 500 rows, 185 ms**, `COUNT_SQL` 1 call — and **no
#: matching UPDATE statement recorded at all.** (The dyno's stdout is not
#: readable from the agent sandbox — `heroku logs` returns EPERM — so the
#: distinction between "ran and yielded nothing" and "never ran" was settled by
#: a second signal rather than assumed. Gotcha #53.)
#:
#: WHY, off the head of the batch itself:
#:
#:     KXTXPRIMARY-31D26   commence_time 2027-11-03   resolution_date 2027-11-03
#:                         expiration_time NULL       updated_at 2026-06-20
#:
#: `commence_time` equals the backstop — the poisoned-column shape #2771 named
#: (4,954 of 5,143 sealed rows carry `commence_time = expiration_time`). So the
#: retention floor, which is a `commence_time` test, reads these as recent and
#: admits them, while the venue purged them months ago and returns no markets.
#: They yield no date, and a row this script may not write is a row whose
#: `updated_at` is never refreshed — so under `ORDER BY updated_at ASC` it stays
#: at the head **forever**.
#:
#: #2771's rotation argument ("every write refreshes the stamp, so the sweep
#: rotates") is true only of rows that get written. Unwritable rows do not
#: rotate, and 500 of them are enough to jam the entire beat: 5,143 sealed rows
#: at 05:00Z became 5,137 seventeen hours later, which is what a jam looks like
#: from outside.
#:
#: The script's own docstring already names the remedy for a human — *"`--offset`
#: exists so an operator can advance past a stuck prefix rather than re-running
#: into it"*. An unattended beat has no operator, so it must do that itself.
#:
#: 🔴 **CERT-863 BLOCK (2026-09-04) — the offset alone could not wrap, so the
#: jam it skipped was never re-reached.** The cursor held TWO facts in one
#: number and they diverge. `offset` answers *"how far past the stuck prefix am
#: I"*; the wrap needs *"how much of the population has this cycle seen"*, and
#: on a stable, fully-writable suffix the first stops moving while the second
#: must keep going. The cert's exact-head reproduction — a 1,500-row population
#: whose first 500 are stranded, then three clean batches — printed
#: ``0 -> 500 -> 500 -> 500 -> 500``. Every clean batch strands nothing, so
#: `offset + stranded` re-returns 500 forever, the wrap test never fires, and
#: the only thing that ever sends the sweep back to the head is the 30-day TTL
#: below. A market that is unresolvable in September and finalized in October
#: therefore keeps rendering its dead last-trade price for up to a month — which
#: is the exact failure this whole ship claims to end, so the claim did not hold.
#:
#: The two facts are now stored as two, and the pair travels together in ONE
#: Redis value (``"<offset>:<scanned>"``) rather than two keys: a half-written
#: pair is a cursor that says a cycle is further along than the offset it
#: carries, which skips rows silently — the failure mode this repair exists to
#: remove. A legacy bare ``"500"`` left in Redis by the pre-repair beat parses as
#: ``(500, 0)``, so the first run after deploy starts where the old cursor
#: pointed and begins counting its cycle from there.
#:
#: 🔁 **VERSIONED at `:v2` by #3284.** An offset is a position in an ORDER, and
#: the played-game band changes that order — `375` under the old ordering names
#: a different 500 rows than `375` under the new one, so resuming on it would
#: skip an arbitrary slice of the population on the first run after deploy and
#: nothing would ever report that it had. Bumping the key retires the old value
#: without deleting it (it expires on its own TTL) and starts one clean cycle at
#: the head, which is exactly where the band is. Any future change to the ORDER
#: BY must bump this again for the same reason.
#:
#: 🔁 **VERSIONED at `:v3` by #7000**, under the standing instruction in the line
#: above. The fully-retracted rank (:data:`RETRACTED_COHORT_RANK_SQL`) is a new
#: ORDER BY term, so every offset banked under `:v2` names a different 500 rows
#: than it would under this ordering. One clean cycle from the head is also what
#: the change is FOR — the promoted cohort is at the head.
SWEEP_CURSOR_KEY = "bainluck:kalshi_resolution_sweep:offset:v3"

#: 30 days. Long enough that a fortnight of failed beats does not silently reset
#: the sweep to the jammed head; short enough that a stale cursor left behind by
#: a retired population expires instead of skipping rows forever.
#:
#: It is a BACKSTOP and must never be the mechanism. Before CERT-863's repair it
#: was the mechanism — expiry was the only path back to offset 0 — and a backstop
#: doing load-bearing work is how a 30-day dead-price window looked like a
#: working nightly sweep. The cycle wrap in :func:`next_cursor` now returns to
#: the head in ``ceil(eligible_total / limit)`` runs; at the measured 6,302
#: eligible rows and a 500-row batch that is ~13 nights, comfortably inside this.
SWEEP_CURSOR_TTL_S = 60 * 60 * 24 * 30


async def _read_cursor() -> tuple[int, int]:
    """``(offset, scanned)`` to start at. An unreadable cursor is the head.

    ``(0, 0)`` is the pre-cursor behaviour, so a Redis outage degrades this sweep
    to exactly what it did before the cursor existed rather than taking it down.

    A bare integer is the pre-CERT-863 encoding and is read as ``(offset, 0)``:
    the offset is still true, and starting that cycle's traversal count at zero
    only makes the first wrap after deploy late by at most one cycle. Guessing a
    `scanned` to match would be inventing a measurement.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(SWEEP_CURSOR_KEY)
        if isinstance(raw, bytes):
            raw = raw.decode()
        offset_s, _, scanned_s = str(raw).partition(":")
        return max(0, int(offset_s)), max(0, int(scanned_s or 0))
    except Exception:  # noqa: BLE001 — a missing cursor is a start, not a failure
        return 0, 0


async def _write_cursor(offset: int, scanned: int) -> bool:
    """Persist the pair. Returns whether it landed — the caller reports it.

    Swallowing this would be the worst option available: the run would look
    clean, the cursor would stay where it was, and the next beat would re-enter
    the same jam. So the boolean travels onto the summary and into the terminal.

    One key, one round trip, both numbers — see :data:`SWEEP_CURSOR_KEY` for why
    the pair must not be split across two keys.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().set(
            SWEEP_CURSOR_KEY,
            f"{int(offset)}:{int(scanned)}",
            ex=SWEEP_CURSOR_TTL_S,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def next_cursor(
    *, offset: int, scanned: int, candidates: int, applied: int, eligible_total: int
) -> tuple[int, int]:
    """The next ``(offset, scanned)``, given what this batch could not move.

    ## The offset half — where the next batch starts

    ``candidates - applied`` is exactly the number of rows that KEPT their slot:
    a written row rotates to the back of `updated_at ASC` on its own (the write
    refreshes the stamp), an unwritten one does not. Advancing by that number —
    not by ``limit`` — is what makes the cursor track the jam rather than a
    batch size, so a run that writes 470 of 500 advances 30 and a run that
    writes none advances a full batch.

    A CLEAN BATCH HOLDS ITS OFFSET; IT DOES NOT RESET. This is the correction
    that the offset-500 measurement forced, and it is worth spelling out because
    the reset is the obvious first implementation and it re-enters the jam every
    other night. Measured 2026-09-03: offset 0 is 500 unwritable rows last
    touched in June, and offset 500 is 500 rows the poller touched today which
    all write cleanly. Under "reset to 0 when nothing was stranded" the sweep
    alternates jam / productive / jam / productive and burns half its nights.
    Holding the offset is also simply correct: when 500 rows rotate to the back,
    the row that was at position 1,000 is now at position 500, so the same
    offset points at fresh content.

    ## The scanned half — CERT-863, and why the offset cannot also do this job

    Holding the offset is right, and it is exactly what made the wrap
    unreachable: a run of clean batches strands nothing, so an offset-only
    cursor is CORRECTLY motionless while the cycle is in fact advancing through
    a rotating suffix. The two facts had to be separated. ``scanned`` accumulates
    ``candidates`` — the rows this cycle has actually looked at — and it is a
    fair count of traversal precisely BECAUSE the suffix rotates: a clean batch
    at a held offset reads 500 rows it has not read before this cycle.

    IT WRAPS ON TRAVERSAL, NOT ON ARITHMETIC LUCK. Once ``scanned + candidates``
    reaches the eligible population the cycle is done: offset and scanned both
    return to 0 and the next run re-reads the head — the stranded prefix
    included. That is the promise the module made and could not keep. The venue
    publishes `close_time` on finalize, so September's unresolvable row is
    October's necessary write, and it is now re-offered every
    ``ceil(eligible_total / limit)`` runs instead of once a month by expiry.

    The old walk-off-the-end guard is kept beside it rather than replaced.
    ``offset <= scanned`` holds for any cursor this function produces (stranded
    is never more than candidates), so on a consistent cursor the traversal test
    always fires first — but a legacy bare offset, or a population that shrank
    under the cursor, can present a high offset with a low scanned, and then the
    offset test is the one that saves the run from selecting nothing forever.
    """
    if candidates == 0:
        # Nothing at this offset: either the cursor is past the end of a
        # population that shrank, or the population is empty. Both are the end
        # of a cycle, not a failure — start the next one at the head.
        return 0, 0

    traversed = scanned + candidates
    advanced = offset + max(0, candidates - applied)

    if eligible_total <= 0 or traversed >= eligible_total or advanced >= eligible_total:
        return 0, 0
    return advanced, traversed


# ---------------------------------------------------------------------------
# The unattended entry point
# ---------------------------------------------------------------------------


async def run_sweep(
    *,
    limit: int = SWEEP_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    offset: Optional[int] = None,
    session_maker: Optional[Callable] = None,
    client_factory: Optional[Callable[[], object]] = None,
) -> dict:
    """One bounded beat run, with terminal truth attached.

    THE TERMINAL IS THE POINT, not decoration. ``_tracked_run`` classifies this
    summary through ``app.utils.task_verdict``, and a summary with no terminal
    field is recorded as a success merely because the invocation returned —
    which is how three calibration tasks reported ``health: healthy`` while
    producing nothing (#1515). This sweep has a zero-yield mode that is a
    perfectly normal return value, so it must say which zero it is:

    * **complete** — the batch wrote what the venue gave it, OR nothing is
      eligible at all (the population really is drained).
    * **partial** — rows were selected and NOTHING could be written. The batch
      spent its whole slot on rows the venue would not resolve; the population
      did not move and the next run selects the same head. Never green.
    * **failed** — every selected row errored at the venue. That is an outage,
      not a drained population, and it must not read as either of the above.

    ``apply`` defaults to TRUE here and FALSE in ``run_backfill``, deliberately:
    the CLI's default must be the harmless one because a human types it, and the
    beat's default must be the useful one because nobody is there to pass a flag.

    ``offset`` defaults to the rotating cursor. Pass an explicit one only to pin
    a run; see :data:`SWEEP_CURSOR_KEY` for the measurement that made the cursor
    necessary — without it this beat writes zero rows every night, forever, and
    looks healthy doing it.
    """
    if offset is None:
        start, scanned = await _read_cursor()
    else:
        # An explicitly pinned run is a probe of one batch, not a step in the
        # cycle, so it starts that cycle's traversal count at zero rather than
        # crediting the pin against a cycle it did not walk.
        start, scanned = max(0, int(offset)), 0

    report = await run_backfill(
        session_maker=session_maker or default_session_maker(),
        client_factory=client_factory or KalshiAPIService,
        limit=limit,
        offset=start,
        apply=apply,
        concurrency=concurrency,
    )

    stats = report.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    applied = int(stats.get("writes_applied") or 0)
    errors = int(stats.get("errors") or 0)
    eligible = int(stats.get("eligible_total") or 0)

    nxt, nxt_scanned = next_cursor(
        offset=start,
        scanned=scanned,
        candidates=candidates,
        applied=applied,
        eligible_total=eligible,
    )
    # BOTH halves must be unchanged to skip the write. The offset alone standing
    # still is the normal healthy case (a clean batch holds it) and it is exactly
    # when `scanned` is moving — skipping the write on the offset alone is how
    # cycle progress would be dropped every productive night, which is the
    # CERT-863 defect rebuilt inside the optimisation that was meant to be free.
    unchanged = nxt == start and nxt_scanned == scanned
    persisted = True if unchanged else await _write_cursor(nxt, nxt_scanned)

    report["offset"] = start
    report["next_offset"] = nxt
    report["scanned_before"] = scanned
    report["next_scanned"] = nxt_scanned
    # The cycle closed on this run: the next beat re-reads the head, stranded
    # prefix included. Named on the summary because "the sweep went back to 0"
    # must be legible as a completed traversal rather than as a lost cursor.
    report["cycle_wrapped"] = nxt == 0 and nxt_scanned == 0 and start != 0
    report["stranded"] = max(0, candidates - applied)
    report["cursor_persisted"] = persisted

    if not persisted:
        # Progress may have been made and it is silently unresumable: the next
        # beat re-enters this exact batch and the jam returns. The typeahead
        # index builder makes the same call for the same reason (#1866).
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"cursor not persisted — the next run repeats offset {start} "
            f"instead of advancing to {nxt}"
        )
    elif candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"all {candidates} selected rows errored at the venue"
        )
    elif candidates and applied == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} rows selected, 0 written — "
            f"{stats.get('unresolvable_at_venue')} unresolvable at the venue; "
            f"cursor advanced {start} -> {nxt} so the next run does not re-enter it"
        )
    else:
        report["terminal"] = "complete"

    # The population this run did NOT reach, carried on the summary so a bounded
    # sweep can never be read as a finished one — the same reason `run_backfill`
    # reports `eligible_total` beside `candidates`.
    report["remaining_after_batch"] = max(0, eligible - applied)
    return report


async def run_recent_finals(
    *,
    limit: int = RECENT_FINAL_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    window_hours: int = RECENT_FINAL_WINDOW_HOURS,
    live_window_hours: int = LIVE_EVENT_WINDOW_HOURS,
    suspended_window_hours: int = SUSPENDED_EVENT_WINDOW_HOURS,
    stale_touch_minutes: int = LIVE_STALE_TOUCH_MINUTES,
    frozen_gap: float = FROZEN_BOOK_GAP,
    session_maker: Optional[Callable] = None,
    client_factory: Optional[Callable[[], object]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """The EVENT-DRIVEN arm — #4655. Reach a finished game's tickers in minutes.

    THE DEFECT THIS EXISTS FOR, measured on production 2026-09-10. Kalshi
    settled all 842 markets across the NFL opener's 61 event tickers at
    03:28:38Z, two minutes after our own event went `completed` at 03:26:32Z.
    Two hours later all 61 of our rows still read `status='open'` with
    `settled_at` NULL, so a finished game kept serving a live-looking price.
    Repo-wide at that moment: 1,181 Kalshi rows held `open` past a passed
    `commence_time` over six hours, 737 over a day, 267 over a week.

    WHY NEITHER EXISTING ARM REACHES THEM, and why this is not a tuning problem:

    * ``backfill_kalshi_settled`` runs 4x daily on the ``background`` queue and
      was hard-killed on its 05:00Z run (0 successes, ``health: critical``).
    * ``sweep_kalshi_resolution_window`` is a POPULATION sweep — 500 rows a night
      against 12,244 eligible, a ~24-night cycle. Worse than slow, it is ordered
      ``updated_at ASC``, which puts a game that just finished LAST: it was being
      polled until minutes ago, so it carries the newest stamp in the population.

    Both are sweeps over a population. Neither is keyed on the event, so neither
    can have a bound measured in minutes. This one is keyed on the event and its
    bound is the beat period.

    AND THE LIVE ARM — #5024. Kalshi markets ``can_close_early``, so a question
    can be decided while the game is still being played: SF@LAR's First Touchdown
    was finalized ``result='yes'`` at 01:22:33Z and our row still read ``open`` at
    02:32Z, mid-second-quarter, drawing a 26-rung ladder that summed to 124%.
    Keyed on ``completed_at``, this arm could not reach that row until the whistle;
    41 of the 48 live rows carrying an empty book at 02:5xZ were already decided
    at the venue. The selection now admits live events too, screened by the empty
    book so a normally-trading market is never asked about, and ordered so a
    finished game still takes the batch first.

    AND THE LIVE ARM'S SECOND REACH — #5024 again, because the empty book
    ARRIVES LATE. Measured end to end on production during Raiders@Chargers,
    2026-09-20, with every stamp read rather than inferred:

    * 21:27:47Z — Kalshi closes Tre Tucker's leg, ``result='yes'``. The first
      touchdown is a fact, and the play feed at the top of our own page says so.
    * 22:07:46Z — the last of the 26 legs finalizes. From here
      ``derive_venue_settlement`` would answer ``settled_past_dormant_legs`` the
      moment it were asked.
    * 22:15Z — our row still reads ``status='open'``. NOT ONE of its 26 legs
      carries the empty book (Tucker: ``0.0200 / 0.3300`` beside a stored 0.99,
      the last two-sided quote from before the close), so the screen above does
      not select it. The page draws the 26-rung ladder #5024 was filed for,
      summing to 189% — and three cards below it, ``1st Las Vegas Touchdown``
      prints ``Tre Tucker — Won``. Same fact, same screen, two answers.
    * 22:30:00Z — the empty book has by now been written, the existing screen
      selects the row and it flips ``resolved``. 22 minutes after the venue
      finished, 62 minutes after the question was decided.

    🔴 SO THE FIRST READING OF THIS DEFECT WAS WRONG AND IS RECORDED AS WRONG:
    "Kalshi omits ``yes_bid``/``yes_ask`` from a finalized market on both doors,
    therefore no poll can ever write the 0/1" is FALSE. The doors do omit them —
    that part is a real venue read — but our poller writes the empty book for an
    absent quote anyway, just tens of minutes later. This arm is therefore not
    unreachable, it is LATE, against #4655's own 30-minute bar. The correction
    matters because the fix it argues for is the same but the claim it makes for
    it is much smaller, and a docstring that overstates its case is how the next
    reader gets misled.

    The second screen is therefore not another reading of the price but a reading
    of the POLLER: a market the venue has stopped serving stops being touched,
    and the touch age tracks the venue's own ``close_time`` to the poll cadence
    on every all-terminal row measured. At 22:34Z it took 31 rows the empty book
    had not yet reached; the ten of the sixteen sampled that the venue called
    all-terminal had been decided for 14 to 20 minutes and were still open. See
    :data:`LIVE_STALE_TOUCH_MINUTES` for that table, the cadence measurement, the
    two precision samples and their control, and why the suspended arm's
    frozen-book predicate was measured on this population (25%) and refused
    rather than reused.

    AND THE SUSPENDED ARM — #5596. Both arms above key on our own event reaching
    `completed` or `live`, and a `suspended` event reaches neither, ever. Over
    #5596's entire Kalshi population (51 markets / 114 legs, 114/114 `finalized`
    at the venue on 2026-09-14 05:16Z) the linked events read `suspended` or
    `scheduled` with `completed_at` NULL, so both arms select ZERO of them and the
    rows sat `status='open'` serving a played J-League game as `Tie 99%` over a
    book naming the other side. Screened by the two freeze signatures — #5024's
    empty book, or a two-sided book that contradicts its own stored probability by
    more than `FROZEN_BOOK_GAP` — at a measured 87% precision, and leashed to
    `SUSPENDED_EVENT_WINDOW_HOURS` because nothing else would ever retire a stuck
    event from the band.

    WHAT IT DOES NOT DO. It writes no grade — never ``is_winner``, never a price.
    That constraint is CAL-P061's and #1852's and it is inherited unchanged,
    because it belongs to the shared write (``UPDATE_SQL``) rather than to any
    one caller. This arm changes only WHICH rows reach that write and HOW SOON.
    So this ship makes the market stop claiming to be open; the VERDICT the
    reader sees is a separate write on a separate rung, and #5024 stays open for
    it.

    WHAT THIS ARM DELIBERATELY DOES NOT REACH — #7035. All three selections here
    open with ``fm.status = 'open'``. A POSTPONED fixture has usually already
    been closed by one of them, so it reads ``resolved`` while its event stays
    ``suspended`` and no leg is graded. Those rows are past every screen in this
    statement, and they belong to :func:`run_resolved_voids`, which is a separate
    task on a slower beat for the reasons written there — chiefly that this one
    carries a 30-minute bar and must not spend it explaining postponements.
    """
    now = now or datetime.now(timezone.utc)
    final_floor = now - timedelta(hours=window_hours)
    live_floor = now - timedelta(hours=live_window_hours)
    suspended_floor = now - timedelta(hours=suspended_window_hours)
    stale_touch_floor = now - timedelta(minutes=stale_touch_minutes)
    maker = session_maker or default_session_maker()

    async with maker() as session:
        rows = (
            await session.execute(
                text(RECENT_FINAL_SELECT_SQL),
                {
                    "final_floor": final_floor,
                    "live_floor": live_floor,
                    "suspended_floor": suspended_floor,
                    "stale_touch_floor": stale_touch_floor,
                    "frozen_gap": frozen_gap,
                    "limit": limit,
                },
            )
        ).all()

    report = await run_backfill(
        session_maker=maker,
        client_factory=client_factory or KalshiAPIService,
        apply=apply,
        concurrency=concurrency,
        now=now,
        rows=rows,
    )

    stats = report.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    settled = int(stats.get("venue_settled") or 0)
    errors = int(stats.get("errors") or 0)

    report["selection"] = "recent_finals"
    report["window_hours"] = window_hours
    report["final_floor"] = final_floor.isoformat()
    report["live_window_hours"] = live_window_hours
    report["live_floor"] = live_floor.isoformat()
    report["suspended_window_hours"] = suspended_window_hours
    report["suspended_floor"] = suspended_floor.isoformat()
    report["stale_touch_minutes"] = stale_touch_minutes
    report["stale_touch_floor"] = stale_touch_floor.isoformat()
    report["frozen_gap"] = frozen_gap
    report["batch_limit"] = limit
    # A full batch means finals are arriving faster than one run drains them, so
    # the NEXT run still has a backlog and the 30-minute bar is at risk. Named on
    # the summary rather than inferred, so it is visible without re-deriving it.
    report["batch_saturated"] = candidates >= limit

    # The terminal is the same three-way contract `run_sweep` uses (#1515) — an
    # invocation that returned is not proof of work — but the SUCCESS SIGNAL is
    # `venue_settled`, NOT `writes_applied`, and the difference is this arm's
    # whole point.
    #
    # Found by running it. A leg whose game is over but whose venue has not
    # finalized it still produces a write: the derivation re-derives the same
    # backstop date off the venue's `close_time` and returns a row, so
    # `writes_applied` reads 1 and the population sweep's rule would grade the
    # run `complete`. It refreshed a date. The row is still `status='open'` and
    # the reader is still looking at a live price on a finished game — the exact
    # defect #4655 exists for, graded GREEN from inside the fix.
    #
    # For the population sweep a date write IS progress, so its rule is right
    # for it. For this arm the job is closing the row, so `venue_settled == 0`
    # over a non-empty batch is `partial`: honest, self-limiting (a leg leaves
    # the six-hour window on its own), and exactly the signal that says "there
    # are finished games we have not been able to close yet".
    if candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"all {candidates} legs of recently-final events errored at the venue"
        )
    elif candidates and settled == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} legs of recently-final events selected, 0 confirmed "
            f"settled at the venue ({stats.get('unresolvable_at_venue')} "
            "unresolvable). Every one of them still reads `open`. Expected while "
            "a game is over and the venue has not finalized it yet; the next run "
            "re-asks, and a leg leaves this selection only when the venue "
            "confirms it."
        )
    else:
        report["terminal"] = "complete"
    return report


async def _retire_rows_the_venue_voided(maker, now) -> dict:
    """Spend the fact the capture just wrote — #7035, CERT-3326's repair.

    THE CONSUMER, AND WITHOUT IT THE CAPTURE IS A COLUMN RATHER THAN A SHIP.
    CERT-3326 blocked the capture-only presentation on exactly this: "the SHA
    has no runtime consumer of that fact … event 15312871 therefore remains
    suspended/served and its card still says 'No result reported'." This is the
    line that closes `capture → retirement`; the route exclusion at the far end
    already refuses :data:`UNREACHABLE_SUSPENDED_TERMINAL` and is guarded.

    🔴 IT IS CALLED ON BOTH OF `run_resolved_voids`'S PATHS, INCLUDING THE
    DRAINED ONE, AND THAT IS THE WHOLE DIFFERENCE BETWEEN A SHIP AND AN ARM THAT
    WORKS FOR FOUR HOURS. The capture's own sizing says the standing 489-row
    band drains in ~4 hours at 60 a run, after which `rows` is empty on every
    subsequent beat forever — that is the intended steady state, not a fault.
    Hung off the write path only, this consumer would then never run again,
    while the rows it exists to retire are precisely the ones already stamped.
    The two halves keep different clocks on purpose: a stamp is written once,
    and the row it describes may not become retirable until the retirement
    floor passes it, hours later. So the retirement re-screens the table every
    beat and is deliberately independent of whether this beat stamped anything.

    Its own session, and the `async with` is what commits (the same contract
    `_transition_event_statuses_impl` documents at its own close). Kept separate
    from the capture's sessions so a retirement can never widen a venue-write
    transaction, and so a failure here cannot roll back a stamp that was correct.
    """
    from app.tasks.espn_sync import (
        _retire_venue_voided_suspended_rows,
        unreachable_suspended_floor,
    )

    async with maker() as session:
        return await _retire_venue_voided_suspended_rows(
            session, now, unreachable_suspended_floor()
        )


async def run_resolved_voids(
    *,
    limit: int = RESOLVED_VOID_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    suspended_window_hours: int = SUSPENDED_EVENT_WINDOW_HOURS,
    session_maker: Optional[Callable] = None,
    client_factory: Optional[Callable[[], object]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """The ALREADY-RESOLVED void arm — #7035, CERT-3324's required repair.

    THE REACHABILITY FAILURE THIS EXISTS FOR. Every selection in this module
    opens with ``fm.status = 'open'`` — that screen IS the drain and it is right
    for all three arms of :func:`run_recent_finals`. But a POSTPONED fixture has
    usually already been closed by one of them: measured on production
    2026-09-23 04:2xZ, all four Levante–Bilbao families (market ids 60481773,
    60636796, 60636798, 60636800, event 15312871) read ``status='resolved'`` with
    ``settled_at`` set, on an event still ``suspended``, every leg ungraded, and
    ``venue_voided`` NULL. The sweep recorded that the venue was finished and
    never recorded that it had named no outcome, so the page can only say "No
    result reported" — and no batch size or cadence reaches those rows, because
    the capture ran on a population its own selection excluded. CERT-3324
    blocked the first presentation of #7035 for exactly this, and was right to.

    🔴 A SEPARATE TASK, NOT A PHASE OF :func:`run_recent_finals`, and the first
    attempt at this repair WAS that phase. Two reasons it was withdrawn:

    * that beat carries #4655's 30-minute bar, and hanging up to
      :data:`RESOLVED_VOID_BATCH_LIMIT` extra venue reads off it makes this arm
      a latency risk to a promise it has nothing to do with. Explaining a
      postponement is not urgent; closing a finished game is;
    * it selects the OPPOSITE ``status`` and writes under a different policy
      (``void_capture_only``), so the two share a name and nothing else.

    Composed, it also broke six guards belonging to #5024, #4655 and #5596 —
    their session doubles answer any statement with one canned batch, so the
    second selection re-served the same specimen and the venue was asked twice.
    Loosening three other ships' guards to fit this one in would have been the
    wrong repair for the right complaint.

    WHAT IT WRITES: one fact, and never a grade. ``venue_voided`` when the venue
    settled the event and declined to grade it; ``venue_void_checked_at`` when it
    settled and DID grade it, so a refusal is as durable as a finding (10 of 14
    sampled rows are graded, and an unrecorded refusal is re-asked forever). A
    venue that has NOT finished is stamped with neither and is asked again.
    """
    now = now or datetime.now(timezone.utc)
    suspended_floor = now - timedelta(hours=suspended_window_hours)
    maker = session_maker or default_session_maker()

    async with maker() as session:
        rows = (
            await session.execute(
                text(RESOLVED_VOID_SELECT_SQL),
                {"suspended_floor": suspended_floor, "limit": limit},
            )
        ).all()

    if not rows:
        # A selection that matched nothing is the DRAINED steady state here, and
        # it is the expected reading most of the time — but it is reported as a
        # shape rather than an absence, because "the band is empty" and "the
        # query never ran" must not look the same to a reader (gotcha #53).
        #
        # THE RETIREMENT STILL RUNS ON THIS PATH. Nothing new to stamp is the
        # normal state within hours of the band draining, and it says nothing
        # about whether an already-stamped row has become retirable since. See
        # `_retire_rows_the_venue_voided`.
        drained = {
            "selection": "resolved_void",
            "mode": "APPLY" if apply else "DRY_RUN",
            "measured_at": now.isoformat(),
            "batch_limit": limit,
            "suspended_floor": suspended_floor.isoformat(),
            "candidates": 0,
            "venue_voided": 0,
            "void_refused_graded": 0,
            "void_writes_applied": 0,
            "void_checked_writes_applied": 0,
            "venue_voided_samples": [],
            "terminal": "complete",
            "terminal_reason": (
                "no already-resolved candidates in the band: every postponed "
                "fixture inside "
                f"{suspended_window_hours}h has already been asked about once. "
                "This is the drained steady state, not a failure."
            ),
        }
        drained.update(await _retire_rows_the_venue_voided(maker, now))
        return drained

    sub = await run_backfill(
        session_maker=maker,
        client_factory=client_factory or KalshiAPIService,
        apply=apply,
        concurrency=concurrency,
        now=now,
        rows=rows,
        void_capture_only=True,
    )
    stats = sub.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    errors = int(stats.get("errors") or 0)
    report = {
        "selection": "resolved_void",
        "mode": "APPLY" if apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "batch_limit": limit,
        "suspended_floor": suspended_floor.isoformat(),
        "candidates": int(stats.get("candidates") or 0),
        "venue_voided": int(stats.get("venue_voided") or 0),
        "void_refused_graded": int(stats.get("void_refused_graded") or 0),
        "void_refused_result_absent": int(stats.get("void_refused_result_absent") or 0),
        "errors": int(stats.get("errors") or 0),
        "void_writes_applied": int(stats.get("void_writes_applied") or 0),
        "void_checked_writes_applied": int(
            stats.get("void_checked_writes_applied") or 0
        ),
        # The settlement write is withheld from this population by construction.
        # Reported so the claim is checkable in the run report rather than only
        # in a docstring.
        "settlement_writes_applied": int(stats.get("writes_applied") or 0),
        "venue_voided_samples": sub.get("venue_voided_samples") or [],
    }

    # The same three-way contract the arms above use (#1515): an invocation that
    # returned is not proof of work. The SUCCESS SIGNAL here is that every
    # selected row got a durable answer — voided or checked — because a row that
    # gets neither is one this arm will ask about again next run, and a batch
    # made entirely of those is the jam CAL-P998 measured, not progress.
    answered = report["void_writes_applied"] + report["void_checked_writes_applied"]
    if candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"all {candidates} already-resolved candidates errored at the venue"
        )
    elif candidates and apply and answered == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} already-resolved candidates asked, 0 given a durable "
            "answer. Every one of them is selected again next run. Expected only "
            "while the venue has not finished these events; a batch that stays "
            "here is not draining."
        )
    else:
        report["terminal"] = "complete"

    # AFTER the terminal verdict, and it does not change it. The terminal is a
    # statement about the VENUE half — did every selected row get a durable
    # answer — and a retirement pass that retires nothing is the normal reading
    # (a stamped row is only retirable once the floor passes it). Folding these
    # counters into that verdict would make a healthy capture read `partial`.
    report.update(await _retire_rows_the_venue_voided(maker, now))
    return report
