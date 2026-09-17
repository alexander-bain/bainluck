"""#6799 — a fixture's winner market is served ONCE, not once per venue.

THE SPECIMEN. On 2026-09-17 at 20:50Z the Crystal Palace v Lech Poznań Europa League
page (`/events/15298552`) was LIVE at 3-0 and served this card under Other Markets:

    Crystal Palace FC                               >99%
    Crystal Palace                                   99%
    Lech Poznan                                       1%
    Tie                                               1%
    Draw (Crystal Palace FC vs. KKS Lech Poznań)      1%

Five rows for a three-way question, the home club named twice at two different
numbers, the draw named twice, the card summing past 200%. `other[]` carried two whole
match-winner markets — Kalshi `60481745` and Polymarket `60207781` — because step 9b's
cross-source dedup is gated `if len(player_props) > 1:` and has never run on
`other_markets`. The frontend groups both into one card and prints the union.

WHAT THIS FILE PINS, and like #5247's file it is mostly a table of rows that must
SURVIVE. The fold's whole risk is over-reach: every market on that page shares the
fixture's name, and three of them (`- Halftime Result`, `- Second Half Result`) carry
the very same three sides as full time. A rule that read the legs alone would fold
halftime into full time; a rule that read the name alone would delete the two O/U
rungs Polymarket packs inside `"Titans vs. Giants"`. Both tests are load-bearing and
both are given their counter-example below.

ROUTE-LEVEL ON PURPOSE. Every assertion about the defect itself goes through
`get_game_markets`, not through the predicates: a unit test builds its own rows and
would pass against a route that never calls the fold. The mutation results recorded in
the PR are what prove these are not vacuous.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _fold_duplicate_match_winner_markets,
    _game_markets_cache,
    _market_is_event_match_winner,
    _match_winner_side,
    get_game_markets,
)

EVENT_ID = 15298552
HOME = "Crystal Palace"
AWAY = "Lech Poznań"

#: The two markets that ARE the one question, verbatim from the production payload.
KALSHI_WINNER = 60481745
POLY_WINNER = 60207781

#: Every other market the live page served, verbatim. These are the rows the fold may
#: not touch — and `- Halftime Result` is the one that makes the name test necessary,
#: because its three legs map to the same three sides as full time.
KALSHI_WINNER_LEGS = [("Crystal Palace", 0.99), ("Tie", 0.01), ("Lech Poznan", 0.01)]
POLY_WINNER_LEGS = [
    ("Crystal Palace FC", 0.9995),
    ("Draw (Crystal Palace FC vs. KKS Lech Poznań)", 0.004),
    ("KKS Lech Poznań", 0.0005),
]
HALFTIME_LEGS = [
    ("Crystal Palace FC", 0.9995),
    ("KKS Lech Poznań", 0.0005),
    ("Draw", 0.0005),
]
SECOND_HALF_LEGS = [
    ("Draw", 0.65),
    ("Crystal Palace FC", 0.225),
    ("KKS Lech Poznań", 0.11),
]
FIRST_SCORER_LEGS = [
    ("Crystal Palace FC", 0.997),
    ("KKS Lech Poznań", 0.004),
    ("Neither", 0.004),
]
EXACT_SCORE_LEGS = [
    ("Crystal Palace FC 3 - 3 KKS Lech Poznań", 0.005),
    ("Crystal Palace FC 2 - 2 KKS Lech Poznań", 0.0035),
]
BTTS_LEGS = [("No", 0.95), ("Yes", 0.05)]

#: CERT-grade counter-example for the leg test, from event 14780547 (Titans at Giants).
#: Polymarket packs the game's TOTAL into the market named only for the fixture, so a
#: name-only rule deletes two real rungs.
MIXED_CONTAINER_LEGS = [("O/U 52.5", 0.52), ("Titans", 0.325), ("O/U 50.5", 0.12)]


# ---------------------------------------------------------------- fixtures --


def _make_result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event(*, home=HOME, away=AWAY):
    event = MagicMock()
    event.id = EVENT_ID
    event.home_team_name = home
    event.away_team_name = away
    event.status = "live"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "soccer_uefa_europa_league"
    event.commence_time = datetime(2026, 9, 17, 19, 0, tzinfo=timezone.utc)
    event.home_score = 3
    event.away_score = 0
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, source):
    market = MagicMock()
    market.id = id
    market.name = name
    # A Kalshi game ticker classifies as `moneyline` and a Polymarket condition id as
    # `other`; both land in the `other` bucket, which is the state the defect needs.
    market.external_id = (
        f"KXUELGAME-26SEP17-{id}" if source == "kalshi" else f"0x{id:064x}"
    )
    market.event_id = EVENT_ID
    market.category = "championship"
    market.status = "open"
    market.source = source
    market.sport_id = None
    market.llm_sport_category = "soccer"
    market.commence_time = datetime(2026, 9, 17, 19, 0, tzinfo=timezone.utc)
    market.market_type = "field"
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
    # Explicit `None` rather than a MagicMock: `is_empty_book_midpoint` reads these
    # three and an auto-attribute would be truthy, which is a different test.
    outcome.current_yes_bid = None
    outcome.current_yes_ask = None
    outcome.volume = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db_for(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            _make_result(rows=[]),      # #2693 folded_event_ids
            _make_result(rows=markets),
            _make_result(all_rows=[]),  # polymarket parent groups
            _make_result(rows=[]),      # unlinked fallback
            _make_result(rows=outcomes),
            _make_result(all_rows=[]),  # #4970 load_latest_observed_at
        ]
    )
    return db


#: (market id, source, name, legs) — the live page, reproduced.
THE_LIVE_PAGE = [
    (KALSHI_WINNER, "kalshi", "Crystal Palace vs Lech Poznan", KALSHI_WINNER_LEGS),
    (POLY_WINNER, "polymarket", "Crystal Palace FC vs. KKS Lech Poznań", POLY_WINNER_LEGS),
    (60207749, "polymarket", "Crystal Palace FC vs. KKS Lech Poznań - Halftime Result", HALFTIME_LEGS),
    (60207747, "polymarket", "Crystal Palace FC vs. KKS Lech Poznań - Second Half Result", SECOND_HALF_LEGS),
    (60207743, "polymarket", "Crystal Palace FC vs. KKS Lech Poznań - First Team to Score", FIRST_SCORER_LEGS),
    (60207738, "polymarket", "Crystal Palace FC vs. KKS Lech Poznań - Exact Score", EXACT_SCORE_LEGS),
    (60779720, "kalshi", "Crystal Palace vs Lech Poznan: BTTS", BTTS_LEGS),
]


def _build(spec):
    markets, outcomes = [], []
    next_id = 900_000
    for market_id, source, name, legs in spec:
        markets.append(_make_market(id=market_id, name=name, source=source))
        for leg_name, prob in legs:
            outcomes.append(
                _make_outcome(
                    id=next_id, market_id=market_id, name=leg_name, probability=prob
                )
            )
            next_id += 1
    return markets, outcomes


async def _payload(spec=None, *, home=HOME, away=AWAY):
    event = _make_event(home=home, away=away)
    markets, outcomes = _build(THE_LIVE_PAGE if spec is None else spec)
    return await get_game_markets(event.id, _db_for(event, markets, outcomes))


def _other_rows(payload):
    return payload.get("other") or []


def _rows_of(payload, market_id):
    return [r for r in _other_rows(payload) if r.get("_market_id") == market_id]


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# ------------------------------------------------------------- the specimen --


class TestTheLivePageStopsNamingTheHomeClubTwice:
    @pytest.mark.asyncio
    async def test_only_one_match_winner_market_reaches_the_reader(self):
        payload = await _payload()
        served = {KALSHI_WINNER, POLY_WINNER} & {
            r["_market_id"] for r in _other_rows(payload)
        }
        assert len(served) == 1, (
            "the fixture's winner question is still served once per venue: "
            f"{sorted(served)}"
        )

    @pytest.mark.asyncio
    async def test_the_home_club_is_named_once(self):
        """The headline. `Crystal Palace FC 99.95%` and `Crystal Palace 99%` were one
        card, 1,500px into a live page, and no reader could tell which was the price.
        """
        payload = await _payload()
        home_rows = [
            r
            for r in _other_rows(payload)
            if _match_winner_side(r.get("outcome_name"), HOME, AWAY) == "home"
            and _market_is_event_match_winner(
                _rows_of(payload, r["_market_id"]), HOME, AWAY
            )
        ]
        assert len(home_rows) == 1, [r["outcome_name"] for r in home_rows]

    @pytest.mark.asyncio
    async def test_the_draw_is_named_once(self):
        """"Tie" and "Draw (Crystal Palace FC vs. KKS Lech Poznań)" were both on it."""
        payload = await _payload()
        draws = [
            r
            for r in _other_rows(payload)
            if _match_winner_side(r.get("outcome_name"), HOME, AWAY) == "draw"
            and _market_is_event_match_winner(
                _rows_of(payload, r["_market_id"]), HOME, AWAY
            )
        ]
        assert len(draws) == 1, [r["outcome_name"] for r in draws]

    @pytest.mark.asyncio
    async def test_the_surviving_card_sums_to_one(self):
        """The five-row card summed past 200%. Three sides, once each, sum to ~1."""
        payload = await _payload()
        winner_rows = [
            r
            for r in _other_rows(payload)
            if _market_is_event_match_winner(
                _rows_of(payload, r["_market_id"]), HOME, AWAY
            )
        ]
        total = sum(r["probability"] for r in winner_rows if r.get("probability"))
        assert 0.97 <= total <= 1.03, (total, [r["outcome_name"] for r in winner_rows])

    @pytest.mark.asyncio
    async def test_every_surviving_price_is_one_a_venue_quoted(self):
        """The fold is a DROP, not an average: no number on the page is invented."""
        payload = await _payload()
        quoted = {p for _n, p in KALSHI_WINNER_LEGS} | {p for _n, p in POLY_WINNER_LEGS}
        for row in _other_rows(payload):
            if _market_is_event_match_winner(
                _rows_of(payload, row["_market_id"]), HOME, AWAY
            ):
                assert row["probability"] in quoted, row


# ------------------------------------------------- the rows that must survive --


class TestEveryOtherMarketOnThatPageSurvives:
    """The fold's only real risk. Each of these shares the fixture's name."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "market_id,label",
        [
            (60207749, "Halftime Result"),
            (60207747, "Second Half Result"),
            (60207743, "First Team to Score"),
            (60207738, "Exact Score"),
            (60779720, "BTTS"),
        ],
    )
    async def test_the_market_is_still_served(self, market_id, label):
        payload = await _payload()
        assert _rows_of(payload, market_id), f"{label} left the page"

    @pytest.mark.asyncio
    async def test_halftime_keeps_all_three_of_its_sides(self):
        """The counter-example for the NAME test.

        Halftime's legs are `Crystal Palace FC` / `KKS Lech Poznań` / `Draw` — the same
        three sides as full time, so the leg test passes on it. Only ``" - "`` in the
        name keeps it off the fold, and if that clause is dropped this market is
        silently merged into the full-time card and the reader loses the half.
        """
        payload = await _payload()
        rows = _rows_of(payload, 60207749)
        assert len(rows) == 3, [r["outcome_name"] for r in rows]

    @pytest.mark.asyncio
    async def test_the_page_loses_exactly_three_rows(self):
        """The whole cost of the fold, stated as a number."""
        before = await _payload()
        _game_markets_cache.clear()
        page_without_the_duplicate = [
            entry for entry in THE_LIVE_PAGE if entry[0] != POLY_WINNER
        ]
        after = await _payload(page_without_the_duplicate)
        assert len(_other_rows(before)) == len(_other_rows(after))


class TestAMixedContainerIsNeverFolded:
    """The counter-example for the LEG test, from event 14780547."""

    @pytest.mark.asyncio
    async def test_the_totals_packed_into_the_fixture_name_survive(self):
        payload = await _payload(
            [
                (61143928, "kalshi", "Tennessee vs New York Giants",
                 [("New York Giants", 0.705), ("Tennessee", 0.295)]),
                (59115833, "polymarket", "Titans vs. Giants", MIXED_CONTAINER_LEGS),
            ],
            home="New York Giants",
            away="Tennessee Titans",
        )
        served = {
            r["outcome_name"] for r in _other_rows(payload)
        } | {
            r["outcome_name"] for r in payload.get("totals") or []
        }
        assert "O/U 52.5" in served or any(
            (r.get("threshold") == 52.5) for r in payload.get("totals") or []
        ), "a real total rung was folded away with the container"

    def test_the_container_is_not_a_candidate(self):
        rows = [
            {"market_name": "Titans vs. Giants", "outcome_name": name}
            for name, _p in MIXED_CONTAINER_LEGS
        ]
        assert (
            _market_is_event_match_winner(rows, "New York Giants", "Tennessee Titans")
            is False
        )


class TestALoneWinnerMarketIsUntouched:
    @pytest.mark.asyncio
    async def test_one_venue_only_keeps_every_row(self):
        """1,086 of the 1,130 live/scheduled events measured are in this shape."""
        spec = [entry for entry in THE_LIVE_PAGE if entry[0] != POLY_WINNER]
        payload = await _payload(spec)
        assert len(_rows_of(payload, KALSHI_WINNER)) == 3


# ------------------------------------------------------ which market survives --


def _winner_rows(market_id, source, name, legs, stamp):
    return [
        {
            "market_name": name,
            "outcome_name": leg,
            "probability": prob,
            "source": source,
            "observed_at": stamp,
            "_market_id": market_id,
        }
        for leg, prob in legs
    ]


class TestWhichMarketSurvives:
    OLD = "2026-09-17T18:00:00+00:00"
    NEW = "2026-09-17T20:46:37+00:00"

    def _fold(self, *groups):
        rows = [row for group in groups for row in group]
        kept = _fold_duplicate_match_winner_markets(rows, HOME, AWAY)
        return {r["_market_id"] for r in kept}

    def test_more_sides_beats_fewer(self):
        """Never lose an outcome the reader could have seen: the two-leg market goes
        even though it is the fresher one."""
        three = _winner_rows(1, "polymarket", "Crystal Palace vs Lech Poznan",
                             KALSHI_WINNER_LEGS, self.OLD)
        two = _winner_rows(2, "kalshi", "Crystal Palace vs Lech Poznan",
                           [("Crystal Palace", 0.99), ("Lech Poznan", 0.01)], self.NEW)
        assert self._fold(three, two) == {1}

    def test_the_fresher_market_beats_the_staler_one(self):
        stale = _winner_rows(1, "kalshi", "Crystal Palace vs Lech Poznan",
                             KALSHI_WINNER_LEGS, self.OLD)
        fresh = _winner_rows(2, "polymarket", "Crystal Palace vs Lech Poznan",
                             KALSHI_WINNER_LEGS, self.NEW)
        assert self._fold(stale, fresh) == {2}, "a 2h-old price beat a 3-minute one"

    def test_an_unknown_age_never_wins(self):
        """`blended_observed_at` answers None for an absent stamp, and None is not
        evidence of freshness — the market whose age we KNOW survives.

        🔴 THE UNKNOWN AGE IS ON THE KALSHI MARKET, AND THAT IS THE WHOLE TEST.
        The first cut put it on the Polymarket one and the mutation battery found it:
        deleting the unknown-age clause outright left this GREEN, because the Kalshi
        tiebreak two keys below reached the same answer for an unrelated reason. A
        control that any of four keys can satisfy is a control for none of them. Here
        the two keys DISAGREE — freshness says the Polymarket market, Kalshi says the
        other — so only the rule under test can produce this result.
        """
        unknown = _winner_rows(1, "kalshi", "Crystal Palace vs Lech Poznan",
                               KALSHI_WINNER_LEGS, None)
        known = _winner_rows(2, "polymarket", "Crystal Palace vs Lech Poznan",
                             KALSHI_WINNER_LEGS, self.OLD)
        assert self._fold(unknown, known) == {2}

    def test_two_unknown_ages_fall_through_to_the_source(self):
        """The other arm of the same clause: when NEITHER age is known there is
        nothing to prefer on freshness, and the Kalshi key decides."""
        poly = _winner_rows(1, "polymarket", "Crystal Palace vs Lech Poznan",
                            KALSHI_WINNER_LEGS, None)
        kalshi = _winner_rows(2, "kalshi", "Crystal Palace vs Lech Poznan",
                              KALSHI_WINNER_LEGS, None)
        assert self._fold(poly, kalshi) == {2}

    def test_kalshi_breaks_a_tie(self):
        """Step 9b's existing preference, reused rather than restated."""
        poly = _winner_rows(1, "polymarket", "Crystal Palace vs Lech Poznan",
                            KALSHI_WINNER_LEGS, self.NEW)
        kalshi = _winner_rows(2, "kalshi", "Crystal Palace vs Lech Poznan",
                              KALSHI_WINNER_LEGS, self.NEW)
        assert self._fold(poly, kalshi) == {2}

    def test_a_row_with_no_market_id_is_passed_through(self):
        """It cannot be grouped, so it cannot be folded."""
        orphan = [{"market_name": "Crystal Palace vs Lech Poznan",
                   "outcome_name": "Crystal Palace", "probability": 0.99,
                   "source": "kalshi", "observed_at": self.NEW}]
        a = _winner_rows(1, "kalshi", "Crystal Palace vs Lech Poznan",
                         KALSHI_WINNER_LEGS, self.NEW)
        b = _winner_rows(2, "polymarket", "Crystal Palace vs Lech Poznan",
                         POLY_WINNER_LEGS, self.NEW)
        kept = _fold_duplicate_match_winner_markets(orphan + a + b, HOME, AWAY)
        assert orphan[0] in kept


# ------------------------------------------------------------- the side test --


class TestTheSideMapper:
    @pytest.mark.parametrize(
        "outcome,expected",
        [
            ("Crystal Palace FC", "home"),
            ("Crystal Palace", "home"),
            ("Lech Poznan", "away"),
            ("KKS Lech Poznań", "away"),
            ("Tie", "draw"),
            ("Draw", "draw"),
            ("Draw (Crystal Palace FC vs. KKS Lech Poznań)", "draw"),
            ("Neither", None),
            ("Yes", None),
            ("No", None),
            ("O/U 52.5", None),
        ],
    )
    def test_the_production_legs(self, outcome, expected):
        assert _match_winner_side(outcome, HOME, AWAY) == expected

    def test_a_diacritic_is_not_a_different_club(self):
        """`"besiktas" in "beşiktaş jk"` is False, which is why this goes through
        `names_match` and not through a substring of `_team_name_patterns`. Event
        15298550, live on the same night."""
        assert _match_winner_side("Beşiktaş JK", "Besiktas JK", "Marseille") == "home"
        assert (
            _match_winner_side("Olympique de Marseille", "Besiktas JK", "Marseille")
            == "away"
        )

    def test_a_truncated_club_still_answers(self):
        """Kalshi writes the Giants as `New York G` (event 14780547)."""
        assert (
            _match_winner_side("New York G", "New York Giants", "Tennessee Titans")
            == "home"
        )

    def test_a_leg_that_answers_to_both_clubs_answers_to_neither(self):
        """Fail closed: the market is kept, never mis-sided."""
        assert _match_winner_side("United", "Manchester United", "Leeds United") is None

    def test_a_club_whose_name_merely_contains_the_draw_word_is_not_the_draw(self):
        """The draw is read off the FIRST TOKEN, so a substring cannot fire it."""
        assert _match_winner_side("Drawbridge Town", "Drawbridge Town", AWAY) == "home"


class TestTheNameTest:
    def _rows(self, name, legs=None):
        return [
            {"market_name": name, "outcome_name": leg}
            for leg, _p in (legs or KALSHI_WINNER_LEGS)
        ]

    @pytest.mark.parametrize(
        "name",
        [
            "Crystal Palace FC vs. KKS Lech Poznań - Halftime Result",
            "Crystal Palace FC vs. KKS Lech Poznań - Second Half Result",
            "Crystal Palace vs Lech Poznan: BTTS",
        ],
    )
    def test_a_qualified_name_is_refused(self, name):
        assert _market_is_event_match_winner(self._rows(name), HOME, AWAY) is False

    @pytest.mark.parametrize(
        "name",
        ["Crystal Palace vs Lech Poznan", "Crystal Palace FC vs. KKS Lech Poznań"],
    )
    def test_the_bare_fixture_qualifies(self, name):
        assert _market_is_event_match_winner(self._rows(name), HOME, AWAY) is True

    def test_one_side_only_is_refused(self):
        """Every Exact Score leg answers `away` (the suffix match finds Lech Poznań and
        refuses Crystal Palace as a prefix), so the market covers one side and is not
        a winner market even before the name is read."""
        rows = [
            {"market_name": "Crystal Palace vs Lech Poznan", "outcome_name": name}
            for name, _p in EXACT_SCORE_LEGS
        ]
        assert _market_is_event_match_winner(rows, HOME, AWAY) is False

    def test_an_empty_market_is_refused(self):
        assert _market_is_event_match_winner([], HOME, AWAY) is False
