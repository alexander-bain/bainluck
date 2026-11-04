"""Tests for the reusable ``field_band`` round-up producer kind and
``roundup-cfp-picture`` (catalog #4, issue #10357).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.utils.field_band import (
    CFP_PICTURE_DEFINITION,
    CFP_PICTURE_DEFINITION_PATH,
    CFP_PICTURE_PRODUCER,
    CFP_PICTURE_SLUG,
    PRODUCER_KIND_FIELD_BAND,
    build_field_band_producer,
    cfp_picture_enabled,
    load_field_band_definition,
    parse_market_ref,
    produce_field_band,
    select_field_band,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
    reset_roundup_cache_for_tests,
    roundup_feed_items,
    serve_roundup,
)

FIXED_UPDATED = "2026-11-03T20:45:00+00:00"


def _make_cfp_qualifiers_market(
    *,
    market_id: int = 227,
    external_id: str = "KXNCAAFPLAYOFF-26",
    source: str = "kalshi",
    status: str = "open",
    mutually_exclusive: bool = False,
    total_outcomes: int = 54,
    bubble_outcomes: list[tuple[int, str, float]] | None = None,
    locks_outcomes: list[tuple[int, str, float]] | None = None,
) -> dict[str, Any]:
    if locks_outcomes is None:
        locks_outcomes = [
            (22701, "Oregon", 0.96),
            (22702, "Ohio State", 0.94),
            (22703, "Texas", 0.91),
            (22704, "Georgia", 0.88),
        ]
    if bubble_outcomes is None:
        bubble_outcomes = [
            (22705, "Penn State", 0.795),
            (22706, "Notre Dame", 0.68),
            (22707, "Alabama", 0.64),
            (22708, "Miami", 0.60),
            (22709, "Indiana", 0.52),
            (22710, "Tennessee", 0.45),
            (22711, "Ole Miss", 0.38),
            (22712, "Boise State", 0.31),
            (22713, "SMU", 0.25),
            (22714, "Clemson", 0.21),
        ]
    outcomes: list[dict[str, Any]] = [
        {
            "id": oid,
            "name": name,
            "probability": prob,
            "movement": 0.03 if idx == 0 else None,
            "last_updated": FIXED_UPDATED,
            "is_winner": None,
            "resolution_source": None,
        }
        for idx, (oid, name, prob) in enumerate((*locks_outcomes, *bubble_outcomes))
    ]
    next_id = 22800
    while len(outcomes) < total_outcomes:
        idx = len(outcomes) - len(locks_outcomes) - len(bubble_outcomes) + 1
        prob = max(0.01, round(0.18 - (idx * 0.003), 3))
        outcomes.append(
            {
                "id": next_id,
                "name": f"Program {idx}",
                "probability": prob,
                "movement": None,
                "last_updated": FIXED_UPDATED,
                "is_winner": None,
                "resolution_source": None,
            }
        )
        next_id += 1

    return {
        "id": market_id,
        "external_id": external_id,
        "name": "College Football Playoff Qualifiers 2026-27",
        "source": source,
        "status": status,
        "mutually_exclusive": mutually_exclusive,
        "market_tier": 1,
        "market_type": "playoff",
        "sport": "americanfootball_ncaaf",
        "sport_name": "NCAAF",
        "category": "sports",
        "llm_sport_category": "football",
        "resolution_date": "2026-12-15T17:00:00+00:00",
        "updated_at": FIXED_UPDATED,
        "prices_updated_at": FIXED_UPDATED,
        "outcomes": outcomes,
    }


def _make_cfp_title_market(
    *,
    market_id: int = 181,
    external_id: str = "KXNCAAF-27",
    source: str = "kalshi",
    status: str = "open",
    mutually_exclusive: bool = True,
    total_outcomes: int = 20,
) -> dict[str, Any]:
    seeded = [
        (18101, "Ohio State", 0.24),
        (18102, "Oregon", 0.21),
        (18103, "Texas", 0.17),
        (18104, "Georgia", 0.14),
        (18105, "Alabama", 0.08),
        (18106, "Penn State", 0.06),
        (18107, "Notre Dame", 0.05),
        (18108, "Miami", 0.03),
    ]
    outcomes: list[dict[str, Any]] = [
        {
            "id": oid,
            "name": name,
            "probability": prob,
            "movement": None,
            "last_updated": FIXED_UPDATED,
            "is_winner": None,
            "resolution_source": None,
        }
        for oid, name, prob in seeded
    ]
    next_id = 18200
    while len(outcomes) < total_outcomes:
        idx = len(outcomes) + 1
        outcomes.append(
            {
                "id": next_id,
                "name": f"Contender {idx}",
                "probability": 0.01,
                "movement": None,
                "last_updated": FIXED_UPDATED,
                "is_winner": None,
                "resolution_source": None,
            }
        )
        next_id += 1

    return {
        "id": market_id,
        "external_id": external_id,
        "name": "College Football National Championship Winner 2026-27",
        "source": source,
        "status": status,
        "mutually_exclusive": mutually_exclusive,
        "market_tier": 1,
        "market_type": "championship",
        "sport": "americanfootball_ncaaf",
        "sport_name": "NCAAF",
        "category": "sports",
        "llm_sport_category": "football",
        "resolution_date": "2027-01-20T04:00:00+00:00",
        "updated_at": FIXED_UPDATED,
        "prices_updated_at": FIXED_UPDATED,
        "outcomes": outcomes,
    }


def _fake_loader(
    markets: list[dict[str, Any]],
    withheld: dict[int, set[int]] | None = None,
):
    mapped = {int(m["id"]): m for m in markets}
    withheld_map = withheld or {}

    async def _load(_db: Any, _market_ids: Any, _external_ids: Any):
        return mapped, withheld_map

    return _load


class TestFieldBandDefinitionAndRegistry:
    """Stored JSON definition and producer registration."""

    def test_stored_definition_loads_expected_contract(self) -> None:
        defn = load_field_band_definition(CFP_PICTURE_DEFINITION_PATH)
        assert defn["slug"] == "roundup-cfp-picture"
        assert defn["name"] == "College Football Playoff picture"
        assert defn["kind"] == "roundup"
        assert defn["membership"] == "computed-produced"
        assert defn["category"] == "ncaaf"
        assert defn["section_title"] == ["On the bubble", "Title contenders"]
        assert (
            defn["footer"]
            == "Chance to make the 12-team field · teams between 20% and 80%"
        )
        rule = defn["rule"]
        assert rule["producer"] == PRODUCER_KIND_FIELD_BAND
        assert rule["field"] == "kalshi:227"
        assert rule["field_external_id"] == "KXNCAAFPLAYOFF-26"
        assert rule["band"] == [0.2, 0.8]
        assert rule["second_section"] == "kalshi:181"
        assert rule["second_section_external_id"] == "KXNCAAF-27"
        assert rule["normalize"] is False
        assert rule["twins"] == "none"

    def test_cfp_picture_is_registered_in_roundup_producers(self) -> None:
        assert CFP_PICTURE_SLUG in ROUNDUP_PRODUCERS
        producer = ROUNDUP_PRODUCERS[CFP_PICTURE_SLUG]
        assert producer.slug == CFP_PICTURE_SLUG
        assert producer.name == "College Football Playoff picture"
        assert producer.section_title == "On the bubble"
        assert producer.section_titles == ("On the bubble", "Title contenders")

    def test_parse_market_ref_handles_numeric_and_ticker_tokens(self) -> None:
        assert parse_market_ref("kalshi:227") == ("kalshi", 227, None)
        assert parse_market_ref("KALSHI:KXNCAAFPLAYOFF-26") == (
            "kalshi",
            None,
            "KXNCAAFPLAYOFF-26",
        )
        with pytest.raises(ValueError):
            parse_market_ref("invalid")
        with pytest.raises(ValueError):
            parse_market_ref("kalshi:0")


class TestSelectFieldBand:
    """Pure selection and compositional rules for ``field_band``."""

    @pytest.mark.asyncio
    async def test_produces_bubble_and_title_sections_without_normalizing_to_100(
        self,
    ) -> None:
        qualifiers = _make_cfp_qualifiers_market()
        title = _make_cfp_title_market()

        result = await produce_field_band(
            None,
            definition=CFP_PICTURE_DEFINITION,
            load_markets=_fake_loader([qualifiers, title]),
        )
        assert isinstance(result, RoundupMembers)

        # Spine has 12 winners of 54 — probabilities are NEVER normalized to sum to 100%.
        rows = list(result.rows)
        assert len(rows) == 4
        assert [r["label"] for r in rows] == [
            "Penn State",
            "Notre Dame",
            "Alabama",
            "Miami",
        ]
        assert [r["probability"] for r in rows] == [0.795, 0.68, 0.64, 0.60]
        assert sum(r["probability"] for r in rows) > 2.5
        assert all(r["market_id"] == 227 for r in rows)
        assert [r["outcome_id"] for r in rows] == [22705, 22706, 22707, 22708]
        assert all("event_id" not in r for r in rows)
        assert all(r["observed_at"] == FIXED_UPDATED for r in rows)

        # Compose feed item and container
        feed_item = compose_roundup_feed_item(CFP_PICTURE_PRODUCER, result)
        container = compose_roundup_container(CFP_PICTURE_PRODUCER, result)
        assert feed_item is not None
        assert container is not None

        assert feed_item["type"] == "bundle"
        assert feed_item["data"]["kind"] == "roundup"
        assert feed_item["data"]["title"] == "College Football Playoff picture"
        assert (
            feed_item["data"]["collection_ref"]["href"]
            == "/collections/roundup-cfp-picture"
        )
        assert feed_item["data"]["roundup"]["rows"] == rows

        assert container["state"] == "published"
        assert container["slug"] == "roundup-cfp-picture"
        assert container["container"]["name"] == "College Football Playoff picture"
        assert container["container"]["kind"] == "roundup"
        assert (
            container["subtitle"]
            == "Chance to make the 12-team field · teams between 20% and 80%"
        )
        assert len(container["sections"]) == 2

        bubble_section, title_section = container["sections"]
        assert bubble_section["title"] == "On the bubble"
        assert bubble_section["count"] == 1
        bubble_member = bubble_section["members"][0]
        assert bubble_member["id"] == 227
        assert bubble_member["destination"] == {
            "kind": "market",
            "id": 227,
            "web": "/futures/227",
            "api": "/api/futures/227",
        }
        bubble_card = bubble_member["card"]
        assert bubble_card["source"] == "kalshi"
        assert bubble_card["sources"] == ["kalshi"]
        assert bubble_card["source_count"] == 1
        assert bubble_card["mutually_exclusive"] is False
        assert bubble_card["outcome_count"] == 10
        assert bubble_card["discover_card"]["remaining_outcome_count"] == 6
        assert bubble_card["discover_card"]["field_is_a_race"] is False

        # Verify bubble outcomes are filtered to [0.20, 0.80] and un-normalized
        bubble_top = bubble_card["top_outcomes"]
        assert len(bubble_top) == 10
        assert [o["name"] for o in bubble_top[:4]] == [
            "Penn State",
            "Notre Dame",
            "Alabama",
            "Miami",
        ]
        assert [o["probability"] for o in bubble_top[:4]] == [0.795, 0.68, 0.64, 0.60]
        for outcome in bubble_top:
            assert 0.20 <= outcome["probability"] <= 0.80
        # Locks (>0.80) like Oregon (0.96) and longshots (<0.20) are excluded from bubble section
        bubble_names = {o["name"] for o in bubble_top}
        assert "Oregon" not in bubble_names
        assert "Ohio State" not in bubble_names

        # Second section: Title contenders (kalshi:181, KXNCAAF-27)
        assert title_section["title"] == "Title contenders"
        assert title_section["count"] == 1
        title_member = title_section["members"][0]
        assert title_member["id"] == 181
        assert title_member["destination"] == {
            "kind": "market",
            "id": 181,
            "web": "/futures/181",
            "api": "/api/futures/181",
        }
        title_card = title_member["card"]
        assert title_card["source"] == "kalshi"
        assert title_card["sources"] == ["kalshi"]
        assert title_card["source_count"] == 1
        assert title_card["mutually_exclusive"] is True
        assert title_card["outcome_count"] == 20
        assert title_card["discover_card"]["remaining_outcome_count"] == 16
        assert title_card["discover_card"]["field_is_a_race"] is True
        title_top = title_card["top_outcomes"]
        assert [o["name"] for o in title_top[:4]] == [
            "Ohio State",
            "Oregon",
            "Texas",
            "Georgia",
        ]
        assert [o["probability"] for o in title_top[:4]] == [0.24, 0.21, 0.17, 0.14]

    @pytest.mark.asyncio
    async def test_narrative_copy_never_mentions_venue_names_or_question(self) -> None:
        result = await produce_field_band(
            None,
            definition=CFP_PICTURE_DEFINITION,
            load_markets=_fake_loader(
                [_make_cfp_qualifiers_market(), _make_cfp_title_market()]
            ),
        )
        assert isinstance(result, RoundupMembers)
        feed_item = compose_roundup_feed_item(CFP_PICTURE_PRODUCER, result)
        container = compose_roundup_container(CFP_PICTURE_PRODUCER, result)
        assert feed_item is not None
        assert container is not None

        narrative_strings = [
            container["container"]["name"],
            container["subtitle"],
            feed_item["headline"],
            feed_item["reason"],
            feed_item["data"]["title"],
            feed_item["data"]["roundup"]["footer"],
            *(s["title"] for s in container["sections"]),
            *(
                m["card"]["name"]
                for s in container["sections"]
                for m in s["members"]
            ),
        ]
        for text in narrative_strings:
            lowered = str(text).lower()
            assert "kalshi" not in lowered
            assert "polymarket" not in lowered
            assert "sportsbook" not in lowered
            assert "question" not in lowered

    def test_matches_by_external_id_when_local_pk_differs(self) -> None:
        qualifiers = _make_cfp_qualifiers_market(
            market_id=900227, external_id="KXNCAAFPLAYOFF-26"
        )
        title = _make_cfp_title_market(market_id=900181, external_id="KXNCAAF-27")

        result = select_field_band(
            [qualifiers, title],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            field_external_id="KXNCAAFPLAYOFF-26",
            second_section_external_id="KXNCAAF-27",
            normalize=False,
        )
        assert isinstance(result, RoundupMembers)
        assert [m["id"] for m in result.members] == [900227, 900181]
        assert all(r["market_id"] == 900227 for r in result.rows)

    def test_ungradeable_result_retraction_is_admitted_while_settled_leg_is_excluded(
        self,
    ) -> None:
        qualifiers = _make_cfp_qualifiers_market()
        # Live Kalshi market 227 carries is_winner=False, resolution_source='ungradeable_result'
        # on open outcomes (CAL-P056/#6876 retraction, not a verdict).
        for o in qualifiers["outcomes"]:
            o["is_winner"] = False
            o["resolution_source"] = "ungradeable_result"
        # An actually settled leg (api_settlement) must be excluded.
        qualifiers["outcomes"][4]["resolution_source"] = "api_settlement"

        result = select_field_band(
            [qualifiers, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupMembers)
        # Penn State (index 4, marked api_settlement) was excluded; the remaining 9 bubble teams survive.
        assert [r["label"] for r in result.rows] == [
            "Notre Dame",
            "Alabama",
            "Miami",
            "Indiana",
        ]


class TestFieldBandRefusals:
    """All-or-nothing refusal checks — refuse rather than serve a thin field."""

    def test_refuses_when_spine_market_missing(self) -> None:
        result = select_field_band(
            [_make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("field", "spine_missing"),)

    def test_refuses_when_spine_market_closed(self) -> None:
        qualifiers = _make_cfp_qualifiers_market(status="settled")
        result = select_field_band(
            [qualifiers, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("field", "spine_status_settled"),)

    def test_refuses_when_spine_venue_differs(self) -> None:
        qualifiers = _make_cfp_qualifiers_market(source="polymarket")
        result = select_field_band(
            [qualifiers, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("field", "spine_source_polymarket_expected_kalshi"),)

    def test_refuses_when_spine_field_is_thin(self) -> None:
        thin_qualifiers = _make_cfp_qualifiers_market(total_outcomes=15)
        result = select_field_band(
            [thin_qualifiers, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("field", "thin_field_15_below_24"),)

    def test_refuses_when_spine_is_marked_mutually_exclusive(self) -> None:
        bad_qualifiers = _make_cfp_qualifiers_market(mutually_exclusive=True)
        result = select_field_band(
            [bad_qualifiers, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("field", "spine_mutually_exclusive"),)

    def test_refuses_when_fewer_than_four_teams_in_band(self) -> None:
        thin_bubble = _make_cfp_qualifiers_market(
            bubble_outcomes=[
                (22705, "Penn State", 0.72),
                (22706, "Notre Dame", 0.55),
                (22707, "Alabama", 0.34),
            ]
        )
        result = select_field_band(
            [thin_bubble, _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(result, RoundupRefusal)
        assert result.reasons == (("band", "thin_band_3_below_4"),)

    def test_refuses_when_second_section_missing_or_thin(self) -> None:
        missing_second = select_field_band(
            [_make_cfp_qualifiers_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(missing_second, RoundupRefusal)
        assert missing_second.reasons == (("second_section", "missing"),)

        thin_second = select_field_band(
            [_make_cfp_qualifiers_market(), _make_cfp_title_market(total_outcomes=8)],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
        )
        assert isinstance(thin_second, RoundupRefusal)
        assert thin_second.reasons == (("second_section", "thin_field_8_below_12"),)

    def test_refuses_all_or_nothing_when_any_outcome_price_is_withheld(self) -> None:
        withheld_spine = select_field_band(
            [_make_cfp_qualifiers_market(), _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
            withheld_by_market={227: {22705}},
        )
        assert isinstance(withheld_spine, RoundupRefusal)
        assert withheld_spine.reasons == (("field", "spine_withheld_price_22705"),)

        withheld_second = select_field_band(
            [_make_cfp_qualifiers_market(), _make_cfp_title_market()],
            field_spec="kalshi:227",
            band=(0.20, 0.80),
            section_titles=("On the bubble", "Title contenders"),
            second_section_spec="kalshi:181",
            normalize=False,
            withheld_by_market={181: {18101}},
        )
        assert isinstance(withheld_second, RoundupRefusal)
        assert withheld_second.reasons == (("second_section", "invalid_withheld_price_18101"),)


class TestReusableProducerKindAndFeedIntegration:
    """Proves ``field_band`` works for any definition and wires into Discover feed + container route."""

    @pytest.mark.asyncio
    async def test_second_synthetic_field_band_definition_works_without_code_changes(
        self,
    ) -> None:
        custom_defn = {
            "slug": "roundup-march-madness-bubble",
            "name": "March Madness bubble watch",
            "kind": "roundup",
            "membership": "computed-produced",
            "category": "ncaab",
            "section_title": ["On the bubble", "Title contenders"],
            "footer": "Chance to make the 68-team field · teams between 25% and 75%",
            "rule": {
                "producer": "field_band",
                "field": "kalshi:501",
                "field_external_id": "KXNCAAMBPLAYOFF-27",
                "band": [0.25, 0.75],
                "second_section": "kalshi:502",
                "second_section_external_id": "KXNCAAMB-27",
                "normalize": False,
                "twins": "none",
                "min_field_outcomes": 10,
                "min_band_outcomes": 4,
                "min_second_section_outcomes": 6,
            },
        }
        spine = _make_cfp_qualifiers_market(
            market_id=501,
            external_id="KXNCAAMBPLAYOFF-27",
            total_outcomes=16,
            bubble_outcomes=[
                (5011, "Gonzaga", 0.70),
                (5012, "Villanova", 0.58),
                (5013, "Xavier", 0.44),
                (5014, "Dayton", 0.30),
            ],
        )
        second = _make_cfp_title_market(
            market_id=502,
            external_id="KXNCAAMB-27",
            total_outcomes=8,
        )
        producer = build_field_band_producer(
            custom_defn,
            load_markets=_fake_loader([spine, second]),
        )
        feed_item, container = await evaluate_roundup_producer(producer, [])
        assert feed_item is not None
        assert container is not None
        assert container["slug"] == "roundup-march-madness-bubble"
        assert [s["title"] for s in container["sections"]] == [
            "On the bubble",
            "Title contenders",
        ]
        assert [r["label"] for r in feed_item["data"]["roundup"]["rows"]] == [
            "Gonzaga",
            "Villanova",
            "Xavier",
            "Dayton",
        ]

    @pytest.mark.asyncio
    async def test_cfp_picture_emitted_by_roundup_feed_items_and_serve_roundup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reset_roundup_cache_for_tests()
        assert cfp_picture_enabled() is True
        producer = build_field_band_producer(
            CFP_PICTURE_DEFINITION,
            enabled=cfp_picture_enabled,
            load_markets=_fake_loader(
                [_make_cfp_qualifiers_market(), _make_cfp_title_market()]
            ),
        )
        monkeypatch.setattr(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {CFP_PICTURE_SLUG: producer},
        )
        items = await roundup_feed_items([])
        assert len(items) == 1
        assert items[0]["data"]["id"] == "roundup:cfp-picture"
        assert (
            items[0]["data"]["collection_ref"]["slug"] == "roundup-cfp-picture"
        )
        assert len(items[0]["data"]["roundup"]["rows"]) == 4

        served = await serve_roundup(CFP_PICTURE_SLUG, [])
        assert served["state"] == "published"
        assert served["slug"] == "roundup-cfp-picture"
        assert [s["title"] for s in served["sections"]] == [
            "On the bubble",
            "Title contenders",
        ]
