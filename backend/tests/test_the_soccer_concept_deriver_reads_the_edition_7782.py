"""#7782 — a link labelled "2030 FIFA World Cup" must not open the settled 2026 page.

`SoccerTournamentConfig.winner_name_re` is `/world\\s*cup/i`, which is edition-blind, so
`derive_soccer_concept` returned the one configured edition for EVERY World Cup winner
field. Production specimen: market `56775477` "2030 FIFA World Cup Champion"
(`KXWC-30`, **open**) stamped `event:soccer:world-cup-2026`, and
`/futures/56775477` drew "Part of: 2030 FIFA World Cup ->" pointing at the SETTLED
2026 tournament page ("Final result: Spain — WON"). The label is read off the market
name and the href off the derived key, so the two only disagree on arrival.

These tests are BEHAVIOURAL — they call the deriver and the breadcrumb builder and
read what comes back. Nothing greps the source, and nothing asserts on
`_named_editions` directly, so the guard may be re-implemented any way that keeps the
answers below.
"""

import re

import pytest

from app.utils.concept_links import derive_market_concept_key
from app.utils.event_soccer import (
    SOCCER_TOURNAMENTS,
    SoccerTournamentConfig,
    derive_soccer_concept,
)

WC_2026_KEY = "event:soccer:world-cup-2026"

# The production population, replayed verbatim. Every `futures_markets` row whose name
# matched '%world cup%' + a winner word on 2026-09-21 and that the deriver answered for
# (4 of the 41 matching rows; the other 37 are group/award/novelty markets and
# other-code World Cups already excluded by `_NON_WINNER_FIELD_RE`).
#   (market_id, status, name, external_id)
PRODUCTION_DERIVING_ROWS = [
    (10, "open", "FIFA World Cup Winner", "soccer_fifa_world_cup_winner"),
    (112892, "resolved", "World Cup Winner ", "30615"),
    (
        31836948,
        "resolved",
        "World Cup: Any Country Ranked Outside FIFA Top 10 to Win",
        "KXWCFIFATOP10-26WIN",
    ),
    (56775477, "open", "2030 FIFA World Cup Champion", "KXWC-30"),
]


class TestTheSpecimen:
    """The one open row that was wrong, and the surface it was wrong on."""

    def test_the_2030_board_derives_no_concept(self):
        assert (
            derive_soccer_concept("KXWC-30", "2030 FIFA World Cup Champion", "soccer")
            is None
        )

    def test_the_2030_board_gets_no_breadcrumb_key(self):
        # The reader-visible consumer: `derive_market_concept_key` is what stamps
        # `event_concept_key`, which becomes "Part of: ... ->" on the futures page.
        # The futures page's contract for a key-less market is "no link — honest",
        # and the fallbacks on this row are all null, so the line disappears.
        assert (
            derive_market_concept_key(
                external_id="KXWC-30",
                name="2030 FIFA World Cup Champion",
                llm_sport_category="soccer",
            )
            != WC_2026_KEY
        )

    def test_a_future_edition_never_borrows_a_configured_one(self):
        # Not just 2030: no unconfigured edition may reach a configured concept.
        for year in (2034, 2038, 2042):
            assert (
                derive_soccer_concept(None, f"{year} FIFA World Cup Winner", "soccer")
                is None
            ), year


class TestTheEditionsThatMustSurvive:
    """#205's never-dead shapes. Two of the three correct production rows are these."""

    @pytest.mark.parametrize(
        "name",
        [
            "FIFA World Cup Winner",  # market 10, open — the Odds API shape
            "World Cup Winner ",  # market 112892 — trailing space, as stored
            "World Cup: Any Country Ranked Outside FIFA Top 10 to Win",  # market 31836948
        ],
    )
    def test_a_market_naming_no_edition_still_resolves(self, name):
        # An empty edition set means "no claim", NEVER "claims nothing matches" —
        # a bare "World Cup Winner" must keep reaching the configured tournament or
        # #205's search-to-concept path goes dark.
        c = derive_soccer_concept(None, name, "soccer")
        assert c is not None, name
        assert c["key"] == WC_2026_KEY

    @pytest.mark.parametrize(
        "name",
        [
            "2026 FIFA World Cup Champion",
            "2026 Men's World Cup Winner",
            "2026 World Cup Winner",
        ],
    )
    def test_a_market_naming_the_configured_edition_resolves(self, name):
        c = derive_soccer_concept(None, name, "soccer")
        assert c is not None, name
        assert c["key"] == WC_2026_KEY
        assert c["name"] == "2026 FIFA World Cup"


class TestTheProductionPopulation:
    """Replay every row that derived on 2026-09-21: 4 before, 3 after, and the one
    that leaves is the mis-edition one. This is the blast radius, asserted."""

    def test_exactly_the_mis_edition_row_stops_deriving(self):
        derived = {
            market_id
            for market_id, _status, name, external_id in PRODUCTION_DERIVING_ROWS
            if derive_soccer_concept(external_id, name, "soccer") is not None
        }
        assert derived == {10, 112892, 31836948}
        assert 56775477 not in derived

    def test_the_rows_that_survive_all_point_at_the_configured_edition(self):
        for market_id, _status, name, external_id in PRODUCTION_DERIVING_ROWS:
            c = derive_soccer_concept(external_id, name, "soccer")
            if c is None:
                continue
            assert c["key"] == WC_2026_KEY, market_id


class TestItDisambiguatesRatherThanRefuses:
    """The guard must pick the RIGHT edition, not merely reject every other year.

    Without this, "reject any name whose year isn't 2026" would pass every test above
    and then silently refuse the 2030 tournament on the day its config is added.
    """

    def test_a_second_configured_edition_claims_its_own_market(self, monkeypatch):
        wc2030 = SoccerTournamentConfig(
            slug="world-cup-2030",
            display="2030 FIFA World Cup",
            sport_key="soccer_fifa_world_cup",
            edition=2030,
            winner_name_re=re.compile(r"world\s*cup", re.I),
        )
        monkeypatch.setitem(SOCCER_TOURNAMENTS, "world-cup-2030", wc2030)

        c2030 = derive_soccer_concept("KXWC-30", "2030 FIFA World Cup Champion", "soccer")
        assert c2030 is not None
        assert c2030["key"] == "event:soccer:world-cup-2030"
        assert c2030["name"] == "2030 FIFA World Cup"

        # ...and the 2026 rows are untouched by the newcomer.
        c2026 = derive_soccer_concept(None, "2026 FIFA World Cup Champion", "soccer")
        assert c2026 is not None and c2026["key"] == WC_2026_KEY

    def test_an_edition_less_market_still_takes_the_first_configured_edition(
        self, monkeypatch
    ):
        # A bare name claims no edition, so it cannot be disambiguated — it keeps
        # taking the first configured tournament. Pinned so that adding a second
        # edition is a visible decision rather than a silent re-route.
        monkeypatch.setitem(
            SOCCER_TOURNAMENTS,
            "world-cup-2030",
            SoccerTournamentConfig(
                slug="world-cup-2030",
                display="2030 FIFA World Cup",
                sport_key="soccer_fifa_world_cup",
                edition=2030,
                winner_name_re=re.compile(r"world\s*cup", re.I),
            ),
        )
        c = derive_soccer_concept(None, "FIFA World Cup Winner", "soccer")
        assert c is not None and c["key"] == WC_2026_KEY


class TestTheOldRefusalsAreUnchanged:
    """The guard is additive: everything that returned None before still does."""

    @pytest.mark.parametrize(
        ("name", "category"),
        [
            ("World Cup: Golden Boot Winner", "soccer"),
            ("World Cup Group C Winner", "soccer"),
            ("2026 ICC T20 Men's World Cup Winner", "soccer"),
            ("2027 FIFA Women's World Cup Champion", "soccer"),
            ("2027 Men's Rugby World Cup Winner", "soccer"),
            ("World Cup Winner", "cricket"),
            ("Who will host the 2038 FIFA World Cup", "soccer"),
            (None, "soccer"),
            ("", "soccer"),
        ],
    )
    def test_still_none(self, name, category):
        assert derive_soccer_concept("x", name, category) is None
