"""#6447 — the event page stops naming a club that does not exist.

Every fixture below is a REAL production row. Market names, tickers and outcome
names are as read from `futures_markets` / `futures_outcomes` on 2026-09-15, and
the club spellings are the ones ``events.home_team_name`` carries for the same
rows. Nothing here is invented, because the whole question is whether a real
truncation is completed and a real club name is left alone.

The load-bearing test is :func:`test_one_vocabulary_per_page`. A per-market
repair passes every other test in this file and still ships the defect #5181
named — a page printing "New York Jets" on one card and "New York J" on the
next. Only the pooled map makes that impossible, so only that test can fail if
the pooling is removed.
"""

from __future__ import annotations

import copy
import re

from app.utils.game_market_club_names import (
    build_page_repairs,
    matchup_sides,
    repair_club_names,
)
from app.utils.kalshi_display_names import apply_name_repairs

# ---------------------------------------------------------------------------
# Production specimens.
# ---------------------------------------------------------------------------

# `/events/14632820` — Los Angeles Rams 27-7 San Francisco 49ers, the page in the
# issue's screenshot. The truncation is in BOTH slots: the card title and a row.
RAMS_TICKER = "KXNFLFIRSTTD-26SEP10SFLAR"
RAMS_HOME = "Los Angeles Rams"
RAMS_AWAY = "San Francisco 49ers"

# `KXNFLSPREAD-26SEP14GBNYJ` resolves; `KXNFLTD-26SEP20GBNYJ` does not — measured,
# and the reason the map has to be pooled rather than built per market.
JETS_TICKER_RESOLVING = "KXNFLSPREAD-26SEP14GBNYJ"
JETS_TICKER_UNRESOLVING = "KXNFLTD-26SEP20GBNYJ"


def _row(market_id, market_name, outcome_name):
    return {
        "_market_id": market_id,
        "market_name": market_name,
        "outcome_name": outcome_name,
        "probability": 0.5,
    }


# ---------------------------------------------------------------------------
# The ship.
# ---------------------------------------------------------------------------


def test_the_card_and_the_row_both_stop_saying_los_angeles_r():
    rows = [
        _row(1, "San Francisco vs Los Angeles R: First Touchdown", "Los Angeles R"),
        _row(1, "San Francisco vs Los Angeles R: First Touchdown", "San Francisco"),
    ]
    changed = repair_club_names(
        (rows,), {1: RAMS_TICKER}, protected_names=(RAMS_HOME, RAMS_AWAY)
    )

    assert changed == 3  # two titles + one outcome label
    assert (
        rows[0]["market_name"] == "San Francisco vs Los Angeles Rams: First Touchdown"
    )
    assert rows[0]["outcome_name"] == "Los Angeles Rams"
    assert rows[1]["outcome_name"] == "San Francisco"  # never truncated, untouched


def test_a_title_only_truncation_is_reached():
    """`Over`/`Under` rows carry the club ONLY in the title.

    Reading outcome names alone — all the two admin callers ever had — finds
    nothing here, which is why :func:`matchup_sides` exists.
    """
    rows = [_row(7, "Green Bay vs New York J: 2nd Half Total", "Over")]
    repair_club_names((rows,), {7: JETS_TICKER_RESOLVING})

    assert rows[0]["market_name"] == "Green Bay vs New York Jets: 2nd Half Total"
    assert rows[0]["outcome_name"] == "Over"


def test_one_vocabulary_per_page():
    """#5181's criterion, and the only test the pooling is needed for.

    Two markets on ONE page. The spread ticker resolves `New York J`; the
    touchdown ticker does not. Per market, the page would print both spellings.
    """
    rows = [
        _row(10, "Green Bay vs New York J: 1st Half Spread", "New York J"),
        _row(11, "Green Bay vs New York J: Touchdowns", "New York J"),
    ]
    repair_club_names(
        (rows,),
        {10: JETS_TICKER_RESOLVING, 11: JETS_TICKER_UNRESOLVING},
        protected_names=("New York Jets", "Green Bay Packers"),
    )

    spellings = {row["market_name"] for row in rows} | {
        row["outcome_name"] for row in rows
    }
    assert not any(
        "New York J:" in s or s == "New York J" for s in spellings
    ), spellings
    assert rows[1]["market_name"] == "Green Bay vs New York Jets: Touchdowns"


# ---------------------------------------------------------------------------
# Controls. Each one is a way the repair could be wrong rather than absent.
# ---------------------------------------------------------------------------


def test_CONTROL_a_page_that_resolves_nothing_is_byte_identical():
    """J-League, cricket, Belgian youth soccer — 15 of 126 pages in the sample."""
    rows = [
        _row(1, "Mito H vs Frontale: First Half Winner", "Mito H"),
        _row(2, "Club NXT vs. Jeugd KAA Gent B: Jeugd KAA Gent B O/U 1.5", "Over"),
    ]
    before = copy.deepcopy(rows)

    assert repair_club_names((rows,), {1: "KXJLEAGUE1H-26SEP12MITKAW", 2: None}) == 0
    assert rows == before


def test_a_reserve_side_is_untouched_because_nothing_resolves_it():
    """`Real Sociedad B` is a real club — the reserve side — and matches the SHAPE.

    What protects it TODAY is that no ticker code resolves it, and this test says
    only that. The veto is what would protect it if one ever did, and that is the
    next test — these are two different guarantees and one test cannot carry both.
    """
    rows = [_row(1, "Real Sociedad B vs Osasuna B: Match Winner", "Real Sociedad B")]
    before = copy.deepcopy(rows)

    assert repair_club_names((rows,), {1: "KXLALIGA2GAME-26SEP14RSBOSB"}) == 0
    assert rows == before


def test_CONTROL_our_own_anchored_name_vetoes_a_repair_that_would_otherwise_fire():
    """The veto measured as a DIFFERENCE, because an absent repair proves nothing.

    Same rows, same resolving ticker, run twice. Without the event's names the
    repair fires; with them it does not. Deleting the veto makes the two runs
    identical and this test fails — which the vacuous version of it did not.
    """
    ticker = {1: RAMS_TICKER}
    unprotected = [_row(1, "San Francisco vs Los Angeles R: Spread", "Los Angeles R")]
    protected = copy.deepcopy(unprotected)

    assert repair_club_names((unprotected,), ticker) == 2
    assert unprotected[0]["outcome_name"] == "Los Angeles Rams"

    # An event whose own anchored row calls the club exactly what the venue sent:
    # then the venue's string is not a truncation and must not be "completed".
    changed = repair_club_names(
        (protected,), ticker, protected_names=("Los Angeles R", RAMS_AWAY)
    )
    assert changed == 0
    assert protected[0]["outcome_name"] == "Los Angeles R"


def test_CONTROL_a_city_only_side_is_not_a_truncation():
    """`Green Bay` is how Kalshi names the club and it reads correctly.

    The shape rule is a trailing 1-3 capital RUN, so a city-only side never
    enters the repair at all — and must not, or the page would start asserting a
    nickname the venue did not send.
    """
    assert matchup_sides("Green Bay vs Chicago: Touchdowns") == ["Green Bay", "Chicago"]

    rows = [_row(1, "Green Bay vs Chicago: Touchdowns", "Green Bay")]
    before = copy.deepcopy(rows)
    repair_club_names((rows,), {1: "KXNFLTD-26SEP14GBCHI"})
    assert rows == before


def test_two_markets_agreeing_is_the_real_case():
    """The pooled map over a page whose markets all resolve the same way."""
    rows = [
        _row(1, "Los Angeles D vs Colorado: Spread", "Los Angeles D"),
        _row(2, "Los Angeles D vs Colorado: Total", "Over"),
    ]
    repairs = build_page_repairs(
        rows,
        {1: "KXMLBGAME-26AUG182040LADCOL", 2: "KXMLBGAME-26AUG182040LADCOL"},
    )
    assert repairs == {"Los Angeles D": "Los Angeles Dodgers"}


def test_CONTROL_two_markets_that_disagree_drop_the_name(monkeypatch):
    """SYNTHETIC BY NECESSITY, AND SAYING SO.

    No real ticker pair reaches this branch, and I tried to build one:
    ``_code_matches`` binds the ticker's own codes to the shipped string before
    any nickname is read, so a code that does not belong to the shipped name
    abstains rather than proposing a rival (``laa`` against ``Los Angeles D``
    matches neither the squashed prefix nor the initials, and the ``D`` tail then
    resolves against no Angels/Rockies nickname either). The measurement agrees:
    zero conflicts across 158 repaired pages.

    The branch exists for the day the ticker map is widened, so it is patched
    into existence rather than faked with data that does not behave this way.
    Deleting the guard must fail this test and nothing else.
    """
    import app.utils.game_market_club_names as mod

    def _two_minds(ticker, names):
        return {
            "Los Angeles D": "Los Angeles Dodgers" if "LAD" in ticker else "LA Drift"
        }

    monkeypatch.setattr(mod, "repair_truncated_names", _two_minds)

    rows = [
        _row(1, "A vs Los Angeles D: X", "Los Angeles D"),
        _row(2, "A vs Los Angeles D: Y", "Los Angeles D"),
    ]
    agreeing = build_page_repairs(rows, {1: "…LADCOL", 2: "…LADMIA"})
    assert agreeing == {"Los Angeles D": "Los Angeles Dodgers"}

    contradicting = build_page_repairs(rows, {1: "…LADCOL", 2: "…XXXMIA"})
    assert "Los Angeles D" not in contradicting

    rows_after = copy.deepcopy(rows)
    repair_club_names((rows_after,), {1: "…LADCOL", 2: "…XXXMIA"})
    assert rows_after == rows  # neither spelling served


def test_CONTROL_a_row_with_no_market_id_or_no_ticker_is_untouched():
    rows = [
        {"market_name": "San Francisco vs Los Angeles R: Spread", "outcome_name": "X"},
        _row(999, "San Francisco vs Los Angeles R: Total", "Over"),
    ]
    before = copy.deepcopy(rows)

    assert repair_club_names((rows,), {}) == 0
    assert rows == before


def test_CONTROL_applying_the_repair_twice_changes_nothing_the_second_time():
    """A truncated name is a prefix of its own replacement.

    Without the right boundary, `Los Angeles R` -> `Los Angeles Rams` applied to
    an already-repaired string gives `Los Angeles Ramsams`, and a cached payload
    rebuilt through the same pass would print it.
    """
    rows = [_row(1, "San Francisco vs Los Angeles R: Spread", "Los Angeles R")]

    repair_club_names((rows,), {1: RAMS_TICKER})
    once = copy.deepcopy(rows)
    repair_club_names((rows,), {1: RAMS_TICKER})

    assert rows == once
    assert "Ramsams" not in rows[0]["market_name"]


def test_CONTROL_a_title_already_holding_the_full_name_is_not_corrupted():
    """The two forms in ONE string — the case the admin callers never saw."""
    repairs = {"Los Angeles R": "Los Angeles Rams"}
    text = "1st Los Angeles Rams Touchdown vs Los Angeles R"

    assert (
        apply_name_repairs(text, repairs)
        == "1st Los Angeles Rams Touchdown vs Los Angeles Rams"
    )


def test_CONTROL_the_repair_does_not_change_the_payload_shape():
    """Rows are mutated in place; no key is added, removed or renamed.

    `_market_id` and the price fields are what every downstream reader — the
    props script, both native clients, the grading columns — key on.
    """
    rows = [_row(1, "San Francisco vs Los Angeles R: Spread", "Los Angeles R")]
    keys_before = set(rows[0])

    repair_club_names((rows,), {1: RAMS_TICKER})

    assert set(rows[0]) == keys_before
    assert rows[0]["_market_id"] == 1
    assert rows[0]["probability"] == 0.5


def test_CONTROL_empty_and_absent_buckets_are_safe():
    assert repair_club_names((), {}) == 0
    assert repair_club_names((None, [], None), {1: RAMS_TICKER}) == 0


# ---------------------------------------------------------------------------
# End to end, through the route — the call site is the half a unit test cannot
# prove. The rig is `test_game_markets.py`'s, whose `db.execute` side-effect list
# is a POSITIONAL contract with the query sequence.
# ---------------------------------------------------------------------------


def _mock_result(scalar=None, rows=None, all_rows=None):
    from unittest.mock import MagicMock

    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _walk_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_strings(item)
    elif isinstance(node, str):
        yield node


async def test_END_TO_END_the_served_payload_never_says_los_angeles_r():
    import datetime as dt
    from unittest.mock import AsyncMock, MagicMock

    from app.routes.events import _game_markets_cache, get_game_markets

    _game_markets_cache.clear()

    kickoff = dt.datetime(2026, 9, 10, 0, 0, tzinfo=dt.timezone.utc)

    event = MagicMock()
    event.id = 14632820
    event.home_team_name = RAMS_HOME
    event.away_team_name = RAMS_AWAY
    event.status = "completed"
    event.sport_id = 1
    event.sport = MagicMock()
    event.sport.key = "americanfootball_nfl"
    event.commence_time = kickoff
    event.home_score = 27
    event.away_score = 7
    event.period = None
    event.game_clock = None

    market = MagicMock()
    market.id = 101
    market.name = "San Francisco vs Los Angeles R: 1st Half Total"
    market.external_id = RAMS_TICKER
    market.event_id = event.id
    market.category = "game_prop"
    market.status = "resolved"
    market.source = "kalshi"
    market.sport_id = 1
    market.llm_sport_category = "football"
    market.commence_time = kickoff
    market.group_id = None
    market.group_type = None

    outcome = MagicMock()
    outcome.id = 201
    outcome.market_id = 101
    outcome.name = "Los Angeles R"
    outcome.current_probability = 0.61
    outcome.opening_probability = 0.55

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _mock_result(scalar=event),
            _mock_result(rows=[]),  # folded_event_ids — positional contract
            _mock_result(rows=[market]),
            _mock_result(all_rows=[]),
            _mock_result(rows=[]),
            _mock_result(rows=[outcome]),
            _mock_result(all_rows=[]),
        ]
    )

    response = await get_game_markets(event.id, db)
    _game_markets_cache.clear()

    served = list(_walk_strings(response))
    assert any("Los Angeles Rams" in s for s in served), served
    # The truncation survives nowhere — not in a card title, not in a row label,
    # and not inside a `props_script` key, which is composed from both.
    assert not any(re.search(r"Los Angeles R(?![A-Za-z])", s) for s in served), served
