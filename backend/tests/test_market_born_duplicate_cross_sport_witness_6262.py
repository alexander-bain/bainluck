"""#6262 gap B — refusal 6 was asking the one witness that is known to be wrong.

THE READER'S COMPLAINT, photographed on production 2026-09-15 03:08Z at 390px
(`artifacts-lane1-334/03-before-games-crop.png`), while the game was live:

    GAMES (70)
    ┌──────────────────────────────────────────────────────────┐
    │ NFL                            ● 5:13 – 4th Quarter      │
    │ Kansas City Chiefs                          31    100%   │
    │ Denver Broncos                              10      0%   │   14638896
    └──────────────────────────────────────────────────────────┘
    ┌──────────────────────────────────────────────────────────┐
    │ OTHER BASKETBALL                    Today 8:15 PM        │
    │ D  Denver                                                │
    │    No price yet                                          │   15305046
    │ KC Kansas City                                           │
    └──────────────────────────────────────────────────────────┘

A search for "Kansas City" offered the chips **"Other Basketball (1)"** and
**"Other Soccer (1)"**; both are that night's Chiefs–Broncos game, tipped off
three hours late with no price. Those rows hold a proven canonical — the market
that minted each one now carries `event_id 14638896` — so refusals 1-5 admit
them. Refusal 6 declined them all.

WHY REFUSAL 6 WAS WRONG HERE, AND WHY THIS IS NOT A RELAXATION
---------------------------------------------------------------
Refusal 6 compared the canonical's sport family against the GHOST ROW's. A
market-born row's `sport_id` is stamped once, at mint, from whatever
`_categorize_kalshi_market` could tell at the time — and for an UNMAPPED Kalshi
series that is step 2, a guess off the market's TEXT. `sport_keys.py` records
what that produces, in its own words: one NFL series scattered across five
sports, `kxnflrace`'s 80 markets ALL landing on `basketball_other`, "Buffalo vs
Houston: Fantasy POINTS" reading as basketball (Q453, #5621). The event row
minted in the meantime keeps the guess forever.

So the disagreement refusal 6 was firing on is not evidence of a cross-sport
read. It is the fossil of a bug fixed elsewhere.

🔴 THE FIRST BUILD OF THIS CLAUSE PICKED THE WRONG SECOND WITNESS, AND THE
BATTERY BELOW IS SHAPED BY THAT (CERT-2891)
---------------------------------------------------------------------------
It asked the MARKET's `sport_id`. But `_set_market_sport_fields` does

    market.sport_id = matched_event["sport_id"]

so the market's sport is COPIED FROM THE EVENT the drain is being asked to
confirm. The supporting measurement — "in 42 of 42 rows the market's sport key
equals the canonical's, byte for byte" — was not corroboration at all. It was a
tautology, and a perfect agreement rate between two stored columns is the
SIGNATURE of one being a copy of the other rather than evidence about either.

The failure it admits is not theoretical: a soccer ghost whose soccer market has
been mis-attached to a TENNIS canonical refuses on the first pass, the writer
then stamps the market tennis, and the second pass ADMITS the cross-sport read
this refusal exists to stop. `test_real_link_writer_cannot_make_cross_sport_
drain_self_confirming_6262` runs that sequence through the real writer.

THE WITNESS THAT IS ACTUALLY INDEPENDENT
-----------------------------------------
The anchor's `source_id` — the venue's own ticker, stored verbatim by
`kalshi_anchor_key` — read through `get_sport_key_from_ticker`, a pure function
over the static maps in `sport_keys.py`. Nothing derives an anchor's `source_id`
from an event, and the witness needs no join to `futures_markets` at all, so
neither the link writer nor the market row can move it.

    ghost 15305032  basketball_other  <- KXNFLRACE-26SEP13BUFHOU-14  -> football
    ghost 15305039  basketball_other  <- KXNFLRACE-26SEP13GBMIN-14   -> football
    ghost 15305046  basketball_other  <- KXNFLRACE-26SEP14DENKC-14   -> football
    ghost 15311150  soccer_other      <- KXNFLFG-26SEP14DENKC        -> NONE

MEASURED by running `_DRAIN_VERDICT_SQL` ITSELF over the whole `live`+`scheduled`
band, production 2026-09-15 05:30Z — 1,337 rows, 45 clearing every other refusal,
41 already folding on the ghost row's own key. **The ticker witness adds 3. Not
4, and not the 42 of 42 the blocked build claimed.**

The fourth is `15311150`: `kxnflfg` is in neither ticker map, so there is no
second witness and it stays refused. It is pinned below by name rather than
rounded away, because an under-covering guard is the safe direction and a
silently over-claimed one is not. (A fifth row of the same SHAPE, 15305029, is
declined by refusal 7 for holding its own markets — which is why the count above
was taken after every refusal rather than before them.)

WHAT IS STILL REFUSED IS THE WHOLE POINT
-----------------------------------------
The guard exists for a market mis-attached ACROSS sports, and a mis-attached
market still carries its own venue ticker. The tests below pin five refusing
shapes: both witnesses disagreeing; the same, AFTER the real writer has run;
two distinct tickers on one ghost; a ticker no map knows; and a canonical whose
own key is unreadable.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import _set_market_sport_fields
from app.utils.event_completion import (
    KALSHI_OCCURRENCE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
)
from app.utils.sport_keys import get_sport_key_from_ticker

from tests.test_market_born_duplicate_reads_as_canonical_q050 import (
    CANONICAL,
    GHOST,
    SOCCER_TICKER,
    SPORT_SOCCER,
    SPORT_TENNIS_ATP,
    SPORT_TENNIS_US_OPEN,
    UNMAPPED_TICKER,
    _connect,
    _plant_specimen,
    _resolve,
)

#: `sports` rows the base specimen does not plant.
SPORT_BASKETBALL = 3
SPORT_NFL = 5

#: The three production rows this ship folds, each with the ticker that minted
#: it. Named so a revert says who comes back onto the page.
_FOLDED_ROWS = [
    pytest.param("15305032", "KXNFLRACE-26SEP13BUFHOU-14", id="bills-texans"),
    pytest.param("15305039", "KXNFLRACE-26SEP13GBMIN-14", id="packers-vikings"),
    pytest.param("15305046", "KXNFLRACE-26SEP14DENKC-14", id="chiefs-broncos"),
]

#: Same shape, and deliberately NOT in the list above: on production this row
#: holds its own markets, so refusal 7 declines it before refusal 6 is reached.
#: It is here so that a later reader counting `KXNFLRACE` ghosts does not think
#: one went missing.
_REFUSED_UPSTREAM = ("15305029", "KXNFLRACE-26SEP10SFLAR-14")


def _plant_nfl_ghost(conn, ticker, *, ghost_sport=SPORT_BASKETBALL, **kwargs):
    """The production shape: a `basketball_other` row minted by an NFL ticker."""
    _plant_specimen(
        conn,
        ghost_sport=ghost_sport,
        canonical_sport=SPORT_NFL,
        market_ticker=ticker,
        **kwargs,
    )
    conn.executemany(
        "INSERT INTO sports (id, key) VALUES (?, ?)",
        [(SPORT_BASKETBALL, "basketball_other"), (SPORT_NFL, "americanfootball_nfl")],
    )
    conn.commit()


# =============================================================================
# The witness's own premise, before anything is asserted about the drain.
# =============================================================================


def test_the_tickers_these_tests_steer_with_are_real_ones_6262():
    """🔴 EVERY FIXTURE BELOW IS VACUOUS IF THIS IS NOT TRUE.

    The witness is a longest-prefix lookup over `sport_keys.py`'s maps, so an
    INVENTED ticker answers `None` — and a test that meant to plant "the ticker
    says football" would silently be testing the no-witness branch instead, and
    would pass against an implementation that had no second witness at all.
    So the map is asked directly, here, once.
    """
    assert get_sport_key_from_ticker(SOCCER_TICKER) == "soccer_epl"
    assert get_sport_key_from_ticker("KXATPMATCH-26AUG30VALMON") == "tennis_atp"
    nfl = [p.values[1] for p in _FOLDED_ROWS] + [_REFUSED_UPSTREAM[1]]
    for ticker in nfl:
        assert get_sport_key_from_ticker(ticker) == "americanfootball_nfl", ticker
    # ...and the one that is deliberately absent from both maps.
    assert get_sport_key_from_ticker(UNMAPPED_TICKER) is None


# =============================================================================
# The ship.
# =============================================================================


@pytest.mark.parametrize("row,ticker", _FOLDED_ROWS)
def test_a_stale_mint_time_sport_does_not_outvote_the_anchor_ticker_6262(row, ticker):
    """THE SHIP. The ghost row says basketball; its own venue ticker says NFL.

    Planted in the shape of the production rows above. Before this change every
    one of these rendered as a second card under the real game.

    🔴 `market_sport` is left at the base specimen's tennis — a value that
    matches NOTHING here. The row still folds, which is the positive proof that
    `futures_markets.sport_id` is not consulted at all (CERT-2891).
    """
    conn = _connect()
    _plant_nfl_ghost(conn, ticker)
    assert _resolve(conn) == CANONICAL, (
        f"{row} (basketball_other, minted by {ticker}) is still refused — "
        "the reader gets the game twice"
    )


def test_the_fifth_production_row_stays_refused_for_want_of_a_map_entry_6262():
    """15311150 is NOT folded, and that is stated rather than rounded away.

    `kxnflfg` is in neither ticker map, so `get_sport_key_from_ticker` answers
    `None`, there is no second witness, and the `soccer_other` ghost falls back
    to its own key against an NFL canonical: refused. Mapping the series is a
    `sport_keys.py` change with its own blast radius and is not smuggled in
    under this one.

    This is the honest 4-of-5. A build claiming 5 of 5 — or the blocked build's
    42 of 42 — goes red here.
    """
    conn = _connect()
    _plant_nfl_ghost(conn, UNMAPPED_TICKER, ghost_sport=SPORT_SOCCER)
    assert _resolve(conn) is None


def test_the_ghost_rows_own_key_is_still_a_witness_on_its_own_6262():
    """The rows that were already folding must keep folding.

    The disjunction's other arm: the ticker is unknown to both maps, so there is
    no second witness and the ghost row's own key has to carry it — exactly as
    it did before gap B. A change that REPLACED the witness rather than adding
    one would go red here.
    """
    conn = _connect()
    _plant_specimen(conn, market_ticker=UNMAPPED_TICKER)
    assert _resolve(conn) == CANONICAL


# =============================================================================
# What is still refused. Five shapes, because one would prove nothing.
# =============================================================================


def test_real_link_writer_cannot_make_cross_sport_drain_self_confirming_6262():
    """🔴 CERT-2891's counterexample, run forward through the REAL writer.

    The sequence that broke the blocked build, in three acts:

      1. A soccer market, mis-attached to a TENNIS canonical, on a soccer ghost.
         Both witnesses say soccer; the drain refuses. Everyone agrees so far.
      2. `_set_market_sport_fields` — the real one, imported, not a paraphrase —
         runs with the tennis event. It COPIES the event's sport onto the
         market. That copy is asserted here rather than assumed, because it is
         the whole mechanism.
      3. The drain is asked again over the row the writer left behind.

    Under the blocked build act 3 ADMITS: the market now says tennis, the
    canonical says tennis, and a witness made of the answer confirms it. Under
    the ticker witness it refuses, because `KXEPLGAME-…` said soccer before the
    writer ran and says soccer after.
    """
    conn = _connect()
    _plant_specimen(
        conn,
        ghost_sport=SPORT_SOCCER,
        canonical_sport=SPORT_TENNIS_ATP,
        market_ticker=SOCCER_TICKER,
        market_sport=SPORT_SOCCER,
    )
    assert _resolve(conn) is None, "act 1: the pre-link state must already refuse"

    # Act 2 — the real stamping path, on a market wearing the soccer ticker.
    market = SimpleNamespace(
        external_id=SOCCER_TICKER, sport_id=SPORT_SOCCER, llm_sport_category=None
    )
    _set_market_sport_fields(market, {"sport_id": SPORT_TENNIS_ATP})
    assert market.sport_id == SPORT_TENNIS_ATP, (
        "the coupling CERT-2891 named is gone — if the writer no longer copies "
        "the event's sport onto the market, this test's premise needs rewriting, "
        "not deleting"
    )
    conn.execute(
        "UPDATE futures_markets SET sport_id = ? WHERE external_id = ?",
        (market.sport_id, SOCCER_TICKER),
    )
    conn.commit()

    # Act 3 — the verdict must not have moved.
    assert _resolve(conn) is None, (
        "the link writer stamped the canonical's sport onto the market and the "
        "drain believed it — refusal 6 is confirming itself (CERT-2891)"
    )


def test_a_market_mis_attached_across_sports_is_still_refused_6262():
    """The outcome the guard exists for, with the witness moved onto the ticker.

    A soccer market has been moved onto a tennis event. Both witnesses say
    soccer, the canonical says tennis, and the row is refused — so re-witnessing
    refusal 6 did not blunt the direction it was written to refuse.
    """
    conn = _connect()
    _plant_specimen(
        conn,
        ghost_sport=SPORT_SOCCER,
        canonical_sport=SPORT_TENNIS_ATP,
        market_ticker=SOCCER_TICKER,
    )
    assert _resolve(conn) is None


def test_two_distinct_tickers_yield_no_second_witness_even_in_one_sport_6262():
    """Ambiguity is not evidence — refusal 4's reading, applied to the sport.

    Two market anchors on one ghost, so `market_ids` is 2 and there is no second
    witness at all. The row falls back to its own key: basketball against an NFL
    canonical, refused.

    🔴 THIS BRANCH IS DELIBERATELY COARSER THAN IT COULD BE, AND THE COARSENESS
    IS THE ASSERTION. Both tickers below are NFL, so a per-ticker derivation
    would collapse them to one witness and fold the row. The aggregation is
    `count(DISTINCT source_id)` inside the verdict statement instead, which
    keeps refusal 6 in the one statement that is `_DRAIN_VERDICT_SQL` — and
    errs toward REFUSAL, the safe direction. Measured: 7,987 of 7,987
    market-born ghosts carry exactly one distinct market anchor, so the branch
    is empty in production today.

    The direction that would matter if it were inverted: taking ANY agreeing
    anchor rather than requiring one would let a single stray attachment fold
    anything onto anything.
    """
    conn = _connect()
    _plant_nfl_ghost(conn, "KXNFLRACE-26SEP14DENKC-14")
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", "KXNFLRACE-26SEP13GBMIN-14", "market"),
    )
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id, sport_id) "
        "VALUES (?, ?, ?, ?)",
        ("kalshi", "KXNFLRACE-26SEP13GBMIN-14", CANONICAL, SPORT_NFL),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_an_unmapped_ticker_cannot_rescue_a_cross_sport_pair_6262():
    """An unknown series is silence, not agreement (gotcha #53).

    The soccer ghost keeps its key, the tennis canonical keeps its, and the
    ticker names nothing either map knows. `None` never enters the witness set,
    and the row must stay refused rather than resolve on an empty witness.
    """
    conn = _connect()
    _plant_specimen(
        conn,
        ghost_sport=SPORT_SOCCER,
        canonical_sport=SPORT_TENNIS_ATP,
        market_ticker=UNMAPPED_TICKER,
    )
    assert _resolve(conn) is None


def test_an_unreadable_canonical_sport_refuses_against_both_witnesses_6262():
    """The canonical is the thing being agreed WITH, so it can never be absent.

    Two arms, and the SECOND is the one that needs saying. Before gap B
    `ghost_family != canonical_family` caught both. The witness-set form relies
    on `None` never entering the set — so an implementation that built the set
    without filtering would refuse arm 1 (the witnesses are real, `None` is not
    among them) and RESOLVE arm 2, where the unreadable canonical would find its
    own `None` sitting in the set and call that agreement.
    """
    # Arm 1: real witnesses, unreadable canonical.
    conn = _connect()
    _plant_specimen(conn)
    conn.execute("UPDATE events SET sport_id = NULL WHERE id = ?", (CANONICAL,))
    conn.commit()
    assert _resolve(conn) is None

    # Arm 2: nothing anywhere has a readable sport, and the ticker is unknown
    # too. Absence is not agreement.
    conn = _connect()
    _plant_specimen(conn, market_ticker=UNMAPPED_TICKER)
    conn.execute("UPDATE events SET sport_id = NULL")
    conn.commit()
    assert _resolve(conn) is None


def test_the_provenance_is_not_what_admits_the_re_witnessed_row_6262():
    """Gap A's surviving clause, re-asserted on gap B's shape.

    Every market-born provenance must reach the same answer, or the two ships
    have become entangled and a later edit to one will move the other.
    """
    for provenance in (
        KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        TICKER_DERIVED_COMMENCE_SOURCE,
    ):
        conn = _connect()
        _plant_nfl_ghost(
            conn, "KXNFLRACE-26SEP14DENKC-14", ghost_provenance=provenance
        )
        assert _resolve(conn) == CANONICAL, provenance


def test_the_us_open_specimen_is_untouched_by_the_second_witness_6262():
    """Q050's own specimen still folds, and folds on the arm it always did.

    `SPORT_TENNIS_US_OPEN` vs `tennis_atp` is the two-rows-one-sport pair
    `_sport_family` exists for. It resolved before gap B on the ghost row's key
    and must still resolve on it — the second witness agrees here too, so this
    is the case where the disjunction must not have changed anything.
    """
    conn = _connect()
    _plant_specimen(conn, canonical_sport=SPORT_TENNIS_US_OPEN)
    assert _resolve(conn) == CANONICAL
