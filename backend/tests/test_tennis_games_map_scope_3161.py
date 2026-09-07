"""#3161 — the games map projects the MATCH, not the number in "Set 4".

THE DEFECT, MEASURED. `GET /api/events/15304847/game-markets` on production,
2026-09-05 (Tommy Paul v Carlos Alcaraz, pre-game), served four `game_total`
rungs:

    Paul vs. Alcaraz: Set 1 Games O/U 9.5   -> threshold 1.0    over 0.530
    Paul vs. Alcaraz: Set 4 Games O/U 9.5   -> threshold 4.0    over 0.495
    Paul vs. Alcaraz: Match O/U 36.5        -> threshold 36.5   over 0.485
    Paul vs. Alcaraz: Match O/U 40.5        -> threshold 40.5   over 0.395

Two of them are the SET number: `_extract_threshold` took the first number in
the market name and Polymarket puts the set in front of the line.
`MarketMapSection.tsx` takes the rung closest to 50% as the card's headline, so
the reader was told `Projected 4` on a rail that runs past 40.

TWO THINGS ARE WRONG THERE AND ONLY ONE OF THEM IS THE PARSE. Reading 9.5 off
the O/U token puts the right number on the rung, but a per-SET games line is
still not a rung on a MATCH games rail — P(this match goes past 9.5 games) is
~1, not the 53% that market quotes for its own set. Same for a sets-COUNT line
("Total Sets O/U 3.5"), which is not measured in games at all. So the map keeps
match-scope rungs only.

FAIL-OPEN IS THE OTHER HALF OF THE RULE, and it is not decoration. On the
finished page (`/api/events/15301243/game-markets`, Wu v Alcaraz, measured the
same morning) the ENTIRE totals list is one set line and one sets line. An
unconditional drop empties `totals`, `MarketMapSection` returns null on an
empty list, and the card that live/073 taught to say `FINAL 26` disappears from
a settled page. `TestTheMapIsNeverEmptiedToCleanIt` is that arm.

RED-FIRST. On the parent commit every assertion in
`TestTheLineIsTheNumberBesideTheOU` and `TestTheMatchMapIsDrawnFromMatchMarkets`
fails: `_extract_threshold("Paul vs. Alcaraz: Set 1 Games O/U 9.5")` returned
1.0 there, and the pre-game map served four rungs instead of two.

THE CONTROL ARM MATTERS AS MUCH AS THE FIX. Every other provider shape must
parse exactly as it did — Kalshi's outcome path ("Over 224.5") carries no O/U
token, and a genuine game total that does ("Reds vs. Cardinals: O/U 10.5")
already had its line first. `TestEveryOtherNameParsesAsItDid` is that control,
and `test_non_tennis_totals_are_untouched` is the sport-scope one: nothing
outside tennis loses a rung to this rule.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _extract_threshold,
    _is_match_scope_tennis_total,
    _match_scope_tennis_totals,
    _game_markets_cache,
    get_game_markets,
)

# ---------------------------------------------------------------- fixtures --


def _make_result(scalar=None, rows=None, all_rows=None):
    rows = rows or []
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_tennis_event(
    *, id=15304847, status="scheduled", home_score=None, away_score=None
):
    event = MagicMock()
    event.id = id
    event.home_team_name = "Tommy Paul"
    event.away_team_name = "Carlos Alcaraz"
    event.status = status
    event.sport_id = 356611
    event.sport = MagicMock()
    event.sport.key = "tennis_atp_us_open"
    event.commence_time = datetime(2026, 9, 3, 5, 5, tzinfo=timezone.utc)
    event.home_score = home_score
    event.away_score = away_score
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, event_id, status="open"):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"0x{id:064x}"
    market.event_id = event_id
    market.category = "game_prop"
    market.status = status
    market.source = "polymarket"
    market.sport_id = 356611
    market.llm_sport_category = "tennis"
    market.commence_time = datetime(2026, 9, 3, 5, 5, tzinfo=timezone.utc)
    market.group_id = None
    market.group_type = None
    return market


def _make_outcome(*, id, market_id, name, probability):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = probability
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db_for(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            # #2693 — `folded_event_ids`: the canonical's suppressed twins, so
            # the surviving card carries the prices the ghost was holding. The
            # list is a POSITIONAL contract with the query sequence.
            _make_result(rows=[]),
            _make_result(rows=markets),
            _make_result(all_rows=[]),  # polymarket parent groups
            _make_result(rows=[]),  # unlinked fallback
            _make_result(rows=outcomes),
        ]
    )
    return db


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# ------------------------------------------------------------------ parse --


class TestTheLineIsTheNumberBesideTheOU:
    """Every name here is copied from production, 2026-09-05."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Paul vs. Alcaraz: Set 1 Games O/U 9.5", 9.5),
            ("Paul vs. Alcaraz: Set 4 Games O/U 9.5", 9.5),
            ("Wu vs. Alcaraz: Set 1 Games O/U 10.5", 10.5),
            ("Wu vs. Alcaraz: Set 1 Games O/U 8.5", 8.5),
            ("Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 3.5", 3.5),
            ("US Open ATP: Yibing Wu vs Carlos Alcaraz Total Sets: O/U 4.5", 4.5),
            ("US Open ATP: Yibing Wu vs Carlos Alcaraz Set 1 O/U 10.5", 10.5),
        ],
    )
    def test_the_set_number_is_not_the_line(self, name, expected):
        assert (
            _extract_threshold(name) == expected
        ), f"{name!r} parsed to the wrong number — this is the 'Projected 4' rung"

    def test_three_set_one_markets_stop_collapsing_into_one_rung(self):
        """The parse bug did not only mislabel rungs, it deleted them.

        All three Set-1 markets parsed to 1.0 and the threshold dedup in
        `_build_game_markets` keys on exactly that number, so two of the three
        lines Polymarket quotes never reached the page.
        """
        lines = [
            "Wu vs. Alcaraz: Set 1 Games O/U 8.5",
            "Wu vs. Alcaraz: Set 1 Games O/U 9.5",
            "Wu vs. Alcaraz: Set 1 Games O/U 10.5",
        ]
        assert len({_extract_threshold(n) for n in lines}) == 3


class TestEveryOtherNameParsesAsItDid:
    """The control arm: no other provider shape moves."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            # Kalshi puts the line in the OUTCOME and there is no O/U token there.
            ("Over 224.5", 224.5),
            ("Under 218.5", 218.5),
            ("Over 220", 220.0),
            ("Over 8.5 goals", 8.5),
            # Polymarket totals whose line was already first.
            ("Reds vs. Cardinals: O/U 10.5", 10.5),
            ("Juan Soto: Home Runs O/U 1.5", 1.5),
            # Threshold-style outcomes.
            ("Joel Embiid: 1+", 1.0),
            ("2+", 2.0),
            # A spread is not a total, and its number must not move either.
            ("Set Handicap: Alcaraz (-2.5) vs Wu (+2.5)", 2.5),
        ],
    )
    def test_unchanged(self, name, expected):
        assert _extract_threshold(name) == expected

    def test_a_name_with_no_number_still_refuses(self):
        assert _extract_threshold("No threshold") is None

    def test_an_ou_token_with_no_number_falls_back(self):
        """ "O/U" with nothing after it must not swallow the name's own number."""
        assert _extract_threshold("Over 47.5 — O/U") == 47.5


# ------------------------------------------------------------------ scope --


class TestWhatCountsAsAMatchTotal:
    @pytest.mark.parametrize(
        "name",
        [
            "Paul vs. Alcaraz: Set 1 Games O/U 9.5",
            "Paul vs. Alcaraz: Set 4 Games O/U 9.5",
            "Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 3.5",
            "US Open ATP: Yibing Wu vs Carlos Alcaraz Total Sets: O/U 4.5",
        ],
    )
    def test_set_scope_and_sets_unit_are_not_match_totals(self, name):
        assert _is_match_scope_tennis_total(name) is False

    @pytest.mark.parametrize(
        "name",
        [
            "Paul vs. Alcaraz: Match O/U 36.5",
            "Paul vs. Alcaraz: Match O/U 40.5",
            "Reds vs. Cardinals: O/U 10.5",
            "Thunder at Lakers: Total Points",
            None,
            "",
        ],
    )
    def test_anything_that_does_not_name_a_set_is_match_scope(self, name):
        assert _is_match_scope_tennis_total(name) is True

    def test_non_tennis_totals_are_untouched(self):
        rows = [
            {"threshold": 220.5, "market_name": "Thunder at Lakers: Total Points"},
            {"threshold": 5.5, "market_name": "Oilers at Kings: Set 1 Goals O/U 5.5"},
        ]
        assert _match_scope_tennis_totals(rows, "basketball") == rows
        assert _match_scope_tennis_totals(rows, None) == rows


# ------------------------------------------------------------------ route --

PREGAME_MARKETS = [
    ("Paul vs. Alcaraz: Set 1 Games O/U 9.5", "Over", 0.53),
    ("Paul vs. Alcaraz: Set 4 Games O/U 9.5", "Under", 0.505),
    ("Paul vs. Alcaraz: Match O/U 36.5", "Under", 0.515),
    ("Paul vs. Alcaraz: Match O/U 40.5", "Under", 0.605),
]


class TestTheMatchMapIsDrawnFromMatchMarkets:
    @pytest.mark.asyncio
    async def test_the_pregame_map_keeps_only_the_match_totals(self):
        event = _make_tennis_event()
        markets, outcomes = [], []
        for i, (name, outcome_name, prob) in enumerate(PREGAME_MARKETS, start=1):
            markets.append(_make_market(id=100 + i, name=name, event_id=event.id))
            outcomes.append(
                _make_outcome(
                    id=200 + i, market_id=100 + i, name=outcome_name, probability=prob
                )
            )

        response = await get_game_markets(event.id, _db_for(event, markets, outcomes))

        thresholds = sorted(t["threshold"] for t in response["totals"])
        assert thresholds == [
            36.5,
            40.5,
        ], "the set-scope rungs are still on the match games rail"

    @pytest.mark.asyncio
    async def test_the_headline_rung_is_a_match_line(self):
        """The card's headline is the rung closest to 50% — Alex's `Projected 4`.

        Asserted here on the payload rather than the component, because this is
        where the number the component picks is decided.
        """
        event = _make_tennis_event()
        markets, outcomes = [], []
        for i, (name, outcome_name, prob) in enumerate(PREGAME_MARKETS, start=1):
            markets.append(_make_market(id=300 + i, name=name, event_id=event.id))
            outcomes.append(
                _make_outcome(
                    id=400 + i, market_id=300 + i, name=outcome_name, probability=prob
                )
            )

        response = await get_game_markets(event.id, _db_for(event, markets, outcomes))

        closest = min(
            response["totals"], key=lambda t: abs(t["over_probability"] - 0.5)
        )
        assert closest["threshold"] == 36.5
        assert "Match" in closest["market_name"]


class TestTheMapIsNeverEmptiedToCleanIt:
    @pytest.mark.asyncio
    async def test_a_page_whose_only_totals_are_set_scope_keeps_them(self):
        """The finished Wu v Alcaraz page, as production served it.

        Its whole totals list is one set line and one sets line. Dropping both
        would take the map — and live/073's `FINAL 26` marker on it — off a
        settled page, which is a worse card than the one this fix is cleaning.
        """
        event = _make_tennis_event(
            id=15301243, status="completed", home_score=0, away_score=3
        )
        markets = [
            _make_market(
                id=501,
                name="Wu vs. Alcaraz: Set 1 Games O/U 10.5",
                event_id=event.id,
                status="resolved",
            ),
            _make_market(
                id=502,
                name="Yibing Wu vs. Carlos Alcaraz: Total Sets O/U 3.5",
                event_id=event.id,
            ),
        ]
        outcomes = [
            _make_outcome(id=601, market_id=501, name="Under", probability=0.9995),
            _make_outcome(id=602, market_id=502, name="Under", probability=0.9995),
        ]

        response = await get_game_markets(event.id, _db_for(event, markets, outcomes))

        thresholds = sorted(t["threshold"] for t in response["totals"])
        assert thresholds == [
            3.5,
            10.5,
        ], "the settled tennis map lost its rungs — and with them the card"
