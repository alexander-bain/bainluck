"""Unit and integrity tests for #13544 set quality gates, #1809 frame integration, 196-A row context, and Blind Deck v2."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.utils.discover_fun_scout import (
    ScoutProposedSet,
    build_scout_rule_file_definition,
    validate_scout_proposed_set,
)
from app.utils.set_quality_13544 import (
    MEASURE_FAMILY_BOX_OFFICE,
    MEASURE_FAMILY_EVENT_OR_WINNER,
    MEASURE_FAMILY_PHYSICAL_QUANTITY,
    MEASURE_FAMILY_PRICE_OR_COST,
    MEASURE_FAMILY_PRICE_RECORD,
    MEASURE_FAMILY_RANKED_POSITION,
    MEASURE_FAMILY_REVIEW_SCORE,
    MEASURE_FAMILY_TIMING_LADDER,
    audit_sets_13544,
    build_row_context_line,
    build_set_selection_explainer,
    check_scout_no_repeated_rows,
    check_scout_single_measure_family,
    classify_market_measure_family,
    extract_cu_frame_context,
    parse_window_date_precision,
    validate_row_context_196a,
)

FROZEN_NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "discover"
DECK_V2_PATH = DATA_DIR / "fun_scout_blind_40_deck_v2_2026_11_23.json"
BANNED_VOICE_RE = re.compile(r"\b(?:traders?|bets?|betting)\b", re.IGNORECASE)
FULL_LEAK_TOKENS = (
    "machinery-",
    "batch3",
    "batch4",
    "batch5",
    "batch6",
    "batch7",
    "batch8",
    "hand_written",
    "model_proposed",
    "claude-",
    "curated",
    "scout",
    "6e214dc62d",
    "13544",
    "branch_13544",
    "baseline_6e214dc62d",
)


def _cu_meta(
    *,
    measure: str | None = None,
    comparator: str | None = None,
    value: object = None,
    unit: str | None = None,
    horizon_kind: str | None = None,
    window_date: str | None = None,
    writer_rev: int = 8,
    schema_version: int = 2,
    frame_drop_reason: str | None = None,
    frame_slot_drops: dict[str, str] | None = None,
    subject_ref: str = "entity:101",
    subject_entity_id: int | None = 101,
    subject_resolved: bool = True,
    story_key: str | None = None,
    row_context: dict[str, str] | None = None,
) -> dict:
    frame = (
        None
        if measure is None
        else {
            "measure": measure,
            "comparator": comparator,
            "value": value,
            "unit": unit,
            "horizon_kind": horizon_kind,
            "window_date": window_date,
        }
    )
    meta: dict = {
        "discover_llm": {
            "schema_version": schema_version,
            "writer_rev": writer_rev,
            "frame": frame,
            "frame_drop_reason": frame_drop_reason,
            "frame_slot_drops": frame_slot_drops or {},
            "subject_ref": subject_ref,
            "subject_entity_id": subject_entity_id,
            "subject_resolved": subject_resolved,
            "story_key": story_key,
        }
    }
    if row_context is not None:
        meta["row_context"] = row_context
    return meta


def _row(
    market_id: int,
    title: str,
    *,
    source: str = "kalshi",
    category: str = "culture",
    market_metadata: dict | None = None,
    story_key: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        market_id=market_id,
        source=source,
        title=title,
        status="open",
        category=category,
        resolution_date=datetime(2027, 6, 1, tzinfo=timezone.utc),
        volume=120_000.0,
        volume_24h=8_000.0,
        canonical_market_key=f"{source}-{market_id}",
        group_id=None,
        market_metadata=market_metadata,
        event_date=None,
        story_key=story_key,
    )


class TestFrame1809ConsumerContract:
    def test_ranking_positive_int_and_missing_value_fallback(self):
        # Ordinal ranking integer >= 2 -> ranked_position
        assert (
            classify_market_measure_family(
                "Ambiguous title without ordinal hint",
                market_metadata=_cu_meta(measure="ranking", value="3"),
            )
            == MEASURE_FAMILY_RANKED_POSITION
        )
        # Explicit integer 1 -> top winner slot
        assert (
            classify_market_measure_family(
                "#1 Streaming Show",
                market_metadata=_cu_meta(measure="ranking", value="1"),
            )
            == MEASURE_FAMILY_EVENT_OR_WINNER
        )
        # Builder B limit #1: '2nd' dropped literal check leaving value=None falls back to title rules
        assert (
            classify_market_measure_family(
                "2nd Largest Company by Market Cap?",
                market_metadata=_cu_meta(measure="ranking", value=None, frame_slot_drops={}),
            )
            == MEASURE_FAMILY_RANKED_POSITION
        )
        # Domain metric with ordinal title still classifies as ranked_position
        assert (
            classify_market_measure_family(
                "2nd largest company by market cap at year-end 2026?",
                market_metadata=_cu_meta(measure="market_cap", value=None),
            )
            == MEASURE_FAMILY_RANKED_POSITION
        )

    def test_frame_measures_and_window_date_precision(self):
        assert parse_window_date_precision("2026") == ("2026", "year")
        assert parse_window_date_precision("2026-12") == ("2026-12", "month")
        assert parse_window_date_precision("2026-12-31") == ("2026-12-31", "day")
        assert parse_window_date_precision("December 31, 2026") == (None, None)

        # Incompatible frame measures within same broad numeric family split via mixed_frame_measures
        r1 = _row(1, "Crude oil high in Dec?", market_metadata=_cu_meta(measure="price_high", window_date="2026-12"))
        r2 = _row(2, "Oil price hit an all-time record?", market_metadata=_cu_meta(measure="price_record_high", window_date="2026"))
        assert classify_market_measure_family(r2.title, market_metadata=r2.market_metadata) == MEASURE_FAMILY_PRICE_RECORD
        assert check_scout_single_measure_family([r1, r2]) is not None

        # Award winner vs nomination split cleanly when both carry distinct frame measures
        a1 = _row(1, "Actor X Oscar?", market_metadata=_cu_meta(measure="award_result", subject_ref="entity:1"))
        a2 = _row(2, "Actor Y Oscar?", market_metadata=_cu_meta(measure="nomination", subject_ref="entity:2"))
        assert check_scout_single_measure_family([a1, a2]) == "mixed_frame_measures:award_result+nomination"

        # Open timing ladder via #1809 release_date / open_ended
        assert (
            classify_market_measure_family(
                "GTA VI released by...?",
                market_metadata=_cu_meta(measure="release_date", horizon_kind="open_ended"),
            )
            == MEASURE_FAMILY_TIMING_LADDER
        )
        # Fallback regexes for tweets (# boundary bug fix) and diesel price
        assert classify_market_measure_family("Elon Musk # tweets in November 2026?") == MEASURE_FAMILY_PHYSICAL_QUANTITY
        assert classify_market_measure_family("How high will US diesel prices get in 2026?") == MEASURE_FAMILY_PRICE_OR_COST

        # Below min writer_rev or dropped frame falls back cleanly to title rules
        dropped = _row(
            3,
            "Avengers: Doomsday: Rotten Tomatoes score",
            market_metadata=_cu_meta(
                measure="box_office_revenue",
                frame_drop_reason="value_not_in_title",
            ),
        )
        assert (
            classify_market_measure_family(dropped.title, market_metadata=dropped.market_metadata)
            == MEASURE_FAMILY_REVIEW_SCORE
        )
        stale_rev = _row(
            4,
            "Dune 3 Opening Weekend Box Office",
            market_metadata=_cu_meta(measure="rt_score", writer_rev=6),
        )
        assert (
            classify_market_measure_family(stale_rev.title, market_metadata=stale_rev.market_metadata)
            == MEASURE_FAMILY_BOX_OFFICE
        )

    def test_grounded_subject_joins_and_unresolved_never_join(self):
        # Rev 8 team: ref without entity_id is still grounded and catches duplicates / ordinal siblings
        t1 = _row(
            1,
            "Team Alpha rank 1",
            market_metadata=_cu_meta(
                measure="ranking",
                value="1",
                window_date="2026",
                subject_ref="team:45",
                subject_entity_id=None,
            ),
        )
        t2 = _row(
            2,
            "Team Alpha rank 2",
            market_metadata=_cu_meta(
                measure="ranking",
                value="2",
                window_date="2026",
                subject_ref="team:45",
                subject_entity_id=None,
            ),
        )
        err = check_scout_no_repeated_rows([t1, t2])
        assert err is not None and err.startswith("repeated_row_ordinal_siblings:")

        # Different window_date precision ("2026" year vs "2026-12-31" day) is NOT falsely equated
        y1 = _row(1, "Crude oil price peak during full year 2026", market_metadata=_cu_meta(measure="price_high", window_date="2026", subject_ref="team:45", subject_entity_id=None))
        y2 = _row(2, "Crude oil price peak before Dec 31 closing bell", market_metadata=_cu_meta(measure="price_high", window_date="2026-12-31", subject_ref="team:45", subject_entity_id=None))
        assert check_scout_no_repeated_rows([y1, y2]) is None

        # unresolved: markers NEVER act as grounded join keys
        u1 = _row(1, "Totally distinct movie one", market_metadata=_cu_meta(measure="award_result", subject_ref="unresolved:__none__", subject_resolved=False, subject_entity_id=None))
        u2 = _row(2, "Completely different book two", market_metadata=_cu_meta(measure="award_result", subject_ref="unresolved:__none__", subject_resolved=False, subject_entity_id=None))
        assert extract_cu_frame_context(u1)["grounded_subject_ref"] is None
        assert check_scout_no_repeated_rows([u1, u2]) is None


class TestTitleFallbackGenuineRejectsAndZeroFalsePositives:
    def test_rejects_mixed_measures_without_cu_frames(self):
        # Box office + RT score + binary delayed
        err_movies = check_scout_single_measure_family(
            [
                _row(1, "Avengers: Doomsday: Rotten Tomatoes score"),
                _row(2, '"Avengers: Doomsday" Opening Weekend Box Office'),
                _row(3, "Will Dune: Part Three be delayed?"),
            ]
        )
        assert err_movies == "mixed_measure_families:review_score+box_office_gross+event_or_winner"

        # Timing ladder + physical quantity + RONI
        err_weather = check_scout_single_measure_family(
            [
                _row(1, "When will Big Bear Mountain Resort open for the 26/27 winter season?"),
                _row(2, "Mammoth Mountain snowfall total by December 24th"),
                _row(3, "How low will Lake Mead drop?"),
            ]
        )
        assert err_weather == "mixed_measure_families:timing_ladder+physical_quantity"

        # #1 search vs Top 5
        err_search = check_scout_single_measure_family(
            [
                _row(1, "#1 Searched Person on Google 2026?"),
                _row(2, "Top 5 Most Searched Movies on Google 2026"),
            ]
        )
        assert err_search == "mixed_measure_families:event_or_winner+ranked_position"

    def test_rejects_restated_duplicates_and_ordinal_siblings_without_false_positives(self):
        # Genuine TIME restatement duplicate
        dup_err = check_scout_no_repeated_rows(
            [
                _row(1, "TIME Person of the Year 2026"),
                _row(2, "Will a single person become TIME's 2026 Person of the Year?"),
            ]
        )
        assert dup_err is not None and dup_err.startswith("repeated_row_")

        # Genuine #1 vs #2 Spotify sibling
        sib_err = check_scout_no_repeated_rows(
            [
                _row(1, "Top Spotify Artist 2026"),
                _row(2, "#2 Spotify Artist 2026"),
            ]
        )
        assert sib_err is not None and sib_err.startswith("repeated_row_ordinal_siblings:")

        # Zero false positives on distinct awards/categories/geographies/halftime props
        clean_awards = [
            _row(1, "Oscars 2027: Best Picture Winner"),
            _row(2, "Oscars 2027: Best Actor Winner"),
            _row(3, "Oscars 2027: Best Supporting Actor Winner"),
            _row(4, "Oscars 2027: Best Actress Winner"),
        ]
        assert check_scout_single_measure_family(clean_awards) is None
        assert check_scout_no_repeated_rows(clean_awards) is None

        clean_game_awards = [
            _row(1, "The Game Awards: Game of the Year"),
            _row(2, "The Game Awards: Best Game Direction"),
            _row(3, "The Game Awards: Best Narrative"),
            _row(4, "The Game Awards: Best Audio Design"),
        ]
        assert check_scout_single_measure_family(clean_game_awards) is None
        assert check_scout_no_repeated_rows(clean_game_awards) is None

        clean_distinct_props = [
            _row(1, "TIME Person of the Year 2026"),
            _row(2, "Time's Person of the Decade"),
            _row(3, "Top Spotify Artist 2026"),
            _row(4, "Top US Spotify Artist 2026"),
        ]
        assert check_scout_single_measure_family(clean_distinct_props) is None
        assert check_scout_no_repeated_rows(clean_distinct_props) is None

        clean_halftime = [
            _row(1, "Who will be in the 2027 Big Game halftime show?"),
            _row(2, "What songs will be played at the 2027 Big Game halftime show?"),
            _row(3, "First song at 2027 Big Game Halftime Show?"),
            _row(4, "Last song at 2027 Big Game Halftime Show?"),
        ]
        assert check_scout_single_measure_family(clean_halftime) is None
        assert check_scout_no_repeated_rows(clean_halftime) is None


class TestRowContext196AAndSelectionExplainer:
    def test_row_context_196a_requires_text_iso_date_and_source_and_never_uses_frame_value(self):
        valid = _row(
            1,
            "US gas price above $4.50?",
            market_metadata=_cu_meta(
                measure="price_high",
                value="4.50",
                unit="$",
                row_context={"text": "Today: $3.62/gal", "as_of": "2026-11-23", "source": "AAA"},
            ),
        )
        assert build_row_context_line(valid) == {
            "text": "Today: $3.62/gal",
            "as_of": "2026-11-23",
            "source": "AAA",
            "kind": "spot_reading",
        }
        # Never synthesizes real-world reading from discover_llm.frame.value when row_context is absent
        frame_only = _row(
            2,
            "US gas price above $4.50?",
            market_metadata=_cu_meta(measure="price_high", value="4.50", unit="$"),
        )
        assert build_row_context_line(frame_only) is None
        assert not validate_row_context_196a({"text": "Today: $3.62", "as_of": "Nov 23", "source": "AAA"})
        assert not validate_row_context_196a({"text": "Today: $3.62", "as_of": "2026-11-23", "source": ""})

    def test_selection_explainer_and_scout_rule_file_wiring(self):
        partial = build_set_selection_explainer(shown_count=4, pool_size=12, slug="machinery-prices")
        assert partial["why_these"] == "Top 4 by trading volume out of 12 open markets in this group"
        assert partial["see_rest_label"] == "See all 12 markets"
        assert partial["see_rest_href"] == "/collections/machinery-prices"

        full = build_set_selection_explainer(shown_count=4, pool_size=4, slug="machinery-prices")
        assert full["see_rest_href"] is None

        catalog = {
            1: _row(1, "Oscars 2027: Best Picture Winner"),
            2: _row(2, "Oscars 2027: Best Actor Winner"),
            3: _row(3, "Oscars 2027: Best Actress Winner"),
        }
        prop = ScoutProposedSet(
            slug="oscar-night-clean",
            name="Oscar Night Winners",
            kicker="MOVIES",
            category="movies",
            why_better_together="Best Picture, Best Actor, and Best Actress winners all decided on the same night.",
            look="bars",
            member_ids=(1, 2, 3),
        )
        vset, err = validate_scout_proposed_set(prop, catalog, now=FROZEN_NOW)
        assert err is None and vset is not None
        rule_def = build_scout_rule_file_definition(vset, model_used="claude-opus-5-5", created_at=FROZEN_NOW)
        assert rule_def["scout"]["selection_explainer"]["shown_count"] == 3


def test_blind_40_v2_deck_schema_blindness_and_no_key_in_repo():
    raw = DECK_V2_PATH.read_text(encoding="utf-8")
    deck = json.loads(raw)

    assert deck["deck_id"] == "discover-blind-40-v2-2026-11-23"
    assert deck["seed"] == 2026112302
    assert deck["card_count"] == 40
    assert deck["blind"] is True
    assert deck["grade_options"] == ["Keep", "Fix", "Drop"]
    assert "key_sha256" not in deck
    assert len(deck["sealed_checksum_sha256"]) == 64

    lower = raw.lower()
    for token in FULL_LEAK_TOKENS:
        assert token not in lower, f"Leaked provenance token {token!r} in Blind Deck v2"

    cards = deck["cards"]
    assert len(cards) == 40
    assert [c["card_id"] for c in cards] == [f"blind-{idx:02d}" for idx in range(1, 41)]
    expected_keys = {"card_id", "title", "kicker", "category", "summary", "look", "members", "grade_options"}

    for card in cards:
        assert set(card.keys()) == expected_keys
        assert card["grade_options"] == ["Keep", "Fix", "Drop"]
        assert card["kicker"] == card["category"].upper()
        assert card["look"] in {"bars", "faces", "map"}
        assert 3 <= len(card["members"]) <= 6
        text = " ".join([card["title"], card["kicker"], card["summary"]]).lower()
        assert "opus" not in text and "sonnet" not in text
        assert not BANNED_VOICE_RE.search(text)
        seen_ids = set()
        for m in card["members"]:
            assert set(m.keys()) == {"market_id", "source", "title"}
            assert isinstance(m["market_id"], int) and m["market_id"] > 0
            assert m["market_id"] not in seen_ids
            seen_ids.add(m["market_id"])
            assert m["source"] in {"kalshi", "polymarket"}
            assert m["title"].strip()

    # Sealed v2 key must remain outside the repository until Alex freezes grades.
    leaked = list(DATA_DIR.rglob("*v2_key*")) + list(DATA_DIR.rglob("*blind_40_v2_key*"))
    assert leaked == [], f"Blind Deck v2 key must never exist in repo: {leaked}"
    assert audit_sets_13544([])["total_sets"] == 0
