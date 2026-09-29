"""#9608 — two players' Polymarket Yes/No props are two rows, not one averaged row.

Production, `GET /api/events/15316808/game-markets` (Northern Ireland 0–0 Hungary,
final), 2026-09-29: "Pierce Charles: 1+ saves" (settled Yes at 1.00) and "Balázs
Tóth: 1+ saves" (open, 0.905) were served as ONE row, "Balázs Tóth: 1+ saves" at
0.9525 with `source_count: 2` and `all_sources: ["polymarket"]`. Same fold for
András Schafer into Shea Charles on "1+ goals + assists".

Cause: step 9b's dedup key comes from `_prop_player_and_stat`, which knew the
Kalshi shape ("Soto: 2+") and the Polymarket O/U shape (#3594) but not the
Polymarket Yes/No shape, so it fell back to the outcome — and every player's
outcome is "Yes" or "No".
"""

import pytest

from app.routes.events import _prop_player_and_stat, get_game_markets
from tests.test_a_runs_map_is_not_four_players_props_3594 import (  # noqa: F401
    _db_for,
    _make_event,
    _make_market,
    _make_outcome,
    clear_game_markets_cache,
)


class TestWhoAYesNoPropIsAbout:
    def test_the_subject_names_the_player(self):
        assert _prop_player_and_stat("Pierce Charles: 1+ saves", "Yes") == (
            "pierce charles",
            "1+ saves",
        )
        assert _prop_player_and_stat("Pierce Charles: 1+ saves", "No") == (
            "pierce charles",
            "1+ saves",
        )

    def test_two_players_one_stat_are_two_identities(self):
        """The whole defect, in one assertion."""
        charles = _prop_player_and_stat("Pierce Charles: 1+ saves", "Yes")
        toth = _prop_player_and_stat("Balázs Tóth: 1+ saves", "Yes")
        assert charles != toth

    def test_a_matchup_subject_keeps_the_old_key(self):
        """A game's own Yes/No question is not a person's; nothing about it moves."""
        assert _prop_player_and_stat(
            "Northern Ireland vs. Hungary: Both teams to score", "Yes"
        ) == ("yes", "both teams to score")


def _soccer_event():
    event = _make_event(id=15316808)
    event.home_team_name = "Northern Ireland"
    event.away_team_name = "Hungary"
    event.sport.key = "soccer_uefa_nations_league"
    return event


def _yes_no_payload(markets_spec):
    """`[(market_id, market_name, yes_prob), ...]` → the endpoint response."""
    event = _soccer_event()
    markets, outcomes = [], []
    for market_id, name, yes_prob in markets_spec:
        markets.append(_make_market(id=market_id, name=name, event_id=event.id))
        outcomes.append(
            _make_outcome(id=market_id * 10, market_id=market_id, name="Yes", probability=yes_prob)
        )
        outcomes.append(
            _make_outcome(
                id=market_id * 10 + 1,
                market_id=market_id,
                name="No",
                probability=round(1 - yes_prob, 4),
            )
        )
    return get_game_markets(event.id, _db_for(event, markets, outcomes))


class TestEachPlayerKeepsHisOwnYesNoRow:
    @pytest.mark.asyncio
    async def test_two_keepers_on_one_saves_line_are_two_rows(self):
        response = await _yes_no_payload(
            [
                (63098839, "Pierce Charles: 1+ saves", 0.85),
                (63118989, "Balázs Tóth: 1+ saves", 0.905),
            ]
        )
        yes_rows = {
            p["market_name"]: p for p in response["player_props"] if p["outcome_name"] == "Yes"
        }
        assert set(yes_rows) == {"Pierce Charles: 1+ saves", "Balázs Tóth: 1+ saves"}, (
            f"one player was averaged into the other: {sorted(yes_rows)}"
        )
        # Two questions, two prices — not both at the 0.8775 average.
        assert yes_rows["Pierce Charles: 1+ saves"]["over_probability"] == 0.85
        assert yes_rows["Balázs Tóth: 1+ saves"]["over_probability"] == 0.905
        assert all(p.get("source_count") in (None, 1) for p in response["player_props"]), (
            "two players on one venue were counted as two venues"
        )

    @pytest.mark.asyncio
    async def test_the_goals_plus_assists_pair_too(self):
        response = await _yes_no_payload(
            [
                (63068072, "Shea Charles: 1+ goals + assists", 0.11),
                (63068073, "András Schafer: 1+ goals + assists", 0.11),
            ]
        )
        served = {p["market_name"] for p in response["player_props"]}
        assert served == {
            "Shea Charles: 1+ goals + assists",
            "András Schafer: 1+ goals + assists",
        }
