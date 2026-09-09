"""#4174 / CERT-2360 — the served grid settles a player whose opponent we cannot name.

THE REPAIR THIS FILE EXISTS FOR, in one sentence: `build_results` drops a match
unless BOTH names resolve to registered players (147 of 467 scored competitions
on 2026-09-09), so a progress pass built on its output left Michael Zheng —
this issue's own headline case — at a stale 52% to reach a final he was knocked
out of in the second round, because the match he lost was dropped on account of
his OPPONENT's name.

The unit tests next door prove `build_progress` resolves sides independently.
This one proves the ROUTE hands it the input that lets it: the raw scoreboard,
before the join, and not `rest["results"]`. It is a wiring test, and wiring is
exactly what the first presentation got wrong — the logic was already sound.

It also holds the other half of the repair: **a half-resolved match must not
reach the results list.** Publishing a score needs two names; knowing one named
player lost needs one. Those stay two different strictnesses.
"""

import pytest

from app.routes import tournaments
from app.services.espn_tennis import normalize_name
from app.utils.tournament_register import TournamentRegister, load_register

SLUG = "us-open"
URL = f"/api/tournaments/{SLUG}"
DRAW = "mens-singles"

#: A name no register will ever resolve. The point of the fixture.
GHOST = "Unresolvable Qualifier"


@pytest.fixture(autouse=True)
def _no_shared_cache(monkeypatch):
    async def _miss(slug, group=tournaments.SECTION_FIRST):
        return None

    async def _noop(slug, payload, group=tournaments.SECTION_FIRST):
        return None

    monkeypatch.setattr(tournaments, "_cache_get", _miss)
    monkeypatch.setattr(tournaments, "_cache_set", _noop)


def _a_registered_player() -> dict:
    """A real player out of the committed register, with reach cells.

    Read from the file rather than named here: a hard-coded name is a fixture
    that rots the next time the register is regenerated, and this test would
    then pass by settling nobody.
    """
    register = load_register(SLUG, "2026")
    assert register is not None, (
        "the committed 2026 register did not load — this guard cannot check "
        "what the build loads if it cannot read what the build reads"
    )
    reg = TournamentRegister(register)
    with_reaches = {
        str(r.get("entity_key"))
        for r in reg.reaches
        if r.get("draw") == DRAW and r.get("round") in ("SF", "F")
    }
    candidates = [
        player
        for player in reg.players
        if player.get("draw") == DRAW and str(player.get("entity_key")) in with_reaches
    ]
    assert candidates, (
        f"no {DRAW} player in the committed register carries an SF/F reach cell — "
        "this fixture would settle nobody and pass anyway"
    )
    return candidates[0]


def _scoreboard(display_name: str) -> dict:
    """`parse_results`' shape: this player beaten in round two by a ghost."""
    return {
        "scoreboard": "live",
        "order_of_play": {},
        "order_of_play_complete": True,
        "draws": {
            DRAW: {
                "pair-1": {
                    "players": [display_name, GHOST],
                    "espn_round": "Round 2",
                    "winner_name": GHOST,
                    "winner_normalized": normalize_name(GHOST),
                    "completion": "final",
                    "score": "6-4, 6-4",
                    "espn_competition_id": "999001",
                    "completed_at": "2026-09-01T18:00Z",
                },
            }
        },
    }


@pytest.fixture
def half_resolved(monkeypatch):
    player = _a_registered_player()

    async def _results(slug, **_kwargs):
        return _scoreboard(str(player.get("display_name")))

    monkeypatch.setattr(tournaments, "_espn_results", _results)
    return player


class TestTheRouteReadsTheScoreboardAndNotTheJoinedList:
    async def test_the_known_player_is_settled_out_across_the_whole_row(
        self, client, half_resolved
    ):
        body = (await client.get(f"{URL}?sections=rest")).json()
        grid = body["grids"][DRAW]
        [row] = [
            r for r in grid["rows"]
            if r["entity_key"] == str(half_resolved.get("entity_key"))
        ]
        for key, cell in row["cells"].items():
            assert cell["state"] == "settled", (key, cell["state"])
            assert cell["probability"] is None, (key, cell["probability"])
            assert cell["note"] == "out", (key, cell["note"])
            assert cell["settled_round"] == "R64", (key, cell["settled_round"])

    async def test_the_half_resolved_match_never_reaches_the_results_list(
        self, client, half_resolved
    ):
        """Publishing a score still needs both names. That strictness is right."""
        body = (await client.get(f"{URL}?sections=rest")).json()
        keys = {
            p["entity_key"]
            for match in body["results"]["matches"]
            for p in match["players"]
        }
        assert str(half_resolved.get("entity_key")) not in keys
        assert body["results"]["unregistered_pairs"] >= 1
        # And the grid knows it settled from a match the list does not hold.
        assert body["grids"][DRAW]["decided_matches"] == 1

    async def test_a_cold_scoreboard_settles_nothing(self, client, monkeypatch):
        """The degradation path, as a differential over ONE variable.

        Same route, same register, same database — only the scoreboard changes.
        The player the fixture above settles must come back unsettled here, or
        the settling is coming from somewhere other than the results and this
        ship is asserting something it has not measured.
        """
        player = _a_registered_player()
        entity_key = str(player.get("entity_key"))

        async def _empty(slug, **_kwargs):
            return {"draws": {}, "order_of_play": {}, "scoreboard": "unavailable"}

        monkeypatch.setattr(tournaments, "_espn_results", _empty)
        grid = (await client.get(f"{URL}?sections=rest")).json()["grids"][DRAW]
        assert grid["decided_matches"] == 0
        assert grid["settled_cells"] == 0
        [row] = [r for r in grid["rows"] if r["entity_key"] == entity_key]
        assert not any(cell["note"] == "out" for cell in row["cells"].values())
        # And every column reports itself open again, so the sum check has not
        # quietly kept a denominator from a build that had results.
        assert all(
            check["expected"] == check["slots"] for check in grid["column_sums"]
        ), grid["column_sums"]
