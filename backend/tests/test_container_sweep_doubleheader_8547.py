"""#8547 — the container sweep stops folding a doubleheader's game 2 into game 1.

SHIP: Friday's Orioles @ Yankees game 2 shows as its own game, not as game 1.
(Pillar: MATCHING.)

The specimen, as production held it at 2026-09-25 18:27Z. Game 2's moneyline
markets (Polymarket event 1053347, venue kickoff 23:05Z) were attached to game
1's row, and game 2's row held only its own player props at that kickoff. The key
``('Baltimore Orioles vs. New York Yankees', 23:05Z)`` therefore named BOTH rows,
with game 1 as its only base-title holder; game 1 won the election and the sweep
tagged game 2 ``provenance:duplicate-of:15318575``. Two ESPN ids, two StatPal ids:
the authorities said two games and the sweep said one.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.polymarket_container_twins import (  # noqa: E402
    REFUSE_ANCHORED,
    REFUSE_DISTINCT_ANCHORS,
    REFUSE_MIXED_KICKOFF,
    ContainerMarket,
    ContainerRow,
    plan_container_tags,
)

GAME1 = 15318575
GAME2 = 15318665
G1_START = "2026-09-25T20:05:00+00:00"
G2_START = "2026-09-25T23:05:00+00:00"
BASE = "Baltimore Orioles vs. New York Yankees"


def _m(event_id: int, name: str, vgs: str) -> ContainerMarket:
    return ContainerMarket(event_id=event_id, name=name, venue_game_start=vgs)


#: The markets as production held them: game 1 carries its own 20:05Z event plus
#: game 2's three misattached 23:05Z rows; game 2 carries only its props.
SPECIMEN = [
    _m(GAME1, BASE, G1_START),
    _m(GAME1, f"{BASE}: O/U 6.5", G1_START),
    _m(GAME1, BASE, G2_START),
    _m(GAME1, f"Will there be a run scored in the first inning?: {BASE}", G2_START),
    _m(GAME2, f"{BASE} - Player Props", G2_START),
]


def _rows(*, g1_espn="401817088", g2_espn="401817073",
          g1_statpal="366746", g2_statpal="366768") -> dict[int, ContainerRow]:
    return {
        GAME1: ContainerRow(
            GAME1, espn_id=g1_espn, statpal_fixture_id=g1_statpal, status="live",
            venue_game_starts=frozenset({G1_START, G2_START}), identity_rank=(3,),
        ),
        GAME2: ContainerRow(
            GAME2, espn_id=g2_espn, statpal_fixture_id=g2_statpal, status="scheduled",
            venue_game_starts=frozenset({G2_START}), identity_rank=(2,),
        ),
    }


class TestTheDoubleheaderIsNotAFold:
    def test_the_production_specimen_tags_nothing(self):
        """The named test. Before the fix this planned GAME2 -> GAME1."""
        plan = plan_container_tags(SPECIMEN, _rows())
        assert plan.tags == []
        assert len(plan.refusals) == 1
        assert plan.refusals[0].startswith(REFUSE_DISTINCT_ANCHORS)

    def test_the_older_guards_do_not_catch_it(self):
        """Why a new clause was needed rather than a stricter old one: the
        canonical is anchored too, so REFUSE_ANCHORED is silent, and the second
        kickoff sits on the CANONICAL, so REFUSE_MIXED_KICKOFF is silent."""
        plan = plan_container_tags(SPECIMEN, _rows())
        assert not any(r.startswith(REFUSE_ANCHORED) for r in plan.refusals)
        assert not any(r.startswith(REFUSE_MIXED_KICKOFF) for r in plan.refusals)

    def test_statpal_alone_disagreeing_refuses(self):
        plan = plan_container_tags(SPECIMEN, _rows(g1_espn=None, g2_espn=None))
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_DISTINCT_ANCHORS)

    def test_espn_alone_disagreeing_refuses(self):
        plan = plan_container_tags(SPECIMEN, _rows(g1_statpal=None, g2_statpal=None))
        assert plan.tags == []
        assert plan.refusals[0].startswith(REFUSE_DISTINCT_ANCHORS)

    def test_an_int_and_a_string_of_the_same_id_agree(self):
        plan = plan_container_tags(
            SPECIMEN, _rows(g1_espn=401817088, g2_espn="401817088",
                            g1_statpal=None, g2_statpal=None))
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [(GAME2, GAME1)]


class TestTheControlsStillFold:
    """Only a DISAGREEMENT refuses. Without these the clause could read "refuse
    whenever both rows are anchored" and pass every test above."""

    def test_both_rows_naming_the_same_fixture_still_fold(self):
        plan = plan_container_tags(
            SPECIMEN, _rows(g2_espn="401817088", g2_statpal="366746"))
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [(GAME2, GAME1)]

    def test_one_provider_missing_on_one_row_is_not_evidence(self):
        plan = plan_container_tags(
            SPECIMEN, _rows(g2_espn=None, g2_statpal=None))
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [(GAME2, GAME1)]

    def test_blank_ids_are_not_a_disagreement(self):
        plan = plan_container_tags(
            SPECIMEN, _rows(g2_espn="  ", g2_statpal=""))
        assert [(t.duplicate_id, t.canonical_id) for t in plan.tags] == [(GAME2, GAME1)]
