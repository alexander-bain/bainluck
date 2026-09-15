"""#6262 gap A — two provenance values that were never added to Q050's set.

THE READER'S COMPLAINT, measured on production 2026-09-15 01:5xZ at 390px:
`bainluck.com/search?q=Badosa` served the SAME fixture twice, back to back, both
"No price yet" —

    15312798  Justina Mikulskyte v Paula Badosa   scheduled  2026-09-15 13:00Z
    15312797  Justina Mikulskyte v Paula Badosa   scheduled  2026-09-15 20:30Z
              both commence_time_source = polymarket_venue

...and `15312798`'s markets sit on `15312797`. No name key and no time key can
fold that pair: the names are byte-identical so a name fold sees one row twice,
and the times are 7.5 hours apart so a time key sees two fixtures. The Q050
verdict does not care — it asks the database, by id, which row a market
already decided it belongs to.

WHY IT WAS NOT ALREADY DRAINED, AND WHY THAT IS NOT A REGRESSION OF #6257
-------------------------------------------------------------------------
`MARKET_BORN_COMMENCE_SOURCES` held `{kalshi, polymarket, kalshi_ticker}`.
`polymarket_venue` and `kalshi_occurrence` were added to the vocabulary AFTER
q076 wrote that set (#6073 and #3488/#3544 respectively) and were simply never
added to it. Nothing in the constant was wrong. **No test that reads the code
can see a missing entry** — which is why this was found by running the real
population through the gate and reading the provenance values that came back,
not by review.

Both new values are the same provider writing the same row, naming WHICH of its
two time fields answered. A row does not stop being market-born because its
market told us a better hour. Worse, the omission was self-defeating:
`recover_kalshi_occurrence_starts` REWRITES `commence_time_source` to
`kalshi_occurrence`, so improving a ghost's hour used to remove it from the
drain class — `test_refining_a_ghosts_hour_does_not_un_drain_it_6262` pins that.

WHAT THIS SHIP DOES NOT CLAIM
-----------------------------
Event `15305046` — the `OTHER BASKETBALL · Today 8:15 PM · Denver / Kansas City`
card that sat directly under the live Chiefs–Broncos game on a search for
"Kansas City" — is `kalshi_occurrence` and DOES enter the band here, but the
sport-family refusal still declines it (`basketball` vs `football`). Closing it
means relaxing that guard for catch-all `*_other` keys, which is #6262 gap B: a
separate change, because completing a set and relaxing a guard are not the same
risk. `test_the_nfl_ghost_is_admitted_to_the_band_and_still_refused_6262` pins
exactly that, so nobody reads this ship as having closed it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.anchor_channel import (
    MARKET_BORN_COMMENCE_SOURCES,
    is_drain_candidate_row,
)
from app.services.event_registry import _SOURCE_PRIORITY
from app.utils.event_completion import (
    KALSHI_OCCURRENCE_COMMENCE_SOURCE,
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    TICKER_DERIVED_COMMENCE_SOURCE,
)

from tests.test_market_born_duplicate_reads_as_canonical_q050 import (
    CANONICAL,
    GHOST,
    SPORT_SOCCER,
    SPORT_TENNIS_ATP,
    _connect,
    _plant_specimen,
    _resolve,
)

#: The two entries #6262 adds, each with the production row that named it.
_ADDED = [
    pytest.param(
        POLYMARKET_VENUE_COMMENCE_SOURCE,
        "15312798, Mikulskyte v Badosa 13:00Z, twin of 15312797 at 20:30Z",
        id="polymarket_venue",
    ),
    pytest.param(
        KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        "15305046, 'Denver v Kansas City' basketball_other, twin of NFL 14638896",
        id="kalshi_occurrence",
    ),
]


@pytest.mark.parametrize("provenance,specimen", _ADDED)
def test_the_missing_provenances_are_in_the_set_6262(provenance, specimen):
    """Membership, stated once, with the row that pays for it.

    The seven-refusal battery in `test_market_born_duplicate_reads_as_canonical
    _q050.py` already parametrizes over `MARKET_BORN_COMMENCE_SOURCES`, so these
    two inherit every refusal test for free. This one exists so a removal names
    the reader who loses.
    """
    assert provenance in MARKET_BORN_COMMENCE_SOURCES, specimen


@pytest.mark.parametrize("provenance,specimen", _ADDED)
def test_the_cheap_gate_agrees_with_the_verdict_on_the_new_sources_6262(
    provenance, specimen
):
    """The optimisation must not hide a row the SQL would drain.

    `is_drain_candidate_row` short-circuits before the verdict query runs, so a
    set the gate reads and the verdict does not would silently re-open the bug
    for exactly the two values this ship adds.
    """
    assert is_drain_candidate_row(
        commence_time_source=provenance,
        home_score=None,
        away_score=None,
        completed_at=None,
    ), specimen


def test_a_refined_ghost_still_resolves_to_its_canonical_6262():
    """End to end through the REAL statement, on the new provenance."""
    conn = _connect()
    _plant_specimen(
        conn, ghost_provenance=POLYMARKET_VENUE_COMMENCE_SOURCE
    )
    assert _resolve(conn) == CANONICAL


def test_refining_a_ghosts_hour_does_not_un_drain_it_6262():
    """🔴 THE PERVERSE SHAPE THE MISSING ENTRIES HAD.

    `recover_kalshi_occurrence_starts` rewrites a `kalshi_ticker` row's
    provenance to `kalshi_occurrence` when the venue publishes a real hour. So
    before this change, giving a ghost a BETTER start time took it out of the
    drain class and left it rendering. Improving the data made the bug worse,
    which is the kind of coupling a membership test cannot notice and a
    behavioural one can.
    """
    conn = _connect()
    _plant_specimen(conn, ghost_provenance=TICKER_DERIVED_COMMENCE_SOURCE)
    assert _resolve(conn) == CANONICAL, "precondition: the ticker row drains"

    # ...the occurrence recovery lands and rewrites only the provenance.
    conn.execute(
        "UPDATE events SET commence_time_source = ? WHERE id = ?",
        (KALSHI_OCCURRENCE_COMMENCE_SOURCE, GHOST),
    )
    conn.commit()
    assert _resolve(conn) == CANONICAL, (
        "refining the hour un-drained the row — the ghost renders again "
        "because its start got BETTER"
    )


def test_the_nfl_ghost_is_admitted_to_the_band_and_still_refused_6262():
    """The scope limit, asserted rather than promised.

    `15305046` is `basketball_other`; its canonical `14638896` is
    `americanfootball_nfl`. Gap A puts it in the band — the provenance no longer
    refuses it — and refusal 6 still declines it. If a later change makes this
    resolve, that change is gap B and it must come with gap B's measurement.
    """
    conn = _connect()
    _plant_specimen(
        conn,
        ghost_provenance=KALSHI_OCCURRENCE_COMMENCE_SOURCE,
        ghost_sport=SPORT_SOCCER,           # soccer_epl ghost...
        canonical_sport=SPORT_TENNIS_ATP,   # ...tennis canonical
    )
    assert _resolve(conn) is None

    # ...and the provenance is NOT why: same rows, same sports, one member
    # provenance swapped for another, still refused.
    conn.execute(
        "UPDATE events SET commence_time_source = ? WHERE id = ?",
        (TICKER_DERIVED_COMMENCE_SOURCE, GHOST),
    )
    conn.commit()
    assert _resolve(conn) is None, (
        "the cross-sport refusal must be doing this, not the provenance"
    )


# ═══ The invariant that makes the set safe, pinned in BOTH directions ═══════


def test_every_market_born_source_ranks_below_every_schedule_source_6262():
    """`MARKET_BORN_COMMENCE_SOURCES`'s safety clause, mechanized.

    The constant's docstring rests on one fact: a row cannot be DOWNGRADED into
    this set, because `commence_time_write_authorized` only writes on
    `incoming > current` and every member ranks 0. If a member ever ranked above
    a schedule source, an `espn`/`statpal`/`odds_api` fixture could acquire a
    market-born provenance and become drainable — a real game suppressed, the
    one direction Q050 calls unrecoverable.

    `.get(..., 0)` is the default the production call uses, so unlisted members
    (`kalshi_ticker`, `kalshi_occurrence`) are checked exactly as production
    reads them, not excused for being absent.
    """
    schedule_floor = min(
        rank for src, rank in _SOURCE_PRIORITY.items() if rank > 0
    )
    for source in sorted(MARKET_BORN_COMMENCE_SOURCES, key=str):
        assert _SOURCE_PRIORITY.get(source, 0) < schedule_floor, (
            f"{source!r} outranks a schedule source, so a real fixture can be "
            "downgraded into the drain class"
        )


def test_every_rank_zero_source_is_market_born_6262():
    """The reverse count, which is the direction that failed here.

    A guard asserting only "every member ranks 0" passes on the bug this ship
    fixes: `polymarket_venue` ranked 0 for a day and was not a member. Rank 0 in
    `_SOURCE_PRIORITY` means "cannot outrank any schedule source" — a market
    venue's word — so a rank-0 entry that is NOT here is an entry someone forgot.
    """
    rank_zero = {src for src, rank in _SOURCE_PRIORITY.items() if rank == 0}
    assert rank_zero, "the priority table has no rank-0 tier — re-derive this"
    missing = rank_zero - MARKET_BORN_COMMENCE_SOURCES
    assert not missing, (
        f"{sorted(missing)} rank below every schedule source but are not in "
        "MARKET_BORN_COMMENCE_SOURCES — either they are market-born and belong "
        "here, or their rank is wrong. #6262 is this bug."
    )


_COMMENCE_SOURCE_CONST = re.compile(
    r"^([A-Z][A-Z0-9_]*_COMMENCE_SOURCE) = \"([^\"]+)\"", re.MULTILINE
)


def test_no_fourth_commence_source_constant_decides_this_by_omission_6262():
    """The scan is here to FAIL on a new constant, never to adopt one.

    `event_completion` declares one constant per market-provider time field, and
    all three are market-born. A fourth is not automatically a member — MMA and
    boxing pads, for instance, are named in `kalshi_occurrence`'s docstring as
    explicitly NOT inheritable — so this asserts the vocabulary is the size it
    was reasoned about. A new entry reddens here and a person decides, which is
    the only mechanism that would have caught #6262 at the time.
    """
    text = (
        Path(__file__).resolve().parents[1]
        / "app" / "utils" / "event_completion.py"
    ).read_text()
    found = dict(
        (name, value) for name, value in _COMMENCE_SOURCE_CONST.findall(text)
    )
    assert len(found) == 3, (
        f"event_completion declares {sorted(found)} — the scan expected the "
        "three market-provider time fields. A new *_COMMENCE_SOURCE constant "
        "must be ruled into or out of MARKET_BORN_COMMENCE_SOURCES by hand."
    )
    assert set(found.values()) <= MARKET_BORN_COMMENCE_SOURCES, (
        f"{sorted(set(found.values()) - MARKET_BORN_COMMENCE_SOURCES)} is a "
        "declared market-provider time field that Q050 does not read as "
        "market-born"
    )
