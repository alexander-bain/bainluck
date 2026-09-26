"""A cup card never leads with one team and no opponent (#8769).

Seen on production `/golf` at 390px, 2026-09-26 02:05Z, during the Presidents Cup:

    47.0% USA — Leader  −17.5 pts today
    Matsuyama 21.5% · Kim 14.0% · Kim 11.0% · Clark 5.5%

USA was BEHIND on both venues: Kalshi International 49.5 / USA 42.5 / Tie 8.5,
Polymarket International 53 / USA 47. International was not on the card at all.

Three steps, all read off `/api/golf` and `routes/golf.py`:

1. Polymarket 62229386 "Presidents Cup 2026 Winner" names its sides `USA` and
   `International` — one word each, so `_is_h2h_matchup` (two-word names) does
   not take it and it is aggregated as a winner FIELD. There,
   `_PROP_OUTCOME_RE`'s single-word-region arm (written for "nationality of
   winner" props) drops `International`. `USA` survives, alone.
2. Kalshi's "Overall Points Leader" field fills in behind it — the card had 14
   entries, `USA 0.47` first.
3. `_promote_team_matchup_to_card` (#7985) only filled a card with NO golfers,
   so it skipped. The right pair — Kalshi 16757297 Team International 0.495 v
   Team USA 0.425 — sat in `h2h_matchups` and never reached the hero, and the
   card, with 14 entries rather than 2, never entered its cup renderer.

Every market row below is a replay of those production rows.
"""

import pytest

from app.routes.golf import _promote_team_matchup_to_card, _strip_lone_team_side
from tests.test_golf_team_match_play_has_no_individual_markets_7985 import (
    _DB,
    _Market,
    _Outcome,
    _card,
    _cup_card,
)
from app.routes import golf as golf_route
from app.routes.golf import get_golf


def _polymarket_cup_winner():
    """Polymarket 62229386 — the two-team market whose `International` is dropped."""
    return _Market(
        62229386, "polymarket", "pm-presidents-cup-2026-winner",
        "Presidents Cup 2026 Winner",
        [_Outcome("USA", 0.47), _Outcome("International", 0.53)],
        mutually_exclusive=True,
    )


def _kalshi_cup_winner():
    """Kalshi 16757297 KXPRESCUP-26 as captured 2026-09-26 01:51:29Z (#8718)."""
    return _Market(
        16757297, "kalshi", "KXPRESCUP-26", "Presidents Cup Winner",
        [
            _Outcome("Team International", 0.495),
            _Outcome("Team USA", 0.425),
            _Outcome("Tie", 0.085),
        ],
        mutually_exclusive=True,
    )


def _kalshi_points_leader():
    """Kalshi 62399270 — the individual field that filled in under `USA`."""
    return _Market(
        62399270, "kalshi", "KXPRESCUPPTS-26", "Presidents Cup: Overall Points Leader",
        [
            _Outcome("Hideki Matsuyama", 0.215),
            _Outcome("Si Woo Kim", 0.14),
            _Outcome("Tom Kim", 0.11),
            _Outcome("Wyndham Clark", 0.055),
        ],
        mutually_exclusive=True,
    )


@pytest.fixture
def serve(monkeypatch):
    """Drive the real `/api/golf` builder over a chosen set of the replayed rows."""
    async def _no_schedule():
        return []

    async def _no_snapshots(_db, _ids, _now):
        return {}

    monkeypatch.setattr(golf_route, "_get_golf_schedule", _no_schedule)
    monkeypatch.setattr(golf_route, "_fetch_24h_snapshots", _no_snapshots)

    async def _run(markets):
        return await get_golf(db=_DB(markets))

    return _run


def _production_rows():
    return [_polymarket_cup_winner(), _kalshi_points_leader(), _kalshi_cup_winner()]


class TestTheLiveCardLeadsWithBothTeams:
    async def test_the_specimen_reproduces_before_the_promotion(self, serve, monkeypatch):
        """The vacuity guard: without the promotion, the replay IS the filing.

        If this ever stops reading "USA first, International absent", the rows
        below no longer reproduce the defect and every other assertion here
        passes for a reason that has nothing to do with the fix.
        """
        monkeypatch.setattr(golf_route, "_promote_team_matchup_to_card", lambda _t: 0)
        card = _card(await serve(_production_rows()), "Presidents Cup")

        names = [g["name"] for g in card["golfers"]]
        assert names[0] == "USA"
        assert "International" not in names
        assert "Hideki Matsuyama" in names

    async def test_the_hero_is_the_team_market_with_the_larger_side_first(self, serve):
        """What the reader should see: International ahead, as both venues say."""
        card = _card(await serve(_production_rows()), "Presidents Cup")

        assert [g["name"] for g in card["golfers"]] == ["Team International", "Team USA"]
        assert card["golfers"][0]["probability"] == pytest.approx(0.495)
        assert card["golfers"][1]["probability"] == pytest.approx(0.425)
        assert [g["rank"] for g in card["golfers"]] == [1, 2]

    async def test_no_individual_player_is_left_under_the_team_hero(self, serve):
        """Matsuyama, named: the string the reader saw second on the card."""
        card = _card(await serve(_production_rows()), "Presidents Cup")
        names = {g["name"] for g in card["golfers"]} | {g["name"] for g in card["_all_golfers"]}

        assert "Hideki Matsuyama" not in names
        assert "USA" not in names

    async def test_the_card_meets_the_cup_renderer_gate(self, serve):
        """`golfers.length === 2` is how TournamentCard.tsx enters `CupCard`."""
        card = _card(await serve(_production_rows()), "Presidents Cup")

        assert len(card["golfers"]) == 2


class TestAPolymarketTwoTeamWinnerNeverMakesAOneSidedHero:
    """The guard the issue names, with no Kalshi pair to fall back on."""

    async def test_a_lone_usa_does_not_lead_the_card(self, serve):
        card = _card(
            await serve([_polymarket_cup_winner(), _kalshi_points_leader()]),
            "Presidents Cup",
        )

        names = [g["name"] for g in card["golfers"]]
        assert "USA" not in names
        assert "International" not in names
        # Players are untouched by this rule — what leads a cup with no team
        # market is #7985's question. Asserted so the strip cannot pass by
        # emptying the card.
        assert names[0] == "Hideki Matsuyama"
        assert [g["rank"] for g in card["golfers"]] == list(range(1, len(names) + 1))

    async def test_the_polymarket_market_alone_leaves_no_one_sided_card(self, serve):
        """Only the two-team market: USA survives aggregation and must not lead."""
        body = await serve([_polymarket_cup_winner()])
        card = _card(body, "Presidents Cup")

        # With nothing else to show, the emptied card is dropped by
        # `_drop_contentless_team_cards` — absent, never "USA" on its own.
        assert card is None


class TestTheStripIsScoped:
    def test_the_ryder_cups_lone_usa_is_stripped_too(self):
        """`Europe` is in the same regex arm, so the Ryder Cup breaks the same way."""
        card = _cup_card([], key="ryder_cup", golfers=[
            {"name": "USA", "probability": 0.55, "rank": 1},
            {"name": "Rory McIlroy", "probability": 0.1, "rank": 2},
        ])
        card["_all_golfers"] = list(card["golfers"])

        assert _promote_team_matchup_to_card([card]) == 0
        assert [g["name"] for g in card["golfers"]] == ["Rory McIlroy"]
        assert card["golfers"][0]["rank"] == 1
        assert [g["name"] for g in card["_all_golfers"]] == ["Rory McIlroy"]

    def test_a_clean_pair_already_on_the_card_is_left_alone(self):
        card = _cup_card([], golfers=[
            {"name": "Team World", "probability": 0.53, "rank": 1},
            {"name": "Team USA", "probability": 0.47, "rank": 2},
        ])

        _strip_lone_team_side(card)

        assert [g["name"] for g in card["golfers"]] == ["Team World", "Team USA"]

    def test_one_side_twice_is_not_a_pair(self):
        """`USA` and `Team USA` fold to one side — still one team, no opponent."""
        card = _cup_card([], golfers=[
            {"name": "USA", "probability": 0.47, "rank": 1},
            {"name": "Team USA", "probability": 0.425, "rank": 2},
        ])

        _strip_lone_team_side(card)

        assert card["golfers"] == []

    def test_a_stroke_play_card_is_never_touched(self):
        """A player whose outcome happens to read `USA` elsewhere is not a cup's."""
        card = _cup_card([], key="fedex_open_de_france", golfers=[
            {"name": "USA", "probability": 0.2, "rank": 1},
        ])

        assert _promote_team_matchup_to_card([card]) == 0
        assert [g["name"] for g in card["golfers"]] == ["USA"]
