"""Tests for the ``same_deadline_board`` round-up producer kind and the
``by-november-30`` and ``by-december-31`` definitions (``docs/discover/grouping-types-2026-11.md`` §1.6).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from app.routes.containers import get_container
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    ROUNDUP_SEAT_FLOOR,
    RoundupMembers,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    evaluate_roundup_producer,
    insert_roundup_feed_items,
    reset_roundup_cache_for_tests,
    roundup_feed_items,
    roundup_revision,
)
from app.utils.same_deadline_board import (
    BY_DECEMBER_31_DEFINITION,
    BY_DECEMBER_31_DEFINITION_PATH,
    BY_DECEMBER_31_PRODUCER,
    BY_DECEMBER_31_SLUG,
    BY_NOVEMBER_30_DEFINITION,
    BY_NOVEMBER_30_DEFINITION_PATH,
    BY_NOVEMBER_30_PRODUCER,
    BY_NOVEMBER_30_SLUG,
    EXCLUDED_CLASSES,
    PRODUCER_KIND_SAME_DEADLINE_BOARD,
    build_same_deadline_board_producer,
    by_december_31_enabled,
    by_november_30_enabled,
    load_same_deadline_board_definition,
    produce_same_deadline_board,
    same_deadline_board_enabled,
    select_same_deadline_board,
    strip_deadline_framing,
)

FIXED_NOW = datetime(2026, 11, 3, 23, 0, 0, tzinfo=timezone.utc)
FIXED_OBSERVED = "2026-11-03T22:30:00+00:00"


def _make_binary_market(
    market_id: int,
    name: str,
    probability: float | None,
    *,
    category: str = "tech",
    resolution_date: str = "2026-12-31T23:59:00+00:00",
    source: str = "polymarket",
    status: str = "open",
    market_type: str = "yes_no",
    group_id: str | None = None,
    template_key: str | None = None,
    claim_key: str | None = None,
    subject_key: str | None = None,
    excluded_class: str | None = None,
    is_winner: bool | None = None,
    resolution_source: str | None = None,
) -> dict[str, Any]:
    yes_oid = market_id * 10 + 1
    no_oid = market_id * 10 + 2
    no_prob = (
        round(1.0 - probability, 6)
        if isinstance(probability, (int, float)) and probability is not None
        else None
    )
    entry: dict[str, Any] = {
        "id": market_id,
        "external_id": f"ext-{market_id}",
        "name": name,
        "source": source,
        "status": status,
        "mutually_exclusive": True,
        "market_tier": 2,
        "market_type": market_type,
        "category": category,
        "llm_sport_category": category,
        "resolution_date": resolution_date,
        "updated_at": FIXED_OBSERVED,
        "prices_updated_at": FIXED_OBSERVED,
        "outcomes": [
            {
                "id": yes_oid,
                "name": "Yes",
                "probability": probability,
                "movement": 0.02,
                "last_updated": FIXED_OBSERVED,
                "is_winner": is_winner,
                "resolution_source": resolution_source,
            },
            {
                "id": no_oid,
                "name": "No",
                "probability": no_prob,
                "movement": -0.02,
                "last_updated": FIXED_OBSERVED,
                "is_winner": None,
                "resolution_source": None,
            },
        ],
    }
    if group_id is not None:
        entry["group_id"] = group_id
    if template_key is not None:
        entry["template_key"] = template_key
    if claim_key is not None:
        entry["claim_key"] = claim_key
    if subject_key is not None:
        entry["subject_key"] = subject_key
    if excluded_class is not None:
        entry["excluded_class"] = excluded_class
    return entry


def _live_december_31_markets() -> list[dict[str, Any]]:
    """Today's live markets for ``by-december-31`` (§1.6 & live API read 2026-11-03)."""
    return [
        _make_binary_market(
            62162058,
            "Next Claude Opus (5.6+) released by December 31, 2026?",
            0.885,
            category="tech",
            resolution_date="2027-01-01T04:59:00+00:00",
        ),
        _make_binary_market(
            27594137,
            "Trump meets with Putin by December 31?",
            0.83,
            category="politics",
            resolution_date="2026-12-31T23:59:00+00:00",
        ),
        _make_binary_market(
            30587891,
            "Will Banksy create a new mural or street artwork by December 31?",
            0.47,
            category="entertainment",
            resolution_date="2026-12-31T23:59:00+00:00",
        ),
        _make_binary_market(
            8422080,
            "Pete Hegseth out as Secretary of Defense by December 31?",
            0.40,
            category="geopolitics",
            resolution_date="2026-12-31T23:59:00+00:00",
        ),
        _make_binary_market(
            13791228,
            "SCOTUS accepts sports event contract case by December 31, 2026?",
            0.205,
            category="legal",
            resolution_date="2027-01-01T04:59:00+00:00",
        ),
        _make_binary_market(
            13794660,
            "Will Samuel Alito announce his retirement by December 31, 2026?",
            0.185,
            category="politics",
            resolution_date="2027-01-01T04:59:00+00:00",
        ),
    ]


def _live_november_30_markets() -> list[dict[str, Any]]:
    """Today's live markets for ``by-november-30`` (§1.6 & live API read 2026-11-03)."""
    return [
        _make_binary_market(
            61341170,
            "Will Anthropic IPO by November 30, 2026?",
            0.855,
            category="economics",
            resolution_date="2026-12-01T04:59:00+00:00",
        ),
        _make_binary_market(
            62611724,
            "Trump meets with Putin by November 30?",
            0.835,
            category="politics",
            resolution_date="2026-11-30T23:59:00+00:00",
        ),
        _make_binary_market(
            68320839,
            "Will a 7.0+ earthquake occur worldwide by November 30?",
            0.66,
            category="weather",
            resolution_date="2026-11-30T23:59:00+00:00",
        ),
        _make_binary_market(
            62141888,
            "Next Claude Opus (5.6+) released by November 30, 2026?",
            0.595,
            category="tech",
            resolution_date="2026-12-01T04:59:00+00:00",
        ),
        _make_binary_market(
            63889649,
            "Will Valve add sticker trade-ups by November 30, 2026?",
            0.495,
            category="esports",
            resolution_date="2026-12-01T04:59:00+00:00",
        ),
        _make_binary_market(
            66907859,
            "Another GTA VI trailer released by November 30?",
            0.17,
            category="entertainment",
            resolution_date="2026-11-30T23:59:00+00:00",
        ),
        # Moved to 4.8% (< 5%) on 2026-11-03 evening; refused as out_of_band when < 0.05.
        _make_binary_market(
            63790740,
            "Will Novak Djokovic announce his retirement by November 30, 2026?",
            0.048,
            category="tennis",
            resolution_date="2026-12-01T04:59:00+00:00",
        ),
    ]


class TestStoredDefinitionsAndRegistry:
    def test_both_stored_definitions_match_catalog_contract(self) -> None:
        dec31 = load_same_deadline_board_definition(BY_DECEMBER_31_DEFINITION_PATH)
        assert dec31 == BY_DECEMBER_31_DEFINITION
        assert dec31["slug"] == "by-december-31"
        assert dec31["membership"] == "computed-produced"
        assert dec31["kind"] == "roundup"
        assert dec31["kicker"] == "SAME DEADLINE"
        assert dec31["name"] == "By December 31"
        assert dec31["category"] == "cross-topic"
        assert dec31["tag"] == ""
        assert dec31["footer"] == "Separate markets that settle by the same day."
        assert dec31["rule"]["producer"] == PRODUCER_KIND_SAME_DEADLINE_BOARD
        assert dec31["rule"]["deadline"] == "2026-12-31"
        assert dec31["rule"]["deadline_phrase"] == "by December 31"
        assert dec31["rule"]["min_members"] == 4
        assert dec31["rule"]["max_members"] == 6
        assert dec31["rule"]["card_rows"] == 5
        assert dec31["rule"]["min_categories"] == 3
        assert dec31["rule"]["band"] == [0.05, 0.95]

        nov30 = load_same_deadline_board_definition(BY_NOVEMBER_30_DEFINITION_PATH)
        assert nov30 == BY_NOVEMBER_30_DEFINITION
        assert nov30["slug"] == "by-november-30"
        assert nov30["membership"] == "computed-produced"
        assert nov30["kind"] == "roundup"
        assert nov30["kicker"] == "SAME DEADLINE"
        assert nov30["name"] == "By November 30"
        assert nov30["category"] == "cross-topic"
        assert nov30["tag"] == ""
        assert nov30["footer"] == "Separate markets that settle by the same day."
        assert nov30["rule"]["producer"] == PRODUCER_KIND_SAME_DEADLINE_BOARD
        assert nov30["rule"]["deadline"] == "2026-11-30"
        assert nov30["rule"]["deadline_phrase"] == "by November 30"

    def test_registered_in_roundup_producers(self) -> None:
        assert ROUNDUP_PRODUCERS.get(BY_NOVEMBER_30_SLUG) is BY_NOVEMBER_30_PRODUCER
        assert ROUNDUP_PRODUCERS.get(BY_DECEMBER_31_SLUG) is BY_DECEMBER_31_PRODUCER
        assert BY_DECEMBER_31_PRODUCER.kicker == "SAME DEADLINE"
        assert BY_DECEMBER_31_PRODUCER.tag == ""
        assert BY_NOVEMBER_30_PRODUCER.kicker == "SAME DEADLINE"
        assert BY_NOVEMBER_30_PRODUCER.tag == ""

    def test_narrative_copy_rejects_venue_names_and_question_word(self) -> None:
        bad = {
            **BY_DECEMBER_31_DEFINITION,
            "footer": "Polymarket questions that settle by the same day.",
        }
        with pytest.raises(ValueError, match="Forbidden token"):
            build_same_deadline_board_producer(bad)

    def test_feature_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert same_deadline_board_enabled() is True
        assert by_november_30_enabled() is True
        assert by_december_31_enabled() is True

        monkeypatch.setenv("BY_NOVEMBER_30_ENABLED", "false")
        assert by_november_30_enabled() is False
        assert by_december_31_enabled() is True

        monkeypatch.setenv("SAME_DEADLINE_BOARD_ENABLED", "0")
        assert by_december_31_enabled() is False


class TestDeadlineFramingAndMemberRule:
    def test_strip_deadline_framing_preserves_market_words_and_drops_will_and_by_date(
        self,
    ) -> None:
        assert (
            strip_deadline_framing(
                "Next Claude Opus (5.6+) released by December 31, 2026?",
                deadline_phrase="by December 31",
                year=2026,
            )
            == "Next Claude Opus (5.6+) released"
        )
        assert (
            strip_deadline_framing(
                "Trump meets with Putin by December 31?",
                deadline_phrase="by December 31",
                year=2026,
            )
            == "Trump meets with Putin"
        )
        assert (
            strip_deadline_framing(
                "Will Banksy create a new mural or street artwork by December 31?",
                deadline_phrase="by December 31",
                year=2026,
            )
            == "Will Banksy create a new mural or street artwork?"
        )
        assert (
            strip_deadline_framing(
                "Will a 7.0+ earthquake occur worldwide by November 30?",
                deadline_phrase="by November 30",
                year=2026,
            )
            == "Will a 7.0+ earthquake occur worldwide?"
        )

    @pytest.mark.parametrize(
        "bad_title",
        [
            "Government shutdown on December 31, 2026?",
            "US recession in 2026?",
            "SpaceX Starship fully reusable before 2027?",
            "Next Claude Opus released prior to 2027?",
            "Trump meets with Putin by December 31, 2027?",
            "Trump meets with Putin by November 30?",
        ],
    )
    def test_strip_deadline_framing_refuses_non_matching_wording(
        self, bad_title: str
    ) -> None:
        assert (
            strip_deadline_framing(
                bad_title,
                deadline_phrase="by December 31",
                year=2026,
            )
            is None
        )


class TestLiveDefinitionsMakeCardsToday:
    @pytest.mark.asyncio
    async def test_by_december_31_makes_card_and_container_from_todays_data(
        self,
    ) -> None:
        markets = _live_december_31_markets()
        # Include §1.6's "SpaceX Starship fully reusable before 2027?" (113322) to prove
        # strict wording refuses "before 2027?" while the 6 "by December 31" markets build the board.
        markets.append(
            _make_binary_market(
                113322,
                "SpaceX Starship fully reusable before 2027?",
                0.44,
                category="tech",
                resolution_date="2026-12-31T23:59:00+00:00",
            )
        )

        outcome = await produce_same_deadline_board(
            markets,
            definition=BY_DECEMBER_31_DEFINITION,
            now=FIXED_NOW,
        )
        assert isinstance(outcome, RoundupMembers)
        assert len(outcome.members) == 6
        assert len(outcome.rows) == 5
        assert outcome.count_line == "Showing 5 of 6"

        assert [r["market_id"] for r in outcome.rows] == [
            62162058,
            27594137,
            30587891,
            8422080,
            13791228,
        ]
        assert [r["label"] for r in outcome.rows] == [
            "Next Claude Opus (5.6+) released",
            "Trump meets with Putin",
            "Will Banksy create a new mural or street artwork?",
            "Pete Hegseth out as Secretary of Defense",
            "SCOTUS accepts sports event contract case",
        ]
        assert [r["probability"] for r in outcome.rows] == [
            0.885,
            0.83,
            0.47,
            0.40,
            0.205,
        ]

        feed_item = compose_roundup_feed_item(BY_DECEMBER_31_PRODUCER, outcome)
        container = compose_roundup_container(BY_DECEMBER_31_PRODUCER, outcome)
        assert feed_item is not None and container is not None

        assert feed_item["data"]["title"] == "By December 31"
        assert feed_item["data"]["collection_ref"] == {
            "slug": "by-december-31",
            "href": "/collections/by-december-31",
            "name": "By December 31",
            "revision": roundup_revision(
                [62162058, 27594137, 30587891, 8422080, 13791228, 13794660]
            ),
            "collection_count": 6,
        }
        roundup = feed_item["data"]["roundup"]
        assert roundup["kicker"] == "SAME DEADLINE"
        assert roundup["tag"] is None
        assert roundup["count_line"] == "Showing 5 of 6"
        assert roundup["footer"] == "Separate markets that settle by the same day."
        assert len(roundup["rows"]) == 5

        assert container["state"] == "published"
        assert container["slug"] == "by-december-31"
        assert container["member_count"] == 6
        assert container["subtitle"] == "Separate markets that settle by the same day."
        sec = container["sections"][0]
        assert sec["title"] == "Markets settling by December 31"
        assert sec["count"] == 6
        assert [m["id"] for m in sec["members"]] == [
            62162058,
            27594137,
            30587891,
            8422080,
            13791228,
            13794660,
        ]
        # Single-venue attribution on the container cards, never claiming a 2-source blend
        for m in sec["members"]:
            assert m["card"]["source"] == "polymarket"
            assert m["card"]["sources"] == ["polymarket"]
            assert m["card"]["source_count"] == 1
            assert m["card"]["top_outcomes"][0]["name"] == "Yes"

    @pytest.mark.asyncio
    async def test_by_november_30_makes_card_and_container_from_todays_data(
        self,
    ) -> None:
        markets = _live_november_30_markets()
        outcome = await produce_same_deadline_board(
            markets,
            definition=BY_NOVEMBER_30_DEFINITION,
            now=FIXED_NOW,
        )
        assert isinstance(outcome, RoundupMembers)
        assert len(outcome.members) == 6
        assert len(outcome.rows) == 5
        assert outcome.count_line == "Showing 5 of 6"

        assert [r["market_id"] for r in outcome.rows] == [
            61341170,
            62611724,
            68320839,
            62141888,
            63889649,
        ]
        assert [r["label"] for r in outcome.rows] == [
            "Will Anthropic IPO?",
            "Trump meets with Putin",
            "Will a 7.0+ earthquake occur worldwide?",
            "Next Claude Opus (5.6+) released",
            "Will Valve add sticker trade-ups?",
        ]
        assert [m["id"] for m in outcome.members] == [
            61341170,
            62611724,
            68320839,
            62141888,
            63889649,
            66907859,
        ]

    @pytest.mark.asyncio
    async def test_pool_market_not_in_candidates_makes_the_board(self) -> None:
        # Take only the first 4 priority candidates from December 31 and add two pool markets
        # whose IDs are NOT in BY_DECEMBER_31_DEFINITION["rule"]["candidates"].
        pool_market_science = _make_binary_market(
            990001,
            "Will NASA Artemis II launch by December 31, 2026?",
            0.64,
            category="science",
            resolution_date="2026-12-31T23:59:00+00:00",
            market_type="container_member",
        )
        pool_market_sports = _make_binary_market(
            990002,
            "FIFA confirms 2030 World Cup final venue by December 31?",
            0.31,
            category="soccer",
            resolution_date="2026-12-31T23:59:00+00:00",
            market_type="unshaped",
        )
        priority_subset = _live_december_31_markets()[:4]

        class _FakeScalars:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def unique(self) -> "_FakeScalars":
                return self

            def all(self) -> list[Any]:
                return list(self._rows)

        class _FakeResult:
            def __init__(self, *, pairs: list[tuple[int, str]] | None = None, rows: list[Any] | None = None) -> None:
                self._pairs = pairs or []
                self._rows = rows or []

            def all(self) -> list[tuple[int, str]]:
                return list(self._pairs)

            def scalars(self) -> _FakeScalars:
                return _FakeScalars(self._rows)

        all_pool_markets = priority_subset + [pool_market_science, pool_market_sports]

        class _FakeDb:
            def __init__(self) -> None:
                self.calls = 0

            async def execute(self, _stmt: Any) -> _FakeResult:
                self.calls += 1
                if self.calls == 1:
                    # Pool scan returns (id, name) pairs including the two non-candidate pool markets
                    return _FakeResult(
                        pairs=[(int(m["id"]), str(m["name"])) for m in all_pool_markets]
                    )
                # Hydration returns full market mappings for matched IDs
                return _FakeResult(rows=all_pool_markets)

        fake_db = _FakeDb()
        outcome = await produce_same_deadline_board(
            fake_db,
            definition=BY_DECEMBER_31_DEFINITION,
            now=FIXED_NOW,
        )
        assert fake_db.calls == 2
        assert isinstance(outcome, RoundupMembers)
        selected_ids = [m["id"] for m in outcome.members]
        assert 990001 in selected_ids
        assert 990002 in selected_ids
        # Ordered highest probability first across priority + pool members
        assert [r["market_id"] for r in outcome.rows] == [
            62162058,  # 88.5%
            27594137,  # 83.0%
            990001,    # 64.0% (pool market, not in candidates!)
            30587891,  # 47.0%
            8422080,   # 40.0%
        ]
        assert outcome.rows[2]["label"] == "Will NASA Artemis II launch?"


class TestRefusalRules:
    def test_refuses_when_fewer_than_four_members_qualify(self) -> None:
        markets = _live_december_31_markets()[:3]
        res = select_same_deadline_board(
            markets,
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("board", "too_few_members_3_below_4") in res.reasons

    def test_refuses_when_fewer_than_three_categories_represented(self) -> None:
        # Four valid markets across only 2 categories (politics and tech) -> refuses whole card.
        markets = [
            _make_binary_market(
                1,
                "Next Claude Opus (5.6+) released by December 31, 2026?",
                0.88,
                category="tech",
            ),
            _make_binary_market(
                2,
                "Trump meets with Putin by December 31?",
                0.83,
                category="politics",
            ),
            _make_binary_market(
                3,
                "Will Samuel Alito announce his retirement by December 31, 2026?",
                0.45,
                category="politics",
            ),
            _make_binary_market(
                4,
                "Will any AI model reach a Chatbot Arena score of at least 1550 by December 31?",
                0.35,
                category="tech",
            ),
        ]
        res = select_same_deadline_board(
            markets,
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("board", "too_few_categories_2_below_3") in res.reasons

    def test_refuses_stored_date_disagreement_and_past_deadline(self) -> None:
        markets = _live_december_31_markets()[:3] + [
            # Title says "by December 31" but stored date is Dec 15 -> refused as stored_date_mismatch
            _make_binary_market(
                901,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                0.40,
                category="geopolitics",
                resolution_date="2026-12-15T23:59:00+00:00",
            ),
            # Stored date already in the past relative to FIXED_NOW
            _make_binary_market(
                902,
                "SCOTUS accepts sports event contract case by December 31, 2026?",
                0.20,
                category="legal",
                resolution_date="2026-11-01T12:00:00+00:00",
            ),
        ]
        res = select_same_deadline_board(
            markets,
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("member", 901, "stored_date_mismatch") in res.reasons
        assert ("member", 902, "past_deadline") in res.reasons

        # Whole board past its deadline
        future_now = datetime(2027, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        res_past_board = select_same_deadline_board(
            _live_december_31_markets(),
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=future_now,
        )
        assert isinstance(res_past_board, RoundupRefusal)
        assert ("board", "past_deadline") in res_past_board.reasons

    def test_refuses_missing_probability_out_of_band_and_withheld(self) -> None:
        base3 = _live_december_31_markets()[:3]
        extras = [
            _make_binary_market(
                801,
                "Pete Hegseth out as Secretary of Defense by December 31?",
                None,
                category="geopolitics",
            ),
            _make_binary_market(
                802,
                "SCOTUS accepts sports event contract case by December 31, 2026?",
                0.04,
                category="legal",
            ),
            _make_binary_market(
                803,
                "Will France pass a national budget by December 31?",
                0.96,
                category="economics",
            ),
            _make_binary_market(
                804,
                "X banned in any European country by December 31?",
                0.25,
                category="culture",
            ),
        ]
        res = select_same_deadline_board(
            base3 + extras,
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
            withheld_by_market={804: {804 * 10 + 1}},
        )
        assert isinstance(res, RoundupRefusal)
        assert ("member", 801, "missing_probability") in res.reasons
        assert ("member", 802, "out_of_band") in res.reasons
        assert ("member", 803, "out_of_band") in res.reasons
        assert ("member", 804, f"withheld_price_{804 * 10 + 1}") in res.reasons

    @pytest.mark.parametrize(
        "expected_class,title,category,market_type",
        [
            (
                "mention",
                "Will Trump mention tariffs by December 31?",
                "politics",
                "yes_no",
            ),
            (
                "statement",
                "Will Powell say inflation in his press conference by December 31?",
                "economics",
                "yes_no",
            ),
            (
                "daily",
                "Will gold close above $2800 in the 15-minute window by December 31?",
                "economics",
                "yes_no",
            ),
            (
                "financial",
                "Will Bitcoin reach $150,000 by December 31?",
                "crypto",
                "yes_no",
            ),
            (
                "combination",
                "Will both Democrats win the House and Republicans win the Senate by December 31?",
                "politics",
                "yes_no",
            ),
            (
                "path",
                "If ceasefire is signed, then sanctions lifted by December 31?",
                "geopolitics",
                "yes_no",
            ),
            (
                "foreign_election",
                "Will Macron call a French parliamentary election by December 31?",
                "politics",
                "yes_no",
            ),
            (
                "person_harm",
                "Will Senator X be indicted or arrested by December 31?",
                "legal",
                "yes_no",
            ),
        ],
    )
    def test_refuses_every_excluded_class(
        self,
        expected_class: str,
        title: str,
        category: str,
        market_type: str,
    ) -> None:
        assert expected_class in EXCLUDED_CLASSES
        base3 = _live_december_31_markets()[:3]
        bad_member = _make_binary_market(
            700,
            title,
            0.50,
            category=category,
            market_type=market_type,
        )
        res = select_same_deadline_board(
            [*base3, bad_member],
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("member", 700, f"excluded_class:{expected_class}") in res.reasons

    def test_enforces_one_per_template_one_per_claim_one_per_story_and_refuses_overlapping_subjects(
        self,
    ) -> None:
        base3 = _live_december_31_markets()[:3]
        # 1) Duplicate claim: two markets asking the same thing about Trump meeting Putin
        dup_claim = _make_binary_market(
            601,
            "Will Trump meets with Putin by December 31, 2026?",
            0.82,
            category="geopolitics",
        )
        # 2) Duplicate template: two retirement markets ("announce his/her retirement")
        retire_1 = _make_binary_market(
            602,
            "Will Samuel Alito announce his retirement by December 31, 2026?",
            0.22,
            category="legal",
        )
        retire_2 = _make_binary_market(
            603,
            "Will Clarence Thomas announce his retirement by December 31, 2026?",
            0.18,
            category="legal",
        )
        # 3) Duplicate story: shares group_id with retire_1
        same_story = _make_binary_market(
            604,
            "SCOTUS accepts sports event contract case by December 31, 2026?",
            0.20,
            category="legal",
            group_id="polymarket:scotus-2026",
        )
        retire_1["group_id"] = "polymarket:scotus-2026"
        # 4) Overlapping row subject (decision D): shares subject "Trump" with 27594137 ("Trump meets with Putin")
        overlapping_trump = _make_binary_market(
            605,
            "Trump visits Beijing by December 31?",
            0.35,
            category="geopolitics",
        )

        # With base3 (3 markets) + retire_1 (4th market), all conflicts (601, 603, 604, 605) are refused;
        # if we drop retire_1's category to match base3 or only pass 2 base markets, the whole board refuses
        # and records every conflict reason.
        res = select_same_deadline_board(
            [
                *base3[:2],
                dup_claim,
                retire_1,
                retire_2,
                same_story,
                overlapping_trump,
            ],
            deadline="2026-12-31",
            deadline_phrase="by December 31",
            now=FIXED_NOW,
        )
        assert isinstance(res, RoundupRefusal)
        assert ("member", 601, "duplicate_claim") in res.reasons
        assert ("member", 603, "duplicate_template") in res.reasons
        assert ("member", 604, "duplicate_story") in res.reasons
        assert ("member", 605, "overlapping_subject:trump") in res.reasons


class TestRouteAndDiscoverFeedIntegration:
    @pytest.mark.asyncio
    async def test_container_route_serves_and_404s_on_refusal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
        reset_roundup_cache_for_tests()

        # Serving with live December 31 markets
        served = await get_container(
            slug=BY_DECEMBER_31_SLUG,
            db=_live_december_31_markets(),
        )
        assert served["state"] == "published"
        assert served["slug"] == "by-december-31"
        assert served["member_count"] == 6

        # Empty DB -> refuses -> 404 unavailable
        with pytest.raises(HTTPException) as exc:
            await get_container(slug=BY_DECEMBER_31_SLUG, db=[])
        assert exc.value.status_code == 404
        assert exc.value.detail == {
            "state": "unavailable",
            "slug": BY_DECEMBER_31_SLUG,
        }

    @pytest.mark.asyncio
    async def test_feed_seating_folds_covered_members_and_seats_in_back_half(
        self,
    ) -> None:
        reset_roundup_cache_for_tests()
        feed_item, container = await evaluate_roundup_producer(
            BY_DECEMBER_31_PRODUCER,
            _live_december_31_markets(),
        )
        assert feed_item is not None and container is not None

        # Build a 16-card Discover deck where member 62162058 sits as a standalone card at index 4
        deck: list[dict[str, Any]] = []
        for idx in range(16):
            mid = 62162058 if idx == 4 else 900000 + idx
            deck.append(
                {
                    "type": "futures",
                    "score": 80.0 - idx,
                    "reason": f"Market {mid}",
                    "headline": f"Market {mid}",
                    "data": {
                        "id": mid,
                        "name": f"Market {mid}",
                        "status": "open",
                        "resolution_date": "2026-11-04T20:00:00+00:00",
                        "top_outcomes": [{"id": 1, "name": "Yes", "probability": 0.6}],
                    },
                }
            )

        merged = insert_roundup_feed_items(
            deck,
            [feed_item],
            seat_floor=ROUNDUP_SEAT_FLOOR,
            now=FIXED_NOW,
        )
        # Standalone member 62162058 folded into the round-up
        standalone_ids = [
            it["data"]["id"] for it in merged if it.get("type") == "futures"
        ]
        assert 62162058 not in standalone_ids

        # Round-up sits at index >= 10 (seat >= 11)
        roundup_idx = next(
            i
            for i, it in enumerate(merged)
            if it.get("type") == "bundle"
            and it.get("data", {}).get("id") == "roundup:by-december-31"
        )
        assert roundup_idx >= ROUNDUP_SEAT_FLOOR
