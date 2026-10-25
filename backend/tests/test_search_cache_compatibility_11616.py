"""Permanent regression suite for #11616 search/typeahead cache compatibility.

PILLARS: TRUTH / MATCHING / FORMATTING.
SHIP: A cached search suggestion or full-search result does not restore a
probability the current representation cannot support. Useful names,
destinations and supported results remain available while servers and workers
adopt the change.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.routes import events as events_mod
from app.routes.events import (
    _TA_CACHE_RETAINED,
    _TA_CACHE_WRITTEN,
    _build_search_top_outcomes,
    _force_cache_rebuild,
    _force_search_cache_rebuild,
    _format_futures_for_search,
    _typeahead_cached_body_is_complete,
    _typeahead_publish_thinner,
    search_events,
    typeahead_search,
)
from app.routes.futures import _format_market_detail
from app.utils import event_concept_cache as cache_mod
from app.utils.search_cache import (
    SEARCH_CACHE_HEADER,
    SEARCH_FUTURES_REPRESENTATION_POLICY,
    SEARCH_FUTURES_REPRESENTATION_POLICY_KEY,
    adapt_cached_futures_row,
    adapt_cached_search_response,
    adapt_cached_typeahead_response,
    attest_represented_top_outcomes,
    is_attested_top_outcomes,
    is_current_represented_futures_row,
    search_response_cache_key,
    stamp_futures_representation_policy,
)


def _http_request(path: str = "/api/events/search", query_string: str = "q=mvp") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query_string.encode("utf-8"),
            "headers": [],
            "client": ("127.0.0.1", 50000),
        }
    )


def _make_outcome(
    oid: int,
    name: str,
    probability: float | None,
    *,
    is_winner: bool | None = None,
    resolution_source: str | None = None,
    last_updated: datetime | None = None,
    price_changed_at: datetime | None = None,
    probability_change_24h: float | None = None,
    opening_probability: float | None = None,
    american_odds: int | None = None,
    rank: int | None = None,
    external_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=oid,
        name=name,
        outcome_name=name,
        current_probability=probability,
        opening_probability=opening_probability,
        probability_change_24h=probability_change_24h,
        american_odds=american_odds,
        opening_american_odds=None,
        rank=rank,
        rank_change_24h=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        last_updated=last_updated,
        price_changed_at=price_changed_at,
        external_id=external_id or f"ext-{oid}",
        current_yes_bid=probability,
        current_yes_ask=probability,
        last_trade_price=probability,
        outcome_metadata=None,
    )


def _make_market(
    market_id: int = 66031970,
    name: str = "NBA MVP",
    *,
    status: str = "open",
    source: str = "polymarket",
    market_tier: int = 3,
    category: str = "award",
    llm_sport_category: str = "basketball",
    mutually_exclusive: bool = True,
    outcomes: list[SimpleNamespace] | None = None,
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    now = updated_at or datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
    sport = SimpleNamespace(id=1, key="basketball_nba", name="NBA")
    return SimpleNamespace(
        id=market_id,
        name=name,
        status=status,
        source=source,
        market_tier=market_tier,
        category=category,
        llm_sport_category=llm_sport_category,
        market_type="award",
        mutually_exclusive=mutually_exclusive,
        sport_id=1,
        sport=sport,
        event_id=None,
        external_id=f"poly-{market_id}",
        resolution_date=now + timedelta(days=60),
        updated_at=now,
        outcomes=outcomes or [],
        volume=250000.0,
        liquidity=50000.0,
        group_id=None,
        market_metadata={},
        hook_description=None,
        description=None,
        rules_primary=None,
        created_at=now,
        image_url=None,
        category_tags=[],
        canonical_market_key=None,
    )


# ---------------------------------------------------------------------------
# 1. Producer attestation & current representation policy eligibility
# ---------------------------------------------------------------------------


class TestProducerAttestationAndEligibility:
    def test_build_search_top_outcomes_attests_and_stamps_policy_marker(self):
        now = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
        market = _make_market(
            outcomes=[
                _make_outcome(1, "Shai Gilgeous-Alexander", 0.55, last_updated=now),
                _make_outcome(2, "Nikola Jokic", 0.45, last_updated=now),
            ],
            updated_at=now,
        )
        top = _build_search_top_outcomes(market, limit=5, lean=False)
        assert is_attested_top_outcomes(top)

        card = _format_futures_for_search(market)
        assert (
            card[SEARCH_FUTURES_REPRESENTATION_POLICY_KEY]
            == SEARCH_FUTURES_REPRESENTATION_POLICY
        )
        assert is_current_represented_futures_row(card)

        lean_top = _build_search_top_outcomes(market, limit=3, lean=True)
        assert is_attested_top_outcomes(lean_top)
        ta_row = stamp_futures_representation_policy(
            {
                "type": "futures",
                "text": market.name,
                "market_id": market.id,
                "market_tier": market.market_tier,
                "status": market.status,
                "market_type_label": "Award",
                "sport_key": "basketball",
                "top_outcomes": lean_top,
            }
        )
        assert (
            ta_row[SEARCH_FUTURES_REPRESENTATION_POLICY_KEY]
            == SEARCH_FUTURES_REPRESENTATION_POLICY
        )
        assert is_current_represented_futures_row(ta_row)

    def test_unexamined_plain_list_cannot_acquire_policy_attestation(self):
        plain_outcomes = [
            {
                "name": "Victor Wembanyama",
                "probability": 0.275,
                "rendered_percent": 28,
                "movement": 0.04,
                "is_winner": False,
                "resolution_source": None,
            }
        ]
        assert not is_attested_top_outcomes(plain_outcomes)
        unexamined_row = stamp_futures_representation_policy(
            {
                "id": 66031970,
                "name": "NBA MVP",
                "status": "open",
                "top_outcomes": plain_outcomes,
            }
        )
        assert SEARCH_FUTURES_REPRESENTATION_POLICY_KEY not in unexamined_row
        assert not is_current_represented_futures_row(unexamined_row)

    def test_spoofed_policy_marker_without_valid_outcome_fields_is_rejected(self):
        spoofed_missing_rendered = {
            "id": 66031970,
            "name": "NBA MVP",
            "status": "open",
            "representation_policy": SEARCH_FUTURES_REPRESENTATION_POLICY,
            "top_outcomes": [
                {
                    "name": "Victor Wembanyama",
                    "probability": 0.275,
                    "movement": 0.04,
                    "is_winner": None,
                    "resolution_source": None,
                }
            ],
        }
        assert not is_current_represented_futures_row(spoofed_missing_rendered)
        adapted = adapt_cached_futures_row(spoofed_missing_rendered)
        assert adapted["top_outcomes"][0]["probability"] is None
        assert adapted["top_outcomes"][0]["rendered_percent"] is None

        spoofed_default_false_winner = {
            "id": 66031970,
            "name": "NBA MVP",
            "status": "open",
            "representation_policy": SEARCH_FUTURES_REPRESENTATION_POLICY,
            "top_outcomes": [
                {
                    "name": "Victor Wembanyama",
                    "probability": 0.275,
                    "rendered_percent": 28,
                    "movement": 0.04,
                    "is_winner": False,
                    "resolution_source": None,
                }
            ],
        }
        assert not is_current_represented_futures_row(spoofed_default_false_winner)
        adapted_false = adapt_cached_futures_row(spoofed_default_false_winner)
        assert adapted_false["top_outcomes"][0]["probability"] is None
        assert adapted_false["top_outcomes"][0]["is_winner"] is None


# ---------------------------------------------------------------------------
# 2. Current supported hit vs legacy full-search / typeahead hit & mixed rollout
# ---------------------------------------------------------------------------


class TestCurrentAndLegacyCacheHits:
    def test_current_supported_search_and_typeahead_hits_stay_unchanged(self):
        now = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
        market = _make_market(
            outcomes=[
                _make_outcome(
                    1,
                    "Shai Gilgeous-Alexander",
                    0.54,
                    probability_change_24h=0.03,
                    opening_probability=0.45,
                    american_odds=-117,
                    rank=1,
                    last_updated=now,
                    price_changed_at=now,
                ),
                _make_outcome(
                    2,
                    "Nikola Jokic",
                    0.46,
                    probability_change_24h=-0.03,
                    opening_probability=0.55,
                    american_odds=117,
                    rank=2,
                    last_updated=now,
                    price_changed_at=now,
                ),
            ],
            updated_at=now,
        )
        card = _format_futures_for_search(market)
        search_payload = {
            "query": "mvp",
            "teams": [],
            "event_concepts": [],
            "results": [],
            "futures": [card],
            "futures_families": [
                {
                    "family_key": "award:basketball:mvp",
                    "label": "NBA MVP",
                    "headline": copy.deepcopy(card),
                    "members": [copy.deepcopy(card)],
                    "total_markets": 1,
                }
            ],
            "pagination": {"page": 1, "per_page": 25, "total": 0, "total_pages": 0},
            "sports": [],
            "filters": {
                "sport": None,
                "tags": [],
                "days_back": 30,
                "include_upcoming": True,
            },
        }
        adapted_search = adapt_cached_search_response(search_payload)
        assert adapted_search == search_payload
        assert adapted_search["futures"][0]["top_outcomes"][0]["probability"] == 0.54
        assert adapted_search["futures"][0]["top_outcomes"][0]["rendered_percent"] == 54
        assert (
            adapted_search["futures_families"][0]["headline"]["top_outcomes"][0][
                "probability"
            ]
            == 0.54
        )

        lean_top = _build_search_top_outcomes(market, limit=3, lean=True)
        ta_payload = {
            "query": "mvp",
            "suggestions": [
                stamp_futures_representation_policy(
                    {
                        "type": "futures",
                        "text": "NBA MVP",
                        "market_id": market.id,
                        "market_tier": 3,
                        "status": "open",
                        "market_type_label": "Award",
                        "sport_key": "basketball",
                        "top_outcomes": lean_top,
                    }
                )
            ],
        }
        adapted_ta = adapt_cached_typeahead_response(ta_payload)
        assert adapted_ta == ta_payload
        assert adapted_ta["suggestions"][0]["top_outcomes"][0]["probability"] == 0.54
        assert (
            adapted_ta["suggestions"][0]["top_outcomes"][0]["rendered_percent"] == 54
        )

    def test_legacy_search_hit_adapts_futures_and_families_and_preserves_navigation(self):
        legacy_card = {
            "id": 66031970,
            "name": "NBA MVP",
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "category": "award",
            "llm_sport_category": "basketball",
            "market_tier": 3,
            "market_type_label": "Award",
            "market_type": "award",
            "status": "open",
            "source": "polymarket",
            "resolution_date": "2027-06-01T00:00:00+00:00",
            "outcome_count": 3,
            "updated_at": "2026-10-24T18:00:00+00:00",
            "prices_updated_at": "2026-10-24T18:00:00+00:00",
            "hook_description": "Wembanyama leads at 28%",
            "leader": "Victor Wembanyama",
            "favorite": "Victor Wembanyama",
            "lead_outcome_id": 101,
            "top_outcomes": [
                {
                    "id": 101,
                    "name": "Victor Wembanyama",
                    "probability": 0.275,
                    "movement": 0.04,
                    "american_odds": 264,
                    "rank": 1,
                    "matched_rank": 1,
                    "query_match": True,
                    "is_winner": False,
                    "resolution_source": None,
                    "last_updated": "2026-10-10T00:00:00+00:00",
                    "price_changed_at": "2026-10-10T00:00:00+00:00",
                },
                {
                    "id": 102,
                    "name": "Shai Gilgeous-Alexander",
                    "probability": 0.19,
                    "movement": -0.02,
                    "american_odds": 426,
                    "rank": 2,
                    "is_winner": False,
                    "resolution_source": None,
                    "last_updated": "2026-10-24T18:00:00+00:00",
                    "price_changed_at": "2026-10-24T18:00:00+00:00",
                },
            ],
        }
        legacy_payload = {
            "query": "wembanyama",
            "teams": [],
            "event_concepts": [],
            "results": [],
            "futures": [copy.deepcopy(legacy_card)],
            "futures_families": [
                {
                    "family_key": "award:basketball:mvp",
                    "label": "NBA MVP",
                    "headline": copy.deepcopy(legacy_card),
                    "members": [copy.deepcopy(legacy_card)],
                    "total_markets": 1,
                }
            ],
            "pagination": {"page": 1, "per_page": 25, "total": 0, "total_pages": 0},
            "sports": [],
            "filters": {
                "sport": None,
                "tags": [],
                "days_back": 30,
                "include_upcoming": True,
            },
        }
        adapted = adapt_cached_search_response(legacy_payload)
        for surface_card in (
            adapted["futures"][0],
            adapted["futures_families"][0]["headline"],
            adapted["futures_families"][0]["members"][0],
        ):
            assert surface_card["id"] == 66031970
            assert surface_card["name"] == "NBA MVP"
            assert surface_card["sport"] == "basketball_nba"
            assert surface_card["market_tier"] == 3
            assert surface_card["outcome_count"] == 3
            assert surface_card["prices_updated_at"] is None
            assert surface_card["hook_description"] is None
            assert surface_card["leader"] is None
            assert surface_card["favorite"] is None
            assert surface_card["lead_outcome_id"] is None
            for outcome in surface_card["top_outcomes"]:
                assert outcome["probability"] is None
                assert outcome["rendered_percent"] is None
                assert outcome["movement"] is None
                assert outcome["american_odds"] is None
                assert outcome["rank"] is None
                assert outcome.get("matched_rank") is None
                assert outcome["is_winner"] is None
                assert outcome["resolution_source"] is None

    @pytest.mark.asyncio
    async def test_mixed_rollout_older_worker_republishing_legacy_entry_after_current_is_adapted(
        self,
    ):
        now = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
        market = _make_market(
            outcomes=[
                _make_outcome(1, "Shai Gilgeous-Alexander", 0.55, last_updated=now),
                _make_outcome(2, "Nikola Jokic", 0.45, last_updated=now),
            ],
            updated_at=now,
        )
        current_card = _format_futures_for_search(market)
        current_search_entry = {
            "query": "mvp",
            "teams": [],
            "event_concepts": [],
            "results": [],
            "futures": [current_card],
            "futures_families": [],
            "pagination": {"page": 1, "per_page": 25, "total": 0, "total_pages": 0},
            "sports": [],
            "filters": {
                "sport": None,
                "tags": [],
                "days_back": 30,
                "include_upcoming": True,
            },
        }
        older_worker_search_entry = {
            **current_search_entry,
            "futures": [
                {
                    "id": market.id,
                    "name": "NBA MVP",
                    "status": "open",
                    "source": "polymarket",
                    "prices_updated_at": "2026-10-24T18:00:00+00:00",
                    "top_outcomes": [
                        {
                            "id": 1,
                            "name": "Victor Wembanyama",
                            "probability": 0.275,
                            "movement": 0.04,
                            "american_odds": 264,
                            "rank": 1,
                            "is_winner": False,
                            "resolution_source": None,
                        }
                    ],
                }
            ],
        }

        store: dict[str, str] = {}
        key = search_response_cache_key(q="mvp")
        rc = MagicMock()
        rc.get.side_effect = lambda k: store.get(k)

        with (
            patch("app.tasks.redis_state.get_redis_client", return_value=rc),
            patch.object(events_mod, "_record_search_query") as rec_mock,
            patch.object(
                events_mod,
                "attach_search_collections",
                new=AsyncMock(side_effect=lambda _db, hit: hit),
            ),
        ):
            # Step 1: Current server publishes attested entry; hit serves 0.55 / 55%.
            store[key] = json.dumps(current_search_entry)
            resp1 = Response()
            hit1 = await search_events(
                request=_http_request(),
                response=resp1,
                q="mvp",
                sport=None,
                tags=None,
                page=1,
                per_page=25,
                days_back=30,
                include_upcoming=True,
                debug_timing=False,
                db=AsyncMock(),
                current_user=None,
            )
            assert resp1.headers.get(SEARCH_CACHE_HEADER) == "hit"
            assert hit1["futures"][0]["top_outcomes"][0]["probability"] == 0.55
            assert hit1["futures"][0]["top_outcomes"][0]["rendered_percent"] == 55

            # Step 2: Older worker overwrites the same key with a legacy entry.
            store[key] = json.dumps(older_worker_search_entry)
            resp2 = Response()
            hit2 = await search_events(
                request=_http_request(),
                response=resp2,
                q="mvp",
                sport=None,
                tags=None,
                page=1,
                per_page=25,
                days_back=30,
                include_upcoming=True,
                debug_timing=False,
                db=AsyncMock(),
                current_user=None,
            )
            assert resp2.headers.get(SEARCH_CACHE_HEADER) == "hit"
            assert hit2["futures"][0]["id"] == market.id
            assert hit2["futures"][0]["name"] == "NBA MVP"
            assert hit2["futures"][0]["prices_updated_at"] is None
            leg = hit2["futures"][0]["top_outcomes"][0]
            assert leg["name"] == "Victor Wembanyama"
            assert leg["probability"] is None
            assert leg["rendered_percent"] is None
            assert leg["movement"] is None
            assert leg["is_winner"] is None
            assert leg["resolution_source"] is None
            assert rec_mock.call_count == 2


# ---------------------------------------------------------------------------
# 3. Outcome state matrix (null, 0.0, winners, losers, default false, missing
#    provenance, retracted, non-terminal CLOB, near-100%, result-only)
# ---------------------------------------------------------------------------


class TestOutcomeStateMatrix:
    def test_true_zero_probability_preserved_when_current_and_withheld_when_legacy(self):
        current_zero_row = {
            "id": 9001,
            "name": "Album of the Year",
            "status": "open",
            "source": "kalshi",
            "representation_policy": SEARCH_FUTURES_REPRESENTATION_POLICY,
            "top_outcomes": [
                {
                    "id": 1,
                    "name": "Longshot Artist",
                    "probability": 0.0,
                    "rendered_percent": 0,
                    "movement": 0.0,
                    "american_odds": None,
                    "rank": 1,
                    "is_winner": None,
                    "resolution_source": None,
                    "last_updated": "2026-10-24T18:00:00+00:00",
                    "price_changed_at": None,
                }
            ],
        }
        adapted_current = adapt_cached_futures_row(current_zero_row)
        assert adapted_current["top_outcomes"][0]["probability"] == 0.0
        assert adapted_current["top_outcomes"][0]["rendered_percent"] == 0

        legacy_zero_row = {
            "id": 9001,
            "name": "Album of the Year",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [
                {
                    "id": 1,
                    "name": "Longshot Artist",
                    "probability": 0.0,
                    "movement": 0.0,
                    "is_winner": False,
                    "resolution_source": None,
                }
            ],
        }
        adapted_legacy = adapt_cached_futures_row(legacy_zero_row)
        assert adapted_legacy["top_outcomes"][0]["probability"] is None
        assert adapted_legacy["top_outcomes"][0]["rendered_percent"] is None
        assert adapted_legacy["top_outcomes"][0]["is_winner"] is None

    def test_legacy_outcome_matrix_preserves_proven_results_and_suppresses_unproven(
        self,
    ):
        legacy_resolved_poly = {
            "id": 68149297,
            "name": "US Club Golf Championship",
            "status": "resolved",
            "source": "polymarket",
            "top_outcomes": [
                # 0: Confirmed authoritative winner without a prediction price
                {
                    "id": 10,
                    "name": "Jon Rahm",
                    "probability": None,
                    "is_winner": True,
                    "resolution_source": "api_settlement",
                },
                # 1: Confirmed terminal CLOB loser (0.0)
                {
                    "id": 11,
                    "name": "Scottie Scheffler",
                    "probability": 0.0,
                    "is_winner": False,
                    "resolution_source": "clob_authoritative",
                },
                # 2: Non-terminal Polymarket CLOB loser at 0.50 -> unknown
                {
                    "id": 12,
                    "name": "Bryson DeChambeau",
                    "probability": 0.50,
                    "is_winner": False,
                    "resolution_source": "clob_authoritative",
                },
                # 3: Default false (is_winner=False, resolution_source=None) -> cleared
                {
                    "id": 13,
                    "name": "Rory McIlroy",
                    "probability": 0.15,
                    "is_winner": False,
                    "resolution_source": None,
                },
                # 4: Missing provenance winner (is_winner=True, resolution_source=None) -> cleared
                {
                    "id": 14,
                    "name": "Collin Morikawa",
                    "probability": 1.0,
                    "is_winner": True,
                    "resolution_source": None,
                },
                # 5: Guess-family source (polymarket_yes_no_2leg) -> cleared
                {
                    "id": 15,
                    "name": "Xander Schauffele",
                    "probability": 0.99,
                    "is_winner": True,
                    "resolution_source": "polymarket_yes_no_2leg",
                },
                # 6: Retracted grade (ungradeable_result) -> unknown / retracted_grade
                {
                    "id": 16,
                    "name": "Viktor Hovland",
                    "probability": 1.0,
                    "is_winner": True,
                    "resolution_source": "ungradeable_result",
                },
                # 7: Live near-100% quote (0.995) without settlement provenance -> cleared
                {
                    "id": 17,
                    "name": "Ludvig Aberg",
                    "probability": 0.995,
                    "is_winner": False,
                    "resolution_source": None,
                },
            ],
        }
        adapted = adapt_cached_futures_row(legacy_resolved_poly)
        outcomes = adapted["top_outcomes"]

        # Every legacy outcome has prediction fields cleared:
        for o in outcomes:
            assert o["probability"] is None
            assert o["rendered_percent"] is None

        # 0: Priceless authoritative winner preserved
        assert outcomes[0]["name"] == "Jon Rahm"
        assert outcomes[0]["is_winner"] is True
        assert outcomes[0]["resolution_source"] == "api_settlement"

        # 1: Terminal CLOB loser preserved
        assert outcomes[1]["name"] == "Scottie Scheffler"
        assert outcomes[1]["is_winner"] is False
        assert outcomes[1]["resolution_source"] == "clob_authoritative"
        assert outcomes[1]["settlement_display"] == {
            "verdict": "lost",
            "basis": "stored_terminal_agreement",
        }

        # 2: Non-terminal 0.50 CLOB grade suppressed to unknown
        assert outcomes[2]["name"] == "Bryson DeChambeau"
        assert outcomes[2]["is_winner"] is None
        assert outcomes[2]["resolution_source"] == "clob_authoritative"
        assert outcomes[2]["settlement_display"] == {
            "verdict": "unknown",
            "basis": "nonterminal_stored_price",
        }

        # 3: Default false cleared
        assert outcomes[3]["name"] == "Rory McIlroy"
        assert outcomes[3]["is_winner"] is None
        assert outcomes[3]["resolution_source"] is None
        assert "settlement_display" not in outcomes[3]

        # 4: Missing provenance winner cleared
        assert outcomes[4]["name"] == "Collin Morikawa"
        assert outcomes[4]["is_winner"] is None
        assert outcomes[4]["resolution_source"] is None
        assert "settlement_display" not in outcomes[4]

        # 5: Guess-family source cleared
        assert outcomes[5]["name"] == "Xander Schauffele"
        assert outcomes[5]["is_winner"] is None
        assert outcomes[5]["resolution_source"] is None
        assert "settlement_display" not in outcomes[5]

        # 6: Retracted grade -> unknown / retracted_grade
        assert outcomes[6]["name"] == "Viktor Hovland"
        assert outcomes[6]["is_winner"] is None
        assert outcomes[6]["resolution_source"] == "ungradeable_result"
        assert outcomes[6]["settlement_display"] == {
            "verdict": "unknown",
            "basis": "retracted_grade",
        }

        # 7: Live near-100% quote -> cleared
        assert outcomes[7]["name"] == "Ludvig Aberg"
        assert outcomes[7]["is_winner"] is None
        assert outcomes[7]["resolution_source"] is None
        assert "settlement_display" not in outcomes[7]

    def test_open_market_legacy_entry_keeps_authoritative_winner_and_clears_open_loser(
        self,
    ):
        legacy_open = {
            "id": 113427,
            "name": "What will Fed Rate hit before 2027",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [
                {
                    "id": 1,
                    "name": "3.5%",
                    "probability": 1.0,
                    "is_winner": True,
                    "resolution_source": "api_settlement",
                },
                {
                    "id": 2,
                    "name": "5.5%",
                    "probability": 0.01,
                    "is_winner": False,
                    "resolution_source": "api_settlement",
                },
            ],
        }
        adapted = adapt_cached_futures_row(legacy_open)
        assert adapted["top_outcomes"][0]["probability"] is None
        assert adapted["top_outcomes"][0]["is_winner"] is True
        assert adapted["top_outcomes"][0]["resolution_source"] == "api_settlement"

        assert adapted["top_outcomes"][1]["probability"] is None
        assert adapted["top_outcomes"][1]["is_winner"] is None
        assert adapted["top_outcomes"][1]["resolution_source"] is None


# ---------------------------------------------------------------------------
# 4. Non-mutation, mixed/nested shapes, rendered_percent, and zero extra IO
# ---------------------------------------------------------------------------


class TestNonMutationAndMixedShapes:
    def test_adapters_do_not_mutate_nested_input_and_leave_non_futures_untouched(
        self,
    ):
        non_futures_event_with_top_outcomes = {
            "id": 555,
            "home_team_name": "Boston Celtics",
            "away_team_name": "New York Knicks",
            "status": "scheduled",
            "top_outcomes": [{"name": "Celtics", "probability": 0.64}],
        }
        non_futures_suggestion_with_top_outcomes = {
            "type": "team",
            "text": "Boston Celtics",
            "team_id": 12,
            "team_slug": "boston-celtics",
            "sport_key": "basketball_nba",
            "top_outcomes": [{"name": "10+ wins", "probability": 0.91}],
        }
        legacy_futures_suggestion = {
            "type": "futures",
            "text": "NBA MVP",
            "market_id": 66031970,
            "market_tier": 3,
            "status": "open",
            "market_type_label": "Award",
            "sport_key": "basketball",
            "top_outcomes": [
                {
                    "name": "Victor Wembanyama",
                    "probability": 0.275,
                    "movement": 0.04,
                    "is_winner": False,
                    "resolution_source": None,
                }
            ],
        }

        search_input = {
            "query": "celtics",
            "teams": [{"id": 12, "name": "Boston Celtics", "slug": "boston-celtics"}],
            "event_concepts": [
                {"key": "event:awards:nba-awards", "name": "NBA Awards"}
            ],
            "results": [non_futures_event_with_top_outcomes],
            "collections": [{"slug": "nba-tipoff", "title": "NBA Tip-Off"}],
            "futures": [
                {
                    "id": 66031970,
                    "name": "NBA MVP",
                    "status": "open",
                    "source": "polymarket",
                    "prices_updated_at": "2026-10-24T18:00:00+00:00",
                    "top_outcomes": [
                        {
                            "id": 101,
                            "name": "Victor Wembanyama",
                            "probability": 0.275,
                            "movement": 0.04,
                            "is_winner": False,
                            "resolution_source": None,
                        }
                    ],
                }
            ],
            "futures_families": [],
            "pagination": {"page": 1, "per_page": 25, "total": 1, "total_pages": 1},
            "sports": [{"key": "basketball_nba", "name": "NBA", "count": 1}],
            "filters": {
                "sport": None,
                "tags": [],
                "days_back": 30,
                "include_upcoming": True,
            },
        }
        search_snapshot = copy.deepcopy(search_input)
        search_out = adapt_cached_search_response(search_input)

        # Input was not mutated in place:
        assert search_input == search_snapshot
        assert search_input["futures"][0]["top_outcomes"][0]["probability"] == 0.275

        # Non-futures containers (including coincidental top_outcomes on game row) are untouched:
        assert search_out["results"] == search_snapshot["results"]
        assert search_out["teams"] == search_snapshot["teams"]
        assert search_out["event_concepts"] == search_snapshot["event_concepts"]
        assert search_out["collections"] == search_snapshot["collections"]
        assert search_out["pagination"] == search_snapshot["pagination"]
        assert search_out["sports"] == search_snapshot["sports"]
        assert search_out["filters"] == search_snapshot["filters"]

        # Futures card was adapted:
        assert search_out["futures"][0]["top_outcomes"][0]["probability"] is None
        assert search_out["futures"][0]["top_outcomes"][0]["rendered_percent"] is None

        ta_input = {
            "query": "celtics",
            "suggestions": [
                {"type": "hub", "text": "NBA Hub", "hub_key": "nba"},
                non_futures_suggestion_with_top_outcomes,
                {
                    "type": "event",
                    "text": "Knicks @ Celtics",
                    "event_id": 555,
                    "status": "scheduled",
                    "sport_key": "basketball_nba",
                },
                {
                    "type": "event_concept",
                    "text": "NBA Awards",
                    "event_key": "event:awards:nba-awards",
                    "sport_key": "awards",
                },
                legacy_futures_suggestion,
            ],
        }
        ta_snapshot = copy.deepcopy(ta_input)
        ta_out = adapt_cached_typeahead_response(ta_input)

        assert ta_input == ta_snapshot
        assert len(ta_out["suggestions"]) == 5
        assert ta_out["suggestions"][:4] == ta_snapshot["suggestions"][:4]
        assert ta_out["suggestions"][4]["market_id"] == 66031970
        assert ta_out["suggestions"][4]["text"] == "NBA MVP"
        assert ta_out["suggestions"][4]["top_outcomes"][0]["probability"] is None
        assert ta_out["suggestions"][4]["top_outcomes"][0]["rendered_percent"] is None

    def test_current_rendered_percent_preserved_and_legacy_never_recomputed_from_top_n(
        self,
    ):
        # On a 10-outcome board, top-3 probabilities 0.245, 0.1693, 0.12 would
        # sum to 0.5343 (46% / 32% / 22% if wrongly re-normalized from top-3).
        # Current whole-field rendered_percent (25, 17, 12) must be preserved
        # on current hits, and legacy hits must set rendered_percent=None.
        current_ta = {
            "query": "mvp",
            "suggestions": [
                {
                    "type": "futures",
                    "text": "NBA MVP",
                    "market_id": 66031970,
                    "market_tier": 3,
                    "status": "open",
                    "market_type_label": "Award",
                    "sport_key": "basketball",
                    "representation_policy": SEARCH_FUTURES_REPRESENTATION_POLICY,
                    "top_outcomes": [
                        {
                            "name": "Victor Wembanyama",
                            "probability": 0.245,
                            "rendered_percent": 25,
                            "movement": None,
                            "is_winner": None,
                            "resolution_source": None,
                            "last_updated": "2026-10-24T18:00:00+00:00",
                            "price_changed_at": None,
                        },
                        {
                            "name": "Shai Gilgeous-Alexander",
                            "probability": 0.1693,
                            "rendered_percent": 17,
                            "movement": None,
                            "is_winner": None,
                            "resolution_source": None,
                            "last_updated": "2026-10-24T18:00:00+00:00",
                            "price_changed_at": None,
                        },
                    ],
                }
            ],
        }
        adapted_current = adapt_cached_typeahead_response(current_ta)
        assert [
            o["rendered_percent"]
            for o in adapted_current["suggestions"][0]["top_outcomes"]
        ] == [25, 17]

        legacy_ta = copy.deepcopy(current_ta)
        legacy_ta["suggestions"][0].pop("representation_policy")
        for o in legacy_ta["suggestions"][0]["top_outcomes"]:
            o.pop("rendered_percent")
        adapted_legacy = adapt_cached_typeahead_response(legacy_ta)
        assert [
            o["rendered_percent"]
            for o in adapted_legacy["suggestions"][0]["top_outcomes"]
        ] == [None, None]
        assert [
            o["probability"]
            for o in adapted_legacy["suggestions"][0]["top_outcomes"]
        ] == [None, None]


# ---------------------------------------------------------------------------
# 5. #10225 warmer-retention pair (complete priced + complete result-only)
# ---------------------------------------------------------------------------


class TestWarmerRetention10225Compatibility:
    def test_complete_priced_and_complete_result_only_entries_retain_bytes_and_ttl_over_thinner_warmer(
        self,
    ):
        now = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
        priced_market = _make_market(
            outcomes=[
                _make_outcome(1, "Shai Gilgeous-Alexander", 0.55, last_updated=now),
                _make_outcome(2, "Nikola Jokic", 0.45, last_updated=now),
            ],
            updated_at=now,
        )
        result_only_market = _make_market(
            market_id=68149297,
            name="US Club Golf Championship",
            status="resolved",
            source="kalshi",
            outcomes=[
                _make_outcome(
                    10,
                    "Jon Rahm",
                    None,
                    is_winner=True,
                    resolution_source="api_settlement",
                    last_updated=now,
                ),
                _make_outcome(
                    11,
                    "Scottie Scheffler",
                    None,
                    is_winner=False,
                    resolution_source="api_settlement",
                    last_updated=now,
                ),
            ],
            updated_at=now,
        )

        for market in (priced_market, result_only_market):
            top = _build_search_top_outcomes(market, limit=3, lean=True)
            assert len(top) == 2
            complete_payload = {
                "query": "test",
                "suggestions": [
                    stamp_futures_representation_policy(
                        {
                            "type": "futures",
                            "text": market.name,
                            "market_id": market.id,
                            "market_tier": market.market_tier,
                            "status": market.status,
                            "market_type_label": "Award",
                            "sport_key": "basketball",
                            "top_outcomes": top,
                        }
                    )
                ],
            }
            complete_bytes = json.dumps(complete_payload)
            assert _typeahead_cached_body_is_complete(complete_bytes)

            thinner_bytes = json.dumps(
                {
                    "query": "test",
                    "suggestions": [],
                    "degraded": ["futures_outcome_arm_SHED"],
                }
            )
            assert not _typeahead_cached_body_is_complete(thinner_bytes)

            # Fake Redis backing store with TTL and #2311 compare-and-set eval:
            state = {"bytes": complete_bytes.encode("utf-8"), "ttl": 41}
            rc = MagicMock()
            rc.get.side_effect = lambda _k: state["bytes"]
            rc.setex.side_effect = lambda _k, ttl, body: state.update(
                bytes=body.encode("utf-8") if isinstance(body, str) else body,
                ttl=ttl,
            )

            def _eval(script, _numkeys, key, absent_only, expected, ttl, value):
                assert script is cache_mod._SETEX_IF_UNCHANGED_LUA
                cur = state["bytes"]
                exp_b = (
                    expected.encode("utf-8")
                    if isinstance(expected, str)
                    else expected
                )
                if absent_only == "1":
                    if cur is not None:
                        return 0
                elif cur != exp_b:
                    return 0
                rc.setex(key, int(ttl), value)
                return 1

            rc.eval.side_effect = _eval

            decision = _typeahead_publish_thinner(
                rc, "bainluck:typeahead:test", 65, thinner_bytes
            )
            assert decision == _TA_CACHE_RETAINED
            assert state["bytes"] == complete_bytes.encode("utf-8")
            assert state["ttl"] == 41  # TTL is NOT extended by retained thinner pass
            rc.setex.assert_not_called()

            # When slot is already thin, thinner warmer writes normally:
            state["bytes"] = thinner_bytes.encode("utf-8")
            decision2 = _typeahead_publish_thinner(
                rc, "bainluck:typeahead:test", 65, thinner_bytes
            )
            assert decision2 == _TA_CACHE_WRITTEN
            rc.setex.assert_called_once_with(
                "bainluck:typeahead:test", 65, thinner_bytes
            )

            # Ordinary fresh replacement (non-shed) overwrites with fresh attested bytes:
            rc.setex("bainluck:typeahead:test", 65, complete_bytes)
            assert state["bytes"] == complete_bytes.encode("utf-8")
            assert state["ttl"] == 65
            adapted_restored = adapt_cached_typeahead_response(
                json.loads(state["bytes"].decode("utf-8"))
            )
            assert adapted_restored == complete_payload


# ---------------------------------------------------------------------------
# 6. Route-level fallback, force-rebuild, debug bypass, and single-count hit IO
# ---------------------------------------------------------------------------


class _BypassStop(Exception):
    """Sentinel raised at the first DB query after the cache-hit branch."""


class TestRouteFallbackBypassAndSingleCount:
    @pytest.mark.asyncio
    async def test_typeahead_hit_makes_no_db_calls_and_records_trending_once(self):
        legacy_ta = {
            "query": "mvp",
            "suggestions": [
                {
                    "type": "futures",
                    "text": "NBA MVP",
                    "market_id": 66031970,
                    "market_tier": 3,
                    "status": "open",
                    "market_type_label": "Award",
                    "sport_key": "basketball",
                    "top_outcomes": [
                        {
                            "name": "Victor Wembanyama",
                            "probability": 0.275,
                            "movement": 0.04,
                            "is_winner": False,
                            "resolution_source": None,
                        }
                    ],
                }
            ],
        }
        rc = MagicMock()
        rc.get.return_value = json.dumps(legacy_ta)
        db = AsyncMock()
        db.execute.side_effect = AssertionError("DB must not be queried on cache hit")

        with (
            patch("app.tasks.redis_state.get_redis_client", return_value=rc),
            patch.object(events_mod, "_record_trending") as trend_mock,
        ):
            out = await typeahead_search(
                q="mvp",
                debug_evidence=False,
                debug_timing=False,
                db=db,
            )

        assert rc.get.call_count == 1
        trend_mock.assert_called_once_with("mvp")
        db.execute.assert_not_called()
        assert out["suggestions"][0]["market_id"] == 66031970
        assert out["suggestions"][0]["top_outcomes"][0]["probability"] is None
        assert out["suggestions"][0]["top_outcomes"][0]["rendered_percent"] is None
        assert out["suggestions"][0]["top_outcomes"][0]["is_winner"] is None

    @pytest.mark.asyncio
    async def test_corrupt_cache_or_force_rebuild_or_debug_bypasses_hit_cleanly(self):
        db = AsyncMock()
        db.execute.side_effect = _BypassStop("reached cold build")

        # 1. Corrupt JSON in `/search` falls through to cold build (header = "miss"):
        rc_corrupt = MagicMock()
        rc_corrupt.get.return_value = "{not-valid-json"
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc_corrupt):
            resp = Response()
            with pytest.raises(_BypassStop):
                await search_events(
                    request=_http_request(),
                    response=resp,
                    q="mvp",
                    sport=None,
                    tags=None,
                    page=1,
                    per_page=25,
                    days_back=30,
                    include_upcoming=True,
                    debug_timing=False,
                    db=db,
                    current_user=None,
                )
            assert resp.headers.get(SEARCH_CACHE_HEADER) == "miss"

        # 2. `_force_search_cache_rebuild` and `debug_timing=True` bypass `/search` cache read:
        rc_populated = MagicMock()
        rc_populated.get.return_value = json.dumps({"query": "mvp", "futures": []})
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc_populated):
            resp_dbg = Response()
            with pytest.raises(_BypassStop):
                await search_events(
                    request=_http_request(),
                    response=resp_dbg,
                    q="mvp",
                    sport=None,
                    tags=None,
                    page=1,
                    per_page=25,
                    days_back=30,
                    include_upcoming=True,
                    debug_timing=True,
                    db=db,
                    current_user=None,
                )
            assert resp_dbg.headers.get(SEARCH_CACHE_HEADER) == "bypass"
            rc_populated.get.assert_not_called()

            token = _force_search_cache_rebuild.set(True)
            try:
                resp_force = Response()
                with pytest.raises(_BypassStop):
                    await search_events(
                        request=_http_request(),
                        response=resp_force,
                        q="mvp",
                        sport=None,
                        tags=None,
                        page=1,
                        per_page=25,
                        days_back=30,
                        include_upcoming=True,
                        debug_timing=False,
                        db=db,
                        current_user=None,
                    )
                assert resp_force.headers.get(SEARCH_CACHE_HEADER) == "bypass"
                rc_populated.get.assert_not_called()
            finally:
                _force_search_cache_rebuild.reset(token)

        # 3. Corrupt JSON, `debug_timing`, `debug_evidence`, and `_force_cache_rebuild` on `/typeahead`:
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc_corrupt):
            with pytest.raises(_BypassStop):
                await typeahead_search(
                    q="mvp",
                    debug_evidence=False,
                    debug_timing=False,
                    db=db,
                )

        with patch("app.tasks.redis_state.get_redis_client", return_value=rc_populated):
            with pytest.raises(_BypassStop):
                await typeahead_search(
                    q="mvp",
                    debug_evidence=True,
                    debug_timing=False,
                    db=db,
                )
            with pytest.raises(_BypassStop):
                await typeahead_search(
                    q="mvp",
                    debug_evidence=False,
                    debug_timing=True,
                    db=db,
                )
            ta_token = _force_cache_rebuild.set(True)
            try:
                with pytest.raises(_BypassStop):
                    await typeahead_search(
                        q="mvp",
                        debug_evidence=False,
                        debug_timing=False,
                        db=db,
                    )
            finally:
                _force_cache_rebuild.reset(ta_token)
            rc_populated.get.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Same-input parity vs genuine newer observation
# ---------------------------------------------------------------------------


class TestSameInputParityVsNewerObservation:
    def test_same_input_revision_matches_detail_while_newer_observation_is_distinguishable(
        self,
    ):
        t0 = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
        market_t0 = _make_market(
            outcomes=[
                _make_outcome(
                    1,
                    "Shai Gilgeous-Alexander",
                    0.55,
                    probability_change_24h=0.02,
                    opening_probability=0.45,
                    american_odds=-122,
                    rank=1,
                    last_updated=t0,
                    price_changed_at=t0,
                ),
                _make_outcome(
                    2,
                    "Nikola Jokic",
                    0.45,
                    probability_change_24h=-0.02,
                    opening_probability=0.55,
                    american_odds=122,
                    rank=2,
                    last_updated=t0,
                    price_changed_at=t0,
                ),
            ],
            updated_at=t0,
        )

        # At t0, cached search card, cached typeahead row, and detail page agree:
        with patch.object(events_mod, "_search_today_ymd", return_value="20261024"):
            search_card_t0 = adapt_cached_futures_row(_format_futures_for_search(market_t0))
            ta_outcomes_t0 = _build_search_top_outcomes(market_t0, limit=3, lean=True)
            ta_row_t0 = adapt_cached_futures_row(
                stamp_futures_representation_policy(
                    {
                        "type": "futures",
                        "text": market_t0.name,
                        "market_id": market_t0.id,
                        "status": market_t0.status,
                        "top_outcomes": ta_outcomes_t0,
                    }
                )
            )
        detail_t0 = _format_market_detail(market_t0)
        detail_by_name_t0 = {o["name"]: o for o in detail_t0["outcomes"]}

        for s_leg in search_card_t0["top_outcomes"]:
            d_leg = detail_by_name_t0[s_leg["name"]]
            assert s_leg["probability"] == d_leg["probability"]
            assert s_leg["rendered_percent"] == d_leg["rendered_percent"]
            assert s_leg["movement"] == d_leg["probability_change_24h"]
            assert s_leg["is_winner"] == d_leg["is_winner"]
            assert s_leg["resolution_source"] == d_leg["resolution_source"]
            assert s_leg["last_updated"] == d_leg["last_updated"]

        for ta_leg in ta_row_t0["top_outcomes"]:
            d_leg = detail_by_name_t0[ta_leg["name"]]
            assert ta_leg["probability"] == d_leg["probability"]
            assert ta_leg["rendered_percent"] == d_leg["rendered_percent"]
            assert ta_leg["last_updated"] == d_leg["last_updated"]

        # At t1 = t0 + 2 minutes, a genuine live trade moves SGA to 0.62:
        t1 = t0 + timedelta(minutes=2)
        market_t1 = _make_market(
            outcomes=[
                _make_outcome(
                    1,
                    "Shai Gilgeous-Alexander",
                    0.62,
                    probability_change_24h=0.09,
                    opening_probability=0.45,
                    american_odds=-163,
                    rank=1,
                    last_updated=t1,
                    price_changed_at=t1,
                ),
                _make_outcome(
                    2,
                    "Nikola Jokic",
                    0.38,
                    probability_change_24h=-0.09,
                    opening_probability=0.55,
                    american_odds=163,
                    rank=2,
                    last_updated=t1,
                    price_changed_at=t1,
                ),
            ],
            updated_at=t1,
        )
        detail_t1 = _format_market_detail(market_t1)
        sga_cached = search_card_t0["top_outcomes"][0]
        sga_detail_t1 = detail_t1["outcomes"][0]

        # The difference (0.55 vs 0.62) is explained by a strictly newer
        # observation timestamp (`last_updated` and `prices_updated_at`), not a
        # same-input representation bug:
        assert sga_cached["probability"] == 0.55
        assert sga_detail_t1["probability"] == 0.62
        assert sga_cached["last_updated"] < sga_detail_t1["last_updated"]
        assert search_card_t0["prices_updated_at"] < detail_t1["updated_at"]
