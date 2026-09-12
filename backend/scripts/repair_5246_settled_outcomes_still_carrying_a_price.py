"""#5246 — zero the price on outcomes the venue has already settled.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15309206` on US Open
men's **semifinal day**, three hours before first serve. The `MORE TENNIS` rail:

    US Open Men's Singles Winner
      Alexander Zverev   34%      <- Kalshi says 49.5%
      Ben Shelton        25%
      Frances Tiafoe      6%
      +45 more
    US Open Women's Singles Winner
      Aryna Sabalenka    45%      <- Kalshi says 57.5%
      Elena Rybakina     33%
      Iga Swiatek         2%      <- out of the tournament

Four men are alive and the card offers 48 names. Iga Swiatek renders as the
third most likely winner of a tournament she is not in. Every live number is
**out by up to 15 points**, on a marquee page, while the site's own hero one
screen above says Zverev is 80% to win this match.

THE NUMBERS ARE WRONG, NOT JUST THE ROSTER, AND THAT IS THE WHOLE POINT. The
survivors' stored probabilities are EXACTLY right. Measured on production
2026-09-11 ~17:2xZ, market 34277822:

    the four semifinalists   0.495 + 0.375 + 0.085 + 0.055 = 1.0100
    all 48 outcomes                                        = 1.4800
    Zverev as rendered            0.495 / 1.4800           =   33.4%
    Zverev after this repair      0.495 / 1.0100           =   49.0%   (venue 49.5%)

The rail renormalises over the column (gotcha #23 — independent binaries can sum
well past 100%), which is SOUND on a live field and unsound the moment most of
the field is dead: the 44 stale rows silently tax every live one. The women's
market is the same shape, 1.2900 -> 1.0300.

WHERE THE RESIDUE COMES FROM, AND WHY NOTHING WILL EVER CLEAR IT. The grade
landed and the price did not. All 44 eliminated men already carry
`is_winner = false, resolution_source = 'api_settlement'` — Kalshi's own
settlement feed graded them correctly, days ago. What the settling statement in
`backfill_winners` never wrote was the PRICE, so each row kept the last number
anyone paid for it. It cannot recover on its own:

  * Measured against the venue 2026-09-11 17:2xZ,
    `GET /events/KXATP-26USO?with_nested_markets=true` returns all 48 markets and
    every `finalized` one carries `yes_bid: null, yes_ask: null, last_price:
    null`. `_kalshi_yes_probability(None, None, None)` is None and every
    price-writing site skips a None.
  * `futures_price_refresh` additionally refuses anything outside `0 < prob < 1`
    — which a settled 0.0 or 1.0 is, by construction.

So a settled leg's price is not stale, it is **unreachable**: no poll will quote
it again, and no poll may write either of the two values it can now legally
hold. That is also why THIS SCRIPT DOES NOT HAVE TO WAIT FOR ITS PRODUCER FIX TO
DEPLOY, which is the opposite of #5221's rule and is worth saying out loud. The
beat cannot re-write what this clears, because the venue hands it nothing to
write; and the producer fix's own `WHERE` only ever touches rows whose
`resolution_source` is NULL or overwritable, which an `api_settlement` row is
not. The two halves are independent, and the data half is what a reader sees.

THE COHORT, re-measured on production 2026-09-11 ~17:2xZ by this script's own
filter. Only markets still `status='open'` are in scope — the 963,492 `resolved`
markets are not rendered as live winner cards, and a repair's blast radius
should stop where the defect stops:

    partition                                    rows    markets
    CLEAR   (a live field survives)              7,127     1,188
    REFUSE  (zeroing would blank the card)       4,613     1,139
    -------------------------------------------------------------
    candidates                                  11,740     2,327

    top of the CLEAR side, by category/source (candidate counts):
      entertainment kalshi 3,164 | politics kalshi 2,299 | football kalshi 1,372
      economics kalshi 1,044 | basketball kalshi 825 | soccer polymarket 818
      baseball kalshi 496 | soccer kalshi 268 | tennis kalshi 217

2,722 probability points of residue sit on open markets. That is the tax, and it
is levied on every live outcome on every one of those cards.

THE REFUSAL, WHICH IS THE SAFETY ARGUMENT. A candidate is cleared only if its
MARKET still has at least one priced outcome that is not itself a settled loser
— the same shape as `futures_price_refresh._KALSHI_FROZEN_CERTAIN_SQL`'s
crowned-sibling clause, and for the same reason: the decisive question is about
the row's SIBLINGS, not the row. Where every priced leg has been graded a loser,
zeroing them all replaces a wrong card with an all-zero card, and an open market
whose entire field is eliminated is a different defect (its market status is
wrong) that this repair must not paper over. It refuses **4,613 of 11,740
candidates across 1,139 markets — 39%** — so the clause is not decoration.

THE VENUE PRECONDITION, AND WHY THE REFUSAL ABOVE WAS NOT ENOUGH (#5515).
Everything above this paragraph reasons from `resolution_source` on the
assumption stated below in "WHAT IS NOT TOUCHED": *the grade is already right.*
**On 2026-09-10 that assumption stopped holding.** #3617's producer began
stamping `is_winner = false, resolution_source = 'api_settlement'` onto legs of
markets Kalshi still lists as `active`, at 742 -> 1,381 -> 4,662 rows/day. This
script did exactly what it was told, on rows that lied to it: the 2026-09-11
21:00Z drain put **167 legs priced >= 50% on screen at 0%**, and a reader on
`https://bainluck.com/futures/52755923` saw the FTSE 100 ladder's "At least
£10,900" rung — stored 0.995, venue `active`, resolving Jan 2027 — render 0%.
322 of those rows were venue-checked and restored; this precondition is what
stops the next drain re-creating them at four times the scale.

The sibling refusal cannot see this defect, and the FTSE market is the proof.
Its eight legs are ALL `api_settlement`; three carry `is_winner = true` and are
priced 0.99. Those three are not settled LOSERS, so `live_field_survives` is
true, so the market CLEARS — the safety clause asks *"would zeroing blank this
card?"*, which is a question about the market's siblings, and a grade fabricated
onto one leg of an otherwise healthy card answers it "no harm done". A refusal
keyed on the row's neighbours can never detect a lie told about the row.

So the premise is now CHECKED rather than assumed, against the only authority
that can settle it — the venue that issued the grade:

  * `venue_verdict()` clears a leg only on POSITIVE agreement: Kalshi reports
    that ticker `finalized`/`settled` **and** `result = 'no'`. That is the venue
    saying, in its own words, this contract closed and this side lost.
  * Everything else REFUSES, and the three reasons are counted separately
    because they mean different things: `active` (the #3617 fabrication),
    `result = 'yes'` (an INVERTED grade — worse than residue, and zeroing it
    would bake in a wrong verdict), and absent/unreadable.
  * A 404 and a transport error are both UNKNOWN and both refuse. They are
    counted apart but not ACTED on apart, and that is deliberate: `market_exists`
    splits them because its caller wants to retire rows on a genuine 404, while
    here both are simply "no agreement", which is the safe side. Reading either
    as licence to write is how a network wobble would zero a live ladder
    (gotcha #36).

THE BAND IS NOT A SUBSTITUTE, and it was measured before being rejected. A
price-band or far-future-date heuristic looks like it would separate these
populations and does not: of 619 venue-checked rows, **46 were genuinely
`finalized`/`'no'` on markets resolving months out** — legitimate early
settlements (an eliminated team, a withdrawn candidate). A band refuses those
too, and a repair that cannot clear a correctly-settled row is not a safer
repair, it is a broken one. Only the venue can tell the two apart.

WHAT THE PRECONDITION COSTS, measured 2026-09-12 on production: the CLEAR side
is 3,055 kalshi rows across **309 distinct event tickers** — one nested-markets
read each, which is why this is affordable inside a script. Polymarket has no
reader here, so its 84 CLEAR rows (2.2 probability points) are refused
`no_venue_reader` and named in the report rather than cleared on trust. That is
the fail-closed direction and it is stated out loud, never silent (gotcha #53).

WHAT IS NOT TOUCHED, and each omission is a column with another owner:

  * `is_winner` / `resolution_source` — the grade is already right. This repair
    changes no verdict; it only stops contradicting one.
  * `opening_probability` / `calibration_probability` — the calibration curve's
    inputs (gotcha #144: the curve price is `COALESCE(calibration_probability,
    opening_probability)`). Zeroing a terminal price moves no published point.
  * `futures_odds_snapshots` — the full price history, untouched, so nothing
    that was ever true stops being recoverable.
  * `last_updated` — the PRICE TOUCH clock three surfaces read as "when did
    somebody last look at this number" (LIVE-077 / CERT-1936, and
    `app/routes/playoffs.py` reads it as a liveness gate). This script reads no
    venue price. `price_changed_at` IS stamped, because the stored price really
    does move, which is exactly what that column was added to record (#2024).

RESTORE, one command (D51(b)):

    UPDATE futures_outcomes fo
       SET current_probability   = b.current_probability,
           current_american_odds = b.current_american_odds,
           price_changed_at      = b.price_changed_at
      FROM bak_5246_futures_outcomes b
     WHERE b.id = fo.id
       AND fo.id IN (SELECT outcome_id FROM bak_5246_repair_manifest);

USAGE:

    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py            # plan only
    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py --backup
    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py --backup --apply
"""

import argparse
import asyncio
import collections
import os
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_5246_futures_outcomes"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited via #5221). A full-row backup records where a row CAME FROM and
#: cannot record that this script is what moved it; without the manifest a
#: restore can only ask "does the live row differ from its backup?", which is
#: also true of a row a poll has legitimately re-priced since.
MANIFEST_TABLE = "bak_5246_repair_manifest"

#: The grade that means THE VENUE SAID SO, and the only one in scope.
#:
#: Every other value in `resolution_source` is either an inference the system is
#: allowed to revise (`pass2_guess`, `multi_max_prob`, `binary_higher_wins` and
#: the rest of `OVERWRITABLE_WINNER_SOURCES_SQL`) or a derivation from data that
#: can itself be wrong (`box_score`, `game_score` — see #5221, which existed
#: because one of those was computed off the wrong period). Zeroing a price on
#: the strength of a guess would spend a reader-visible number on a verdict we
#: are not sure of. `api_settlement` is written only from Kalshi's own settled
#: events feed, off a `status: finalized` market carrying an explicit
#: `result` — it is the venue closing the contract, and there is nothing better
#: to wait for.
SETTLED_SOURCE = "api_settlement"

#: The price floor that separates "carries residue" from "already zero".
#:
#: `current_probability` is `Numeric(7, 6)`, and a genuine zero stores as
#: exactly 0.000000, so `> 0` alone would be correct. The floor is half a basis
#: point instead, so that a row already repaired — or one a future producer
#: rounds to 0.000000 by a different route — is not re-planned on every run, and
#: so the count this script reports is the count of rows a reader could actually
#: see a number on.
RESIDUE_FLOOR = 0.0005

#: The sanity floor. 7,127 clearable rows were measured at ~17:2xZ on 2026-09-11.
#: Unlike #5221's population this one does NOT grow while a fix waits to deploy —
#: it grows whenever a round completes anywhere in sport, and it shrinks whenever
#: a market flips `open` -> `resolved` and leaves scope. So the floor is set at
#: ~80% of the measurement and a plan below it needs a DISCRIMINATOR rather than
#: an `--allow-small` override, because "the filter broke" and "the job is done"
#: are two different causes that both present as a small plan.
SANITY_FLOOR = 5700

#: The venue statuses that mean KALSHI HAS CLOSED THIS CONTRACT.
#:
#: `active` is the one that matters and it is not here: it is what the venue
#: reported for every one of the 167 legs this script zeroed on 2026-09-11 (see
#: the module docstring). `initialized` and `closed` are also absent — a market
#: that has stopped trading but has not been graded has no result to agree with.
VENUE_SETTLED_STATUSES = frozenset({"finalized", "settled"})

#: The only venue result that AGREES with a stored `is_winner = false`.
#:
#: `'yes'` is not merely disagreement, it is an inverted grade: the venue says
#: this side WON and the row says it lost. Zeroing its price would spend a
#: reader-visible number making a wrong verdict look settled, so it refuses and
#: is counted under its own reason. `''` is an ungraded market (gotcha: a
#: `finalized` Kalshi market can carry an empty result), and `'void'` is a
#: cancelled contract whose price is not this script's to retire.
VENUE_LOSS_RESULT = "no"

#: The three venue verdicts. Only the first may write.
VENUE_AGREES = "agrees"
VENUE_REFUTES = "refutes"
VENUE_UNKNOWN = "unknown"

#: Concurrent nested-markets reads.
#:
#: MEASURED DOWN FROM 8, which is not a tuning preference. At 8-wide Kalshi
#: rate-limited 183 of 309 event tickers, and because the first cut of the
#: reader refused on any non-200 those became "421 rows `event_unreadable`" in
#: the report — a number that reads like a venue finding and was produced
#: entirely by this script. Three of the first six re-read sequentially answered
#: 200. 4-wide plus the 429 backoff in `read_event_book` is what makes the
#: refusal counts mean what they say.
VENUE_CONCURRENCY = 4

#: Attempts per event before a read is abandoned. A 429 costs an attempt and a
#: sleep; a 404 costs neither, because it is an answer.
VENUE_READ_ATTEMPTS = 4

#: Backoff base, multiplied by the attempt number.
VENUE_BACKOFF_SECONDS = 2.0

#: Sources this script can ask. A source absent from this set is refused
#: `no_venue_reader` — never cleared on the strength of the stored grade alone,
#: which is the entire premise #5515 refuted.
VENUE_READABLE_SOURCES = frozenset({"kalshi"})

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_outcomes INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_outcomes s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_outcomes s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run. A missing table still yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    # THE SCAN. One row per candidate, carrying the two facts the classifier
    # needs: which market it belongs to, and whether that market still has a
    # live priced field to normalise over.
    #
    # `market_id IN (SELECT id FROM futures_markets WHERE status = 'open')`
    # rather than a JOIN: measured on production, the JOIN form of this scan
    # times out at the 10s db-query budget and the IN form returns, because it
    # lets the planner drive from the 51,762 open markets instead of the
    # 3.9M-row outcome table.
    "scan": f"""
        SELECT fo.id            AS outcome_id,
               fo.market_id     AS market_id,
               fo.name          AS outcome_name,
               fo.external_id   AS outcome_ticker,
               fo.current_probability AS residue,
               EXISTS (
                   SELECT 1 FROM futures_outcomes live
                    WHERE live.market_id = fo.market_id
                      AND live.current_probability > {RESIDUE_FLOOR}
                      AND NOT (live.is_winner = false
                               AND live.resolution_source = '{SETTLED_SOURCE}')
               )                AS live_field_survives
          FROM futures_outcomes fo
         WHERE fo.market_id IN (SELECT id FROM futures_markets WHERE status = 'open')
           AND fo.is_winner = false
           AND fo.resolution_source = '{SETTLED_SOURCE}'
           AND fo.current_probability > {RESIDUE_FLOOR}
         ORDER BY fo.market_id, fo.id
    """,
    # The venue coordinates of each candidate market, fetched separately rather
    # than joined into `scan`. The scan's shape is load-bearing and measured —
    # its comment above records that the JOIN form times out — so the two extra
    # columns come from an indexed by-id lookup over the ~2,300 candidate
    # markets instead of risking that plan.
    "market_meta": "SELECT id, source, external_id FROM futures_markets "
                   "WHERE id = ANY(CAST(:ids AS int[]))",
    # THE FORWARD WRITE, and it is a compare-and-swap on every column of the
    # premise. If anything re-graded or re-priced the row between the plan and
    # the write — a poll that found the venue quoting again, a grader that
    # changed its mind, the fixed producer arriving first — the statement
    # no-ops instead of overwriting a fresher, better number with a zero.
    #
    # `last_updated` is deliberately NOT stamped; `price_changed_at` is. See the
    # module docstring: one column answers "when did a poll last look at this",
    # which this script is not, and the other answers "when did the stored price
    # last move", which is exactly what is happening.
    "clear": "UPDATE futures_outcomes "
             "SET current_probability = 0, "
             "    current_american_odds = NULL, "
             "    price_changed_at = NOW() "
             "WHERE id = :oid "
             "  AND is_winner = false "
             f"  AND resolution_source = '{SETTLED_SOURCE}' "
             f"  AND current_probability > {RESIDUE_FLOOR}",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  outcome_id  integer PRIMARY KEY,"
                  f"  market_id   integer NOT NULL,"
                  f"  applied_at  timestamptz NOT NULL DEFAULT NOW())",
    # A row can legitimately be cleared, restored and cleared again, so the
    # later row REPLACES the earlier one; `DO NOTHING` would leave the restore
    # reasoning about a move that is two states stale.
    "man_record": f"INSERT INTO {MANIFEST_TABLE} (outcome_id, market_id, applied_at) "
                  f"VALUES (:oid, :mid, :now) "
                  f"ON CONFLICT (outcome_id) DO UPDATE SET "
                  f"  market_id = EXCLUDED.market_id,"
                  f"  applied_at = EXCLUDED.applied_at",
}


def classify(legs):
    """Split one market's settled-loser legs into (clear, refuse).

    The market is the unit of judgement, not the leg: every candidate on a
    market either clears or is refused together, because the question asked —
    *does a live priced field survive here?* — is a property of the market. A
    per-leg answer would clear the legs of a market one at a time and blank the
    card on the last one.

    `all()` and not `legs[0]`, and the difference is fail-closed vs fail-open.
    The scan's `EXISTS` is keyed on `fo.market_id` alone, so today every leg of
    a market carries the identical flag and the two forms agree on every
    production row. That is a property of one subquery, not of this function —
    and reading `legs[0]` would let a future scan that computed the flag per-leg
    clear a whole market off one row's answer, silently, which is the exact
    outcome the refusal exists to prevent. Disagreement resolves to REFUSE, so
    the safe direction is also the one that needs no new plumbing to be seen:
    the rows land in the refused count.
    """
    survives = all(bool(leg["live_field_survives"]) for leg in legs)
    return (legs, []) if survives else ([], legs)


class VenueCall(NamedTuple):
    """One leg's venue verdict and the reason, which is reported, not acted on.

    Two fields because the DECISION is binary — only ``VENUE_AGREES`` may write
    — while the DIAGNOSIS has five distinguishable shapes that mean very
    different things about the health of the system. Collapsing them would hide
    an inverted grade inside the same counter as a network blip, and it was
    exactly that kind of collapse (a verdict and its wording in one string) that
    made `explain_small_plan`'s discriminator decorative for two sessions.
    """

    verdict: str
    reason: str


def venue_verdict(leg, book) -> VenueCall:
    """Does the venue itself agree this leg is a settled loser?

    PURE, and takes the already-fetched book rather than doing the read, so the
    rule can be exercised on every shape the venue can produce — including the
    ones that are awkward to provoke over a network — without a fixture that
    mocks HTTP.

    ``book`` is the event's nested-markets index (``{ticker: market}``) or
    ``None`` when the event could not be read at all. The default is REFUSE: the
    only path to ``VENUE_AGREES`` is an explicit, positive statement from Kalshi
    that this exact ticker is closed and lost.
    """
    if leg.get("source") not in VENUE_READABLE_SOURCES:
        return VenueCall(VENUE_UNKNOWN, f"no_venue_reader:{leg.get('source')}")
    if not leg.get("event_ticker"):
        return VenueCall(VENUE_UNKNOWN, "no_event_ticker")
    if book is None:
        return VenueCall(VENUE_UNKNOWN, "event_unreadable")

    ticker = leg.get("outcome_ticker")
    market = book.get(ticker)
    if market is None:
        return VenueCall(VENUE_UNKNOWN, "leg_absent_from_book")

    status = (market.get("status") or "").lower()
    if status not in VENUE_SETTLED_STATUSES:
        # The #3617 fabrication lands here: the venue is still trading it.
        return VenueCall(VENUE_REFUTES, f"venue_status:{status or 'missing'}")

    result = (market.get("result") or "").lower()
    if result != VENUE_LOSS_RESULT:
        return VenueCall(VENUE_REFUTES, f"venue_result:{result or 'empty'}")

    return VenueCall(VENUE_AGREES, "")


class VenueRead(NamedTuple):
    """One event's book, or ``None`` plus WHY it could not be read.

    The reason never changes the decision — every unreadable event refuses its
    legs — but it decides whether an operator should re-run or investigate, and
    those are opposite actions. Measured 2026-09-12: a first cut of this reader
    treated any non-200 as unreadable at 8-wide concurrency and reported 421
    rows `event_unreadable`, which read as "the venue does not list these". It
    was Kalshi rate-limiting: three of the first six re-read sequentially
    answered 200 and three answered 429. An absence produced by the rig, wearing
    a finding's clothes.
    """

    book: dict | None
    reason: str


async def read_event_book(svc, event_ticker) -> VenueRead:
    """Fetch one event's nested markets as ``{ticker: market}``, or say why not.

    Retries 429 with a widening backoff, because a rate limit is the venue
    saying "later", not "no" — refusing on the first one silently shrinks the
    repair and, worse, reports the shortfall as though the venue had answered.
    A 404, a persistent 429 and a transport error all end in ``book = None``,
    which refuses every leg beneath them (module docstring, gotcha #36); they
    are merely counted apart.

    This does not call :meth:`KalshiAPIService.get_event`, which returns ``None``
    for a 404 *and* ``None`` after three failed attempts, because a reader that
    cannot distinguish "no event" from "no answer" cannot honestly report why it
    refused. The transport is the service's client either way, so the API key,
    timeouts and connection pool are the configured ones.
    """
    from app.utils.agent_origin import tagged

    url = f"{svc.BASE_URL}/events/{event_ticker}"
    for attempt in range(VENUE_READ_ATTEMPTS):
        try:
            # Notice 39: every outbound call from `scripts/` goes through the
            # carrier. `is_our_host` decides at runtime, so tagging a
            # third-party venue read costs nothing and keeps the static rule
            # the simple one.
            response = await svc.client.get(
                url,
                params={"with_nested_markets": "true"},
                headers=tagged(url),
            )
            if response.status_code == 429:
                await asyncio.sleep(VENUE_BACKOFF_SECONDS * (attempt + 1))
                continue
            if response.status_code == 404:
                return VenueRead(None, "http_404")
            if response.status_code != 200:
                return VenueRead(None, f"http_{response.status_code}")
            markets = (response.json().get("event") or {}).get("markets") or []
        except Exception:
            if attempt + 1 < VENUE_READ_ATTEMPTS:
                await asyncio.sleep(VENUE_BACKOFF_SECONDS * (attempt + 1))
                continue
            return VenueRead(None, "transport_error")
        else:
            return VenueRead(
                {m.get("ticker"): m for m in markets if m.get("ticker")}, ""
            )
    return VenueRead(None, "rate_limited")


async def confirm_against_venue(legs, reader=None):
    """Split planned legs into (confirmed, refused, reasons) by asking the venue.

    Returns the legs the venue positively agrees are settled losers, the ones it
    did not, and a count per reason so the operator sees WHY a plan shrank.
    Called before the write loop and its result gates that loop — a version of
    this that ran afterwards, or whose verdict the loop ignored, would leave the
    script doing precisely what #5515 was filed for.
    """
    readable = [
        leg for leg in legs if leg.get("source") in VENUE_READABLE_SOURCES
    ]
    tickers = sorted({
        leg.get("event_ticker") for leg in readable if leg.get("event_ticker")
    })

    reads = {}
    if tickers:
        reads = await (reader or _read_books)(tickers)

    confirmed, refused = [], []
    reasons = collections.Counter()
    for leg in legs:
        read = reads.get(leg.get("event_ticker"))
        call = venue_verdict(leg, read.book if read else None)
        if call.verdict == VENUE_AGREES:
            confirmed.append(leg)
            continue
        refused.append(leg)
        reason = call.reason
        # Refine the generic unreadable into the transport truth, so a
        # rate-limited run cannot be mistaken for a venue that went dark.
        if reason == "event_unreadable" and read is not None:
            reason = f"event_unreadable:{read.reason}"
        reasons[reason] += 1
    return confirmed, refused, reasons


async def _read_books(tickers) -> dict:
    """Fetch every event ticker's book, bounded-concurrency, refusing on error."""
    from app.services.kalshi_api import KalshiAPIService

    svc = KalshiAPIService()
    sem = asyncio.Semaphore(VENUE_CONCURRENCY)

    async def one(ticker):
        async with sem:
            return ticker, await read_event_book(svc, ticker)

    try:
        pairs = await asyncio.gather(*(one(t) for t in tickers))
    finally:
        await svc.close()
    return dict(pairs)


def backup_is_exact(recon) -> bool:
    """The D51 gate: every clearable row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


class SmallPlanVerdict(NamedTuple):
    """A small plan's diagnosis AND what it means for `--apply`.

    These are two facts, and collapsing them into one string is what made the
    discriminator below decorative. See `explain_small_plan`.
    """

    #: True only for the cause that must stop a write.
    blocks_apply: bool
    #: Operator-facing explanation; "" when the plan is not small at all.
    message: str


def explain_small_plan(plan_count: int, manifest_rows: int) -> SmallPlanVerdict:
    """Why is the plan below the floor — a broken filter, or a done job?

    A sanity floor that names two causes needs a DISCRIMINATOR, not an override
    flag: `--allow-small` would let the broken-filter case through wearing the
    completed-run case's clothes. The manifest is the discriminator, because
    only a successful forward write puts a row in it.

    THE DISCRIMINATOR HAS TO REACH THE DECISION, AND FOR TWO SESSIONS IT DID
    NOT. This returned a bare `str`, and the caller's test was `if small:` — so
    both causes refused `--apply` identically and the discriminator only ever
    changed the wording of the refusal. It cost the #5246 re-drain a session:
    the drain leaked 189 rows, the guard (#5411) shipped, and the re-run that
    was supposed to clear the residue could not write, on the one branch the
    docstring was written to let through. A handoff then recorded "the floor
    will NOT block you" from reading THIS docstring, which describes the design
    correctly and the behaviour not at all — the definition read right and the
    enforcement was the bug.

    So the verdict is now structured, and the two facts are separate: every
    small plan still gets an explanation printed, and only `FILTER BROKE`
    stops the write. Fail-closed stays the default — an unrecognised shape
    would have to be added here deliberately, as a blocking one.
    """
    if plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(blocks_apply=False, message="")
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(
            blocks_apply=False,
            message=(
                f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} "
                f"and {plan_count} remain clearable; together they clear the "
                f"floor of {SANITY_FLOOR}. This is a drained backlog, not a "
                f"broken filter, so --apply proceeds."
            ),
        )
    return SmallPlanVerdict(
        blocks_apply=True,
        message=(
            f"FILTER BROKE — only {plan_count} rows are clearable and "
            f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} "
            f"of an expected {SANITY_FLOOR}+ are accounted for. Either the "
            f"cohort SQL stopped matching or markets left `open` faster than "
            f"expected. Do NOT lower the floor; find the rows."
        ),
    )


async def backup(session, outcome_ids):
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["bak_copy"]), {"ids": outcome_ids})
    await session.commit()


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def reconcile_backup(session, outcome_ids) -> dict:
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = (
        await session.execute(text(SQL["bak_missing"]), {"ids": outcome_ids})
    ).scalar_one()
    return {"futures_outcomes": int(missing)}


async def attach_venue_coordinates(session, legs) -> None:
    """Stamp each leg with its market's `source` and venue event ticker.

    A leg whose market is missing from the lookup keeps ``source = None``, which
    `venue_verdict` refuses as `no_venue_reader:None` — the fail-closed
    direction, so a gap in this step can never widen what gets written.
    """
    from sqlalchemy import text

    market_ids = sorted({leg["market_id"] for leg in legs})
    if not market_ids:
        return
    rows = (
        await session.execute(text(SQL["market_meta"]), {"ids": market_ids})
    ).fetchall()
    meta = {
        r._mapping["id"]: (r._mapping["source"], r._mapping["external_id"])
        for r in rows
    }
    for leg in legs:
        source, event_ticker = meta.get(leg["market_id"], (None, None))
        leg["source"] = source
        leg["event_ticker"] = event_ticker


def plan(rows):
    """Group the candidate scan by market and classify each one."""
    by_market = collections.OrderedDict()
    for row in rows:
        leg = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        by_market.setdefault(leg["market_id"], []).append(leg)

    clear, refuse = [], []
    for legs in by_market.values():
        c, r = classify(legs)
        clear.extend(c)
        refuse.extend(r)
    return clear, refuse


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        rows = (await s.execute(text(SQL["scan"]))).fetchall()
        clear, refuse = plan(rows)
        if args.limit:
            clear = clear[: args.limit]

        markets_clear = len({leg["market_id"] for leg in clear})
        markets_refuse = len({leg["market_id"] for leg in refuse})
        residue = sum(float(leg["residue"] or 0) for leg in clear)

        print(f"candidates : {len(rows)}")
        print(f"CLEAR      : {len(clear)} rows / {markets_clear} markets "
              f"({residue:.1f} probability points of residue)")
        print(f"REFUSE     : {len(refuse)} rows / {markets_refuse} markets "
              f"(no live priced field would survive)")

        manifest_rows = await manifest_count(s)
        # The floor is asked about the PRE-venue plan, deliberately. It was
        # calibrated on the sibling rule's cohort and exists to answer "did the
        # cohort SQL stop matching?"; the venue precondition below is a
        # deliberate narrowing, not a broken filter, and letting it drive the
        # floor would make every correctly-refused drain look like a defect.
        small = explain_small_plan(len(clear), manifest_rows)
        if small.message:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"   {small.message}")

        await attach_venue_coordinates(s, clear)
        confirmed, unconfirmed, reasons = await confirm_against_venue(clear)
        confirmed_residue = sum(float(leg["residue"] or 0) for leg in confirmed)

        print(f"\nVENUE       : {len(confirmed)} of {len(clear)} CLEAR rows "
              f"confirmed settled-and-lost by the venue "
              f"({confirmed_residue:.1f} of {residue:.1f} points)")
        for reason, n in reasons.most_common():
            print(f"  refused   : {n:>6}  {reason}")
        if clear and not confirmed:
            # Loud, because a silent zero-yield run is indistinguishable from a
            # successful one and reads as "nothing left to fix" (gotcha #53).
            print("  ⚠️  ZERO YIELD — the venue confirmed none of the plan. "
                  "That is a finding about the grades, not an idle run.")

        if not args.backup and not args.apply:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return

        # Only venue-confirmed rows are ever backed up or written. Everything
        # downstream of here reads `confirmed`; `clear` is a reporting number.
        outcome_ids = [leg["outcome_id"] for leg in confirmed]
        if not outcome_ids:
            print("\nnothing to do.")
            return

        if args.backup:
            await backup(s, outcome_ids)
            print(f"\nbacked up {len(outcome_ids)} rows into {BAK_TABLE}")

        recon = await reconcile_backup(s, outcome_ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned row.")
            return

        if not args.apply:
            print("\nbackup staged — re-run with --apply to write.")
            return

        if small.blocks_apply:
            print("REFUSING --apply: plan is below the sanity floor (see above).")
            return

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = declined = 0
        for leg in confirmed:
            r = await s.execute(text(SQL["clear"]), {"oid": leg["outcome_id"]})
            if r.rowcount:
                applied += 1
                await s.execute(
                    text(SQL["man_record"]),
                    {"oid": leg["outcome_id"], "mid": leg["market_id"], "now": now},
                )
            else:
                declined += 1
        await s.commit()
        print(f"\napplied {applied}, declined {declined} "
              f"(a decline means the row moved under us — the good case)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="copy every planned row into the backup table first")
    p.add_argument("--apply", action="store_true",
                   help="write the zeros (requires an exact backup)")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
