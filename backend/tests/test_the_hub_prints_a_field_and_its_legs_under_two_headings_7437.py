"""#7437 — one question under TWO headings: /hub/tennis PROPS was 64 rows of 64 legs.

The cross-section half of #7400, split off it deliberately. `/hub/tennis` drew
the ranked field

    MORE MARKETS  Nitto ATP Finals: Player to Qualify — 37 outcomes

and then PROPS restated 33 of its rows one at a time ("Will <player> Qualify for
the Nitto ATP Finals 2026?"), and did it again with ATP 2026 End of Year
Rankings: Player to Make Top 10 (31 outcomes, 31 legs). Those two families were
the ENTIRE props section.

MEASURED ON PRODUCTION 2026-09-20, `GET /api/hub/{slug}`, replaying this fix over
the served payload with #7400's rule as the baseline so only THIS ship's effect
is counted:

    hub        served   #7400 only   +#7437     this ship's marginal effect
    tennis        194          194      130     more_markets 12→10, props 64→2
    mma            59           37       37     none (#7400's 22, already its own)
    esports       136          136      136     none
    boxing          9            9        9     none
    golf            6            6        6     none

No heading is emptied on any of the five. `/hub/esports` carried two such
families when #7437 was filed and carries none today — the issue's table is four
families, the live population is two, and the fixtures below are the two that
survived the re-measure.

🔴 **THE FIX MOVES A CARD; IT NEVER DROPS ONE.** The collapse is still
`drop_legs_of_a_rendered_field`'s and is still scoped to one list. Widening THAT
to run page-wide is the option this issue exists to refuse: on tennis it removes
64 of 64 rows and the PROPS heading with them. Carrying the two fields DOWN to
the heading their own rows are under leaves PROPS holding two ranked fields.

THE WAYS THIS GOES WRONG, each with an arm here:

1. Moving a field out of a section it is ALONE in trades the destination's
   heading for the source's — the same loss, relocated (`test_a_field_alone_
   under_its_heading_is_left_where_it_is`).
2. Moving a field whose legs are spread over several sections: there is no one
   right destination, and picking one leaves the others duplicating it anyway
   (`test_legs_in_two_other_sections_are_ambiguous_and_nothing_moves`).
3. Moving the card and not its `section` field, so the row claims one heading
   while being drawn under another (`test_the_moved_field_carries_its_new_
   section`).
4. Running after the collapse instead of before it, which makes the whole ship
   inert (`test_the_move_runs_BEFORE_the_collapse`).
"""

import pytest

from app.routes import hub as hub_module
from app.utils.grouped_field_legs import (
    drop_legs_of_a_rendered_field,
    move_parents_to_their_legs_section,
)

HUB_CONFIGS = hub_module.HUB_CONFIGS

#: Nitto ATP Finals: Player to Qualify — 37 outcomes in MORE MARKETS, 33 legs in
#: PROPS. Production ids, 2026-09-20.
QUALIFY = "polymarket:766238"
#: ATP 2026 End of Year Rankings: Player to Make Top 10 — 31 outcomes, 31 legs.
TOP_10 = "polymarket:768652"
#: A Kalshi ranking field with no legs anywhere: it shares MORE MARKETS with the
#: two above and has every right to stay there.
ATP_RANK = "kalshi:KXATP1RANK-26DEC31"


def _card(market_id, name, *, outcomes=2, group_id=None, section="props", tier=1):
    """One section card in the shape `/api/leagues/{key}` really serves.

    `top_outcomes` carries a priced outcome because `build_hub` drops every card
    `is_unpriced_card` recognises (UX-P181) — a fixture with no number is one the
    page legitimately refuses to draw, and a test written on those would pass
    against an empty section.
    """
    return {
        "id": market_id,
        "name": name,
        "market_tier": tier,
        "section": section,
        "source": "polymarket",
        "group_id": group_id,
        "outcome_count": outcomes,
        "top_outcomes": [{"name": "Yes", "probability": 0.49}],
    }


def _tennis_sections():
    """`/hub/tennis` as production served it, trimmed to 3 legs per family.

    MORE MARKETS holds both fields plus one unrelated ranking market; PROPS holds
    nothing but their legs, which is what made emptying it the live risk.
    """
    return {
        "more_markets": [
            _card(766238, "Nitto ATP Finals: Player to Qualify", outcomes=37, group_id=QUALIFY, section="more_markets"),
            _card(768652, "ATP 2026 End of Year Rankings: Player to Make Top 10", outcomes=31, group_id=TOP_10, section="more_markets"),
            _card(990001, "ATP #1 Ranked Men's Singles Player on Dec 31, 2026?", outcomes=12, group_id=ATP_RANK, section="more_markets"),
        ],
        "props": [
            _card(766301, "Will Arthur Fils Qualify for the Nitto ATP Finals 2026?", group_id=QUALIFY),
            _card(766302, "Will Jakub Mensik Qualify for the Nitto ATP Finals 2026?", group_id=QUALIFY),
            _card(768701, "Will Jannik Sinner Make the Top 10 in the 2026 ATP EOY Rankings?", group_id=TOP_10),
            _card(766303, "Will Alex de Minaur Qualify for the Nitto ATP Finals 2026?", group_id=QUALIFY),
        ],
    }


def _fixed(sections):
    """The two rules in the order `build_hub` runs them."""
    return drop_legs_of_a_rendered_field(move_parents_to_their_legs_section(sections))


class TestTheShip:
    """§1 — the reader stops meeting one question under two headings."""

    def test_the_section_it_replaced_printed_the_field_AND_its_rows(self):
        """RED, executed: the fixture IS the defect, so the ship is falsifiable.

        #7400's rule alone leaves the page exactly as production drew it — that
        is the baseline the measured table above is taken against.
        """
        before = drop_legs_of_a_rendered_field(_tennis_sections())
        assert [c["id"] for c in before["more_markets"]] == [766238, 768652, 990001]
        assert len(before["props"]) == 4

    def test_props_holds_the_two_fields_and_none_of_their_legs(self):
        after = _fixed(_tennis_sections())
        assert [c["name"] for c in after["props"]] == [
            "Nitto ATP Finals: Player to Qualify",
            "ATP 2026 End of Year Rankings: Player to Make Top 10",
        ]

    def test_more_markets_keeps_the_market_that_was_never_part_of_this(self):
        after = _fixed(_tennis_sections())
        assert [c["id"] for c in after["more_markets"]] == [990001]

    def test_the_props_heading_survives(self):
        """The whole reason this was split off #7400: the cheap widening empties
        this section, 64 rows of 64."""
        after = _fixed(_tennis_sections())
        assert after["props"], "PROPS must not be left with nothing under it"

    def test_the_moved_field_carries_its_new_section(self):
        """Trap 3. Each card publishes the section it belongs to and `build_hub`
        already restamps it when it moves a combat-sport prop out of `matches`."""
        after = _fixed(_tennis_sections())
        assert [c["section"] for c in after["props"]] == ["props", "props"]

    def test_the_field_lands_where_its_own_rows_were(self):
        """The reader meets the field at the point the list was about to restate
        it — not appended after every unrelated prop."""
        sections = _tennis_sections()
        sections["props"].insert(0, _card(999, "Will the final go to five sets?", group_id=None))
        after = _fixed(sections)
        assert [c["id"] for c in after["props"]] == [999, 766238, 768652]

    def test_the_smallest_real_field_three_outcomes_is_still_a_field(self):
        """The `>= 3` boundary, and it is live: `polymarket:768653` (ATP 2026 End
        of Year Rankings: Player to be Number 1) is a 3-outcome field on tennis
        today, and production carries 3-outcome rows on esports and mma too.
        Read as `> 3` the smallest fields keep printing twice.
        """
        sections = {
            "more_markets": [
                _card(768653, "ATP 2026 EOY Rankings: Player to be Number 1", outcomes=3, group_id="polymarket:768653", section="more_markets"),
                _card(990001, "ATP #1 Ranked Player?", outcomes=12, group_id=ATP_RANK, section="more_markets"),
            ],
            "props": [_card(768661, "Will Carlos Alcaraz finish 2026 at number 1?", group_id="polymarket:768653")],
        }
        after = _fixed(sections)
        assert [c["id"] for c in after["more_markets"]] == [990001]
        assert [c["id"] for c in after["props"]] == [768653]

    def test_a_one_outcome_row_is_not_a_leg(self):
        """Also live: tennis serves 10 one-outcome rows, esports 6, mma 3. A leg
        is EXACTLY the two sides of one row of a field; a one-sided market is a
        different thing and cannot license moving a field onto it.
        """
        sections = {
            "more_markets": [
                _card(766238, "Nitto ATP Finals: Player to Qualify", outcomes=37, group_id=QUALIFY, section="more_markets"),
                _card(990001, "ATP #1 Ranked Player?", outcomes=12, group_id=ATP_RANK, section="more_markets"),
            ],
            "props": [_card(766401, "Novak Djokovic: 25th Major Next Year", outcomes=1, group_id=QUALIFY)],
        }
        after = _fixed(sections)
        assert [c["id"] for c in after["more_markets"]] == [766238, 990001]
        assert [c["id"] for c in after["props"]] == [766401]

    def test_the_field_is_placed_BEFORE_its_first_row_not_after(self):
        """Asserted on the move alone, deliberately. In the shipped pipeline the
        anchor leg is dropped a line later, so either placement serves the same
        page — but this function is public, its docstring promises the position,
        and the promise is what a later caller would rely on.
        """
        sections = _tennis_sections()
        moved = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in moved["props"]] == [
            766238,  # the field, immediately before the first row of it
            766301,
            766302,
            768652,
            768701,
            766303,
        ]

    def test_the_move_runs_BEFORE_the_collapse(self):
        """Trap 4. Reversed, the collapse sees each family split across two lists,
        matches nothing, and the move then parks the field next to legs nobody
        removed — the ship is inert and the page is worse."""
        inert = move_parents_to_their_legs_section(
            drop_legs_of_a_rendered_field(_tennis_sections())
        )
        assert len(inert["props"]) == 6
        assert len(_fixed(_tennis_sections())["props"]) == 2


class TestWhatMustSurvive:
    """§2 — every arm is a family the rule must decline to move."""

    def test_a_field_alone_under_its_heading_is_left_where_it_is(self):
        """Trap 1. Moving it empties MORE MARKETS instead of PROPS: the same
        heading lost, relocated. Fail open — the duplication is the cheaper cost.
        """
        sections = {
            "more_markets": [_card(766238, "Nitto ATP Finals: Player to Qualify", outcomes=37, group_id=QUALIFY, section="more_markets")],
            "props": [_card(766301, "Will Arthur Fils Qualify?", group_id=QUALIFY)],
        }
        after = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in after["more_markets"]] == [766238]
        assert [c["id"] for c in after["props"]] == [766301]

    def test_legs_in_two_other_sections_are_ambiguous_and_nothing_moves(self):
        """Trap 2. Whichever section won, the other would still restate the field.
        """
        sections = {
            "more_markets": [
                _card(766238, "Nitto ATP Finals: Player to Qualify", outcomes=37, group_id=QUALIFY, section="more_markets"),
                _card(990001, "ATP #1 Ranked Player?", outcomes=12, group_id=ATP_RANK, section="more_markets"),
            ],
            "props": [_card(766301, "Will Arthur Fils Qualify?", group_id=QUALIFY)],
            "futures": [_card(766302, "Will Jakub Mensik Qualify?", group_id=QUALIFY, section="futures")],
        }
        after = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in after["more_markets"]] == [766238, 990001]
        assert [c["id"] for c in after["props"]] == [766301]
        assert [c["id"] for c in after["futures"]] == [766302]

    def test_two_grouped_markets_in_one_family_are_not_a_field(self):
        """Ambiguity, not a field: there is no single card to carry down."""
        sections = {
            "more_markets": [
                _card(1, "Player to Qualify", outcomes=37, group_id=QUALIFY, section="more_markets"),
                _card(2, "Player to Qualify (alt)", outcomes=12, group_id=QUALIFY, section="more_markets"),
            ],
            "props": [_card(3, "Will Arthur Fils Qualify?", group_id=QUALIFY)],
        }
        after = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in after["more_markets"]] == [1, 2]
        assert [c["id"] for c in after["props"]] == [3]

    def test_a_family_already_together_is_left_for_7400(self):
        """#7400's own case. Moving here would be a no-op at best and a reorder
        at worst; the collapse that follows is what handles it."""
        sections = {
            "futures": [
                _card(1, "VCT Partnership 2027: Pacific", outcomes=17, group_id="polymarket:792938", section="futures"),
                _card(2, "Will Paper Rex be a 2027 VCT Pacific partner team?", group_id="polymarket:792938", section="futures"),
            ]
        }
        moved = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in moved["futures"]] == [1, 2]
        assert [c["id"] for c in drop_legs_of_a_rendered_field(moved)["futures"]] == [1]

    def test_a_field_with_no_legs_anywhere_never_moves(self):
        sections = {
            "more_markets": [
                _card(990001, "ATP #1 Ranked Player?", outcomes=12, group_id=ATP_RANK, section="more_markets"),
                _card(990002, "WTA #1 Ranked Player?", outcomes=8, group_id="kalshi:KXWTA1RANK", section="more_markets"),
            ],
            "props": [_card(766301, "Will Arthur Fils Qualify?", group_id=QUALIFY)],
        }
        after = move_parents_to_their_legs_section(sections)
        assert [c["id"] for c in after["more_markets"]] == [990001, 990002]
        assert [c["id"] for c in after["props"]] == [766301]

    @pytest.mark.parametrize("missing", ["group_id", "outcome_count"])
    def test_a_row_the_rule_cannot_read_is_left_alone(self, missing):
        """Fail open, the same contract as the collapse: the cost of keeping a
        card is a duplicate; the cost of moving or dropping one wrongly is a
        market the reader cannot reach."""
        sections = _tennis_sections()
        sections["more_markets"][0] = {**sections["more_markets"][0], missing: None}
        after = _fixed(sections)
        # The unreadable field stays under its own heading and KEEPS its legs —
        # nothing is dropped on the strength of a row we could not classify.
        assert 766238 in [c["id"] for c in after["more_markets"]]
        assert [c["id"] for c in after["props"] if c["group_id"] == QUALIFY] == [
            766301,
            766302,
            766303,
        ]
        # The neighbouring family is unaffected: it still moves and still collapses.
        assert [c["id"] for c in after["props"] if c["group_id"] == TOP_10] == [768652]

    def test_neither_the_mapping_nor_its_lists_are_mutated(self):
        """🔴 `build_hub`'s `sections` share their list objects with a
        Redis-cached league payload; mutating one in place re-composes every page
        that reads that slot (#3964)."""
        sections = _tennis_sections()
        before = {k: [c["id"] for c in v] for k, v in sections.items()}
        result = move_parents_to_their_legs_section(sections)
        assert {k: [c["id"] for c in v] for k, v in sections.items()} == before
        assert all(result[k] is not sections[k] for k in sections)
        # The moved card is a COPY: restamping `section` must not reach the
        # cached row still sitting in the league payload.
        assert sections["more_markets"][0]["section"] == "more_markets"

    def test_an_empty_or_absent_mapping_is_not_an_error(self):
        assert move_parents_to_their_legs_section(None) == {}
        assert move_parents_to_their_legs_section({}) == {}
        assert move_parents_to_their_legs_section({"props": None}) == {"props": []}


class TestTheCountsMoveWithTheCards:
    """§3 — on the payload `build_hub` actually serves.

    The section chip is `markets.length` in `app/hub/[competition]/page.tsx` and
    the hero's "N active markets" is `total_markets`, so a collapse that runs
    after the counts are taken swaps a duplication defect for a lying chip.
    """

    async def _hub(self, monkeypatch, sections):
        async def _league(*, sport_key, db=None, **kwargs):
            # Tennis is a two-tour hub (ATP + WTA); only the primary carries the
            # specimen, and the sibling read must not double the fixture.
            return {"sections": sections if sport_key == "tennis_atp" else {}}

        async def _no_matches(*args, **kwargs):
            return []

        monkeypatch.setattr(hub_module, "get_league_futures", _league)
        monkeypatch.setattr(hub_module, "build_linked_matches", _no_matches)
        return await hub_module.build_hub(HUB_CONFIGS["tennis"], db=None)

    async def test_the_page_serves_two_props_cards_not_four(self, monkeypatch):
        payload = await self._hub(monkeypatch, _tennis_sections())
        assert [c["name"] for c in payload["sections"]["props"]] == [
            "Nitto ATP Finals: Player to Qualify",
            "ATP 2026 End of Year Rankings: Player to Make Top 10",
        ]

    async def test_the_props_chip_counts_what_is_drawn(self, monkeypatch):
        payload = await self._hub(monkeypatch, _tennis_sections())
        counts = payload["section_counts"]["props"]
        assert counts["shown"] == 2
        assert counts["total"] == 2

    async def test_total_markets_does_not_count_the_legs_as_answers(self, monkeypatch):
        """The move and the collapse both run BEFORE `resolve_entity_tier`, so
        this hub is not told it holds 7 answers where it holds 3 questions."""
        payload = await self._hub(monkeypatch, _tennis_sections())
        assert payload["total_markets"] == 3

    async def test_a_hub_with_no_cross_section_family_is_unchanged(self, monkeypatch):
        """boxing / golf / esports measured 0 on the day this shipped and must
        stay byte-identical."""
        rows = [
            _card(1, "Will Sentinels make a roster change by December?", group_id="polymarket:806410"),
            _card(2, "Will Cloud9 make a roster change by December?", group_id="polymarket:806410"),
        ]
        payload = await self._hub(monkeypatch, {"props": rows})
        assert [c["id"] for c in payload["sections"]["props"]] == [1, 2]
        assert payload["total_markets"] == 2
