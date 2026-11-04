"""Unit and integration tests for the ``yardstick_pair`` producer kind (§1.4 of ``docs/discover/grouping-types-2026-11.md``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
    compose_roundup_container,
    evaluate_roundup_producer,
    insert_roundup_feed_items,
    reset_roundup_cache_for_tests,
)
from app.utils.yardstick_pair import (
    FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION,
    FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER,
    FOR_SCALE_SNOW_IN_BUFFALO_SLUG,
    FOR_SCALE_SNOW_IN_DC_DEFINITION,
    FOR_SCALE_SNOW_IN_DC_PRODUCER,
    FOR_SCALE_SNOW_IN_DC_SLUG,
    FOR_SCALE_US_RECESSION_2026_DEFINITION,
    FOR_SCALE_US_RECESSION_2026_PRODUCER,
    FOR_SCALE_US_RECESSION_2026_SLUG,
    MAX_YARDSTICK_PERCENT,
    MIN_YARDSTICK_PERCENT,
    PRODUCER_KIND_YARDSTICK_PAIR,
    for_scale_snow_in_buffalo,
    for_scale_snow_in_dc,
    for_scale_us_recession_2026,
    produce_yardstick_pair,
    select_yardstick_pair,
)

NOW_NOV_4 = datetime(2026, 11, 4, 21, 0, 0, tzinfo=timezone.utc)
OBS_FRESH = "2026-11-04T20:15:00Z"
OBS_STALE = "2026-11-01T12:00:00Z"


def _make_binary_market(
    market_id: int,
    name: str,
    probability: float | None,
    *,
    source: str = "polymarket",
    category: str = "politics",
    resolution_date: str = "2026-12-31T23:59:00Z",
    status: str = "open",
    market_type: str = "binary",
    observed_at: str = OBS_FRESH,
) -> dict[str, Any]:
    no_prob = round(1.0 - probability, 6) if probability is not None else None
    return {
        "id": market_id,
        "name": name,
        "status": status,
        "source": source,
        "category": category,
        "llm_sport_category": category,
        "market_tier": 2,
        "market_type": market_type,
        "mutually_exclusive": True,
        "resolution_date": resolution_date,
        "updated_at": observed_at,
        "outcomes": [
            {
                "id": market_id * 10 + 1,
                "name": "Yes",
                "probability": probability,
                "is_winner": False,
                "resolution_source": None,
                "observed_at": observed_at,
            },
            {
                "id": market_id * 10 + 2,
                "name": "No",
                "probability": no_prob,
                "is_winner": False,
                "resolution_source": None,
                "observed_at": observed_at,
            },
        ],
    }


class TestYardstickPairSelection:
    @pytest.mark.asyncio
    async def test_for_scale_snow_in_dc_with_nov_3_prices_pairs_newsom_against_dc_snow(
        self,
    ) -> None:
        """Catalog §1.4 worked example: Gavin Newsom announces a 2028 run (40%)
        paired against Snow in DC by Nov 30 (39%).
        """
        pool = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-12-04T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.40,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.44,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        members = await produce_yardstick_pair(
            pool,
            definition=FOR_SCALE_SNOW_IN_DC_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "FOR SCALE"
        assert (
            members.title
            == "Gavin Newsom announces a 2028 run: as likely as snow in DC by Nov 30"
        )
        assert (
            members.footer
            == "Two unrelated markets with the same chance."
        )
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (60880786, "Gavin Newsom announces a 2028 run", 40),
            (60104328, "Snow in Washington, DC by Nov 30", 39),
        ]
        assert len(members.sections) == 1
        assert members.sections[0]["title"] == "For scale"
        assert members.sections[0]["count"] == 2

        container = compose_roundup_container(FOR_SCALE_SNOW_IN_DC_PRODUCER, members)
        assert container is not None
        assert container["state"] == "published"
        assert container["slug"] == FOR_SCALE_SNOW_IN_DC_SLUG
        assert (
            container["container"]["name"]
            == "Gavin Newsom announces a 2028 run: as likely as snow in DC by Nov 30"
        )
        assert container["member_count"] == 2

    @pytest.mark.asyncio
    async def test_for_scale_snow_in_buffalo_live_nov_4_prices_pairs_hegseth_against_buffalo_snow(
        self,
    ) -> None:
        """Live Nov 4 prices: Pete Hegseth out by Dec 31 (43%) vs Snow in Buffalo by Nov 15 (42%)."""
        pool = [
            _make_binary_market(
                60087427,
                "Will it snow in Buffalo, NY by November 15?",
                0.42,
                category="weather",
                resolution_date="2026-11-19T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.425,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        members = await produce_yardstick_pair(
            pool,
            definition=FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "FOR SCALE"
        assert (
            members.title
            == "Pete Hegseth out by Dec 31: as likely as snow in Buffalo by Nov 15"
        )
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (
                8422080,
                "Pete Hegseth out as Secretary of Defense by Dec 31",
                43,
            ),
            (60087427, "Snow in Buffalo by Nov 15", 42),
        ]

    @pytest.mark.asyncio
    async def test_for_scale_us_recession_2026_live_nov_4_prices_pairs_iran_against_recession(
        self,
    ) -> None:
        """Catalog §1.4 second worked example: The Iranian regime falls before 2027 (4%)
        paired against a US recession by end of 2026 (6%).
        """
        pool = [
            _make_binary_market(
                113012,
                "US recession by end of 2026?",
                0.055,
                category="economy",
                resolution_date="2027-07-31T00:00:00Z",
            ),
            _make_binary_market(
                113200,
                "Will the Iranian regime fall before 2027?",
                0.036,
                category="geopolitics",
                resolution_date="2026-12-31T00:00:00Z",
            ),
        ]
        members = await produce_yardstick_pair(
            pool,
            definition=FOR_SCALE_US_RECESSION_2026_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(members, RoundupMembers)
        assert members.kicker == "FOR SCALE"
        assert (
            members.title
            == "The Iranian regime falls before 2027: as likely as a US recession by end of 2026"
        )
        assert [
            (r["market_id"], r["label"], r["rendered_percent"]) for r in members.rows
        ] == [
            (113200, "The Iranian regime falls before 2027", 4),
            (113012, "US recession by end of 2026", 6),
        ]

    @pytest.mark.asyncio
    async def test_recomputes_sentence_on_every_serve_and_never_caches_text(
        self,
    ) -> None:
        """Catalog §1.4: 'The sentence is recomputed from the two live numbers on every
        serve, never cached as text.' When candidate prices move, the very next call to
        evaluate_roundup_producer updates or refuses immediately without cache expiry.
        """
        reset_roundup_cache_for_tests()
        pool_v1 = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-12-04T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.40,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.46,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        feed_1, container_1 = await for_scale_snow_in_dc(pool_v1)
        assert feed_1 is not None and container_1 is not None
        assert (
            feed_1["headline"]
            == "Gavin Newsom announces a 2028 run: as likely as snow in DC by Nov 30"
        )

        # Now Newsom moves to 32% (outside 2pp) and Hegseth moves to 39% (exact match).
        pool_v2 = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-12-04T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.32,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.39,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        feed_2, container_2 = await for_scale_snow_in_dc(pool_v2)
        assert feed_2 is not None and container_2 is not None
        assert (
            feed_2["headline"]
            == "Pete Hegseth out by Dec 31: as likely as snow in DC by Nov 30"
        )

        # Now both candidates move >2pp away; next serve refuses immediately.
        pool_v3 = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-12-04T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.32,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.50,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        feed_3, container_3 = await for_scale_snow_in_dc(pool_v3)
        assert feed_3 is None and container_3 is None


class TestYardstickPairRefusals:
    def test_refuses_same_category(self) -> None:
        """Refuses when the candidate is in the same category as the anchor."""
        markets = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
            ),
            _make_binary_market(
                60087427,
                "Will it snow in Buffalo, NY by November 15?",
                0.39,
                category="weather",
            ),
        ]
        res = select_yardstick_pair(
            markets,
            anchor_spec="polymarket:60104328",
            candidate_specs=["polymarket:60087427"],
            now=NOW_NOV_4,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("candidate", 60087427, "same_category") in res.reasons

    def test_refuses_when_candidate_is_not_binary(self) -> None:
        markets = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
            ),
            {
                "id": 61321728,
                "name": "Who will be featured on GTA VI: The Album?",
                "status": "open",
                "source": "polymarket",
                "category": "entertainment",
                "market_type": "field",
                "mutually_exclusive": False,
                "resolution_date": "2026-11-27T04:59:00Z",
                "outcomes": [
                    {"id": 1, "name": "Kodak Black", "probability": 0.39, "observed_at": OBS_FRESH},
                    {"id": 2, "name": "Don Toliver", "probability": 0.39, "observed_at": OBS_FRESH},
                ],
            },
        ]
        res = select_yardstick_pair(
            markets,
            anchor_spec="polymarket:60104328",
            candidate_specs=["polymarket:61321728"],
            now=NOW_NOV_4,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("candidate", 61321728, "non_binary_market_type:field") in res.reasons

    def test_refuses_when_rounded_gap_is_in_three_to_nine_point_band(self) -> None:
        """Decision C: pairs sitting 3–9 points apart refuse."""
        markets = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.42,
                category="politics",
            ),
        ]
        res = select_yardstick_pair(
            markets,
            anchor_spec="polymarket:60104328",
            candidate_specs=["polymarket:60880786"],
            now=NOW_NOV_4,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("candidate", 60880786, "band_gap_between_bands:3") in res.reasons

    @pytest.mark.asyncio
    async def test_refuses_when_price_is_withheld_or_stale_beyond_48h(self) -> None:
        """Reproduces today's live DC snow refusal when Yes probability is None (withheld
        after >24h without a trade) or when observed_at is older than max_age_hours.
        """
        pool_withheld = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                None,
                category="weather",
                market_type="container_member",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.35,
                category="politics",
                market_type="container_member",
            ),
        ]
        res_withheld = await produce_yardstick_pair(
            pool_withheld,
            definition=FOR_SCALE_SNOW_IN_DC_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(res_withheld, RoundupRefusal)
        assert ("anchor", 60104328, "missing_probability") in res_withheld.reasons

        pool_stale = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                market_type="container_member",
                observed_at=OBS_STALE,
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.40,
                category="politics",
                market_type="container_member",
                observed_at=OBS_FRESH,
            ),
        ]
        res_stale = await produce_yardstick_pair(
            pool_stale,
            definition=FOR_SCALE_SNOW_IN_DC_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(res_stale, RoundupRefusal)
        assert ("anchor", 60104328, "stale_observation") in res_stale.reasons

    def test_refuses_when_deciding_within_48_hours_or_past_deadline(self) -> None:
        markets_soon = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-11-05T12:00:00Z",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.40,
                category="politics",
            ),
        ]
        res_soon = select_yardstick_pair(
            markets_soon,
            anchor_spec="polymarket:60104328",
            candidate_specs=["polymarket:60880786"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_soon, RoundupRefusal)
        assert ("anchor", 60104328, "deciding_within_48h") in res_soon.reasons

        markets_past = [
            _make_binary_market(
                60104328,
                "Will it snow in Washington, DC by November 30?",
                0.39,
                category="weather",
                resolution_date="2026-11-01T00:00:00Z",
            ),
            _make_binary_market(
                60880786,
                "Will Gavin Newsom announce a Presidential run before 2028?",
                0.40,
                category="politics",
            ),
        ]
        res_past = select_yardstick_pair(
            markets_past,
            anchor_spec="polymarket:60104328",
            candidate_specs=["polymarket:60880786"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_past, RoundupRefusal)
        assert ("anchor", 60104328, "anchor_deadline_passed") in res_past.reasons

    def test_refuses_outside_three_to_ninety_seven_percent_band(self) -> None:
        """Enforces the 3%-97% whole-number band on both anchor and candidate legs
        with explicit boundary assertions at 2%, 3%, 97%, and 98%.
        """
        assert MIN_YARDSTICK_PERCENT == 3
        assert MAX_YARDSTICK_PERCENT == 97

        # 2% candidate (outside band) is refused when anchor is 3%.
        res_cand_2 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.03, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.02, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_cand_2, RoundupRefusal)
        assert ("candidate", 113200, "outside_probability_band:2") in res_cand_2.reasons

        # 2% anchor (outside band) is refused.
        res_anchor_2 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.02, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.03, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_anchor_2, RoundupRefusal)
        assert ("anchor", 113012, "outside_probability_band:2") in res_anchor_2.reasons

        # 3% anchor and 3% candidate (lower boundary) succeed.
        res_3 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.03, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.03, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_3, RoundupMembers)
        assert [r["rendered_percent"] for r in res_3.rows] == [3, 3]

        # 97% anchor and 97% candidate (upper boundary) succeed.
        res_97 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.97, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.97, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_97, RoundupMembers)
        assert [r["rendered_percent"] for r in res_97.rows] == [97, 97]

        # 98% candidate (outside band) is refused when anchor is 97%.
        res_cand_98 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.97, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.98, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_cand_98, RoundupRefusal)
        assert ("candidate", 113200, "outside_probability_band:98") in res_cand_98.reasons

        # 98% anchor (outside band) is refused when candidate is 97%.
        res_anchor_98 = select_yardstick_pair(
            [
                _make_binary_market(113012, "US recession by end of 2026?", 0.98, category="economy"),
                _make_binary_market(113200, "Will the Iranian regime fall before 2027?", 0.97, category="geopolitics"),
            ],
            anchor_spec="kalshi:113012",
            candidate_specs=["kalshi:113200"],
            now=NOW_NOV_4,
        )
        assert isinstance(res_anchor_98, RoundupRefusal)
        assert ("anchor", 113012, "outside_probability_band:98") in res_anchor_98.reasons

    @pytest.mark.asyncio
    async def test_refuses_uncurated_in_band_market_when_curated_candidates_miss(
        self,
    ) -> None:
        """Candidates are restricted strictly to the curated pool in the definition;
        an uncurated market within 2 points of the anchor is never selected.
        """
        pool = [
            _make_binary_market(
                60087427,
                "Will it snow in Buffalo, NY by November 15?",
                0.42,
                category="weather",
                resolution_date="2026-11-19T04:59:00Z",
                market_type="container_member",
            ),
            # Curated candidate 8422080 is at 55% (outside the 2-point band).
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.55,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
            # Uncurated market 99999999 sits at 42% (exact match), cross-category, open & fresh.
            _make_binary_market(
                99999999,
                "Will an uncurated market resolve Yes by December 31?",
                0.42,
                category="tech",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="binary",
            ),
        ]
        res = await produce_yardstick_pair(
            pool,
            definition=FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION,
            now=NOW_NOV_4,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("pair", "no_qualifying_target") in res.reasons

    @pytest.mark.asyncio
    async def test_registered_in_roundup_producers_and_folds_covered_feed_cards(
        self,
    ) -> None:
        reset_roundup_cache_for_tests()
        assert FOR_SCALE_SNOW_IN_DC_SLUG in ROUNDUP_PRODUCERS
        assert FOR_SCALE_SNOW_IN_BUFFALO_SLUG in ROUNDUP_PRODUCERS
        assert FOR_SCALE_US_RECESSION_2026_SLUG in ROUNDUP_PRODUCERS
        assert (
            FOR_SCALE_SNOW_IN_BUFFALO_DEFINITION["rule"]["producer"]
            == PRODUCER_KIND_YARDSTICK_PAIR
        )

        pool = [
            _make_binary_market(
                60087427,
                "Will it snow in Buffalo, NY by November 15?",
                0.42,
                category="weather",
                resolution_date="2026-11-19T04:59:00Z",
                market_type="container_member",
            ),
            _make_binary_market(
                8422080,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.425,
                category="politics",
                resolution_date="2026-12-31T00:00:00Z",
                market_type="container_member",
            ),
        ]
        feed_item, container = await evaluate_roundup_producer(
            FOR_SCALE_SNOW_IN_BUFFALO_PRODUCER, pool
        )
        assert feed_item is not None and container is not None

        deck: list[dict[str, Any]] = [
            {
                "type": "futures",
                "score": 90.0 - i,
                "reason": f"Card {i}",
                "headline": f"Card {i}",
                "data": {"id": 900000 + i, "name": f"Card {i}"},
            }
            for i in range(15)
        ]
        deck[3] = {
            "type": "futures",
            "score": 87.0,
            "reason": "Pete Hegseth",
            "headline": "Pete Hegseth",
            "data": {
                "id": 8422080,
                "name": "Pete Hegseth out as Secretary of Defense by December 31?",
            },
        }
        merged = insert_roundup_feed_items(deck, [feed_item], now=NOW_NOV_4)
        standalone_ids = [
            it["data"]["id"] for it in merged if it.get("type") == "futures"
        ]
        assert 8422080 not in standalone_ids

    @pytest.mark.asyncio
    async def test_db_loader_tolerates_none_and_unrelated_fake_session_rows(
        self,
    ) -> None:
        feed_none, container_none = await for_scale_snow_in_buffalo(None)
        assert feed_none is None and container_none is None

        class _FakeScalars:
            def all(self) -> list[dict[str, Any]]:
                return [{"team": "BUF", "win_prob": 0.55}]

        class _FakeResult:
            def scalars(self) -> _FakeScalars:
                return _FakeScalars()

        class _FakeSession:
            async def execute(self, _stmt: Any) -> _FakeResult:
                return _FakeResult()

        feed_fake, container_fake = await for_scale_us_recession_2026(_FakeSession())
        assert feed_fake is None and container_fake is None
