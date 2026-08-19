"""The census measures TWO windows, and the difference between them is the point.

`boring-rate@20` has always meant "filter the payload to futures, take the first
twenty". The served payload interleaves bundle/concept/tournament cards, so the
twentieth *futures* card can be the twenty-fourth *card*. Measured on production
2026-08-19: the served top-20 carried 4–6 bundles, every card the futures window
flagged sat at served position 22–24, and the server's own
`debug_summary.boring_count` read 0 over the same payload the futures window
scored 2. Both numbers were right about their own window; only one of them
describes a screen.

These tests pin that both are reported, that neither is quietly renamed into the
other, and that the offset between them is recorded as a measurement rather than
asserted in prose.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.census_boring_rate import _classify  # noqa: E402

# A card the shipped classifier calls low_quality on name alone: a dated equity
# ladder. Used because it is the real 2026-08-19 specimen.
LADDER = "Will Meta (META) close above $540 on August 19?"


def _futures(name: str, market_id: int) -> dict:
    return {
        "type": "futures",
        "data": {
            "name": name,
            "market_id": market_id,
            "id": market_id,
            "category": "economics",
            "outcomes": [{"name": "Yes", "probability": 0.42}],
        },
    }


def _bundle(idx: int) -> dict:
    return {"type": "bundle", "data": {"name": f"Bundle {idx}", "id": 9000 + idx}}


def _payload(items: list[dict]) -> dict:
    return {"items": items}


def test_a_ladder_past_the_served_fold_counts_in_one_window_and_not_the_other():
    """The exact production shape: 5 bundles up top push the ladder to slot 22."""
    items = [_bundle(i) for i in range(5)]
    items += [_futures(f"Clean market {i}?", i) for i in range(16)]
    items += [_futures(LADDER, 500)]
    items += [_futures(f"Tail market {i}?", 600 + i) for i in range(10)]

    result = _classify(_payload(items), ground_truth_items=[])

    # futures-only window: the ladder is the 17th futures card -> inside 20.
    assert result["boring_count"] == 1
    assert [b["name"] for b in result["boring"]] == [LADDER]

    # served window: slots 1-20 are 5 bundles + the first 15 clean futures.
    assert result["served_window_size"] == 20
    assert result["served_futures_in_window"] == 15
    assert result["non_futures_in_served_window"] == 5
    assert result["served_boring_count"] == 0
    assert result["served_boring"] == []


def test_a_ladder_inside_the_served_fold_counts_in_both_windows():
    """The other direction — the served window must not be a way to report zero."""
    items = [_bundle(0)]
    items += [_futures(LADDER, 500)]
    items += [_futures(f"Clean market {i}?", i) for i in range(30)]

    result = _classify(_payload(items), ground_truth_items=[])

    assert result["boring_count"] == 1
    assert result["served_boring_count"] == 1
    assert [b["name"] for b in result["served_boring"]] == [LADDER]
    assert result["non_futures_in_served_window"] == 1


def test_with_no_bundles_the_two_windows_agree():
    """No interleaving, no offset — the discrepancy must be caused by the cause."""
    items = [_futures(f"Clean market {i}?", i) for i in range(19)]
    items += [_futures(LADDER, 500)]

    result = _classify(_payload(items), ground_truth_items=[])

    assert result["non_futures_in_served_window"] == 0
    assert result["boring_count"] == result["served_boring_count"] == 1


def test_the_served_window_counts_slots_not_futures():
    """A bundle occupies a slot. It is not an offender and it is not invisible."""
    items = [_bundle(i) for i in range(12)]
    items += [_futures(f"Clean market {i}?", i) for i in range(30)]

    result = _classify(_payload(items), ground_truth_items=[])

    # The denominator is 20 SLOTS, not the 8 futures inside them: a page that is
    # mostly bundles has not thereby earned a smaller denominator.
    assert result["served_window_size"] == 20
    assert result["served_futures_in_window"] == 8
    assert result["non_futures_in_served_window"] == 12


def test_the_served_window_type_census_is_recorded():
    items = [_bundle(0), _bundle(1)]
    items += [{"type": "concept", "data": {"name": "A concept", "id": 1}}]
    items += [_futures(f"Clean market {i}?", i) for i in range(25)]

    result = _classify(_payload(items), ground_truth_items=[])

    assert result["served_window_types"] == {"bundle": 2, "concept": 1, "futures": 17}


def test_the_legacy_futures_window_keys_are_unchanged():
    """Prior cycles' artifacts and the pooler both key on these. Renaming a
    metric mid-series takes its own history with it."""
    items = [_futures(f"Clean market {i}?", i) for i in range(25)]

    result = _classify(_payload(items), ground_truth_items=[])

    for key in ("window_size", "boring_count", "boring", "short_window",
                "window_fingerprint", "futures_returned"):
        assert key in result, key
    assert result["window_size"] == 20


def test_a_short_served_page_reports_its_real_slot_count():
    items = [_bundle(0)] + [_futures(f"Clean market {i}?", i) for i in range(4)]

    result = _classify(_payload(items), ground_truth_items=[])

    assert result["served_window_size"] == 5
    assert result["short_window"] is True
