"""Guardrail tests for the Content Understanding v2 writer (#891).

Covers the two writer bugs caught in CU-1 validation:
1. liveness was computed from the rank-1 outcome, which on bundled prop markets
   (esports, etc.) is a settled side-prop at 0%/100% — falsely "dead".
2. temporal_class was written under the key "temporal", so consumers reading
   "temporal_class" saw null on 100% of profiles.
"""

import inspect
from datetime import datetime, timezone

import pytest

from app.utils.cu_event_facts import cu_event_facts, cu_unlinked_event_date

from app.tasks.enrich_markets import (
    _compute_liveness,
    _cu_prompt_outcome,
    _cu_series_key,
    enrich_cu_v2_profiles,
    CU_WRITER_REV,
    _CU_V2_PROMPT,
)


class TestComputeLiveness:
    def test_resolved_status_short_circuits(self):
        assert _compute_liveness([0.5], "resolved") == "resolved"
        assert _compute_liveness([0.5], "closed") == "resolved"

    def test_none_or_empty_is_unknown(self):
        assert _compute_liveness(None, "open") == "unknown"
        assert _compute_liveness([], "open") == "unknown"
        assert _compute_liveness([None, None], "open") == "unknown"

    def test_coinflip_is_active(self):
        assert _compute_liveness([0.52, 0.48], "open") == "active"

    def test_decided_two_way_is_dead(self):
        assert _compute_liveness([0.995, 0.005], "open") == "dead"
        assert _compute_liveness([0.01, 0.99], "open") == "dead"

    def test_near_certain_is_extreme(self):
        # 3% / 97% — decided in practice but not pinned; "extreme" still passes
        # the "dead/extreme" liveness gate for genuinely-dead markets.
        assert _compute_liveness([0.03, 0.97], "open") == "extreme"

    def test_bundled_market_uses_most_competitive_outcome(self):
        # Open match whose rank-1 outcome is a settled prop at 100% (the old bug),
        # but which still has a genuine coin-flip prop -> must read "active".
        bundled = [1.0, 1.0, 1.0, 0.5, 0.1]
        assert _compute_liveness(bundled, "open") == "active"

    def test_fully_settled_bundle_is_dead(self):
        # Every outcome pinned -> nothing in play -> dead.
        assert _compute_liveness([1.0, 1.0, 0.0, 0.999], "open") == "dead"


class TestProfileShape:
    def test_writer_rev_is_bumped_past_one(self):
        # rev 1 == original (implicit) writer; the fix ships as rev >= 2 so old
        # profiles get re-tagged without a schema_version bump.
        assert CU_WRITER_REV >= 2

    def test_profile_uses_temporal_class_key(self):
        # The profile dict must emit temporal_class (not temporal) and writer_rev.
        src = inspect.getsource(enrich_cu_v2_profiles)
        assert '"temporal_class": raw.get("temporal")' in src
        assert '"writer_rev": CU_WRITER_REV' in src
        assert '"temporal":' not in src


class TestPilotInputAndProfile:
    def test_an_unpriced_outcome_and_a_quoted_zero_have_different_prompt_text(self):
        assert _cu_prompt_outcome({"name": "No", "prob": None, "move": 0.04}) == "- No: no price"
        assert _cu_prompt_outcome({"name": "Yes", "prob": 0.0}) == "- Yes: 0%"
        assert _cu_prompt_outcome({"name": "Other", "prob": 0.64, "move": -0.01}) == (
            "- Other: 64%, 24h -1.0pp"
        )

    @pytest.mark.parametrize("raw_key", [None, "", "null", " NULL ", "None"])
    def test_an_absent_series_key_is_json_null(self, raw_key):
        assert _cu_series_key(raw_key) is None

    def test_a_real_series_key_is_kept(self):
        assert _cu_series_key("series:weekly-fed") == "series:weekly-fed"

    def test_prompt_separates_the_event_day_from_venue_resolution(self):
        prompt = _CU_V2_PROMPT.format(
            name="Cup final on 14 July 2027",
            category="soccer",
            source="kalshi",
            resolution_date="2027-07-31",
            outcomes="- Home: no price",
            measure_vocabulary="goals",
        )
        assert "Venue resolution date (settlement metadata): 2027-07-31" in prompt
        assert 'event_date "2027-07-14"' in prompt
        assert "Never use January 1 as a placeholder" in prompt


class TestWriterV3Rubric:
    """Round-1 grading verdict (#891, cu_grading_round1.md): the v3 prompt must
    carry the explicit rubric rules + calibrated anchors that fixed the failing
    fields (topic 88.5%, temporal 69%, stakes 69%, breadth 69%, oddity 54%).
    """

    def test_writer_rev_is_v3(self):
        # v3 ships with the round-1 rubric; the bump forces a re-tag of rev-2 rows.
        assert CU_WRITER_REV >= 3

    def test_esports_is_a_first_class_topic(self):
        # Rule 2: ALL esports is topic 'esports', never entertainment/sports —
        # so it must be in the topic enum or the model can't emit it.
        assert "esports" in _CU_V2_PROMPT

    def test_prompt_encodes_the_failing_field_rules(self):
        p = _CU_V2_PROMPT
        # oddity baseline 1 (was drifting to 2)
        assert "oddity baseline is 1" in p
        # stakes = real-world consequence, not volume (geopolitics vs esports inversion)
        assert "real-world consequence" in p and "NOT market volume" in p
        # breadth = THIS market's reach, not the topic's fame
        assert "THIS market" in p
        # temporal: deadline for "by [date]?", periodic for recurring, reserve event_tied
        assert "periodic" in p and "deadline" in p and "event_tied" in p
        # geopolitics covers armed conflict regardless of countries
        assert "geopolitics" in p

    def test_prompt_carries_calibrated_anchors(self):
        p = _CU_V2_PROMPT
        # A representative subset of Alex's verbatim anchors.
        assert "ceasefire" in p           # geopolitics / deadline / S4 B4 O1
        assert "Fed Decision" in p        # economics / periodic / S3 B4 O1
        assert "Clavicular pregnancy" in p  # health / oddity 5


class TestWriterV4Rubric:
    """Round-2 sample findings (#891, Queue #47): v3 mis-tagged ATP tennis as
    topic=esports and emitted wild-year event_dates. v4 must guard both.
    """

    def test_writer_rev_is_v4(self):
        # The bump forces a re-tag of rev-3 rows with the corrected prompt.
        assert CU_WRITER_REV >= 4

    def test_esports_is_video_games_only(self):
        p = _CU_V2_PROMPT
        # Rule 2 must scope esports to video games and exclude human-played sports.
        assert "VIDEO-GAME" in p or "video-game" in p
        # tennis (and physical sports) must be called out as NOT esports
        assert "tennis" in p.lower()
        assert "not esports" in p.lower() or "never \"esports\"" in p.lower() \
            or "is NOT automatically esports" in p

    def test_tennis_anchor_present(self):
        # A human-played "X vs Y" match anchored to sports, not esports.
        p = _CU_V2_PROMPT
        assert "Stuttgart Open" in p

    def test_event_date_sanity_guards_past_and_wild_years(self):
        p = _CU_V2_PROMPT
        # Rule 6 must reject distant-past dates, not just far-future ones.
        assert "distant past" in p or "in the past" in p
        assert "13 months" in p


@pytest.mark.parametrize(
    ("league", "geography"),
    [
        ("soccer_france_coupe_de_france", "country:FR"),
        ("soccer_netherlands_knvb_cup", "country:NL"),
        ("soccer_paraguay_primera_division", "country:PY"),
        ("soccer_uefa_europa_league", "global"),
        ("icehockey_nhl", "us"),
        ("soccer_other", None),
        (None, None),
    ],
)
def test_linked_match_facts_take_the_day_and_league(league, geography):
    facts = cu_event_facts(
        "Spread: home team (-1.5)",
        linked_game_id=1,
        linked_start=datetime(2026, 11, 28, 14, 0, tzinfo=timezone.utc),
        start_source="odds_api",
        linked_league=league,
    )
    expected = {"event_date": "2026-11-28" if geography else None}
    if geography:
        expected["geography"] = geography
    assert facts == expected


@pytest.mark.parametrize(
    "title",
    [
        "Vermont House Orleans-3 winner? (2028)",
        "Alaska House District 11 winner? (2028)",
        "West Virginia House of Delegates District 48 winner? (2028)",
        "Massachusetts House 4th Suffolk District winner? (2028)",
        "Hawaii House District 41 winner? (2028)",
        "Connecticut Senate District 36 winner? (2028)",
    ],
)
def test_state_legislative_districts_have_fixed_geography_and_ratings(title):
    assert cu_event_facts(title) == {"geography": "local", "stakes": 1, "breadth": 1}


@pytest.mark.parametrize(
    "title",
    [
        "Winner of California's 12th U.S. House district",
        "VA-09 House election: Morgan Griffith vote percent",
        "Ohio Senate election winner?",
        "Will the Cowboys win their season series?",
    ],
)
def test_other_markets_keep_model_fields_when_there_is_no_link(title):
    assert cu_event_facts(title) == {}


@pytest.mark.parametrize(
    ("league", "start", "local_day"),
    [
        ("basketball_ncaab", "2026-11-26T00:30:00+00:00", "2026-11-25"),
        ("soccer_italy_serie_b", "2026-11-25T23:30:00+00:00", "2026-11-26"),
    ],
)
def test_scheduled_link_uses_the_league_day(league, start, local_day):
    facts = cu_event_facts(
        "Who wins?",
        linked_game_id=1,
        linked_start=datetime.fromisoformat(start),
        start_source="espn",
        linked_league=league,
    )
    assert facts["event_date"] == local_day


@pytest.mark.parametrize("source", ["kalshi", "kalshi_ticker", "polymarket_venue", None])
def test_unscheduled_link_supplies_no_event_day(source):
    facts = cu_event_facts(
        "Who wins?",
        linked_game_id=1,
        linked_start=datetime(2026, 11, 26, 0, 30, tzinfo=timezone.utc),
        start_source=source,
        linked_league="basketball_ncaab",
    )
    assert facts == {"event_date": None, "geography": "us"}


@pytest.mark.parametrize(
    ("category", "topic", "date", "expected"),
    [
        ("politics", "politics", "2028-11-08", None),
        ("politics", "politics", "2028-11-07", "2028-11-07"),
        ("football", "sports", "2028-11-08", "2028-11-08"),
        ("other", "esports", "2028-11-08", "2028-11-08"),
        ("other", "weather", "2028-11-08", None),
    ],
)
def test_only_unlinked_non_sport_payout_day_copies_are_dropped(
    category, topic, date, expected
):
    payout = datetime(2028, 11, 8, 4, 59, tzinfo=timezone.utc)
    assert cu_unlinked_event_date(date, payout, category=category, topic=topic) == expected
