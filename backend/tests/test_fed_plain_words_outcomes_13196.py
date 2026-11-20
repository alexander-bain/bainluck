"""Tests for #13196: plain-English Fed/central-bank rate outcome display names everywhere.

Verifies:
1. Single shared mapping (`plain_rate_outcome.plain_rate_outcome_label`) used by both
   `series_card_labels.reader_outcome_name` (pages, cards, widgets, Watch, search)
   and `container_machinery._clean_outcome_label` (groupings).
2. Market 57574217 ("Fed Decision in January?") exact outcomes map cleanly with zero "bps":
   - "25 bps increase"  -> "Quarter-point increase"
   - "50+ bps increase" -> "Half-point or larger increase"
   - "25 bps decrease"  -> "Quarter-point cut"
   - "50+ bps decrease" -> "Half-point or larger cut"
   - "No change"        -> "No change"
3. Kalshi prefix forms ("Hike 25bps", "Hike >25bps", "Cut 25bps", "Cut >25bps") and
   count-with-bps forms ("0 (0 bps)", "1 (25 bps)", "5+ (125+ bps)") map cleanly,
   respecting rate-cuts vs rate-hikes market titles.
4. Stored `FuturesOutcome.name` stays untouched for matching.
5. Signed rate-ladder ordering in `discover_card_archetypes` preserves exact order
   (-50 below, -25, 0, +25, +50 above) on the formatted plain-English labels.
6. Economics dashboard `_leader_name` and `_brackets_from_outcomes` emit plain words,
   zero "bps".
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.routes.economics import _brackets_from_outcomes, _leader_name
from app.utils.container_machinery import _clean_outcome_label
from app.utils.discover_card_archetypes import (
    _ladder_axis_is_signed,
    _outcome_threshold_value,
    _threshold_points,
)
from app.utils.plain_rate_outcome import plain_rate_outcome_label
from app.utils.series_card_labels import reader_outcome_name


_BPS_RE = re.compile(r"\bbps\b|(?<=\d)bps\b|\bbasis\s+points?\b", re.IGNORECASE)


def test_57574217_outcomes_match_grouping_card_wording():
    cases = {
        "25 bps increase": "Quarter-point increase",
        "50+ bps increase": "Half-point or larger increase",
        "25 bps decrease": "Quarter-point cut",
        "50+ bps decrease": "Half-point or larger cut",
        "No change": "No change",
    }
    for raw, expected in cases.items():
        served = reader_outcome_name(None, raw, market_name="Fed Decision in January?") or raw
        grouped = _clean_outcome_label(raw)
        assert served == expected
        assert grouped == expected
        assert not _BPS_RE.search(served)


def test_kalshi_prefix_bps_forms_map_identically():
    cases = {
        "Hike 25bps": "Quarter-point increase",
        "Hike >25bps": "Half-point or larger increase",
        "Cut 25bps": "Quarter-point cut",
        "Cut >25bps": "Half-point or larger cut",
        "Hike 25 bps": "Quarter-point increase",
        "Cut 50+ bps": "Half-point or larger cut",
    }
    for raw, expected in cases.items():
        served = reader_outcome_name(None, raw, market_name="Fed decision in Dec 2026?") or raw
        assert served == expected
        assert _clean_outcome_label(raw) == expected
        assert not _BPS_RE.search(served)


def test_count_bps_paren_respects_cuts_vs_hikes_and_removes_bps():
    cuts_title = "How many Fed rate cuts in 2026?"
    hikes_title = "How many Fed rate hikes in 2026?"

    assert reader_outcome_name(None, "0 (0 bps)", market_name=cuts_title) == "0 cuts"
    assert reader_outcome_name(None, "1 (25 bps)", market_name=cuts_title) == "1 cut (quarter point)"
    assert reader_outcome_name(None, "2 (50 bps)", market_name=cuts_title) == "2 cuts (half point)"
    assert reader_outcome_name(None, "3 (75 bps)", market_name=cuts_title) == "3 cuts (three-quarter point)"
    assert reader_outcome_name(None, "4 (100 bps)", market_name=cuts_title) == "4 cuts (full point)"
    assert reader_outcome_name(None, "5+ (125+ bps)", market_name=cuts_title) == "5+ cuts (1.25 points or more)"

    assert reader_outcome_name(None, "0 (0 bps)", market_name=hikes_title) == "0 hikes"
    assert reader_outcome_name(None, "1 (25 bps)", market_name=hikes_title) == "1 hike (quarter point)"
    assert reader_outcome_name(None, "5+ (125+ bps)", market_name=hikes_title) == "5+ hikes (1.25 points or more)"

    # Without market direction context, neutral plain words (never mislabels cuts as hikes)
    assert reader_outcome_name(None, "1 (25 bps)") == "1 (quarter point)"
    assert reader_outcome_name(None, "0 (0 bps)") == "0"
    assert not _BPS_RE.search(reader_outcome_name(None, "5+ (125+ bps)") or "")


def test_non_bps_outcomes_are_untouched():
    for raw in ("Yes", "No", "No change", "Hold", "Los Angeles Lakers", "Over 2.5 goals", "Above 4.25%"):
        assert plain_rate_outcome_label(raw) is None


def test_plain_rate_labels_preserve_signed_ladder_order_on_discover_card():
    outcomes = [
        {"name": "Quarter-point increase", "probability": 0.57},
        {"name": "No change", "probability": 0.40},
        {"name": "Half-point or larger increase", "probability": 0.013},
        {"name": "Quarter-point cut", "probability": 0.012},
        {"name": "Half-point or larger cut", "probability": 0.007},
    ]
    labels = [o["name"] for o in outcomes]
    assert _ladder_axis_is_signed(labels) is True
    assert _outcome_threshold_value("Quarter-point increase") == (25.0, "bps", "exact")
    assert _outcome_threshold_value("Half-point or larger increase") == (50.0, "bps", "above")
    assert _outcome_threshold_value("Quarter-point cut") == (25.0, "bps", "exact")
    assert _outcome_threshold_value("Half-point or larger cut") == (50.0, "bps", "above")

    points = _threshold_points(
        name="Fed Decision in January?",
        outcomes=outcomes,
        outcome_count=len(outcomes),
    )
    served_labels = [row["label"] for row in points]
    assert served_labels == [
        "Half-point or larger cut",
        "Quarter-point cut",
        "No change",
        "Quarter-point increase",
        "Half-point or larger increase",
    ]
    for lbl in served_labels:
        assert not _BPS_RE.search(lbl)


def test_economics_route_helpers_emit_plain_words_and_keep_raw_orm_name():
    o1 = SimpleNamespace(
        id=1, name="25 bps increase", current_probability=0.57, rank=1,
        is_winner=None, resolution_source=None,
    )
    o2 = SimpleNamespace(
        id=2, name="No change", current_probability=0.40, rank=2,
        is_winner=None, resolution_source=None,
    )
    o3 = SimpleNamespace(
        id=3, name="50+ bps decrease", current_probability=0.03, rank=3,
        is_winner=None, resolution_source=None,
    )
    market = SimpleNamespace(
        id=57574217,
        name="Fed Decision in January?",
        mutually_exclusive=True,
        outcomes=[o1, o2, o3],
    )
    assert _leader_name(market, o1, [o1, o2, o3]) == "Quarter-point increase"
    brackets = _brackets_from_outcomes(market)
    names = [row[1] for row in brackets]
    assert "Quarter-point increase" in names
    assert "Half-point or larger cut" in names
    assert all(not _BPS_RE.search(n) for n in names)
    # Raw stored ORM names remain untouched for matching
    assert o1.name == "25 bps increase"
    assert o3.name == "50+ bps decrease"


def test_feed_card_helpers_emit_plain_words_and_keep_raw_keys():
    from app.routes.feed import _card_display_names, _card_outcome_name

    o1 = SimpleNamespace(id=213618739, external_id="poly-1", name="25 bps increase")
    o2 = SimpleNamespace(id=213618736, external_id="poly-2", name="50+ bps increase")
    o3 = SimpleNamespace(id=213618737, external_id="poly-3", name="25 bps decrease")
    o4 = SimpleNamespace(id=213618735, external_id="poly-4", name="50+ bps decrease")
    o5 = SimpleNamespace(id=213618738, external_id="poly-5", name="No change")

    assert _card_outcome_name(o1) == "Quarter-point increase"
    display = _card_display_names([o1, o2, o3, o4, o5])
    assert display == {
        "25 bps increase": "Quarter-point increase",
        "50+ bps increase": "Half-point or larger increase",
        "25 bps decrease": "Quarter-point cut",
        "50+ bps decrease": "Half-point or larger cut",
        "No change": "No change",
    }
    assert all(not _BPS_RE.search(v) for v in display.values())
    # Raw ORM names untouched for matching
    assert o1.name == "25 bps increase"


def test_remaining_eight_live_range_and_more_than_forms_plus_strict_gt():
    """#13196 follow-up (Item 6): Israel/Russia/Thailand/Turkey range & 'more than' forms,
    plus strict '>' never collapsing into 'or larger'."""
    cases = {
        "Cut 1-25bps": "Cut of up to a quarter point",
        "Hike 1-25bps": "Increase of up to a quarter point",
        "Cut more than 25bps": "Cut of more than a quarter point",
        "Hike more than 25bps": "Increase of more than a quarter point",
        "Cut 1-250bps": "Cut of up to 2.5 points",
        "Hike 1-250bps": "Increase of up to 2.5 points",
        "Cut more than 250bps": "Cut of more than 2.5 points",
        "Hike more than 250bps": "Increase of more than 2.5 points",
        # Strict '>' outside the FOMC >25bps special case must say "more than", never "or larger"
        "Cut >50bps": "Cut of more than a half point",
        "Hike >50bps": "Increase of more than a half point",
        "Cut >250bps": "Cut of more than 2.5 points",
        ">50 bps cut": "Cut of more than a half point",
        # Inclusive operators keep "or larger"
        "Cut >=50bps": "Half-point or larger cut",
        "Hike 50+ bps": "Half-point or larger increase",
        # FOMC 25-bps grid special case preserved (Ruling 244: A)
        "Hike >25bps": "Half-point or larger increase",
        "Cut >25bps": "Half-point or larger cut",
    }
    for raw, expected in cases.items():
        got = plain_rate_outcome_label(raw)
        assert got == expected, f"{raw!r} -> {got!r} != {expected!r}"
        assert not _BPS_RE.search(got)

    # Signed threshold parser recognizes the new "of up to / of more than" forms
    from app.utils.plain_rate_outcome import parse_plain_rate_threshold

    assert parse_plain_rate_threshold("Cut of up to a quarter point") == (25.0, "bps", "exact")
    assert parse_plain_rate_threshold("Cut of more than a quarter point") == (25.0, "bps", "above")
    assert parse_plain_rate_threshold("Increase of up to 2.5 points") == (250.0, "bps", "exact")
    assert parse_plain_rate_threshold("Increase of more than 2.5 points") == (250.0, "bps", "above")

