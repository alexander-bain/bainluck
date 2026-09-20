"""#7400 — one question, 23 cards: the hub printed a field and then every row of it.

`/hub/esports` opened TOURNAMENT WINNERS (25) with the grouped card

    VCT Partnership 2027: Pacific — Paper Rex 93% · FULL SENSE 49% · +13 more

and then, immediately below it, ten cards restating its rows one at a time
("Will FULL SENSE be a 2027 VCT Pacific partner team? — Yes 49%"). `/hub/mma`
did the same 22 times under one 28-outcome parent. 32 cards across two pages,
each leg's Yes byte-identical to the row above it.

MEASURED ON PRODUCTION 2026-09-20, `GET /api/hub/{slug}`:

    hub        family                parent (outcomes)                     legs
    esports    polymarket:792938     VCT Partnership 2027: Pacific (17)      10
    mma        polymarket:131517     Who will become a UFC champion…? (28)   22
    tennis / golf / boxing           —                                        0

and every one of those 32 legs' contenders was verified present in its parent's
FULL outcome list (`/api/futures/{parent_id}`, 28 and 17 outcomes): 32 matched,
0 unmatched. The fixtures below are those two families, trimmed.

THE THREE WAYS THIS FIX GOES WRONG, each with an arm here:

1. Collapsing on `group_id` alone deletes ~150 real cards. `polymarket:806410`
   is 32 genuinely distinct roster-change questions and `polymarket:1048814` is
   three real props of one match; both are binary families with no parent, and
   both must survive untouched (`TestWhatMustSurvive`).
2. Reading membership off `top_outcomes` — it is truncated to ten, so 4 of 8
   sampled MMA legs were absent from their parent's serialized rows purely by
   truncation while being genuine rows of it (`test_a_leg_absent_from_the_parents_
   truncated_row_list_is_still_a_leg`).
3. Collapsing the cards and not the counts: the section chip is the length of
   the array served and `total_markets` is their sum, so a collapse that runs
   after the counts are taken swaps a duplication defect for a lying chip
   (`TestTheCountsMoveWithTheCards`).
"""

from app.routes import hub as hub_module
from app.utils.grouped_field_legs import drop_legs_of_a_rendered_field

HUB_CONFIGS = hub_module.HUB_CONFIGS

VCT = "polymarket:792938"
UFC = "polymarket:131517"
#: Measured the same day: 32 separate roster-change questions under one venue
#: event, no grouped market among them. The population a naive collapse eats.
ROSTER = "polymarket:806410"
#: Three real props of one match — First Blood in Game 2, Total Kills O/U in
#: Game 2, in Game 3 — likewise binary, likewise no parent.
MATCH_PROPS = "polymarket:1048814"


def _card(market_id, name, *, outcomes=2, group_id=None, tier=1, section="futures"):
    """One section card in the shape `/api/leagues/{key}` really serves.

    `top_outcomes` carries a priced outcome because `build_hub` drops every card
    `is_unpriced_card` recognises (UX-P181) — a fixture with no number is one the
    page legitimately refuses to draw, and a collapse test written on those would
    pass against an empty section.
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


def _esports_futures():
    """`/hub/esports` TOURNAMENT WINNERS as production served it, trimmed.

    The parent at index 0, three of its ten legs, and two unrelated rows that
    have every right to the section.
    """
    return [
        _card(58112488, "VCT Partnership 2027: Pacific", outcomes=17, group_id=VCT),
        _card(58112501, "LCK 2027 Winner", outcomes=10, group_id="polymarket:800001"),
        _card(58112510, "Will Paper Rex be a 2027 VCT Pacific partner team?", group_id=VCT),
        _card(58112511, "Will FULL SENSE be a 2027 VCT Pacific partner team?", group_id=VCT),
        _card(58112512, "Will Team Secret be a 2027 VCT Pacific partner team?", group_id=VCT),
        _card(58112530, "Esports World Cup 2027 Winner", outcomes=8, group_id=None),
    ]


def _mma_futures():
    return [
        _card(114091, "Who will become a UFC champion in 2026?", outcomes=28, group_id=UFC),
        _card(114101, "Will Ciryl Gane become UFC champion in 2026?", group_id=UFC),
        _card(114102, "Will Alexander Volkov become UFC champion in 2026?", group_id=UFC),
    ]


class TestTheShip:
    """§1 — the reader stops meeting one question twice."""

    def test_the_esports_legs_go_and_the_field_stays(self):
        kept = drop_legs_of_a_rendered_field({"futures": _esports_futures()})["futures"]
        assert [c["name"] for c in kept] == [
            "VCT Partnership 2027: Pacific",
            "LCK 2027 Winner",
            "Esports World Cup 2027 Winner",
        ]

    def test_the_section_it_replaced_printed_the_field_and_its_rows(self):
        """RED, executed: the fixture IS the defect, so the ship is falsifiable."""
        rows = _esports_futures()
        assert sum(1 for c in rows if c["group_id"] == VCT) == 4
        assert "VCT Partnership 2027: Pacific" in [c["name"] for c in rows]

    def test_the_mma_parent_keeps_its_28_outcome_card(self):
        kept = drop_legs_of_a_rendered_field({"futures": _mma_futures()})["futures"]
        assert [c["outcome_count"] for c in kept] == [28]

    def test_a_leg_absent_from_the_parents_truncated_row_list_is_still_a_leg(self):
        """Trap 2. `top_outcomes` is capped at ten; 4 of 8 sampled MMA legs were
        missing from it while being genuine rows of a 28-outcome field. The
        parent fixture here lists nobody the legs name, and they still collapse —
        the venue's grouping is the evidence, not the display list."""
        parent = _card(114091, "Who will become a UFC champion in 2026?", outcomes=28, group_id=UFC)
        parent["top_outcomes"] = [{"name": "Somebody Else", "probability": 0.6}]
        kept = drop_legs_of_a_rendered_field(
            {"futures": [parent, _card(114101, "Will Ciryl Gane become UFC champion in 2026?", group_id=UFC)]}
        )["futures"]
        assert [c["id"] for c in kept] == [114091]

    def test_the_legs_go_wherever_in_the_list_they_sit(self):
        """On MMA the parent is at index 0 and the legs run from 17 to 38. Order
        is not part of the predicate."""
        legs_first = [
            _card(114101, "Will Ciryl Gane become UFC champion in 2026?", group_id=UFC),
            _card(114091, "Who will become a UFC champion in 2026?", outcomes=28, group_id=UFC),
        ]
        kept = drop_legs_of_a_rendered_field({"futures": legs_first})["futures"]
        assert [c["id"] for c in kept] == [114091]


class TestWhatMustSurvive:
    """§2 — trap 1: `group_id` means "one venue event", not "one question"."""

    def test_32_distinct_roster_questions_under_one_group_all_survive(self):
        rows = [
            _card(800000 + i, f"Will team {i} make a roster change by December?", group_id=ROSTER)
            for i in range(32)
        ]
        kept = drop_legs_of_a_rendered_field({"props": rows})["props"]
        assert len(kept) == 32

    def test_three_real_props_of_one_match_survive(self):
        rows = [
            _card(1, "First Blood in Game 2?", group_id=MATCH_PROPS),
            _card(2, "Total Kills O/U 27.5 in Game 2?", group_id=MATCH_PROPS),
            _card(3, "Total Kills O/U 27.5 in Game 3?", group_id=MATCH_PROPS),
        ]
        kept = drop_legs_of_a_rendered_field({"props": rows})["props"]
        assert [c["id"] for c in kept] == [1, 2, 3]

    def test_a_binary_in_a_DIFFERENT_family_from_the_parent_survives(self):
        """The parent licenses a collapse of its OWN family and nothing else."""
        rows = [
            _card(1, "VCT Partnership 2027: Pacific", outcomes=17, group_id=VCT),
            _card(2, "Will Sentinels make a roster change?", group_id=ROSTER),
        ]
        kept = drop_legs_of_a_rendered_field({"futures": rows})["futures"]
        assert [c["id"] for c in kept] == [1, 2]

    def test_a_parents_family_in_ANOTHER_SECTION_does_not_reach_this_one(self):
        """Scoped to one list (#7437 is the cross-section case, deliberately out
        of scope): a leg under PROPS survives while its parent is under MORE
        MARKETS, because emptying a whole rendered section is its own decision."""
        kept = drop_legs_of_a_rendered_field(
            {
                "more_markets": [_card(1, "Nitto ATP Finals: Player to Qualify", outcomes=37, group_id="polymarket:766238")],
                "props": [_card(2, "Will Alcaraz qualify for the Nitto ATP Finals?", group_id="polymarket:766238")],
            }
        )
        assert [c["id"] for c in kept["props"]] == [2]

    def test_a_row_with_no_group_id_is_never_touched(self):
        rows = [
            _card(1, "VCT Partnership 2027: Pacific", outcomes=17, group_id=VCT),
            _card(2, "Will there be a franchise expansion in 2027?", group_id=None),
        ]
        kept = drop_legs_of_a_rendered_field({"futures": rows})["futures"]
        assert [c["id"] for c in kept] == [1, 2]

    def test_a_row_with_no_outcome_count_is_KEPT(self):
        """Fail open. The cost of keeping a card is a duplicate; the cost of
        dropping one is a market the reader cannot reach."""
        unknown = _card(2, "Will FULL SENSE be a 2027 VCT Pacific partner team?", group_id=VCT)
        unknown.pop("outcome_count")
        kept = drop_legs_of_a_rendered_field(
            {"futures": [_card(1, "VCT Partnership 2027: Pacific", outcomes=17, group_id=VCT), unknown]}
        )["futures"]
        assert [c["id"] for c in kept] == [1, 2]

    def test_a_section_can_never_be_emptied(self):
        """A family only loses legs where its parent is in the same list, and the
        parent is kept — so no heading is ever left over nothing."""
        for rows in (_esports_futures(), _mma_futures()):
            kept = drop_legs_of_a_rendered_field({"futures": rows})["futures"]
            assert kept

    def test_neither_the_mapping_nor_its_lists_are_mutated(self):
        """🔴 `build_hub`'s `sections` share their list objects with a
        Redis-cached league payload; mutating one in place re-composes every page
        that reads that slot (#3964)."""
        sections = {"futures": _esports_futures()}
        before = [c["id"] for c in sections["futures"]]
        result = drop_legs_of_a_rendered_field(sections)
        assert [c["id"] for c in sections["futures"]] == before
        assert result["futures"] is not sections["futures"]


class TestTheCountsMoveWithTheCards:
    """§3 — trap 4, on the payload `build_hub` actually serves.

    The chip is `markets.length` in `app/hub/[competition]/page.tsx` and the
    hero's "N active markets" is `total_markets`, so both are measured on the
    rows served — as long as the collapse happens before they are taken.
    """

    async def _hub(self, monkeypatch, sections):
        async def _league(*, sport_key, db=None, **kwargs):
            return {"sections": sections}

        async def _no_matches(*args, **kwargs):
            return []

        monkeypatch.setattr(hub_module, "get_league_futures", _league)
        monkeypatch.setattr(hub_module, "build_linked_matches", _no_matches)
        return await hub_module.build_hub(HUB_CONFIGS["esports"], db=None)

    async def test_the_page_serves_three_cards_not_six(self, monkeypatch):
        payload = await self._hub(monkeypatch, {"futures": _esports_futures()})
        assert [c["name"] for c in payload["sections"]["futures"]] == [
            "VCT Partnership 2027: Pacific",
            "LCK 2027 Winner",
            "Esports World Cup 2027 Winner",
        ]

    async def test_total_markets_counts_what_is_drawn(self, monkeypatch):
        payload = await self._hub(monkeypatch, {"futures": _esports_futures()})
        assert payload["total_markets"] == 3

    async def test_section_counts_do_not_keep_the_legs_in_total(self, monkeypatch):
        """The collapse runs BEFORE `resolve_entity_tier`, so the legs are not
        counted as answers this hub holds and `total` does not disagree with the
        three cards under the heading."""
        payload = await self._hub(monkeypatch, {"futures": _esports_futures()})
        counts = payload["section_counts"]["futures"]
        assert counts["shown"] == 3
        assert counts["total"] == 3

    async def test_an_unpriced_row_is_still_counted_as_dropped(self, monkeypatch):
        """The two rules are different on purpose and this proves the older one
        survives: an unpriced card is a real, distinct market we refuse to DRAW,
        so it stays in `total` and is published as `dropped`."""
        blank = _card(58112540, "Unpriced field", outcomes=0, group_id=None)
        blank["top_outcomes"] = []
        payload = await self._hub(monkeypatch, {"futures": [*_esports_futures(), blank]})
        counts = payload["section_counts"]["futures"]
        assert counts["shown"] == 3
        assert counts["dropped"] == 1
        assert counts["total"] == 4

    async def test_a_hub_with_no_grouped_field_is_unchanged(self, monkeypatch):
        """tennis / golf / boxing measured 0 on the day this shipped, and they
        must stay byte-identical."""
        rows = [
            _card(1, "Will Sentinels make a roster change by December?", group_id=ROSTER),
            _card(2, "Will Cloud9 make a roster change by December?", group_id=ROSTER),
        ]
        payload = await self._hub(monkeypatch, {"props": rows})
        assert [c["id"] for c in payload["sections"]["props"]] == [1, 2]
        assert payload["total_markets"] == 2
