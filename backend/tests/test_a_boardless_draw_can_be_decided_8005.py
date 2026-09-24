"""#8005 — the Doubles pill apologised for a missing live match ten days after
all three finals.

Production 2026-09-23 11:03Z, `/tournaments/us-open` → Doubles at 390px (lane1b/399):

    We can't show today's schedule … so a match that is on right now would be
    missing. We're checking.

above 147 finished doubles results including three graded finals. Men's on the
same page correctly said "This draw is done" (#5924).

#5924 made the empty state read `board.decided` first, and a board's decided
state comes from `DrawProgress.champion`, which needs the REGISTER to know the
players. The register carries no doubles player and the payload carries no
doubles board, so the Doubles pill was permanently boardless and fell through
to the tournament-wide `order_of_play_listed` (625) — the exact mismatch #5924
names. The scoreboard already graded the three finals; this is the per-draw
fact, stamped on the slate beside the count it qualifies.
"""

from __future__ import annotations

import pytest

from app.routes import tournaments as route
from app.routes.tournaments import _withheld_slate
from app.utils.tournament_progress import decided_draws

# The fixture drives the real `_build_sections` first-screen path; reused from
# the #5917 file so the two guards read one register and one scoreboard shape.
from tests.test_tournament_board_decided_5917 import _first_screen, routed  # noqa: F401


def _final(completion="final", winner="pairwinner", espn_round="Final"):
    return {
        "espn_round": espn_round,
        "completion": completion,
        "winner_normalized": winner,
        "players": ["A / B", "C / D"],
        "entity_keys": ["espn:pair:1-2", "espn:pair:3-4"],
    }


def _sf():
    return {**_final(), "espn_round": "Semifinal"}


# Production's shape on 2026-09-23: all three doubles finals graded, no board.
PRODUCTION = {
    "scoreboard": "live",
    "draws": {
        "mens-doubles": {"sf1": _sf(), "f": _final()},
        "womens-doubles": {"f": _final()},
        "mixed-doubles": {"f": _final(completion="walkover")},
        "womens-singles": {"sf": _sf()},
    },
}


class TestDecidedDraws:
    def test_the_three_production_doubles_finals_are_decided(self):
        assert decided_draws(PRODUCTION) == [
            "mens-doubles",
            "mixed-doubles",
            "womens-doubles",
        ]

    def test_a_semifinal_does_not_decide_a_draw(self):
        """The control arm: `womens-singles` above holds a decided SF only."""
        assert "womens-singles" not in decided_draws(PRODUCTION)

    @pytest.mark.parametrize("completion", ["", "in_progress", "scheduled", None])
    def test_a_final_still_being_played_is_not_decided(self, completion):
        draws = {"draws": {"mens-doubles": {"f": _final(completion=completion)}}}
        assert decided_draws(draws) == []

    def test_a_final_with_no_named_winner_is_not_decided(self):
        draws = {"draws": {"mens-doubles": {"f": _final(winner=None)}}}
        assert decided_draws(draws) == []

    @pytest.mark.parametrize("espn_round", ["Final", "final", " FINAL ", "F"])
    def test_espn_display_name_and_register_key_both_read_as_the_final(self, espn_round):
        draws = {"draws": {"mens-doubles": {"f": _final(espn_round=espn_round)}}}
        assert decided_draws(draws) == ["mens-doubles"]

    @pytest.mark.parametrize("espn_round", ["Round 7", "Semifinal", "Quarterfinal", ""])
    def test_no_other_round_reads_as_the_final(self, espn_round):
        """`Round 7` IS the final of a 128 draw, but only a draw size can say so
        and this reader deliberately has none — it under-claims."""
        draws = {"draws": {"mens-doubles": {"f": _final(espn_round=espn_round)}}}
        assert decided_draws(draws) == []

    @pytest.mark.parametrize("empty", [None, {}, {"draws": {}}, {"draws": None}])
    def test_no_scoreboard_decides_nothing(self, empty):
        """The #5728 degraded read returns `draws: {}` — no claim on a read we
        did not make."""
        assert decided_draws(empty) == []


class TestTheRouteStampsIt:
    async def test_a_first_only_request_carries_decided_draws(self, routed):  # noqa: F811
        """Through the real `_build_sections`, first screen only — the
        fragment the empty state renders from (`results` is not in it)."""
        first = await _first_screen()
        assert "results" not in first
        assert first["slate"]["decided_draws"] == ["womens-singles"]

    async def test_a_degraded_read_claims_no_draw_decided(self, routed, monkeypatch):  # noqa: F811
        async def _degraded(slug):  # noqa: ANN001
            return {"draws": {}, "stats": {}, "errors": [], "scoreboard": route.SCOREBOARD_DEGRADED}

        monkeypatch.setattr(route, "_espn_results", _degraded)
        first = await _first_screen()
        assert first["slate"]["withheld_reason"] == "scoreboard_read_failed"
        assert first["slate"]["decided_draws"] == []

    def test_withholding_does_not_erase_a_decided_draw_list(self):
        """`_withheld_slate` zeroes ints only. A decided final is a permanent
        fact, and the route stamps the list after withholding anyway."""
        slate = {"matches": [1], "count": 1, "scoreboard": "degraded", "decided_draws": ["x"]}
        assert _withheld_slate(slate)["decided_draws"] == ["x"]
