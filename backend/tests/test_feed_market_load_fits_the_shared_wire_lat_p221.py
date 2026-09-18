"""LAT-P221 (#2971) — the feed's most expensive artifact must FIT the wire.

WHAT WENT WRONG, AND WHY NOTHING CAUGHT IT.

`futures.market_load` — the hydrated Discover candidate base — is the single
biggest stage of a cold `/api/feed`. LAT-P174 made it a principal-independent
shared artifact precisely because every principal rebuilds the identical rows.
Then it silently stopped being shared, and stayed that way for weeks.

It did not break. It ROTTED. LAT-P174 sized the artifact at ~1.2 MB against a
2 MB cap, for 700 markets and 2,223 outcomes. The outcome population is now
6,904 — 3.1x — so the envelope is 2.79 MB, `_publish_cross_worker` refuses it on
every build, and the artifact never leaves the worker that made it. Measured in
production 2026-09-04: `x-feed-shared` listed `canonical_counts,concepts` and
never `market_load`, and the only reuse ever observed for it was
`x-feed-shared-tier: local`.

The cost was the whole cold feed. `futures.market_load` was 692-775 ms of a
1,537-1,982 ms miss; on the requests that happened to reuse it from the building
worker's own L1 the same stage cost 68-71 ms and the whole request 735-774 ms.
47% of production feed requests miss.

**Every guard in the suite tested that the cache WORKS. None tested that the
artifact FITS.** So the size guards passed on toy fixtures forever while the one
artifact they existed for was refused in production on every single build. That
is the class this file closes: a bound that is only ever exercised against
fixtures smaller than the thing it bounds is not a bound, it is a decoration.

HOW TO RE-MEASURE THE SHAPE BELOW (it is a population, so it moves — and it
moved 35% in the two weeks nobody re-read it; see the block above
`PROD_MARKETS`):

    POST /api/admin/db-query
    WITH top700 AS (
      SELECT id, row_number() OVER (ORDER BY market_tier ASC NULLS LAST,
                                             resolution_date ASC NULLS LAST) AS rn
        FROM futures_markets
       WHERE status='open' AND event_id IS NULL
         AND (resolution_date IS NULL OR resolution_date >= now())
         AND name NOT LIKE '%% vs %%' AND name NOT LIKE '%% vs. %%'
       ORDER BY market_tier ASC NULLS LAST, resolution_date ASC NULLS LAST
       LIMIT 700)
    SELECT (SELECT count(*) FROM top700) AS n_markets,
           (SELECT count(*) FROM futures_outcomes o
              JOIN top700 t ON o.market_id = t.id) AS n_outcomes

`MEASURED_ENVELOPE_BYTES` is NOT re-pointed from that count. It is re-measured
by pulling 40 of those markets (every 17th by `rn`, never `LIMIT 40` — the
order key is the tier and the head is all one tier) with their outcomes,
casting the values back to their python types, encoding them through
`encode_shared_payload`, and extrapolating spine + per-market + per-outcome to
the counts above. Scaling the old constant by the fixture's own growth would
make `test_the_fixture_reproduces_the_measured_artifact` a fixture held to a
target derived from itself, i.e. exactly the decoration this file was written
to end.

When this file goes red, the answer is NOT to raise a cap. It is that the
artifact outgrew its wire and needs a narrower one (drop a column, compact the
row form, or chunk the publish).

2026-09-18: IT WENT RED IN NINE DAYS' TIME AND THE ANSWER WAS THE SECOND ONE.
The byte alarm was ~16% of population growth away, so the row form was compacted
rather than the cap raised: `principal_independent_cache`'s three SCALAR tags
became prefixed strings instead of two-key dicts, `{"__pic__":"dec","v":"0.15"}`
-> `"~D0.15"`. The outcome row carries six `Decimal` columns and there are ~9,300
outcomes, so it is a per-outcome saving, which at ~13 legs per market is worth
~13x a per-market one. Envelope 0.722x, and the reader's inflate-and-parse 20.9
-> 11.5 ms of GIL-held work on every cross-worker read (gotcha #38). The full
argument, the rollout, and what it cost is the block above `_TAG` in that module.

What it did NOT buy is storage — zlib was already eating the repeated tag, so the
stored blob moved 0.942x. That is worth carrying: compression hid this cost
exactly where it was cheapest to look, and the storage budget is the wrong
instrument for asking whether the wire is wide.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.models import FuturesMarket, FuturesOutcome
from app.utils import futures_market_snapshot as fs
from app.utils import principal_independent_cache as pic

#: Tz-aware and microsecond-bearing, because that is what the columns hold and
#: the isoformat length is what the codec pays for.
_A_TIMESTAMP = datetime(2026, 9, 4, 4, 47, 12, 123456, tzinfo=timezone.utc)

# --- the measured production shape, 2026-09-18 (was 2026-09-04) -------------
#
# 🔴 RE-POINTED 2026-09-18, and the reason is this file's OWN failure class.
# LAT-P221 exists because "every guard tested that the cache WORKS, none tested
# that the artifact FITS" — and the first version of it then rebuilt that exact
# failure one level up, by pinning the population it fits against to a number
# hand-copied on 2026-09-04 and never re-read. Two weeks later the outcome
# population was 9,325 and this file was still sizing 6,904: it was measuring a
# population that no longer existed, which is the same decoration in a
# different place. Ask of any size guard: what re-measures the number it is
# comparing to?
#
#: Candidate-base size. The eight Discover pools are capped at 80/80/80/120/100/
#: 100/80/80 = 720 ids before dedup, so 700 is the population's real ceiling and
#: not an estimate. This one does NOT move with the population — it is the only
#: constant here that is structural rather than measured.
PROD_MARKETS = 700
#: Measured, not derived: 9,325 outcomes across those 700 markets (2026-09-18,
#: the re-measure SQL in this module's docstring; was 6,904 on 2026-09-04, so
#: the population grew 35% in two weeks).
#:
#: This is a LIVE population and it moves by ones between any two reads — the
#: same query read 9,326 an hour earlier. Do not re-point this constant for a
#: drift of a few rows; it is here to catch the 35% kind, and re-measuring the
#: baseline must never become a way of quietly absorbing growth.
#:
#: 🔴 2026-09-18 11:59Z, LAT-P274: THE SAME QUERY READ 9,818 — 5.3% above this
#: constant, hours after it was written. DELIBERATELY NOT RE-POINTED HERE, for
#: two reasons. (1) Re-pointing would not buy a green; at ~16.8 nodes/outcome
#: that shape is ~164,900 nodes against the 200,000 alarm, so this file is
#: honestly green either way, and moving the number would only exercise the
#: habit this docstring warns about. (2) `MEASURED_ENVELOPE_BYTES`,
#: `PROD_*_TEXT_BYTES` and `MEASURED_NODES` are NOT derivable from this count —
#: they need the 40-real-row pull and the decomposition described above, and a
#: population re-point without them would leave the file internally
#: inconsistent, which is worse than leaving it slightly behind.
#:
#: 🟢 THE STANDING ANSWER TO THIS FILE'S OWN QUESTION — "what re-measures the
#: number it is comparing to?" — IS NO LONGER "a person, when they remember".
#: LAT-P274 records the node count `assert_plain_data` actually walks, per
#: namespace, on every production build, and warns once past
#: `pic.NODE_GROWTH_ALARM`. So the failure this file already suffered once
#: (sizing 6,904 while production carried 9,325) is now reported by production
#: itself rather than waiting on the next hand re-measure. Read
#: `/api/admin/shared-build-stats` -> `node_high_water` before trusting the
#: constant above.
PROD_OUTCOMES = 9_325
#: Mean bytes of the variable-width text a row actually carries (names, external
#: ids, urls, hooks, and `market_metadata`, which dominates the market row).
#: Re-measured 2026-09-18 over the same 40 real rows as the envelope below: the
#: market row nearly doubled (955 -> 1,864, `market_metadata` having grown) and
#: the outcome row shrank (68 -> 47). They moved in OPPOSITE directions, which
#: is why neither can be inferred from the other or from the row counts.
#:
#: Re-measured again 2026-09-18 08:55Z with the compact codec: 1,864 -> 1,448 and
#: 47 -> 53. NOTHING ABOUT THE CODEC MOVED THESE — it does not touch text. The
#: SAMPLE moved: every-17th of the ordered top-700 selected different markets
#: (776 real outcomes behind the 40 sampled markets in the morning read, 613 in
#: this one), which is the composition churn the population note above describes,
#: seen from the text side. Two pulls 10 minutes apart returned byte-identical
#: numbers, so this is a real read of a churning composition and not sampling
#: noise — and it is why the envelope control below carries a +/-10% band rather
#: than an equality.
PROD_MARKET_TEXT_BYTES = 1_448
PROD_OUTCOME_TEXT_BYTES = 53

#: The measured envelope of the REAL artifact, encoded by this module's own
#: codec over 40 real production rows and extrapolated to the shape above. It is
#: what `test_the_fixture_reproduces_the_measured_artifact` holds the fixture to.
#:
#: Re-measured 2026-09-18: 2,928,973 -> 3,827,678 B (3.83 MB). METHOD MATTERS
#: MORE THAN THE NUMBER, because the cheap way to re-point this is to scale it
#: with the fixture's own growth — and that would make the control vacuous, a
#: fixture held to a target derived from itself. So it is measured the way the
#: original was and the docstring says: 40 real markets and their 776 real
#: outcomes pulled from the candidate-base population, cast back to their
#: PYTHON types (a `Decimal` and a `datetime` are the only tagged values on this
#: wire — left as strings they under-measure the artifact by exactly the thing
#: that makes it expensive), encoded through `encode_shared_payload`, then
#: decomposed into spine + per-market + per-outcome and extrapolated to 700 /
#: 9,325. Per market 2,539 B, per outcome 220 B, spine 122 B.
#:
#: The 40 are sampled SYSTEMATICALLY across the ordered top-700 (every 17th),
#: not `LIMIT 40`: the order key is `market_tier ASC NULLS LAST`, so a head
#: sample would measure tier-1 text widths and call them the population's.
#:
#: 🟢 2026-09-18 08:55Z — THE COMPACT CODEC. 3,827,678 -> 2,760,864 B (2.76 MB).
#: Re-measured by the method above, not scaled: the same 40-real-row pull, cast
#: back to python types, through the same `encode_shared_payload`, which is now
#: the compact one. Per market 2,539 -> 1,905.8 B, per outcome 220 -> 153.0 B,
#: spine 122 B unchanged.
#:
#: TWO INDEPENDENT MEASUREMENTS, which is the only reason a drop this large is
#: accepted rather than re-checked. (1) This file's own fixture, seed and text
#: constants held fixed and ONLY the codec swapped: 3,785,526 -> 2,734,169 B,
#: 0.722x. (2) The real-row pull above, which also absorbs the sample churn in
#: `PROD_*_TEXT_BYTES`: 2,760,864 B. Applying (1)'s ratio to the old measured
#: artifact predicts 2,763,582 B, and (2) read 2,760,864 — 0.1% apart, from a
#: synthetic fixture and a production pull that share no inputs.
MEASURED_ENVELOPE_BYTES = 2_760_864
#: Fraction of nullable columns left `None`. CALIBRATED, not chosen: it is the
#: one free parameter, and it is set to whatever reproduces
#: `MEASURED_ENVELOPE_BYTES`. Re-calibrate it when the shape constants move.
#:
#: Re-calibrated 2026-09-18 with the shape constants above: 0.25 -> 0.34, which
#: puts the fixture at 3,785,526 B against the measured 3,827,678 B (ratio
#: 0.989, band 0.9-1.1). Worth recording that production's OWN observed null
#: rate over the same 40 rows is 0.519, not 0.34 — the two are not the same
#: quantity and should not be reconciled: this parameter spreads one text budget
#: across all text columns of a synthetic row, so it absorbs the difference
#: between that flat budget and production's very uneven one. It is a fitting
#: parameter for the envelope, never a claim about how null production is.
#:
#: Re-calibrated again 2026-09-18 for the compact codec and the re-read text
#: widths: 0.34 -> 0.23, putting the fixture at 2,742,650 B against the measured
#: 2,760,864 B (ratio 0.993). Production's own observed null rate on this pull is
#: 0.438 — still a different quantity, and still not reconciled, for the reason
#: in the paragraph above.
NULL_RATE = 0.23

#: Node count of the fixture, measured 2026-09-05 (LAT-P230 ITEM 2a). Nodes are
#: what `assert_plain_data` counts, and they are a function of the SHAPE alone —
#: 700 markets x 29 columns, 6,904 outcomes x 12 columns, plus the list spine and
#: the `market_metadata` dicts — so unlike the byte constants this one does not
#: move with text widths. Deterministic given the shape constants above, which is
#: what makes a 1.5x alarm on it a real signal rather than a flaky one.
#:
#: Re-measured 2026-09-05 after rebasing onto master: 114,421 -> 115,133. The
#: cause is the `price_polled_at` derived snapshot field that landed on master
#: independently, i.e. the shape genuinely grew by one column's worth of nodes;
#: this is the guard reporting real drift, not a flake. The 1.5x budget
#: assertion below is UNCHANGED and still passes with room (115,133 against a
#: 200,000 cap is 58%, and the alarm sits at 133,333) — re-measuring the
#: baseline must never become a way of quietly absorbing growth, so the two are
#: deliberately separate assertions: this one says "the shape moved", the other
#: says "the shape is still safe". Flagged by CERT-1856 as a follow-up.
#:
#: Re-measured 2026-09-11 for #4758's `opening_baseline_at`, the second derived
#: market column: 115,133 -> 115,863. The delta is +730 and it DECOMPOSES, which
#: is the only reason it is accepted rather than copied off a red run:
#:
#:   +700  one derived value per market — market row values go 21,000 -> 21,700
#:         over 700 rows, i.e. exactly one column's worth and nothing else.
#:    +30  the fixture's own RNG stream. `_row_at_kinds` draws `rng.random()` for
#:         every NULLABLE column before it looks at the kind, so a 31st market
#:         column consumes one extra draw per row and shifts everything built
#:         after it. Ten `market_metadata` cells flip from `None` to a populated
#:         dict (526 -> 536), and a 3-value dict counts 4 nodes against the 1 a
#:         `None` costs: 10 x 3.
#:
#: That second term is worth stating rather than absorbing, because it means the
#: count above is a function of the shape AND of this file's fixed seed — a
#: future column will not move it by a round number either, and a delta that
#: does NOT decompose is the drift this assertion exists to catch.
#:
#: It did not move by a round number, exactly as predicted. #5809's
#: `top_price_observed_at` — the THIRD derived market column — takes it
#: 115,863 -> 116,527, a delta of +664 that decomposes on the same two terms and
#: was measured, not copied off the red run:
#:
#:   +700  one derived value per market — market row values go 21,700 -> 22,400
#:         over 700 rows, i.e. exactly one column's worth and nothing else.
#:    -36  the same RNG-stream shift, in the other direction this time: a 32nd
#:         market column consumes one more draw per row, and twelve
#:         `market_metadata` cells flip from a populated dict to `None`
#:         (536 -> 524) at 4 nodes against 1, i.e. 12 x 3.
#:
#: The budget assertion below is UNCHANGED and still has room: 116,527 against a
#: 200,000 cap is 58%, and the 1.5x alarm sits at 133,333.
#:
#: #5809 COMPLETED moves it the other way as well as up, and this is the first
#: delta with a NEGATIVE term, so it is worth reading rather than absorbing:
#: 116,527 -> 122,749, +6,222, measured and decomposed before the constant was
#: touched.
#:
#:   -700  `top_price_observed_at` REMOVED from the market row. The market-level
#:         fold over the top three by probability was a proxy for "the legs the
#:         card prints"; the card prints the top three of a FILTERED list, so it
#:         is replaced rather than kept beside its successor.
#: +6,904  one derived value per OUTCOME — `price_observed_epoch`, an untagged
#:         int of whole UTC seconds, which is what makes the per-leg carrier
#:         affordable where the `last_updated` DATETIME this file refused at +15%
#:         was not. Outcome row values go 82,848 -> 89,752 over 6,904 rows, i.e.
#:         exactly one column's worth and nothing else.
#:    +18  the fixture's own RNG stream, shifted in BOTH directions this time:
#:         the market row draws one FEWER nullable per row and the outcome row
#:         one MORE, so six `market_metadata` cells flip from `None` to a
#:         populated dict (524 -> 530) at 4 nodes against 1, i.e. 6 x 3.
#:
#: The envelope barely moves — 3,026,119 B -> 3,028,144 B on this fixture, ratio
#: to the measured artifact 1.033 -> 1.034 — because 700 tagged datetimes leaving
#: the wire very nearly pays for 6,904 untagged ints arriving on it. That is the
#: whole economic argument for the completion and it is measured here, not
#: asserted in the module's prose.
#:
#: The budget assertion below is again UNCHANGED and still has room: 122,749
#: against a 200,000 cap is 61%, and the 1.5x alarm still sits at 133,333.
#:
#: 2026-09-18 — the first move of this constant that is NOT a schema change.
#: Every delta above was a column arriving or leaving; this one is the
#: POPULATION, re-pointed from the stale 2026-09-04 shape (see the block at the
#: top of this file). 122,749 -> 156,466, +33,717, and it decomposes on three
#: terms that were each measured by holding the other two fixed rather than
#: inferred from the total:
#:
#: +33,930  outcomes 6,904 -> 9,325. 2,421 new outcome rows at 14 nodes each
#:          (13 values + the row's own list) is +33,894; the residual +36 is the
#:          RNG-stream term below, shifted by the extra draws those rows consume.
#:     -48  the text widths (955/68 -> 1,864/47). This term SHOULD be zero —
#:          node count is a function of the shape, not of how wide the text is —
#:          and it is not, because `_texty` loops until it has filled its budget
#:          and so consumes a budget-dependent number of `rng` draws. Changing a
#:          text width therefore shifts every later draw, flipping a handful of
#:          `market_metadata` cells between `None` (1 node) and a populated dict
#:          (4 nodes). Recorded rather than rounded away: it is the same RNG
#:          coupling the two deltas above already document, reached by a new
#:          route, and a future reader re-measuring only the counts would
#:          otherwise find 48 nodes they cannot account for.
#:    -165  `NULL_RATE` 0.25 -> 0.34. 55 `market_metadata` cells flip from a
#:          populated dict to `None` at 4 nodes against 1, i.e. 55 x 3.
#:
#: The harness that produced these was first checked against the constant it was
#: replacing — at the old four constants it returns 122,749 exactly — because a
#: decomposition from a harness that cannot reproduce the baseline is arithmetic
#: about nothing.
#:
#: The budget assertion below is UNCHANGED and still has room, but LESS of it:
#: 156,466 against the 200,000 growth alarm is 78%, where the 2026-09-04 shape
#: sat at 61%. The BYTE alarm is the tighter one now — see `HEADROOM_FACTOR`.
#:
#: 2026-09-18, the compact codec: 156,466 -> 156,640, +174. THE CODEC CONTRIBUTES
#: NOTHING TO THIS and that is the point of printing the delta rather than
#: skipping it — `_count_validator_nodes` walks the PLAIN value, where a
#: `Decimal` is one node whether the wire spends 32 bytes on it or 12. The whole
#: +174 is the RNG-stream term the deltas above document, reached by a third
#: route: `NULL_RATE` 0.34 -> 0.23 and the two text widths all change how many
#: draws `_texty` and `_row_at_kinds` consume, so `market_metadata` cells flip
#: between `None` (1 node) and a populated dict (4 nodes) — 58 of them, 58 x 3.
#: A delta here that does NOT decompose is the drift this assertion exists for.
MEASURED_NODES = 156_640

#: The alarm fires BEFORE breakage, not at it. A guard that goes red at the
#: moment the share stops working has told us nothing the latency would not
#: have; the point is to be red while there is still room to fix it. 1.5 puts
#: the alarm at a 4.19 MB envelope against a 6.29 MB bound.
#:
#: 🔴 2026-09-18: THIS IS NOW THE TIGHTEST OF THE THREE ALARMS, and the margin
#: is small. Today's artifact is 3.83 MB, so ~1.10x growth in BYTES trips this
#: file and ~1.64x actually breaks the share. On 2026-09-04 those were ~1.4x and
#: ~2.1x and the NODE alarm was the one to watch; the population grew 35% in two
#: weeks while the node count grew 27%, so the byte alarm overtook it.
#:
#: Measured in the units that actually move — the outcome population — by
#: bisecting this fixture against each alarm:
#:
#:    9,325  today
#:   10,836  the BYTE alarm trips        (+16.2%)
#:   12,435  the NODE alarm trips        (+33.4%)
#:   18,839  the share actually breaks   (`DECODE_BUDGET_OUTCOMES`)
#:
#: At the rate this population has actually grown — 6,904 to 9,325 in the
#: fourteen days nobody was re-measuring it, ~173 outcomes a day — the byte
#: alarm is about nine days out.
#:
#: 🟢 THAT IS THE ONE THE COMPACT CODEC WAS BUILT FOR, AND IT IS PAID. The
#: factor itself is UNCHANGED — the remedy was the one the docstring prescribes
#: (compact the row form), not a larger number here. Re-bisected at the shipped
#: constants, 700-outcome granularity:
#:
#:              before        after
#:    9,325     today         today
#:   11,900       —           the NODE alarm trips        (+27.6%)
#:   14,700       —           the STORE alarm trips       (+57.6%)
#:   17,500       —           the BYTE alarm trips        (+87.7%)
#:   29,869       —           the share actually breaks
#:
#: So the byte alarm went from ~9 days of runway to ~7 weeks, and the order
#: changed: the NODE alarm is the first to fire again, as it was on 2026-09-04.
#: Read that as the design working rather than as a new problem — the codec
#: cannot answer a node count (nodes are scalars; see `_MAX_NODES`), so when the
#: node alarm goes the answer is fewer rows or chunking the publish, and it must
#: NOT be answered by moving `NODE_GROWTH_ALARM`.
HEADROOM_FACTOR = 1.5

#: The NODE growth alarm (LAT-P273). Keeps the 200,000 that `pic._MAX_NODES`
#: used to be, because 200,000 was always the defensible answer to "is this
#: artifact getting big?" and only ever the wrong answer to "is it unsafe to
#: walk?" — the two questions that one number was serving. Deliberately a
#: constant and NOT `pic._MAX_NODES / HEADROOM_FACTOR`: an alarm expressed as a
#: fraction of the cap it warns about rises with the cap, so raising the safety
#: cap to repair the ordering defect would have relaxed this alarm in the same
#: commit. `test_the_growth_alarm_is_not_tied_to_the_safety_cap` pins that.
#:
#: 2026-09-18, LAT-P274: MOVED INTO THE APP AND IMPORTED HERE, so the fixture
#: guard below and the production alarm in `_note_nodes` are the SAME number
#: rather than two constants that agree until one of them is edited. This file
#: sizes a synthetic fixture from a hand-copied population; production now
#: reports the node count it actually walked. Two instruments, one threshold.
NODE_GROWTH_ALARM = pic.NODE_GROWTH_ALARM

#: Plausibility band for the fixture's own compression ratio. The storage
#: assertion below runs the fixture through the REAL `wire_encode`, which makes
#: it sensitive to how compressible this file's filler happens to be — so the
#: band is what stops a future edit buying a green with easier text. Measured:
#: 4.2x on the real artifact, 3.8x on the fixture, both at zlib level 1.
#:
#: 🔴 2026-09-18: THE COMPACT CODEC SEPARATED THESE TWO NUMBERS, and the band had
#: to be re-derived rather than widened to fit. Re-measured at zlib level 1:
#: 3.85-3.88x on real rows (two pulls), 2.68x on this fixture. Under the old
#: codec both sat near 4x — because the two-key tag dict, repeated ~56,000 times,
#: was the most compressible thing on the wire and dominated BOTH. Remove it and
#: the fixture's own filler entropy shows through: `_texty` appends a random
#: number to every word, which is less repetitive than production's names and
#: `market_metadata`.
#:
#: THE BOUND THAT MATTERS IS THE UPPER ONE, and it is now pinned to the measured
#: real ratio. The failure this assertion exists to stop is a fixture that
#: compresses BETTER than production — that buys a green on the storage budget
#: with text production does not have. A fixture that compresses WORSE is
#: conservative: it reports 1.02 MB stored where the real artifact is ~0.71 MB,
#: so the storage assertion fails early rather than late. That is the direction
#: to be wrong in, and it is recorded here rather than tuned away, because
#: tuning `_texty`'s entropy to hit a compression target would add a SECOND free
#: parameter to a fixture whose whole discipline is having exactly one
#: (`NULL_RATE`).
#:
#: Consequence worth knowing before reading a red: the store alarm now fires at
#: ~14,700 outcomes on this fixture, ahead of the byte alarm's ~17,500, and it
#: is the pessimistic one of the three.
COMPRESSION_RATIO_BAND = (2.5, 3.9)


def _texty(rng: random.Random, n_bytes: int) -> str:
    """`n_bytes` of text with prose-like — not degenerate, not random — entropy.

    Both failure modes matter. Repeated filler compresses ~50x and would make
    every storage assertion below vacuously true; `os.urandom` compresses not at
    all and would make them unmeetable. Neither would be measuring the artifact.
    """
    out: list[str] = []
    size = 0
    while size < n_bytes:
        word = rng.choice(_WORDS) + str(rng.randrange(1000))
        out.append(word)
        size += len(word) + 1
    return " ".join(out)[:n_bytes]


_WORDS = (
    "winner championship market open close outright tournament round leader "
    "polymarket kalshi series playoff conference division award nominee "
    "election primary candidate senate governor forecast landfall category"
).split()


def _column_kinds(model, columns: tuple[str, ...]) -> list[str]:
    """One kind per column position, READ OFF THE MODEL rather than listed here.

    🔴 This is the load-bearing half of the fixture, and the reason it is
    introspected instead of transcribed. Most of the artifact's bytes are not
    its text — they are the wire codec's per-value tags, and only `Decimal` and
    `datetime` carry one (`{"__pic__":"dec","v":"0.155000"}` is 31 bytes to
    express six characters). A fixture that leaves those columns `None` encodes
    to 58% of the real artifact, sails under the cap the real one is breaching,
    and reports green on the exact defect it was written for. Measured: it did.

    Reading the types off `FuturesMarket` / `FuturesOutcome` also means a column
    added to `MARKET_COLUMNS` grows this fixture on the same commit, instead of
    quietly shrinking it relative to production.
    """
    from sqlalchemy import DateTime, Integer, Numeric

    kinds = []
    for name in columns:
        col_type = model.__table__.columns[name].type
        if isinstance(col_type, DateTime):
            kinds.append("dt")
        elif isinstance(col_type, Numeric) and not isinstance(col_type, Integer):
            # `Numeric` is the Decimal one; SQLAlchemy's `Float` subclasses it
            # and is NOT (a float needs no tag), so check the python type.
            kinds.append("dec" if col_type.python_type is Decimal else "num")
        elif isinstance(col_type, Integer):
            kinds.append("int")
        elif name == "market_metadata":
            kinds.append("json")
        else:
            kinds.append("str")
    return kinds


def _row_at_kinds(
    rng: random.Random, kinds: list[str], nullable: list[bool], text_budget: int
) -> list:
    """One positional row whose values have production's TYPES and text width."""
    text_cols = [i for i, k in enumerate(kinds) if k in ("str", "json")] or [0]
    per_text = max(1, text_budget // len(text_cols))
    row: list = []
    for i, kind in enumerate(kinds):
        if nullable[i] and rng.random() < NULL_RATE:
            # A `None` is four bytes and no tag. Production rows are full of
            # them (no image, no hook, no closing line), so a fixture that
            # fills every nullable column is not a heavier version of the real
            # artifact — it is a different one.
            row.append(None)
        elif kind == "dt":
            row.append(_A_TIMESTAMP)
        elif kind == "dec":
            row.append(Decimal(f"0.{rng.randrange(100000, 999999)}"))
        elif kind == "num":
            row.append(rng.random())
        elif kind == "int":
            row.append(rng.randrange(1, 900_000))
        elif kind == "json":
            row.append({"shape": _texty(rng, per_text), "v": 2, "confidence": "low"})
        else:
            row.append(_texty(rng, per_text))
    return row


#: The kinds of `DERIVED_MARKET_COLUMNS`, declared BY NAME because they are not
#: on `FuturesMarket` and `_column_kinds` therefore cannot introspect them. A
#: derived column added without a line here is a `KeyError` in this fixture, not
#: a silently-cheap `str` that shrinks the artifact relative to production —
#: which is the whole reason the loaded kinds are introspected in the first
#: place. `price_polled_at` is a `datetime`, and a datetime is a TAGGED value on
#: this wire (~31 bytes of codec around it), so it must be measured as one.
_DERIVED_KINDS = {
    "price_polled_at": "dt",
    "opening_baseline_at": "dt",
}

#: The kinds of `DERIVED_OUTCOME_COLUMNS`, by name and for the same reason as
#: the map above — they are not on `FuturesOutcome`, so a column added without a
#: line here is a `KeyError` in this fixture rather than a silently-cheap `str`.
#:
#: #5809 completed. `top_price_observed_at` was a third tagged DATETIME on the
#: market row and is gone; `price_observed_epoch` is an UNTAGGED int on every
#: OUTCOME row, which is a far bigger population and still a smaller artifact
#: than the datetime this file's own +15% refusal was measured against. That
#: asymmetry is the entire reason the completion is affordable, so it is
#: measured here rather than asserted in a docstring — see the delta
#: decomposition on `MEASURED_NODES`.
_DERIVED_OUTCOME_KINDS = {
    "price_observed_epoch": "int",
}


def _production_scale_payload(n_outcomes: int | None = None) -> dict:
    """A `to_plain`-shaped artifact at the measured production shape.

    `n_outcomes` overrides the outcome population for the ONE guard that has to
    ask about a scale the population has not reached yet
    (`test_the_node_cap_never_refuses_what_the_decode_budget_accepts`). Every
    other caller takes the default and is about the measured shape.
    """
    n_total = PROD_OUTCOMES if n_outcomes is None else n_outcomes
    rng = random.Random(20260904)
    market_kinds = _column_kinds(FuturesMarket, fs.MARKET_COLUMNS) + [
        _DERIVED_KINDS[name] for name in fs.DERIVED_MARKET_COLUMNS
    ]
    outcome_kinds = _column_kinds(FuturesOutcome, fs.OUTCOME_COLUMNS) + [
        _DERIVED_OUTCOME_KINDS[name] for name in fs.DERIVED_OUTCOME_COLUMNS
    ]
    # Derived values are nullable by construction: `to_plain` writes `None` for
    # a market the caller's map does not cover (a market with no outcome rows),
    # and for an outcome whose `last_updated` was never projected or never set.
    market_null = _nullable(FuturesMarket, fs.MARKET_COLUMNS) + [True] * len(
        fs.DERIVED_MARKET_COLUMNS
    )
    outcome_null = _nullable(FuturesOutcome, fs.OUTCOME_COLUMNS) + [True] * len(
        fs.DERIVED_OUTCOME_COLUMNS
    )
    per_market = n_total // PROD_MARKETS
    remainder = n_total - per_market * PROD_MARKETS
    rows = []
    for i in range(PROD_MARKETS):
        n = per_market + (1 if i < remainder else 0)
        rows.append(
            [
                _row_at_kinds(rng, market_kinds, market_null, PROD_MARKET_TEXT_BYTES),
                [
                    _row_at_kinds(
                        rng, outcome_kinds, outcome_null, PROD_OUTCOME_TEXT_BYTES
                    )
                    for _ in range(n)
                ],
                None,
            ]
        )
    return {"v": fs.SNAPSHOT_SCHEMA_VERSION, "rows": rows}


def _nullable(model, columns: tuple[str, ...]) -> list[bool]:
    return [
        bool(model.__table__.columns[name].nullable) and name != "id"
        for name in columns
    ]


@pytest.fixture(name="payload", scope="module")
def _payload():
    return _production_scale_payload()


def test_the_fixture_is_the_measured_production_shape(payload):
    """A control. If this fixture drifts off the population it is standing in
    for, every assertion below is about a different artifact."""
    assert len(payload["rows"]) == PROD_MARKETS
    assert sum(len(r[1]) for r in payload["rows"]) == PROD_OUTCOMES
    pic.assert_plain_data(payload)  # must not raise, or it is not shareable


def test_the_fixture_reproduces_the_measured_artifact(payload):
    """The control that makes every size assertion below mean something.

    The first version of this fixture left the nullable `Decimal` and `datetime`
    columns empty and encoded to 58% of the real artifact — green under the very
    cap production was breaching. A synthetic fixture standing in for a measured
    population has to be held to the measurement, or it is only testing itself.
    """
    envelope = _envelope_bytes(payload)
    ratio = envelope / MEASURED_ENVELOPE_BYTES

    assert 0.9 <= ratio <= 1.1, (
        f"the fixture encodes to {envelope:,} B against a measured "
        f"{MEASURED_ENVELOPE_BYTES:,} B ({ratio:.0%}). Re-calibrate NULL_RATE, "
        f"or re-measure MEASURED_ENVELOPE_BYTES if the population moved."
    )


def test_the_fixture_compresses_like_real_data(payload):
    """And the other way a synthetic fixture can buy a green: filler that
    compresses better than prose. The storage assertion runs the real
    `wire_encode`, so its verdict is only as honest as this band."""
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    ratio = len(envelope.encode()) / len(pic.wire_encode(envelope))

    low, high = COMPRESSION_RATIO_BAND
    assert low <= ratio <= high, (
        f"the fixture compresses {ratio:.1f}x, outside the {low}-{high}x band "
        f"real market_load rows sit in — the storage assertion is measuring "
        f"this file's filler, not the artifact."
    )


def test_a_production_scale_market_load_fits_the_decode_budget(payload):
    """The bound that was actually being violated. 2.79 MB against 2 MB."""
    envelope = _envelope_bytes(payload)

    assert envelope <= pic.MAX_ENVELOPE_BYTES / HEADROOM_FACTOR, (
        f"market_load encodes to {envelope:,} B; the decode budget is "
        f"{pic.MAX_ENVELOPE_BYTES:,} B and this guard wants {HEADROOM_FACTOR}x "
        f"headroom. The artifact outgrew its wire — narrow the wire, do not "
        f"raise the cap (gotcha #38: the parse holds the GIL)."
    )


def test_a_production_scale_market_load_fits_the_storage_budget(payload):
    """The other bound: what Redis has to hold, through the real wire."""
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    stored = len(pic.wire_encode(envelope))

    assert stored <= pic.MAX_STORED_BYTES / HEADROOM_FACTOR, (
        f"market_load stores {stored:,} B; the storage budget is "
        f"{pic.MAX_STORED_BYTES:,} B and Redis is a shared 100 MB LRU that "
        f"Celery's state lives in too."
    )


# --- LAT-P230 ITEM 2a: the THIRD cap, which fails worse than the two above ----
#
# `assert_plain_data` enforces `_MAX_NODES` as well as the byte bounds, and it had
# no production-scale guard at all — the exact omission this file was written to
# close, left open for the one cap whose breach is silent.
#
# It fails WORSE than the byte caps. A byte breach only stops the Redis publish;
# the artifact still lands in the local tier and a warm worker still reuses it. A
# NODE breach makes `assert_plain_data` raise inside `get_or_build`, which returns
# the value BEFORE the `entries[key] = ...` store — so the artifact is not cached
# at all, local tier included, silently, on every single build.


def _count_validator_nodes(value) -> int:
    """Count nodes exactly as `assert_plain_data`'s walker does.

    A mirror, so it can drift — which is why
    `test_the_node_counter_matches_the_real_validator` pins it against the real
    walker at the accept/reject boundary rather than trusting it.
    """
    n = 0
    stack = [value]
    while stack:
        node = stack.pop()
        n += 1
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return n


def test_the_node_counter_matches_the_real_validator(payload, monkeypatch):
    """The control for the two assertions below: our count IS the walker's count.

    Proven at the boundary, not by sampling. `_walk` raises once `nodes` exceeds
    the cap, so the real validator must accept the payload at exactly our count
    and refuse it at one less. Off by a single node and one of these fails.
    """
    counted = _count_validator_nodes(payload)

    monkeypatch.setattr(pic, "_MAX_NODES", counted)
    pic.assert_plain_data(payload)  # accepted at exactly the count

    monkeypatch.setattr(pic, "_MAX_NODES", counted - 1)
    with pytest.raises(pic.NotPlainData):
        pic.assert_plain_data(payload)


def test_the_fixture_is_the_measured_node_shape(payload):
    """A control, on the same discipline as the envelope-bytes control."""
    counted = _count_validator_nodes(payload)
    assert counted == MEASURED_NODES, (
        f"the fixture is {counted:,} nodes against a recorded {MEASURED_NODES:,}. "
        f"The shape constants moved — re-measure MEASURED_NODES, and check the "
        f"node budget below still has room."
    )


def test_a_production_scale_market_load_fits_the_node_budget(payload):
    """The cap that had no production-scale guard until LAT-P230.

    Today: 156,640 nodes against a 200,000 alarm — 78%, 1.28x of headroom, and
    since the compact codec this is the FIRST of the three alarms to fire
    (~11,900 outcomes, against the byte alarm's ~17,500). The codec cannot
    answer it: see below.

    LAT-P273 re-pointed this at `NODE_GROWTH_ALARM` instead of
    `pic._MAX_NODES / HEADROOM_FACTOR`. The number is the same 200,000 it has
    always been; what changed is that it no longer MOVES when the safety cap
    does, so raising the cap to fix the ordering defect could not buy a green
    here. See `test_the_growth_alarm_is_not_tied_to_the_safety_cap`.
    """
    nodes = _count_validator_nodes(payload)

    assert nodes <= NODE_GROWTH_ALARM, (
        f"market_load validates to {nodes:,} nodes, past the "
        f"{NODE_GROWTH_ALARM:,} growth alarm. The share still WORKS — the safety "
        f"cap is {pic._MAX_NODES:,} — and that is the point: this fires while "
        f"there is still room. Nodes are scalars, so narrowing the row form "
        f"cannot answer it; fewer rows or fewer columns can. Do not answer it by "
        f"moving this constant."
    )


@pytest.mark.asyncio
async def test_a_node_cap_breach_defeats_even_the_local_tier(payload, monkeypatch):
    """The claim above, proven through the real `get_or_build` rather than argued.

    This is what makes the node cap worth its own guard: the byte caps degrade to
    "local tier only", which is slower but still a cache. This one degrades to no
    cache anywhere, and says so only at `logger.warning`.
    """
    pic.clear_shared_builds("lat_p230_nodecap")
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")

    # Captured before the patch below: the control at the end has to restore the
    # REAL cap, and a literal here would silently stop being the real cap the
    # next time it moves (it moved in LAT-P273).
    real_max_nodes = pic._MAX_NODES

    builds = {"n": 0}

    async def _build():
        builds["n"] += 1
        return payload

    monkeypatch.setattr(pic, "_MAX_NODES", _count_validator_nodes(payload) - 1)

    for _ in range(3):
        await pic.get_or_build("lat_p230_nodecap", ("k",), _build, ttl_s=600.0)

    assert builds["n"] == 3, (
        "a node-cap breach should defeat the local tier too — every call must "
        f"rebuild, but only {builds['n']} of 3 did"
    )
    assert pic.peek_shared_build("lat_p230_nodecap") is None

    # And the control: under the real cap the same artifact caches normally, so
    # the assertion above is about the cap and not about a broken fixture.
    pic.clear_shared_builds("lat_p230_nodecap")
    monkeypatch.setattr(pic, "_MAX_NODES", real_max_nodes)
    builds["n"] = 0
    for _ in range(3):
        await pic.get_or_build("lat_p230_nodecap", ("k",), _build, ttl_s=600.0)
    assert builds["n"] == 1


# --- LAT-P273 (#2143 residual): THE TWO CAPS ARE IN THE WRONG ORDER ---------
#
# The test directly above proves the node cap's failure mode is the bad one: a
# byte breach degrades to "local tier only", a NODE breach degrades to no cache
# anywhere, silently, on every build. This section proves the consequence nobody
# had measured: *the bad failure fires first.*
#
# Measured 2026-09-18 with this file's own fixture, `/tmp/lat536_cross.py`:
#
#     outcomes    nodes     envelope B      what happens
#      6,904    122,749      3,028,144      (the shape recorded above)
#      9,326    156,690      3,767,604      TODAY's production population
#     12,421    200,00x      4,702,xxx      <== NODE cap. Silent. No cache at all.
#     17,631    272,88x      6,291,xxx      <== BYTE cap. Loud. Local tier lives.
#
# So the artifact loses its cache ENTIRELY 5,210 outcomes before it is even close
# to the wire it is checked against — and the only signal is a `logger.warning`,
# because `refused` is a namespace-less top-level counter while the byte refusal
# is per-namespace and computed onto `/api/admin/shared-build-stats` as
# `publish_refused_namespaces`. The failure with no instrument is the one that
# arrives first.
#
# WHY "NARROW THE ROW FORM" — the remedy this file prescribes for a byte breach —
# CANNOT BE THE REMEDY HERE. Nodes are scalars. `market_load` is a table of
# (rows x columns) scalars, every column load-bearing with a named incident
# behind it (`futures_market_snapshot.OUTCOME_COLUMNS`), and the walker counts
# cells. Column-major, compaction, a tighter text form: all of them leave the
# scalar count identical. Only fewer rows or fewer columns move a node count, and
# neither is available. A remedy that does not exist is not a remedy.
#
# WHAT THE NODE CAP IS ACTUALLY BOUNDING, measured rather than assumed. It bounds
# `assert_plain_data`'s walk, at ~0.13 us/node on this fixture:
#
#     nodes     walk      json.dumps of the same value
#     122,749   15.7 ms   45.3 ms
#     250,045   32.0 ms   59.9 ms
#
# The walk is 2-3x CHEAPER than the `json.dumps` that the byte budget already
# permits on the very same value, so capping the walk tighter than the dump is
# backwards on its own terms. And the work a breach forfeits is not speculative:
# `futures.market_load` measured 1,037 ms unshared against 105 ms reused
# (#2143, lat520's per-stage table, 2026-09-17).
#
# Hence the split, which is the LAT-P221 lesson applied to the third cap: ONE
# NUMBER WAS SERVING TWO UNRELATED BOUNDS. `_MAX_NODES` is the SAFETY bound — how
# big a value may be before we refuse to validate it — and it now sits above the
# byte budget so the loud, partial, instrumented failure always fires first.
# `NODE_GROWTH_ALARM` is the GROWTH alarm, and it keeps the old 200,000 number,
# because 200,000 was always the defensible answer to "is this artifact getting
# big?" and only ever the wrong answer to "is it unsafe to walk?".

#: The largest `market_load` that still fits `MAX_ENVELOPE_BYTES`, and its node
#: count. MEASURED by bisection on this file's own fixture, not extrapolated —
#: `test_the_decode_budget_scale_is_what_it_says` is the control that keeps it
#: honest, so a future edit cannot quietly retune it into fiction.
#:
#: Re-bisected 2026-09-18 with the re-pointed shape constants: 17,630 -> 18,839
#: outcomes, 272,886 -> 289,659 nodes. These are DERIVED from the fixture's text
#: widths, so they had to move when those did, and the direction is the
#: interesting part: the crossing point went UP even though the market row
#: nearly doubled, because the outcome row shrank (68 -> 47 B) and at this scale
#: there are ~27 outcomes per market. A per-outcome saving buys far more budget
#: than a per-market cost spends — the same asymmetry #5809 was built on.
#:
#: Re-bisected at ONE-outcome granularity, which is the resolution the control
#: below checks: 18,839 encodes to 6,289,600 B against the 6,291,456 B cap, and
#: 18,840 encodes to 6,294,448 B, so this is the actual edge and not merely a
#: point below it.
#:
#: 🔴 The headroom `test_the_node_cap_never_refuses_what_the_decode_budget_accepts`
#: asserts is now THIN: 289,659 against `pic._MAX_NODES` of 300,000 is 3.4%,
#: where the 2026-09-04 shape had 9%. That test is LAT-P273's invariant — the
#: safety cap must never refuse an artifact the decode budget accepts — and if
#: the outcome row ever grows a column back, it is the one that goes red. The
#: fix then is the node cap, not this constant: a `market_load` that fits the
#: wire must not be refused for being long.
#:
#: 2026-09-18, the compact codec — AND THAT THIN HEADROOM WENT NEGATIVE, exactly
#: as predicted, just not by the predicted cause. 18,839 -> 29,869 outcomes,
#: 289,659 -> 444,271 nodes, re-bisected on this fixture at one-outcome
#: granularity: 29,869 encodes to 6,291,399 B against the 6,291,456 B cap — 57
#: bytes of margin — and 29,870 encodes to 6,291,784 B, which does not fit.
#:
#: 🪤 The first bisection returned 27,999 and was WRONG, because its ceiling was
#: `40 * PROD_MARKETS = 28,000` and the real crossing is past it: a bisection
#: whose bracket never contains the answer converges to its own ceiling and
#: reports it with full confidence. `test_the_decode_budget_scale_is_what_it_says`
#: caught it on the one-more-round assertion, which is precisely the job that
#: control was given. The ceiling is now found by doubling until the envelope is
#: PROVEN over the cap, never assumed.
#:
#: The asymmetry the 2026-09-04 note records is the whole story: the codec made
#: BYTES cheaper and left NODES untouched, so the decode budget now admits half
#: again as many rows while the walk that `_MAX_NODES` bounds is unchanged.
#: `_MAX_NODES` moves 300,000 -> 500,000 in the same commit, which is what the
#: invariant's own failure message prescribes — raise the SAFETY cap, never lower
#: the growth alarm. The measured walk-vs-encode table behind that number is in
#: `principal_independent_cache.py` above `_MAX_NODES`, and it is thinner than
#: the one it replaces: 1.2-1.4x, not 2-3x, because this change is precisely what
#: made the encode side cheaper.
DECODE_BUDGET_OUTCOMES = 29_869
DECODE_BUDGET_NODES = 444_271

def test_the_decode_budget_scale_is_what_it_says():
    """Control for the two constants above.

    Without this, `DECODE_BUDGET_NODES` is a number someone typed. With it, the
    guard below is a statement about the real crossing point: this scale fits the
    decode budget and one step past it does not.
    """
    at_budget = _production_scale_payload(DECODE_BUDGET_OUTCOMES)
    assert _envelope_bytes(at_budget) <= pic.MAX_ENVELOPE_BYTES
    assert _count_validator_nodes(at_budget) == DECODE_BUDGET_NODES

    # One outcome per market more — the smallest step this fixture can take —
    # and the envelope no longer fits. So `DECODE_BUDGET_OUTCOMES` really is at
    # the edge and not merely somewhere below it.
    past_budget = _production_scale_payload(DECODE_BUDGET_OUTCOMES + PROD_MARKETS)
    assert _envelope_bytes(past_budget) > pic.MAX_ENVELOPE_BYTES


def test_the_node_cap_never_refuses_what_the_decode_budget_accepts():
    """The ordering invariant. RED at `_MAX_NODES = 200_000`, which is the point.

    An artifact that the decode budget accepts must not be refused by the node
    budget, because the node refusal is the one that defeats every tier and
    carries no per-namespace counter.
    """
    assert DECODE_BUDGET_NODES <= pic._MAX_NODES, (
        f"a market_load that FITS the decode budget ({pic.MAX_ENVELOPE_BYTES:,} B) "
        f"validates to {DECODE_BUDGET_NODES:,} nodes against a node cap of "
        f"{pic._MAX_NODES:,}. The node cap therefore bites FIRST — and it is the "
        f"cap whose breach un-shares the artifact from every tier, silently, "
        f"where a byte breach only loses the cross-worker hop and is counted "
        f"per namespace. Raise the SAFETY cap (`_MAX_NODES`); do not lower the "
        f"growth alarm (`NODE_GROWTH_ALARM`)."
    )


def test_the_growth_alarm_is_not_tied_to_the_safety_cap():
    """The anti-ratchet. This is what stops the fix above buying a green.

    An alarm written as a fraction of the cap it warns about is not an alarm:
    raising the cap raises the alarm with it, and the growth the alarm existed to
    report disappears in the same commit. So the two are separate numbers, and
    the alarm must fire strictly first.
    """
    assert NODE_GROWTH_ALARM < pic._MAX_NODES, (
        f"the growth alarm ({NODE_GROWTH_ALARM:,}) must fire BEFORE the safety "
        f"cap ({pic._MAX_NODES:,}) or it is not an alarm"
    )
    assert DECODE_BUDGET_NODES <= pic._MAX_NODES, (
        "the safety cap must still admit everything the decode budget does — "
        "see the ordering invariant above"
    )


@pytest.mark.asyncio
async def test_a_production_scale_market_load_is_published_not_refused(
    payload, monkeypatch
):
    """End to end through the real publish path — the assertion whose absence
    is the whole reason this file exists.

    The two size tests above are arithmetic on the same numbers; this one proves
    the arithmetic is about the code that runs.
    """
    stored: dict[str, object] = {}

    class _Redis:
        async def set(self, key, value, ex=None):
            stored[key] = value
            return True

    monkeypatch.setattr(pic, "_shared_redis_client", _fake_client(_Redis()))
    pic.clear_shared_builds()

    await pic._publish_cross_worker("market_load", ("market_load", 2, "d"), payload, 60)

    assert stored, (
        "a production-scale market_load was REFUSED by _publish_cross_worker — "
        "it will only ever be reused by the worker that built it, which is the "
        "692-775 ms defect LAT-P221 fixed"
    )
    assert pic.shared_build_stats()["cross_worker_publish_refused"] == 0
    blob = next(iter(stored.values()))
    assert isinstance(blob, bytes)
    assert json.loads(pic.wire_decode(blob))["ns"] == "market_load"


@pytest.mark.asyncio
async def test_the_published_artifact_round_trips_byte_for_byte(payload, monkeypatch):
    """Fitting is not enough — the reader has to get the same rows back.

    `market_load` rows are what the scoring loop reads. A wire that fits and
    lies is worse than one that refuses (the module docstring's own argument for
    the tagged codec), so the compression layer gets the same standard.
    """
    stored: dict[str, object] = {}

    class _Redis:
        async def set(self, key, value, ex=None):
            stored[key] = value
            return True

        async def get(self, key):
            return stored.get(key)

    monkeypatch.setattr(pic, "_shared_redis_client", _fake_client(_Redis()))
    pic.clear_shared_builds()
    key = ("market_load", 2, "roundtrip")

    await pic._publish_cross_worker("market_load", key, payload, 60)
    ok, value, age_s = await pic._read_cross_worker("market_load", key, 60)

    assert ok, "the artifact we just published did not read back"
    assert value == payload
    # LAT-P229: the reader also reports how old the artifact already was, so the
    # promotion into the local tier can backdate it instead of restarting its TTL.
    assert 0.0 <= age_s < 60.0, "a just-published artifact read back as aged"
    assert fs.is_snapshot_payload(value), "it read back in an unusable shape"


def test_the_shared_redis_client_hands_back_bytes_not_str():
    """The wire is BINARY now, and that is a dependency worth a guard.

    `wire_encode` returns a zlib stream. If the shared async client were ever
    built with `decode_responses=True`, redis-py would UTF-8-decode that stream
    on the way out and the value would arrive unrecoverable — `wire_decode`
    would return `None` for every read, every reader would rebuild, and the feed
    would go straight back to 692-775 ms with nothing failing and nothing
    logged. That is the same silence LAT-P221 is about, so it gets a test rather
    than a comment.
    """
    from app.tasks.redis_state import get_async_redis_client

    client = get_async_redis_client()  # constructing does not connect
    kwargs = client.connection_pool.connection_kwargs

    assert not kwargs.get("decode_responses"), (
        "the shared Redis client decodes responses, which corrupts the "
        "compressed shared-artifact wire into an unrecoverable str"
    )


def _envelope(payload: dict) -> dict:
    """The envelope `_publish_cross_worker` builds, built the same way."""
    return {
        # Not a literal: the version is part of what the publisher writes, and a
        # sizing helper that drifts off the real envelope is measuring a shape
        # production does not have.
        "v": pic.WIRE_ENVELOPE_VERSION,
        "ns": "market_load",
        "k": "('market_load', 2, 'digest')",
        "stored_wall": 1_788_000_000.0,
        "payload": pic.encode_shared_payload(payload),
    }


def _envelope_bytes(payload: dict) -> int:
    envelope = json.dumps(_envelope(payload), separators=(",", ":"), ensure_ascii=False)
    return len(envelope.encode("utf-8", "replace"))


def _fake_client(redis):
    async def _get_client():
        return redis

    return _get_client
