"""#6126 — the historical cleanup: retire the 99% openings Kalshi's empty book minted.

THE SHIP: a settled ladder stops telling you an eliminated player opened at 99%.
`https://bainluck.com/futures/34277822` (US Open Men's Singles), production
2026-09-14 — three players who went out early each print **OPEN 99%**:

    Alexander Bublik   OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Cameron Norrie     OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Dino Prizmic       OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Jannik Sinner      OPEN 48%    opening_captured_at 2026-06-09 08:47:04.007243+00

Sinner is the control and he is the whole tell: an honest row carries a real
`opening_source` (`bid_ask_midpoint`) and a poller timestamp with microseconds,
while all three 99% rows share one instant exactly on the hour and carry no
source at all. Bublik's very next stored point is **0.13** — the series refutes
its own first point one hour later.

CAUSE, READ AT THE VENUE (notice 26), NOT INFERRED FROM OUR MIRROR: Kalshi opens
an untraded market at **bid 0.0000 / ask 0.9900**. Both candle reducers read
rule 3 as "trust a lone quote unless it is exactly 1.00", so that default book
was published as a probability.

    PREVENTION SHIPPED FIRST — `aadbe27ab` (PR #6131, CERT-2853 GREEN) makes
    `candle_yes_price` and `normalize_candle` refuse a lone ask above
    `app.utils.kalshi_empty_book.ASK_ONLY_TRUSTED_MAX`. This script is the owed
    DATA REPAIR for the rows written before that landed.

    THE TAP MUST BE OFF BEFORE THIS RUNS — repair_2871's lesson, and this script
    does not take it on trust. `tap_is_off()` pushes the venue's OWN opening
    candle through the deployed reducer and requires `None` back. It is not a
    version string or a map lookup: it is the defect itself, re-enacted in the
    interpreter that is about to write.

    THE TAP IS ON THE MAIN APP, NOT `bainluck-heavy` — re-derived, not assumed.
    `HEAVY_TASKS` has 33 members and the only Kalshi one is
    `app.tasks.poll_kalshi_markets`, which never reads a candle (zero
    candlestick references in `_poll_kalshi_markets`). Every caller of the two
    reducers — `kalshi_cliff`, `_backfill_kalshi_price_history`,
    `_backfill_kalshi_chart_history`, `event_chart_backfill` — is absent from
    `HEAVY_TASKS`, so the code that could re-mint these rows is what is deployed
    to `bainluck`. That is why `PRODUCER_APP` is the main app here and
    `bainluck-heavy` in repair_5621; the answer differs per population and is
    measured each time rather than copied.

------------------------------------------------------------------------------
THE POPULATION, AND WHY A SHARED VALUE IS NOT A FINGERPRINT
------------------------------------------------------------------------------

Measured on production 2026-09-14 11:0xZ, whole population, no sampling.

The obvious predicate — `opening_probability = 0.99 AND opening_source IS NULL`
— is WRONG and is not used here. `opening_source IS NULL` is the majority state
of the table for ordinary historical reasons, and 0.99 is a value honest rows
also carry. The discriminator is the TIMESTAMP'S PRECISION: a candle's
`end_period_ts` lands exactly on the hour, where the poller's `now` carries
microseconds. Splitting the 0.99 Kalshi legs four ways:

    exact hour + no source   4,402 legs / 610 markets   <- this rail
    off-hour   + no source  17,273 legs
    off-hour   + a source    5,135 legs
    exact hour + a source       45 legs

Only the first band is this writer's. But "written by this rail" still is not
"wrong" — a market really can be at 99c on the hour. So NOTHING here is repaired
on the fingerprint alone. ONE test, and only one, authorises a write:

  SUM    the leg shares its exact opening instant with another leg of the same
         market, also at exactly 0.99, AND that market is mutually exclusive.
         Two exclusive legs at 0.99 is 1.98, which is arithmetically
         impossible; up to 140 legs share one instant (138.6). This is the venue
         default applied field-wide, and it refutes itself on the row.

SERIES IS NO LONGER AN AUTHORITY — CERT-2855's required repair, and it was right.
The earlier version of this script also repaired a leg whose own next stored
point was exactly 0.99 or below 0.90 ("the series refutes its first point", as
Bublik's 0.99 -> 0.13 does). That test does not survive contact with what the
candle rail actually stores. The rail records a price and a time and NO book, so
a genuine 0.99 trade and the untraded default book are byte-identical in our
data; the only thing "next point 0.89" adds is that the price moved, and PRICE
MOVEMENT DOES NOT REFUTE A PRIOR PROBABILITY. It also cut arbitrarily: the same
real trade followed by 0.89 was deleted and followed by 0.95 was refused, on a
cliff at 0.90 that nothing in the venue's behaviour puts there. A series-only
leg is therefore excluded unless immutable venue candle history proves its
opening was bid 0 / no trade / ask 0.99 — a proof this script does not attempt
and does not fake (see THE 127, below). `series_refutes` is still computed and
still printed, as a reason a leg was refused. It never writes.

Measured on production 2026-09-14 12:05Z, whole band, no sampling:

    SUM + exclusive           ->  REPAIRED                        953
    SUM, not exclusive        ->  refused, gotcha #23           3,239
    series only               ->  refused, CERT-2855              127
    nothing refutes it        ->  refused                          87
    ------------------------------------------------------------------
    band                                                        4,406

953 IS STILL WELL SHORT OF THE 4,315 THE FIRST PRESENTATION CLAIMED, and it is
reached by adding a second sound witness, never by widening a band. CERT-2857's
version repaired 219; the venue witness below adds 734 and takes nothing away.

WHAT A READER ACTUALLY SEES TODAY, COUNTED PAGE BY PAGE RATHER THAN LEG BY LEG.
A stored 0.99 opening is only visible where the page prints it, and #5539's
serve-time coherence rule (`app/utils/field_opening_coherence.py`) already
withholds the WHOLE opening column from a mutually exclusive field whose
openings sum past 3.0 at a mean of 0.4 or more — which is most of this
population. Measured against the served payload of all 57 markets the venue arm
admits (`GET /api/futures/{id}`, `openings_withheld`, 2026-09-14 12:20Z):

    45 markets   openings ALREADY withheld — the repair restores a suppressed
                 column rather than changing a number a reader can see today
    12 markets   openings PUBLISHED, carrying 93 legs printing OPEN 99% NOW
                 (3 of them are market 34277822, which CERT-2857 already fixes)

So the venue arm's reader-visible increment today is 90 legs across 11 pages,
and the honest headline is a page, not a leg count. `/futures/25927225`,
*Austrian Alpine Open presented by Kitzbühel Tirol Winner*, settled: the winner
Kota Kaneko shows OPEN 12% and the runner-up OPEN 19%, while Gregorio De Leo,
Brandon Robinson-Thompson, Alexander Levy, Austin Bautista, Jason Scrivener,
Darius Van Driel and Fred Biondi each read **OPEN 99% · Lost · 0%** — seven of
them above the fold, 34 in the market. The original reader-visible defect, the
settled US Open Men's Singles ladder (market 34277822: 48 outcomes, one winner,
`sum(current_probability)` exactly 1.000, three 99% legs in one instant), is
SUM-backed under both witnesses and stays repaired.

THE 45 ARE NOT A SECOND SHIP AND ARE NOT CLAIMED AS ONE. Repairing them makes
their fields coherent again, which is the condition #5539's rule withholds on,
so the column should come back — but that is a consequence of another module's
serve-time verdict, it is not asserted here, and it is not counted in any
before/after this script prints. The widest of them is the KLM Open End of Round
1 Leader ladder (market 30782643): 151 of 156 golfers carry a 0.99 opening, 140
stamped in the same second, and a reader currently sees no opening column at all.

EXCLUSIVITY HAS TWO WITNESSES, AND THE REASON IS THAT EACH IS BLIND WHERE THE
OTHER SEES. This is what CERT-2857's version named as owed and did not build; it
is built here, additively, on venue-read proof rather than on a wider band.

  * PRICE (`price_exclusive`): the market's outcomes sum to ~1, i.e.
    `sum(current_probability) BETWEEN 0.85 AND 1.25`. This is the arm CERT-2857
    graded and it is unchanged. Its blind spot is that THE DEFECT IS AN INPUT TO
    THE SCREEN: an untraded market's frozen 0.99 default book is also its
    current price, so "Dow Jones price on Jul 28 at 2pm" — 80 mutually exclusive
    buckets, 73 of them still reading 0.99 — sums to 72.27 and screens out as
    "not exclusive". The rows the screen is most confident about rejecting are
    the most obviously broken ones.
  * VENUE (`venue_exclusive`): `futures_markets.mutually_exclusive`, which the
    Kalshi ingest copies from `mutually_exclusive` on the venue's own event
    (`tasks/kalshi.py`, `services/kalshi_api.py`). Price-independent, so the
    frozen book cannot defeat it.

SOUND WHEN TRUE, UNSOUND WHEN FALSE — WHICH IS WHY THE VENUE FLAG ONLY EVER ADDS.
Kalshi sets it FALSE on plain partitions: `KXDJI-26JUL2316` (70 price buckets),
`KXTEMPAUSH-26JUL0900` (10 temperature buckets) and
`KXMLBINNINGTOTAL-26AUG211840STLPHI-8` (2 outcomes summing to 1.00) are all
FALSE at the venue, read 2026-09-14 12:10Z. So the flag may never be used to
REFUSE, and `OR` is the only shape it can take. In the TRUE direction it was
read at the venue for every market this arm admits — not sampled: all 57
markets / 870 legs were fetched from `GET /trade-api/v2/events/{ticker}`, and
`mutually_exclusive` is explicitly present in 57/57 payloads and true in 57/57.
The per-ticker table is in the cert body. Every one is a one-winner contract by
its own title — round leaders, correct scores, champions, fastest lap, top
artist, #1 ranked team.

WHAT THE PRICE ARM STILL LETS THROUGH, SAID OUT LOUD. It admits 83 legs in 17
markets the venue calls non-exclusive, and 16 of those 17 are real partitions
the venue mislabels. The seventeenth is `KXNFLAWARDFIN-27DPOY` ("Defensive
Player of the Year Finalists", 40 outcomes, currently summing to 0.95, 9 band
legs) — genuinely multi-winner, admitted by arithmetic coincidence. It is a
pre-existing false positive of the arm CERT-2857 graded, it is NOT inherited by
the venue arm, and no gate is added for it here: the shape classifier records no
`expected_winners > 1` anywhere in this band, so such a clause would be vacuous
today and would be a guard that cannot fire.

THE 127, AND WHY NO VENUE FETCH IS ATTEMPTED. Venue proof is not uniformly
impossible: 59 of the 127 are past Kalshi's measured MARKET-data purge (gotcha
#35, >=74/<86 days — `app/utils/kalshi_retention.py`), 66 are still inside it,
2 sit in the grey band. So this is a choice, not a wall: fetching 127 candle
histories from a one-off dyno to enlarge a repair by 3% is not worth the write
surface during launch week. They are refused, counted by name in the dry run,
and recoverable later by anyone who wants to pay for the venue read.

THE REFUSED COHORT IS THE POINT, NOT THE RESIDUE. 3,453 of 4,406 legs are left
exactly as they are. An absent correction is a gap; a fabricated one is a lie a
curve then grades.

SCOPED TO 0.99 ON PURPOSE. The reducer refuses any lone ask above 0.50, so in
principle other values were mintable. They are NOT repaired here: the candle
rail stores no book (NULL bid/ask), so for any other value there is no stored
fingerprint separating it from an honest price, and a repair that cannot name
its population does not get to run. 0.99 is the venue's measured default and is
the only value this script claims.

------------------------------------------------------------------------------
WHAT IS WRITTEN
------------------------------------------------------------------------------

Per repaired leg, in this order:

  1. futures_odds_snapshots   DELETE the LEADING RUN of bad-shape rows
  2. futures_outcomes         opening_probability  -> first surviving point
                              opening_captured_at  -> its timestamp
                                                   (both NULL if none survives)

THE LEADING RUN, NOT JUST THE FIRST ROW — this is the correction the measurement
forced. For 1,768 legs in the band the next point is ALSO exactly 0.99, because
an untraded market keeps serving the same default book hour after hour. Deleting
only the opening point would leave the curve starting at 99% anyway, one hour
later, and the repair would read as done while the reader saw no change. So the
run is deleted up to the first row that is not this shape, and never past it: a
0.99 appearing LATER in a series is a genuine move to near-certainty and is left
alone.

AND THE RUN IS DEFINED BY THE FIELD'S ARITHMETIC, NOT BY THE VALUE 0.99 (#6159).
The first version of this run pinned its last clause to `probability = 0.99`.
Three of that predicate's four clauses describe a SHAPE — kalshi, no book,
exactly on the hour — and the fourth was a VALUE, and the rail also serves
0.989, 0.98 and 0.97 on rows with the identical shape. Those survived the delete
and BECAME the re-derived opening: 216 of 953 legs came out at >= 0.95, 204 of
them on outcomes that lost. The shape was the evidence; the number was a sample
of it.

So the run now continues while the row is a rail row AND EITHER it carries the
venue's default value OR the field refutes it at that instant — two legs of one
exclusive market whose stored prices alone exceed the ceiling the whole field
must sit under, with this leg the LARGER of the two (`_FIELD_REFUTES`). No
constant is introduced:
:data:`EXCLUSIVE_SUM_MAX` is the upper bound of the `price_exclusive` screen
this script already uses, and the argument is the one the opening test already
makes out loud — "two exclusive legs at 0.99 is 1.98, which is arithmetically
impossible" — with the 0.99 taken out of it.

MEASURED ON PRODUCTION, 2026-09-14 13:4x-14:1xZ, all 953 legs, no sampling. The
model reproduces the shipped script's own numbers first (band 4,407; 953 legs;
216 re-derived >= 0.95; 46 blank; KLM sum 58.32 / mean 0.3787), which is the
control that says it is modelling this script and not a lookalike:

                                        shipped     with the field witness
    snapshot rows deleted                 2,796                      7,549
    legs re-derived to >= 0.95              216                         11
       of those, on an outcome that LOST    204                          9
    legs re-derived to a blank               46                         51
    legs whose published opening moves        -                        229
    WINNERS whose published opening moves     0                          0

NOT ONE STORED POINT BELOW 0.60 IS DELETED that the shipped version kept: the
4,753 rows this adds are 2,926 at >= 0.95, 1,392 in [0.80, 0.95) and 435 in
[0.60, 0.80). The rule reaches up, never down.

THE WINNER LINE IS THE ONE THAT MATTERS, and it is why this is neither of the
two forms #6159 sized. Reusing `classify_field_openings` at the instant reaches
296 legs and deletes the genuine near-certain opening of 2 winners; a pairwise
rule keyed on ">= 0.95" needs a 0.95 nobody derived. The pair-versus-ceiling
rule takes neither. It extends 284 runs, 2 of them on a winner's leg — Julien
Guerrier (KLM) and Frances Tiafoe (ATP Halle) — and NEITHER winner's published
opening moves, because in both an earlier honest point already survives the
longer delete: Guerrier opens at 0.650 under both rules, and Tiafoe is refused
outright by the no-op rule below. The specimen that shows the value pin was the
wrong witness is the loser cohort: 51 KLM golfers re-derive to exactly 0.989
under the shipped rule, which nobody traded 51 times.

AND THE CONSTANT IS NOT LOAD-BEARING, which is the other half of "not tuned".
Sweeping the pairwise ceiling across 1.05 / 1.10 / 1.25 / 1.50 / 1.80 leaves the
outcome unchanged at every step (measured on the pair rule before the
larger-member clause: 7 legs >= 0.95, 51 blank, 0 winners moved at all five);
the cliff is at 2.00, where 2 x 0.99 stops clearing it and the rule collapses
back to the value pin. 1.25 is chosen inside that plateau because the script
already uses it, not because the data came out nicely there.

WHAT IT STILL LEAVES, SAID OUT LOUD. Eleven legs keep an opening >= 0.95 that
nothing refutes: at their instant no partner leg of the field carries a price at
or below theirs, so the arithmetic is silent, and a lone 0.98 among longshots is
a coherent distribution. Two of the eleven are winners and correct; nine are
not, and four of those nine are the price paid for the larger-member clause —
a high leg whose only high partner sits ABOVE it is spared, because the partner
is then the member that cannot be right.
They are left exactly as they are — CERT-2855's line, unchanged: an absent
correction is a gap, a fabricated one is a lie a curve then grades. The KLM
ladder keeps 4 such legs where it currently has 55.

A REPAIR THAT WOULD PUBLISH THE VALUE IT IS RETIRING IS REFUSED (see
:func:`repair_is_a_no_op`). Six legs re-derive onto a bookless Kalshi row
carrying 0.99 stamped OFF the hour — the band's own declared exclusion, a row
this script cannot claim, surfacing in the re-derive rather than in the
population. Deleting their runs costs 27 real chart points and leaves the page
reading OPEN 99% exactly as before, so those legs are dropped from the plan and
counted. 953 planned legs become 947.

WHAT A READER GETS, COUNTED ON THE SERVED SHAPE. Applying #5539's serve-time
verdict to the post-repair field of all 74 markets — the only way to count what
is actually printed, since a withheld column shows nothing at all:

                            markets withholding     legs printing OPEN >= 95%
                            the opening column      on a page that publishes it
    today                             52                     104
    shipped repair                    18                      79
    with the field witness            13                       9

That is the ship: 104 fabricated near-certainties a reader can see today, 9
afterwards, and 39 markets get their opening column back instead of 34.

`opening_source` is deliberately NOT written. It is NULL on these rows because
the rail never set one, and the surviving candle row it is re-derived from has
no source either; inventing one would fabricate provenance. Its value is still
copied into the backup so the undo is exact.

------------------------------------------------------------------------------
REVERSIBILITY (D51(b))
------------------------------------------------------------------------------

`--backup` copies the FULL deleted snapshot rows and the three opening columns
into `backup_6126_snapshots` / `backup_6126_openings`. The undo re-INSERTs the
snapshots and restores the openings:

    heroku run:detached -a bainluck -- \
        python3 scripts/restore_6126_candle_lone_ask_openings.py --apply

Runtime DDL, attended invocation only — `CREATE TABLE IF NOT EXISTS backup_*`
behind `--backup`, run by a person against a named app. Not migration-class
(notice 47(c)): nothing here executes as a consequence of merge or release.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PRODUCER_APP = "bainluck"

#: The venue's own opening book, read 2026-09-14 from
#: `KXWTACHALLENGERMATCH-26SEP14ZELNAJ-NAJ` candlesticks. This is the defect's
#: input, kept verbatim so `tap_is_off` re-enacts it rather than describing it.
#:
#: Kalshi publishes candle prices ONLY in the `*_dollars` spellings and ONLY as
#: strings — the cents keys are absent on this payload. Getting that wrong is
#: not a harmless typo here: a misspelled candle carries no readable price, both
#: reducers correctly answer `None` for want of data, and the tap check passes
#: VACUOUSLY against an unfixed deploy. Hence `TRADED_CONTROL_CANDLE`.
VENUE_DEFAULT_CANDLE = {
    "yes_bid": {"close_dollars": "0.0000"},
    "yes_ask": {"close_dollars": "0.9900"},
}

#: A real 0.99 trade — the population the refusal must NOT take. It also makes
#: `tap_is_off` falsifiable: a reducer stubbed to return `None` for everything
#: would satisfy the refusal while pricing nothing, and this control catches it.
TRADED_CONTROL_CANDLE = {"price": {"close_dollars": "0.9900"}}

#: The value Kalshi's untraded default book reduces to, and therefore the only
#: value this script's population predicate admits. Named rather than repeated
#: because the SAME number is three different claims — the band's fingerprint,
#: the leading run's value pin, and the value the repair must not re-publish —
#: and a literal in three places is three chances for them to drift apart.
VENUE_DEFAULT_PROBABILITY = 0.99

#: How far a one-winner Kalshi field's stored prices may sum from certainty and
#: still be read as a priced field. These are the `price_exclusive` bounds
#: CERT-2857 graded, lifted out of the SQL so the leading run can reuse the
#: upper one instead of restating it — see `_FIELD_REFUTES`.
EXCLUSIVE_SUM_MIN = 0.85
EXCLUSIVE_SUM_MAX = 1.25

#: One row per leg in the fingerprint band, with both refutation tests and the
#: exclusivity check evaluated in SQL so the dry run prints exactly what
#: `--apply` would act on.
_POPULATION_SQL = f"""
WITH band AS (
    SELECT o.id, o.market_id, o.name,
           o.opening_probability, o.opening_captured_at AS ts, o.opening_source,
           m.mutually_exclusive
      FROM futures_outcomes o
      JOIN futures_markets m ON m.id = o.market_id
     WHERE m.source = 'kalshi'
       AND o.opening_probability = {VENUE_DEFAULT_PROBABILITY}
       AND o.opening_source IS NULL
       AND o.opening_captured_at IS NOT NULL
       AND date_part('minute', o.opening_captured_at) = 0
       AND date_part('second', o.opening_captured_at) = 0
),
grp AS (
    SELECT market_id, ts, count(*) AS n FROM band GROUP BY 1, 2
),
excl AS (
    -- Gotcha #23: a futures market's outcomes are not always mutually
    -- exclusive. A market whose own outcomes sum to roughly one is; that is
    -- what makes "two legs at 0.99" arithmetically impossible rather than
    -- merely surprising.
    SELECT x.market_id, sum(x.current_probability) AS cur_sum
      FROM futures_outcomes x
      JOIN (SELECT DISTINCT market_id FROM band) b ON b.market_id = x.market_id
     GROUP BY 1
)
SELECT b.id,
       b.market_id,
       b.name,
       b.ts,
       b.opening_source,
       (g.n > 1)                                         AS sum_refutes,
       (b.mutually_exclusive IS TRUE)                    AS venue_exclusive,
       (e.cur_sum BETWEEN {EXCLUSIVE_SUM_MIN} AND {EXCLUSIVE_SUM_MAX})
                                                         AS price_exclusive,
       nxt.p                                             AS next_p,
       (nxt.p = {VENUE_DEFAULT_PROBABILITY} OR nxt.p < 0.90)
                                                         AS series_refutes
  FROM band b
  JOIN grp  g ON g.market_id = b.market_id AND g.ts = b.ts
  LEFT JOIN excl e ON e.market_id = b.market_id
  LEFT JOIN LATERAL (
        SELECT s.probability AS p
          FROM futures_odds_snapshots s
         WHERE s.outcome_id = b.id
           AND s.captured_at > b.ts
         ORDER BY s.captured_at
         LIMIT 1
  ) nxt ON true
 ORDER BY b.market_id, b.id
"""

#: The RAIL, as stored: which writer put this row here. The candle rail writes
#: no book at all, which is why `app.utils.kalshi_empty_book`'s
#: `lone_ask_on_empty_book_sql` (which tests `yes_bid`) cannot see these rows —
#: noted in that module too — and its `end_period_ts` lands exactly on the hour
#: where the poller's `now` carries microseconds.
#:
#: This is a statement about PROVENANCE and carries no claim that the row is
#: wrong. Everything that authorises a delete is in `_FIELD_REFUTES` and the
#: value pin below.
_RAIL_SHAPE = (
    "s.bookmaker = 'kalshi' "
    "AND s.yes_bid IS NULL AND s.yes_ask IS NULL "
    "AND date_part('minute', s.captured_at) = 0 "
    "AND date_part('second', s.captured_at) = 0"
)

#: THE FIELD'S OWN ARITHMETIC, EVALUATED AT ONE INSTANT. Two outcomes of a
#: one-winner market cannot both happen, so their true probabilities sum to at
#: most 1; stored prices may exceed that by the book's overround, and
#: :data:`EXCLUSIVE_SUM_MAX` is this script's own declaration of how far a
#: whole Kalshi field may sum and still read as priced. A single PAIR that
#: already exceeds the whole field's ceiling therefore leaves no room for the
#: other legs, and the market has other legs. That is the same argument the
#: opening test makes — "two exclusive legs at 0.99 is 1.98" — stated once
#: instead of pinned to the one value the venue happened to serve.
#:
#: The leg's market is exclusive by construction: this runs only for legs
#: `classify()` admitted, and admission requires a witness of exclusivity.
#:
#: `peer.probability <= s.probability` IS LOAD-BEARING AND IT IS NOT A MARGIN.
#: An impossible pair says one of the two is wrong; it does not say which. The
#: member this script may act on is the one claiming the larger share of a
#: certainty already spoken for — never the smaller, which may be the honest
#: price the other leg is crowding out. Without it the rule deleted 15 real
#: mid-band prices on production, three of them on `Over 0.5 / 1.5 / 2.5 1H
#: goals` ladders, where the market is NOT exclusive at all (a pre-existing
#: gotcha #23 false positive of the screen) and 0.98 + 0.495 is perfectly
#: coherent for nested thresholds. The test is `<=`, not `<`, so a field frozen
#: at one value still refutes itself — the EXISTS is existential, so every leg
#: of a cluster finds a partner at its own level and the whole cluster falls.
#:
#: `s.probability > EXCLUSIVE_SUM_MAX / 2` is arithmetic, not a tuning knob:
#: with the partner bounded above by this row, the pair can reach at most
#: `2 * s.probability`, so a row at or below half the ceiling can never be
#: refuted by anything and the subquery would be wasted work on every longshot.
_FIELD_REFUTES = f"""s.probability > {EXCLUSIVE_SUM_MAX} / 2.0 AND EXISTS (
                SELECT 1
                  FROM futures_odds_snapshots peer
                  JOIN futures_outcomes peer_leg ON peer_leg.id = peer.outcome_id
                 WHERE peer_leg.market_id = :mid
                   AND peer.outcome_id <> s.outcome_id
                   AND peer.captured_at = s.captured_at
                   AND peer.bookmaker = 'kalshi'
                   AND peer.probability <= s.probability
                   AND peer.probability + s.probability > {EXCLUSIVE_SUM_MAX}
           )"""

#: `_BAD_SHAPE` USED TO LIVE HERE AND IS DELIBERATELY GONE. "This row is the
#: untraded default book" is now a decision with two witnesses, so it belongs in
#: :func:`is_default_book` where it can be tested against rows instead of by
#: scanning a string. Keeping the old constant beside the new function would
#: have left a predicate nothing executes and a guard that still passed on it —
#: CodeQL flagged exactly that on the first push of this change.

#: Every stored point of one leg, with the two facts :func:`leading_run` needs
#: decided in SQL. The WHOLE series is read, not just the part from the stored
#: opening instant, because the re-derive picks the earliest row that SURVIVES
#: and 155 of these legs carry points stamped BEFORE their own stored opening.
#: A plan that cannot see those cannot see what it is about to publish.
_RUN_CANDIDATES_SQL = f"""
SELECT s.id,
       s.captured_at,
       s.probability,
       (s.captured_at >= :ts)  AS from_ts,
       ({_RAIL_SHAPE})         AS rail,
       ({_FIELD_REFUTES})      AS field_refutes
  FROM futures_odds_snapshots s
 WHERE s.outcome_id = :oid
 ORDER BY s.captured_at, s.id
"""


def is_default_book(row):
    """True when this stored point is Kalshi's untraded default book.

    Two witnesses, and the OR is deliberate — each is blind where the other
    sees, the same shape the exclusivity test takes:

      * the FIELD refutes it at that instant (`_FIELD_REFUTES`). Value-free, so
        it reaches the 0.989 / 0.98 / 0.97 the rail also serves.
      * the row carries the venue's measured default VALUE. Instant-free, so it
        reaches a leg whose field partners have no stored point at that moment.

    Both are gated on the rail: this repair answers for the candle rail and no
    other writer. A poller row carrying a real book is not this script's to
    judge, however odd its number looks.
    """
    return bool(row.rail) and (
        float(row.probability) == VENUE_DEFAULT_PROBABILITY or bool(row.field_refutes)
    )


def leading_run(rows):
    """`(ids to delete, the point that becomes the new opening)`.

    `rows` is one leg's whole stored series in `captured_at` order, as
    :data:`_RUN_CANDIDATES_SQL` returns it.

    THE RUN IS A PREFIX AND STOPS AT THE FIRST HONEST POINT. A 0.99 appearing
    LATER in a series is a genuine move to near-certainty and is left alone;
    losing that bound would delete real points from the middle of a curve.

    THE RUN STARTS AT THE STORED OPENING, THE SURVIVOR IS SOUGHT OVER THE WHOLE
    SERIES. Those are different spans on purpose. The run is what this repair
    has a warrant to delete — the warrant was issued about the opening instant.
    The survivor is whatever a reader will actually see afterwards, and a point
    stamped before the stored opening is still the first point of the curve.
    """
    doomed = []
    for row in rows:
        if not row.from_ts:
            continue
        if not is_default_book(row):
            break
        doomed.append(row.id)

    cut = set(doomed)
    survivor = next((row for row in rows if row.id not in cut), None)
    return doomed, survivor


def repair_is_a_no_op(survivor):
    """True when deleting the run would change nothing a reader can see.

    Six legs re-derive to a point carrying the very value being retired — five
    onto a bookless Kalshi row at 0.99 stamped OFF the hour (the band's own
    declared exclusion, a row this script cannot claim), one onto a row whose
    book is empty on both sides, which is a different writer's rail. For those
    the delete costs 27 real chart points and buys the reader nothing: the page
    still reads OPEN 99%.

    This is the script's own argument about the leading run, applied to its
    result — "the repair would read as done while the reader saw no change."
    It is a post-condition on the OUTCOME, not a predicate on the population,
    which is why it may test a value where #5539 measured that a value rule
    must never choose who gets repaired.
    """
    return (
        survivor is not None
        and float(survivor.probability) == VENUE_DEFAULT_PROBABILITY
    )


def tap_is_off():
    """The prevention is deployed *in this interpreter*.

    Not a version string and not a map lookup: the venue's actual opening book
    is pushed through both deployed reducers and both must answer `None`. If
    either still returns 0.99 the fix is not on this dyno, and applying would
    repair rows the next backfill immediately re-mints.

    BOTH HALVES ARE REQUIRED, and the second is the one that makes the first
    mean something. A refusal alone is satisfied by any reducer that prices
    nothing at all — including one broken by an unrelated change, and including
    the vacuous pass a misspelled fixture would produce. So a real 0.99 trade
    must still come back as 0.99 through both.

    Deliberately narrow: this can only answer for the process it runs in.
    `wrong_app_refusal` is what makes that process the right one.
    """
    from app.tasks.event_chart_backfill import normalize_candle
    from app.utils.kalshi_candle_price import candle_yes_price

    refuses_default = (
        candle_yes_price(VENUE_DEFAULT_CANDLE) is None
        and normalize_candle(VENUE_DEFAULT_CANDLE) is None
    )
    still_prices_a_trade = (
        candle_yes_price(TRADED_CONTROL_CANDLE) == 0.99
        and normalize_candle(TRADED_CONTROL_CANDLE) == 0.99
    )
    return refuses_default and still_prices_a_trade


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must happen on the
    producer's app, because that is the only place where `tap_is_off()` is
    inspecting the code that could re-mint these rows.

    Unset means we are not on a dyno at all — a laptop pointed at the production
    database with whatever happens to be checked out, which is precisely the
    case this gate exists to stop, so it refuses too rather than falling
    through.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. The two "
        "candle reducers are reached only by tasks that are NOT in HEAVY_TASKS "
        f"({', '.join(_REDUCER_CALLERS)}), so the code that can re-mint these "
        f"rows is what is deployed to '{PRODUCER_APP}'. Run from anywhere else "
        "and the tap check above passes against the wrong interpreter while the "
        "real producer keeps writing. Re-run with "
        f"`heroku run:detached -a {PRODUCER_APP}`."
    )


_REDUCER_CALLERS = (
    "kalshi_cliff",
    "_backfill_kalshi_price_history",
    "_backfill_kalshi_chart_history",
    "event_chart_backfill",
)


def classify(row):
    """None to REPAIR, or the reason this leg is refused.

    SUM under exclusivity is the ONLY authority to write. Exclusivity now has
    TWO independent witnesses and either one is enough, because each is blind
    where the other sees (measured; see EXCLUSIVITY HAS TWO WITNESSES above):

      * `venue_exclusive` — Kalshi's own `mutually_exclusive` on the event.
        Price-independent, so the frozen default book cannot defeat it.
        Sound when TRUE, unsound when FALSE, which is why it only ever adds.
      * `price_exclusive` — the market's outcomes sum to ~1. Catches the
        partitions Kalshi flags FALSE, and is the arm CERT-2857 graded.

    Both are NULL-safe: `venue_exclusive` is `IS TRUE` in SQL, and
    `price_exclusive` is NULL for a market with no priced outcomes, where `or`
    on a NULL is still falsey — unknown refuses, it does not pass.

    `series_refutes` deliberately appears only as a refusal REASON below.
    Restoring it as an early `return None` is the defect CERT-2855 named:
    the candle rail stores no book, so a real 0.99 trade and the untraded
    default are identical in our data and the later price tells us only that
    the price moved.
    """
    if row.sum_refutes and (row.venue_exclusive or row.price_exclusive):
        return None
    if row.sum_refutes:
        return (
            "sum-refuted leg in a market the venue does not call mutually "
            "exclusive and whose outcomes do not sum to ~1 (gotcha #23)"
        )
    if row.series_refutes:
        return (
            "series-only leg — price movement does not refute a prior "
            "probability, and no venue candle proves an empty book"
        )
    if row.next_p is None:
        return "singleton with no later point — nothing refutes it"
    return (
        "singleton whose next point sits in [0.90, 0.99) — consistent with a "
        "real favourite"
    )


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    if (args.apply or args.backup) and not tap_is_off():
        print(
            "REFUSING: the deployed reducers still price Kalshi's untraded "
            "bid-0.00/ask-0.99 book at 0.99. aadbe27ab (PR #6131) is not on "
            "this dyno, so any repair would be re-minted by the next backfill. "
            "Deploy it, then re-run."
        )
        return 2

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        rows = (await s.execute(text(_POPULATION_SQL))).fetchall()

        repair, refused = [], []
        for r in rows:
            why = classify(r)
            (refused if why else repair).append((r, why))

        print(f"\n=== population === (band {len(rows)} legs)")
        print(f"  repair : {len(repair)}")
        print(f"  refused: {len(refused)}")
        by_reason = {}
        for _, why in refused:
            by_reason[why] = by_reason.get(why, 0) + 1
        for why, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f"      {n:5d}  {why}")

        # The leading run per repaired leg, and the point that will become the
        # new opening. Read for every mode, including the dry run, so the
        # attended operator sees the real write plan before authorising it.
        plan, no_ops = [], []
        for r, _ in repair:
            rows = (
                await s.execute(
                    text(_RUN_CANDIDATES_SQL),
                    {"oid": r.id, "mid": r.market_id, "ts": r.ts},
                )
            ).fetchall()
            ids, survivor = leading_run(rows)
            if repair_is_a_no_op(survivor):
                no_ops.append((r, len(ids)))
                continue
            plan.append((r, ids, survivor))

        if no_ops:
            print(
                f"\n=== refused as no-ops === {len(no_ops)} legs "
                f"({sum(n for _, n in no_ops)} rows NOT deleted)"
            )
            print(
                "      the earliest surviving point already carries the value "
                "being retired, so the page would not change"
            )

        deleted_total = sum(len(ids) for _, ids, _ in plan)
        print(f"\n=== snapshot rows in the leading runs === {deleted_total}")
        multi = sum(1 for _, ids, _ in plan if len(ids) > 1)
        print(f"  legs whose default book persisted past the opening: {multi}")
        print(
            "  what the plan publishes: "
            f"{sum(1 for _, _, sv in plan if sv is not None)} legs re-derive to "
            f"an earlier point, {sum(1 for _, _, sv in plan if sv is None)} go "
            "blank because the leg's whole stored series was the default book"
        )

        if args.limit:
            plan = plan[: args.limit]
            print(f"  (--limit {args.limit}: acting on {len(plan)} legs)")

        print("\n=== sample ===")
        for r, ids, survivor in plan[:8]:
            opens = "blank" if survivor is None else str(survivor.probability)
            print(
                f"  {r.id:>10}  {r.name[:34]:<34} {str(r.ts)[:19]}  "
                f"run={len(ids):<3} opens={opens}"
            )

        if not (args.backup or args.apply):
            print("\ndry run — nothing written")
            return 0

        outcome_ids = [r.id for r, _, _ in plan]
        snap_ids = [i for _, ids, _ in plan for i in ids]

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_6126_snapshots "
                    "(id bigint PRIMARY KEY, outcome_id bigint, bookmaker text, "
                    "probability numeric, american_odds integer, yes_bid numeric, "
                    "yes_ask numeric, last_price numeric, captured_at timestamptz, "
                    "reading_count integer, valid_until timestamptz)"
                )
            )
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_6126_openings "
                    "(id bigint PRIMARY KEY, opening_probability numeric, "
                    "opening_captured_at timestamptz, opening_source text)"
                )
            )
            await s.execute(
                text(
                    # DO UPDATE, not DO NOTHING: a second --backup after an
                    # unrelated writer moved a row must REFRESH it, or the undo
                    # restores a value that was never the one we overwrote.
                    "INSERT INTO backup_6126_snapshots SELECT id, outcome_id, "
                    "bookmaker, probability, american_odds, yes_bid, yes_ask, "
                    "last_price, captured_at, reading_count, valid_until "
                    "FROM futures_odds_snapshots WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "probability = EXCLUDED.probability, "
                    "captured_at = EXCLUDED.captured_at"
                ),
                {"ids": snap_ids},
            )
            await s.execute(
                text(
                    "INSERT INTO backup_6126_openings "
                    "SELECT id, opening_probability, opening_captured_at, "
                    "opening_source FROM futures_outcomes WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "opening_probability = EXCLUDED.opening_probability, "
                    "opening_captured_at = EXCLUDED.opening_captured_at, "
                    "opening_source = EXCLUDED.opening_source"
                ),
                {"ids": outcome_ids},
            )
            await s.commit()
            print(
                f"  copied {len(snap_ids)} snapshot rows + "
                f"{len(outcome_ids)} openings"
            )

        if args.apply:
            covered = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM backup_6126_openings "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": outcome_ids},
                )
            ).scalar()
            if covered != len(outcome_ids):
                print(
                    f"REFUSING to apply: backup covers {covered} of "
                    f"{len(outcome_ids)} openings. Run --backup first."
                )
                return 2

            print("\n=== apply ===")
            await s.execute(
                text("DELETE FROM futures_odds_snapshots WHERE id = ANY(:ids)"),
                {"ids": snap_ids},
            )
            # Re-derive AFTER the delete, so "earliest surviving" means what it
            # says. NULL when nothing survives: the leg's whole stored series
            # was the venue's default book, and an absent opening is the honest
            # answer — the same one the shipped reducer now gives.
            await s.execute(
                text(
                    "UPDATE futures_outcomes o SET "
                    "opening_probability = nxt.p, opening_captured_at = nxt.ts "
                    "FROM (SELECT o2.id, f.probability AS p, f.captured_at AS ts "
                    "        FROM futures_outcomes o2 "
                    "        LEFT JOIN LATERAL ("
                    "             SELECT s.probability, s.captured_at "
                    "               FROM futures_odds_snapshots s "
                    "              WHERE s.outcome_id = o2.id "
                    # (captured_at, id) — the same tie-break `leading_run` uses,
                    # or a leg with two points in one instant could publish a
                    # different one than the plan showed the operator.
                    "              ORDER BY s.captured_at, s.id LIMIT 1) f ON true "
                    "       WHERE o2.id = ANY(:ids)) nxt "
                    "WHERE o.id = nxt.id"
                ),
                {"ids": outcome_ids},
            )
            await s.commit()
            print(
                f"  deleted {len(snap_ids)} snapshot rows; "
                f"re-derived {len(outcome_ids)} openings"
            )

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="read only (default)")
    p.add_argument("--backup", action="store_true", help="copy in-scope rows")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    p.add_argument("--limit", type=int, default=0, help="act on the first N legs")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
