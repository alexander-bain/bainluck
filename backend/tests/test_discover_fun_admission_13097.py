"""Tests for #13097 (Rulings 272: A & 273: B): fun-market tagging, guards, and admission."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes import feed as feed_mod
from app.utils import candidate_base as candidate_base_mod
from app.utils.discover_fun_tags import (
    DISCOVER_FUN_ADMISSION_ENV,
    DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV,
    FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME,
    all_fun_market_ids,
    check_fun_real_trading,
    check_fun_still_ahead,
    check_fun_taste_guard,
    discover_fun_admission_market_ids,
    evaluate_fun_market_guards,
    fun_entry_allows_extreme_odds,
    fun_market_ids_for_sub_tag,
    fun_tags_for_market,
    get_fun_market_entry,
    is_discover_fun_admission_enabled,
    load_fun_markets_registry,
    resolve_fun_effective_category,
)
from app.utils.feed_cache import (
    feed_page_base_cache_key,
    feed_response_cache_key,
)
from app.utils.futures_liveness import BOOK_REFUSED_KEY, VENUE_SETTLED_KEY

FROZEN_NOW = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)


class TestFunMarketsRegistry:
    def test_seed_file_loads_100_markets_and_declares_all_sub_tags(self):
        registry = load_fun_markets_registry()
        assert len(registry.markets) == 100
        assert len(registry.ordered_market_ids) == 100
        assert get_fun_market_entry(109536) is None  # Removed per Fable pre-flip item 1
        assert registry.default_min_lifetime_volume == FUN_TAG_DEFAULT_MIN_LIFETIME_VOLUME
        # Required Batch 2 & Batch 3 selector sub-tags from #13097
        for required_tag in (
            "long-shot",
            "long-awaited",
            "year-end",
            "space",
            "super-bowl-culture",
            "elon-musk",
            "taylor-swift",
            "engagements",
            "white-christmas",
            "james-bond",
        ):
            assert required_tag in registry.sub_tags
            assert len(fun_market_ids_for_sub_tag(required_tag)) >= 3

    def test_taylor_swift_wedding_markets_are_not_in_seed_registry(self):
        # Ruling 273: B: no Taylor Swift wedding markets (already happened).
        assert get_fun_market_entry(52755900) is None
        assert get_fun_market_entry(113799) is None
        for mid in fun_market_ids_for_sub_tag("taylor-swift"):
            entry = get_fun_market_entry(mid)
            assert entry is not None
            assert "wedding" not in entry.title.lower()

    def test_unblended_twins_are_never_double_registered(self):
        registry = load_fun_markets_registry()
        primary_ids = set(registry.markets.keys())
        for entry in registry.markets.values():
            for twin_id in entry.unblended_twin_ids:
                assert twin_id not in primary_ids, (
                    f"twin {twin_id} for {entry.market_id} must not be double-registered"
                )

    def test_misfiled_seed_markets_derive_subject_from_fun_tag_not_sports(self):
        # 9 markets noted on #13097 as filed under basketball/football/motorsports/politics/geopolitics
        misfiled_ids = (
            66925975,  # Bryan Johnson dunk (stored: basketball)
            109291,    # Blake Lively and Taylor Swift (stored: politics)
            109412,    # Elon purchase Ryanair (stored: politics)
            109489,    # Tesla Optimus (stored: motorsports)
            68858738,  # Miss Universe 2026 (stored: politics)
            70400892,  # World Happiness Report (stored: politics)
            70239521,  # NFL Christmas Day halftime show (stored: football)
            70239540,  # Big Game commercial (stored: football)
            108232,    # Nuclear fusion (stored: geopolitics)
        )
        for mid in misfiled_ids:
            entry = get_fun_market_entry(mid)
            assert entry is not None
            assert entry.discover_category in {"entertainment", "culture", "tech"}
            assert entry.fun_bucket in {"odd", "entertainment"}

    def test_zero_taste_false_positives_across_all_seed_entries(self):
        registry = load_fun_markets_registry()
        for entry in registry.markets.values():
            ok, reason = check_fun_taste_guard(entry.title)
            assert ok, f"unexpected taste rejection on {entry.market_id} ({entry.title}): {reason}"


class TestFunGuards:
    def test_check_1_real_trading_bar_enforces_lifetime_volume(self, monkeypatch):
        monkeypatch.delenv(DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV, raising=False)
        assert check_fun_real_trading(None) == (False, "missing_volume")
        assert check_fun_real_trading(0)[0] is False
        assert check_fun_real_trading(1_235)[0] is False   # Chipotle burrito
        assert check_fun_real_trading(2_641)[0] is False   # Big Mac
        assert check_fun_real_trading(9_999)[0] is False
        assert check_fun_real_trading(10_000) == (True, None)
        assert check_fun_real_trading(18_316) == (True, None)

        monkeypatch.setenv(DISCOVER_FUN_MIN_LIFETIME_VOLUME_ENV, "5000")
        assert check_fun_real_trading(5_171) == (True, None)
        assert check_fun_real_trading(4_194)[0] is False

    @pytest.mark.parametrize(
        ("title", "expected_category"),
        [
            ("Will Celebrity X announce a pregnancy in 2026?", "pregnancy"),
            ("Will Actor Y be hospitalized before 2027?", "health"),
            ("Did Politician Z have an affair this year?", "affairs"),
            ("Will Couple A and B file for divorce in 2026?", "divorce"),
            ("Will Person C be arrested before 2027?", "arrest"),
            ("Will Defendant D be convicted in murder trial?", "trial"),
            ("Will Public Figure E die before 2027?", "death"),
        ],
    )
    def test_check_2_taste_guard_blocks_all_seven_prohibited_categories(
        self, title: str, expected_category: str
    ):
        ok, reason = check_fun_taste_guard(title)
        assert ok is False
        assert reason == f"taste:{expected_category}"

    def test_check_2_taste_guard_checks_description_and_allows_engagements(self):
        # Ruling 273: B — engagements are allowed as a set.
        for title in (
            "Timothee Chalamet and Kylie Jenner: engaged in 2026?",
            "Katy Perry and Justin Trudeau: engaged in 2026?",
            "Tom Brady and Alix Earle: engaged in 2026?",
            "Kim Kardashian and Lewis Hamilton: engaged in 2026?",
        ):
            assert check_fun_taste_guard(title) == (True, None)

        # Description-only taste violation is also caught.
        ok, reason = check_fun_taste_guard(
            "Big celebrity news in 2026?",
            description="Resolves Yes if the actor is arrested on criminal charges.",
        )
        assert ok is False
        assert reason == "taste:arrest"

    def test_check_3_still_ahead_blocks_concluded_wedding_and_past_markets(self):
        # Both Taylor Swift wedding markets fail even if status='open' and resolution_date is future.
        for title in (
            "Taylor Swift: wedding dress",
            "Who will attend Taylor Swift and Travis Kelce's wedding?",
        ):
            verdict = evaluate_fun_market_guards(
                title=title,
                status="open",
                volume=1_409_571,
                resolution_date=FROZEN_NOW + timedelta(days=180),
                sport_category="entertainment",
                market_metadata=None,
                now=FROZEN_NOW,
            )
            assert verdict.passed is False
            assert verdict.passed_still_ahead is False
            assert verdict.still_ahead_reason == "concluded_event:taylor-swift-wedding"

        # Non-open, venue-settled, book-refused, past resolution_date, past event_date, title-stale.
        assert check_fun_still_ahead(
            title="Valid future market",
            status="resolved",
            resolution_date=FROZEN_NOW + timedelta(days=30),
            sport_category="entertainment",
            market_metadata=None,
            now=FROZEN_NOW,
        )[0] is False

        assert check_fun_still_ahead(
            title="Valid future market",
            status="open",
            resolution_date=FROZEN_NOW + timedelta(days=30),
            sport_category="entertainment",
            market_metadata={VENUE_SETTLED_KEY: "2026-07-14T00:00:00Z"},
            now=FROZEN_NOW,
        ) == (False, "venue_settled")

        assert check_fun_still_ahead(
            title="Valid future market",
            status="open",
            resolution_date=FROZEN_NOW + timedelta(days=30),
            sport_category="entertainment",
            market_metadata={BOOK_REFUSED_KEY: "2026-07-14T00:00:00Z"},
            now=FROZEN_NOW,
        ) == (False, "book_refused")

        assert check_fun_still_ahead(
            title="Valid future market",
            status="open",
            resolution_date=FROZEN_NOW - timedelta(hours=1),
            sport_category="entertainment",
            market_metadata=None,
            now=FROZEN_NOW,
        ) == (False, "past_resolution_date")

        assert check_fun_still_ahead(
            title="Will it snow in Denver on Christmas?",
            status="open",
            resolution_date=datetime(2027, 1, 5, tzinfo=timezone.utc),
            sport_category="weather",
            market_metadata=None,
            now=datetime(2026, 12, 26, 12, 0, tzinfo=timezone.utc),
            event_date=date(2026, 12, 25),
        ) == (False, "past_event_date:2026-12-25")

        assert check_fun_still_ahead(
            title="Who will win the 2025 Oscars?",
            status="open",
            resolution_date=None,
            sport_category="entertainment",
            market_metadata=None,
            now=FROZEN_NOW,
            concluded_events=(),
        ) == (False, "past_title_year:2025")

        assert check_fun_still_ahead(
            title="Will Half-Life 3 be announced before 2026?",
            status="open",
            resolution_date=None,
            sport_category="entertainment",
            market_metadata=None,
            now=FROZEN_NOW,
            concluded_events=(),
        ) == (False, "past_title_deadline:before_2026")

        assert check_fun_still_ahead(
            title="Will Half-Life 3 be announced before 2027?",
            status="open",
            resolution_date=None,
            sport_category="entertainment",
            market_metadata=None,
            now=FROZEN_NOW,
            concluded_events=(),
        ) == (True, None)


class TestFunAdmissionAndSwitch:
    @pytest.mark.asyncio
    async def test_switch_defaults_off_and_runs_zero_queries(self, monkeypatch):
        monkeypatch.delenv(DISCOVER_FUN_ADMISSION_ENV, raising=False)
        assert is_discover_fun_admission_enabled() is False

        db = AsyncMock()
        admitted = await discover_fun_admission_market_ids(db, now=FROZEN_NOW)
        assert admitted == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_switch_on_admits_qualifying_fun_markets_including_vs_title(
        self, monkeypatch
    ):
        monkeypatch.setenv(DISCOVER_FUN_ADMISSION_ENV, "1")
        assert is_discover_fun_admission_enabled() is True

        # Rows returned by SQL: includes Dune vs Avengers (" vs " in title, 0 daily vol),
        # Earth flat longshot, a thin-trading market (fails Check 1), a taste-violating
        # rewritten title (fails Check 2), and a past-event White Christmas row (fails Check 3).
        fake_rows = [
            SimpleNamespace(
                id=59172754,
                name="Dune vs Avengers: Highest Rotten Tomatoes Score",
                description=None,
                status="open",
                volume=18_316,
                resolution_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
                llm_sport_category="entertainment",
                market_metadata=None,
            ),
            SimpleNamespace(
                id=34191685,
                name="Is Earth flat?",
                description=None,
                status="open",
                volume=103_155,
                resolution_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
                llm_sport_category="entertainment",
                market_metadata=None,
            ),
            SimpleNamespace(
                id=70170648,
                name="McDonald's Big Mac price",
                description=None,
                status="open",
                volume=2_641,
                resolution_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
                llm_sport_category="economics",
                market_metadata=None,
            ),
            SimpleNamespace(
                id=108339,
                name="Will Trump be arrested before SNL?",
                description=None,
                status="open",
                volume=30_345,
                resolution_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
                llm_sport_category="entertainment",
                market_metadata=None,
            ),
        ]

        class _FakeResult:
            def all(self):
                return fake_rows

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_FakeResult())

        admitted = await discover_fun_admission_market_ids(db, now=FROZEN_NOW)
        assert admitted == [34191685, 59172754]  # Registry order; thin + taste rows dropped

        # SQL query deliberately omits "% vs %" exclusion so Dune vs Avengers can enter.
        executed_query = db.execute.call_args.args[0]
        compiled_sql = str(executed_query).lower()
        assert "not like" not in compiled_sql
        assert "volume" in compiled_sql

    def test_cache_and_candidate_base_keys_stay_identical_when_off_and_isolate_when_on(
        self, monkeypatch
    ):
        monkeypatch.delenv(DISCOVER_FUN_ADMISSION_ENV, raising=False)
        off_resp = feed_response_cache_key(limit=50, offset=0, event_pct=0.15)
        off_resp_explicit = feed_response_cache_key(
            limit=50, offset=0, event_pct=0.15, fun_admission=False
        )
        on_resp = feed_response_cache_key(
            limit=50, offset=0, event_pct=0.15, fun_admission=True
        )
        assert off_resp == off_resp_explicit
        assert on_resp != off_resp

        off_base = feed_page_base_cache_key(limit=50, event_pct=0.15)
        off_base_explicit = feed_page_base_cache_key(
            limit=50, event_pct=0.15, fun_admission=False
        )
        on_base = feed_page_base_cache_key(
            limit=50, event_pct=0.15, fun_admission=True
        )
        assert off_base == off_base_explicit
        assert on_base != off_base

        off_cb_id = candidate_base_mod.base_identity(None, None)
        assert off_cb_id == "discover-candidates:v2:all:no-static-tags"

        monkeypatch.setenv(DISCOVER_FUN_ADMISSION_ENV, "1")
        on_cb_id = candidate_base_mod.base_identity(None, None)
        assert on_cb_id == "discover-candidates:v2:all:no-static-tags:fun=1"
        # Filtered sport/tag bases stay untouched
        assert candidate_base_mod.base_identity("basketball", None) == (
            "discover-candidates:v2:basketball:no-static-tags"
        )

    def test_runtime_filter_allows_curated_longshot_extreme_odds_without_relaxing_staleness(
        self,
    ):
        fresh_market = SimpleNamespace(
            id=34191685,
            name="Is Earth flat?",
            source="polymarket",
            external_id="flat-earth",
            group_id=None,
            status="open",
            commence_time=None,
            resolution_date=FROZEN_NOW + timedelta(days=120),
            updated_at=FROZEN_NOW - timedelta(hours=1),
            market_metadata=None,
            outcomes=[],
        )
        outcomes_data = [
            {"name": "No", "probability": 0.996, "probability_change_24h": 0.0, "opening_probability": 0.995},
            {"name": "Yes", "probability": 0.004, "probability_change_24h": 0.0, "opening_probability": 0.005},
        ]

        # Standard path drops extreme 99.6% / 0.4% market as locked.
        default_trace = feed_mod._market_runtime_filter_trace(
            fresh_market,
            outcomes_data,
            "No",
            0.996,
            FROZEN_NOW,
            sport_category="culture",
            newest_outcome_at=FROZEN_NOW - timedelta(hours=1),
            allow_extreme_odds=False,
        )
        assert default_trace["eligible"] is False
        assert "locked_market" in default_trace["blockers"]

        # Curated admitted fun longshot survives extreme-odds check while liveness is fresh.
        fun_trace = feed_mod._market_runtime_filter_trace(
            fresh_market,
            outcomes_data,
            "No",
            0.996,
            FROZEN_NOW,
            sport_category="culture",
            newest_outcome_at=FROZEN_NOW - timedelta(hours=1),
            allow_extreme_odds=True,
        )
        assert fun_trace["eligible"] is True

        # Past resolution_date STILL blocks even when allow_extreme_odds=True.
        expired_market = SimpleNamespace(
            **{
                **fresh_market.__dict__,
                "resolution_date": FROZEN_NOW - timedelta(hours=1),
            }
        )
        expired_trace = feed_mod._market_runtime_filter_trace(
            expired_market,
            outcomes_data,
            "No",
            0.996,
            FROZEN_NOW,
            sport_category="culture",
            newest_outcome_at=FROZEN_NOW - timedelta(hours=1),
            allow_extreme_odds=True,
        )
        assert expired_trace["eligible"] is False
        assert "past_resolution_date" in expired_trace["blockers"]

    def test_fun_tags_helper_returns_sub_tags_and_empty_for_untagged(self):
        assert "long-shot" in fun_tags_for_market(109435)
        assert "taylor-swift" in fun_tags_for_market(109295)
        assert "pope-leo-xiv" in fun_tags_for_market(109295)
        assert fun_tags_for_market(999999999) == ()
        assert len(all_fun_market_ids()) == 100

    def test_extreme_odds_lift_applies_only_to_long_shot_tag(self):
        # Fable non-blocking look on #13105: only long-shot markets bypass extreme-odds
        # suppression; a 99% nearly-over release/award stays subject to normal filters.
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(34191685)) is True
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(113504)) is True
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(109435)) is True
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(109540)) is False
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(109315)) is False
        assert fun_entry_allows_extreme_odds(get_fun_market_entry(108505)) is False
        assert fun_entry_allows_extreme_odds(None) is False

    def test_resolve_fun_effective_category_preserves_valid_stored_editorial_category(self):
        # Follow-up on #13097 live flip: TIME Person of the Year (27467306) is stored
        # as entertainment (base 40) while its fun entry has discover_category="culture"
        # (base 38); Nobel Peace Prize (65544835) is stored as politics (base 45).
        # Keep valid stored editorial categories so fun admission cannot downgrade them.
        time_entry = get_fun_market_entry(27467306)
        nobel_entry = get_fun_market_entry(65544835)
        satoshi_entry = get_fun_market_entry(9997262)
        halftime_entry = get_fun_market_entry(70239521)

        assert resolve_fun_effective_category("entertainment", time_entry) == "entertainment"
        assert resolve_fun_effective_category("politics", nobel_entry) == "politics"
        assert resolve_fun_effective_category("economics", get_fun_market_entry(52755535)) == "economics"
        assert resolve_fun_effective_category("tech", get_fun_market_entry(109435)) == "tech"

        # Missing, other, crypto, esports, or sport-filed fun markets still fall back
        # to the fun entry's discover_category.
        assert resolve_fun_effective_category(None, time_entry) == "culture"
        assert resolve_fun_effective_category("", time_entry) == "culture"
        assert resolve_fun_effective_category("other", time_entry) == "culture"
        assert resolve_fun_effective_category("crypto", satoshi_entry) == "tech"
        assert resolve_fun_effective_category("esports", time_entry) == "culture"
        assert resolve_fun_effective_category("football", halftime_entry) == "entertainment"
        assert resolve_fun_effective_category("crypto", None) == "crypto"

    @pytest.mark.asyncio
    async def test_score_futures_keeps_time_person_of_the_year_score_with_fun_admission_on(
        self, monkeypatch
    ):
        """Real _score_futures check: TIME Person of the Year (27467306) must not lose
        points when DISCOVER_FUN_ADMISSION_ENABLED turns on."""
        outcomes = [
            SimpleNamespace(
                id=274673061,
                name="James Talarico",
                display_name="James Talarico",
                current_probability=0.25,
                opening_probability=0.25,
                probability_change_24h=0.0,
                probability_change_7d=0.0,
                is_winner=None,
                resolution_source=None,
                rank=1,
                team_id=None,
                updated_at=FROZEN_NOW - timedelta(minutes=10),
                last_updated=FROZEN_NOW - timedelta(minutes=10),
                outcome_metadata=None,
                external_outcome_id=None,
            ),
            SimpleNamespace(
                id=274673062,
                name="Zohran Mamdani",
                display_name="Zohran Mamdani",
                current_probability=0.22,
                opening_probability=0.22,
                probability_change_24h=0.0,
                probability_change_7d=0.0,
                is_winner=None,
                resolution_source=None,
                rank=2,
                team_id=None,
                updated_at=FROZEN_NOW - timedelta(minutes=10),
                last_updated=FROZEN_NOW - timedelta(minutes=10),
                outcome_metadata=None,
                external_outcome_id=None,
            ),
            SimpleNamespace(
                id=274673063,
                name="Abdul El-Sayed",
                display_name="Abdul El-Sayed",
                current_probability=0.18,
                opening_probability=0.18,
                probability_change_24h=0.0,
                probability_change_7d=0.0,
                is_winner=None,
                resolution_source=None,
                rank=3,
                team_id=None,
                updated_at=FROZEN_NOW - timedelta(minutes=10),
                last_updated=FROZEN_NOW - timedelta(minutes=10),
                outcome_metadata=None,
                external_outcome_id=None,
            ),
        ]
        market = SimpleNamespace(
            id=27467306,
            name="TIME Person of the Year 2026",
            source="kalshi",
            sport=None,
            sport_id=None,
            sport_name="Entertainment",
            llm_sport_category="entertainment",
            description="",
            llm_league=None,
            llm_gender=None,
            llm_level=None,
            category="entertainment",
            market_tier=2,
            market_type="outright",
            status="open",
            resolution_date=FROZEN_NOW + timedelta(days=170),
            volume=500000,
            volume_24h=15000,
            canonical_market_key=None,
            group_id=None,
            group_type=None,
            external_id="KXTIMEPOTY-26",
            event_id=None,
            image_url=None,
            image_width=None,
            image_height=None,
            hook_description=None,
            market_metadata={},
            curation_score_adj=0,
            updated_at=FROZEN_NOW - timedelta(minutes=10),
            created_at=FROZEN_NOW - timedelta(days=60),
            outcomes=outcomes,
        )

        def _make_db():
            db = AsyncMock()

            def _exec(*_args, **_kwargs):
                res = MagicMock()
                scalars = MagicMock()
                scalars.all.return_value = [market.id]
                unique = MagicMock()
                unique.all.return_value = [market]
                scalars.unique.return_value = unique
                res.scalars.return_value = scalars
                res.all.return_value = []
                return res

            db.execute = AsyncMock(side_effect=_exec)
            return db

        async def _score(fun_enabled: bool) -> dict:
            if fun_enabled:
                monkeypatch.setenv(DISCOVER_FUN_ADMISSION_ENV, "true")
            else:
                monkeypatch.delenv(DISCOVER_FUN_ADMISSION_ENV, raising=False)
            with (
                patch(
                    "app.routes.feed._external_curator_recall_market_ids",
                    new=AsyncMock(return_value=[]),
                ),
                patch(
                    "app.routes.feed._get_canonical_source_counts",
                    new=AsyncMock(return_value={}),
                ),
                patch(
                    "app.utils.discover_fun_tags.discover_fun_admission_market_ids",
                    new=AsyncMock(return_value=[27467306] if fun_enabled else []),
                ),
                patch(
                    "app.tasks.redis_state.get_async_redis_client",
                    side_effect=Exception("no redis in test"),
                ),
            ):
                items = await feed_mod._score_futures(
                    _make_db(),
                    FROZEN_NOW,
                    None,
                    feed_mod.PersonalizationContext(),
                )
            by_id = {it["data"]["id"]: it for it in items if it.get("type") == "futures"}
            assert 27467306 in by_id
            return by_id[27467306]

        card_off = await _score(False)
        card_on = await _score(True)
        assert card_on["score"] == card_off["score"]
        assert card_on["data"]["llm_sport_category"] == "entertainment"
        assert "year-end" in card_on.get("_fun_tags", [])
