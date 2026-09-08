"""#3938 — the tennis hub's TOURNAMENT WINNERS section could only ever be men's.

`/hub/tennis` is the site's only tennis surface. Its sections came from ONE read,
`get_league_futures(sport_key="tennis_atp")`, so the women's draw had no way in.
Measured on production 2026-09-08, the two tour payloads were:

    /api/leagues/tennis_atp   futures: ["US Open Men's Singles Winner"]
                              more_markets: 18   total_markets: 86
    /api/leagues/tennis_wta   futures: ["US Open Women's Singles Winner"]
                              more_markets: 8    total_markets: 9

and only the first reached the hub. Sabalenka's half of the tournament existed,
was fresh, was already cached — and was not on the page.

🔴 THE HALF UX-P182 LEFT BEHIND. #3447 fixed exactly this asymmetry on the
MATCHES rail and said in as many words that it "widens the MATCHES rail only, not
`get_league_futures`". That sentence was right about the tour ENDPOINT and was
read as a rule about the hub: `/api/leagues/tennis_atp` is a tour page and must
stay one tour, but the hub is a SPORT and was never entitled to only one.

🔴 COMPOSED FROM EACH TOUR'S OWN PAYLOAD, NOT FROM A WIDER QUERY. Passing
`also_sport_keys` down into `build_league` would have widened the tour endpoint
itself, and worse: that payload is Redis-cached under
`league_cache_keys(sport_key)`, so a two-tour build would be written to the tour
page's own slot. Reading the sibling's endpoint instead means its slot is already
warm, the existing single-flight revalidation already maintains it, and no cache
identity, Celery task signature or scope argument has to change.
"""

# The MODULE, not its names, and once — `TestTheWiring` monkeypatches attributes
# on it, so it needs the module object anyway, and mixing `import x` with
# `from x import y` for one module is what CodeQL's `py/import-and-import-from`
# note is about.
#
# No `pytestmark`: `pytest.ini` sets `asyncio_mode = auto`, so the async tests in
# `TestTheWiring` are collected without one and a module-level mark would only
# warn on every sync test in the file.
from app.routes import hub as hub_module

HUB_CONFIGS = hub_module.HUB_CONFIGS
merge_league_sections = hub_module.merge_league_sections


def _card(market_id, name, *, tier=1, section="futures"):
    """One section card, in the shape `/api/leagues/{key}` really serves.

    `top_outcomes` carries a priced outcome because `build_hub` drops every card
    `is_unpriced_card` recognises (UX-P181) — a fixture with no number is a
    fixture the page legitimately refuses to draw, and a merge test written on
    those would pass against an empty section.
    """
    return {
        "id": market_id,
        "name": name,
        "market_tier": tier,
        "section": section,
        "source": "kalshi",
        "top_outcomes": [{"name": "Yes", "probability": 0.42}],
    }


#: The two payloads as production served them on 2026-09-08, trimmed to the rows
#: that carry the argument.
ATP_SECTIONS = {
    "futures": [_card(1, "US Open Men's Singles Winner", tier=1)],
    "more_markets": [
        _card(
            2,
            "US Open 2026: To Reach the Final (Men's Singles)",
            tier=3,
            section="more_markets",
        ),
    ],
}
WTA_SECTIONS = {
    "futures": [_card(10, "US Open Women's Singles Winner", tier=1)],
    "more_markets": [
        _card(
            11,
            "US Open 2026: To Reach the Final (Women's Singles)",
            tier=3,
            section="more_markets",
        ),
    ],
}


class TestTheWomensWinnerReachesThePage:
    """§1 — the ship, at the level of the payload the page renders."""

    def test_both_winners_are_in_the_futures_section(self):
        merged = merge_league_sections(ATP_SECTIONS, WTA_SECTIONS)
        assert [c["name"] for c in merged["futures"]] == [
            "US Open Men's Singles Winner",
            "US Open Women's Singles Winner",
        ]

    def test_the_read_it_replaced_could_only_ever_carry_one(self):
        """RED, stated as the shape of the bug: the primary payload IS the whole
        of what the hub used to render, and the women's winner is not in it."""
        assert [c["name"] for c in ATP_SECTIONS["futures"]] == [
            "US Open Men's Singles Winner"
        ]

    def test_every_section_gains_its_sibling_rows(self):
        merged = merge_league_sections(ATP_SECTIONS, WTA_SECTIONS)
        assert len(merged["more_markets"]) == 2


class TestTheOrderIsEarnedAndNotInherited:
    """§2 — the decision a plain concatenation would have got wrong.

    Concatenating puts every men's row above every women's row in every section,
    forever, by construction rather than by merit. `build_league` orders its own
    pool `market_tier ASC NULLS LAST`; this restores that order over the union.
    """

    def test_a_womens_tier_1_outranks_a_mens_tier_3(self):
        merged = merge_league_sections(
            {"futures": [_card(1, "Men's Reach the Final", tier=3)]},
            {"futures": [_card(10, "Women's Singles Winner", tier=1)]},
        )
        assert [c["name"] for c in merged["futures"]] == [
            "Women's Singles Winner",
            "Men's Reach the Final",
        ]

    def test_concatenation_would_have_put_it_second(self):
        """RED, executed: the shape that reads as a merge and encodes a bias."""
        concatenated = [
            *[_card(1, "Men's Reach the Final", tier=3)],
            *[_card(10, "Women's Singles Winner", tier=1)],
        ]
        assert [c["name"] for c in concatenated][0] == "Men's Reach the Final"

    def test_an_untiered_row_sorts_last_not_first(self):
        """`NULLS LAST`, and `None` is not tier 0 — the reading that would put
        every unclassified market at the top of every section."""
        merged = merge_league_sections(
            {"futures": [_card(1, "Untiered", tier=None), _card(2, "Tier 2", tier=2)]},
            {},
        )
        assert [c["name"] for c in merged["futures"]] == ["Tier 2", "Untiered"]

    def test_a_genuine_tie_keeps_the_primary_tour_first(self):
        """A tie-break, which is a different thing from a rule: equal tiers keep
        the order they arrived in, because Python's sort is stable."""
        merged = merge_league_sections(
            {"futures": [_card(1, "Men's Winner", tier=1)]},
            {"futures": [_card(10, "Women's Winner", tier=1)]},
        )
        assert [c["name"] for c in merged["futures"]] == [
            "Men's Winner",
            "Women's Winner",
        ]


class TestWhatMustNotHappenToTheOtherRows:
    """§3 — the ways a merge quietly damages the page it is fixing."""

    def test_a_market_both_tours_claim_is_served_once(self):
        """A mixed-doubles or combined-event market can satisfy both league
        clauses. Served twice, it is #2263's duplicate card arriving through a
        new door."""
        shared = _card(99, "US Open Mixed Doubles Winner", tier=1)
        merged = merge_league_sections({"futures": [shared]}, {"futures": [shared]})
        assert len(merged["futures"]) == 1

    def test_a_section_only_the_sibling_has_is_kept(self):
        """Dropping it would make the hub's vocabulary the PRIMARY tour's
        vocabulary — a section that exists only because the women's draw has one
        is exactly the content this ship is about."""
        merged = merge_league_sections(
            {"futures": [_card(1, "Men's Winner")]},
            {"awards": [_card(10, "WTA Player of the Year")]},
        )
        assert set(merged) == {"futures", "awards"}
        assert [c["name"] for c in merged["awards"]] == ["WTA Player of the Year"]

    def test_the_primary_key_order_leads(self):
        """The page has always rendered the primary tour's section order, and a
        merge is not the place to reshuffle headings."""
        merged = merge_league_sections(
            {"futures": [], "more_markets": []}, {"awards": [], "futures": []}
        )
        assert list(merged) == ["futures", "more_markets", "awards"]

    def test_neither_input_is_mutated(self):
        """🔴 The caller's `sections` dict shares its LIST OBJECTS with a
        Redis-cached payload. An in-place append here is a silent re-tiering of
        every page that reads that slot — live/103's `census_sections` lesson
        (#3964), which was the same shallow-copy shape."""
        primary = {"futures": [_card(1, "Men's Winner")]}
        sibling = {"futures": [_card(10, "Women's Winner")]}
        merge_league_sections(primary, sibling)
        assert [c["id"] for c in primary["futures"]] == [1]
        assert [c["id"] for c in sibling["futures"]] == [10]


class TestTheWiring:
    """§4 — a helper nobody calls with the config's keys fixes nothing."""

    def test_the_tennis_hub_still_declares_the_womens_tour(self):
        assert HUB_CONFIGS["tennis"].sibling_sport_keys == ("tennis_wta",)

    async def test_build_hub_reads_one_league_payload_per_tour(self, monkeypatch):
        read: list[str] = []

        async def _league(*, sport_key, db=None, **kwargs):
            read.append(sport_key)
            return {
                "sections": {
                    "futures": [_card(hash(sport_key) % 1000, f"{sport_key} winner")]
                }
            }

        async def _no_matches(*args, **kwargs):
            return []

        monkeypatch.setattr(hub_module, "get_league_futures", _league)
        monkeypatch.setattr(hub_module, "build_linked_matches", _no_matches)

        payload = await hub_module.build_hub(HUB_CONFIGS["tennis"], db=None)

        assert read == ["tennis_atp", "tennis_wta"]
        names = {c["name"] for c in payload["sections"].get("futures", [])}
        assert names == {"tennis_atp winner", "tennis_wta winner"}

    async def test_a_sibling_that_fails_does_not_blank_the_primary(self, monkeypatch):
        """🔴 gotcha #42, and it is the trade this ship exists to refuse, aimed
        the other way. A shared `try` would let a `tennis_wta` hiccup take the
        men's sections down with it — turning a page that was half right into a
        page that is empty. The loss is PARTIAL: poorer, not broken.
        """

        async def _league(*, sport_key, db=None, **kwargs):
            if sport_key == "tennis_wta":
                raise RuntimeError("wta league read exploded")
            return {"sections": {"futures": [_card(1, "US Open Men's Singles Winner")]}}

        async def _no_matches(*args, **kwargs):
            return []

        monkeypatch.setattr(hub_module, "get_league_futures", _league)
        monkeypatch.setattr(hub_module, "build_linked_matches", _no_matches)

        payload = await hub_module.build_hub(HUB_CONFIGS["tennis"], db=None)

        assert [c["name"] for c in payload["sections"]["futures"]] == [
            "US Open Men's Singles Winner"
        ]
        assert payload["_build_degraded"] is False
