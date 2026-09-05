"""#1854 — a range served beside a probability must contain that probability.

## The defect

`current_odds.home_probability` became the multi-source BLEND in #1829 (UX-P072).
`current_odds.probability_range` stayed what it had always been: the SPORTSBOOK
consensus min/max. Nothing recomputed it, so the two disagreed in the same object.

Measured on production `1ac0aa08` / v3805, 2026-08-13:

| event | status | `home_probability` | `probability_range` | in range? |
|---|---|---|---|---|
| 15191315 | live | 0.2813 | 0.6117 – 0.626 | **no** |
| 15196976 | completed | 0.999 | 0.426 – 0.9901 | **no** |

The range always contained the *betting* value and never the value it was served
beside. It was typed on both clients (`lib/types.ts`, iOS `CommonTypes.swift`) and
rendered by neither — so it was not a live lie, it was a loaded gun for whoever
rendered it next, who would have drawn a hero outside its own envelope and had
every reason to believe the payload.

## The ruling, and why the fix is REMOVAL

Alex, 2026-08-14: re-derive it from the blend, or remove it — *"a stated range the
served number sits outside is worse than no range"*, and coherent-by-accident is
not a third option.

Removal, because re-deriving would ship a source-divergence display: the standing
ruling is that **the blend is the product** — divergence is a data bug to fix, not
a feature to show, outside a short closed list of comparison surfaces the general
event payload is not on.

## The shape of the guard

Not "the field is gone from line N" — that dies the moment the code moves, and it
says nothing about the next payload someone adds a range to. The assertion is the
INVARIANT, applied recursively to the whole served object: **anywhere a dict
carries both a probability and a range, the probability is inside the range.**
That covers the three sites deliberately KEPT (the live-odds object and the two
odds-history buckets, whose numbers ARE the sportsbook aggregate and are therefore
bounded by their own min/max) and it fails if a hero payload grows one again.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import _format_event_with_aggregated_odds


# ---------------------------------------------------------------------------
# The invariant, as a reusable check
# ---------------------------------------------------------------------------


def find_range_violations(payload, path="$"):
    """Every place a range excludes the probability it is served beside.

    Recursive on purpose: the point is to police the SHAPE wherever it occurs,
    not one line in one route.
    """
    violations = []
    if isinstance(payload, dict):
        rng = payload.get("probability_range")
        prob = payload.get("home_probability")
        if isinstance(rng, dict) and prob is not None:
            lo, hi = rng.get("min"), rng.get("max")
            if lo is not None and hi is not None and not (lo <= prob <= hi):
                violations.append(
                    f"{path}: home_probability {prob} outside stated range {lo}-{hi}"
                )
        for k, v in payload.items():
            violations.extend(find_range_violations(v, f"{path}.{k}"))
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            violations.extend(find_range_violations(v, f"{path}[{i}]"))
    return violations


# ---------------------------------------------------------------------------
# Fixtures — the production numbers from #1854
# ---------------------------------------------------------------------------

#: Event 15191315's real disagreement: a blend of 0.2813 with sportsbooks at
#: 0.6117-0.626. Reproduced rather than invented, because the whole defect was a
#: gap between two numbers that a hand-picked pair would close by accident.
BLEND = 0.2813
BOOK_MIN = 0.6117
BOOK_MAX = 0.626
BOOK_CONSENSUS = 0.6212


def _event():
    return SimpleNamespace(
        id=15191315,
        external_id="odds-api-15191315",
        sport=SimpleNamespace(key="baseball_mlb"),
        home_team_name="Minnesota Twins",
        away_team_name="Philadelphia Phillies",
        commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        completed_at=None,
        status="live",
        home_score=1,
        away_score=5,
        # live/073: `_format_event` reads the per-set line out of here. A fake
        # missing a column the formatter reads is not a lighter fixture, it is
        # a fake that cannot tell whether the formatter works.
        box_score_data=None,
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        llm_importance=None,
        espn_id=None,
        period=None,
        game_clock=None,
        broadcast_info=None,
        espn_win_prob_home=None,
        win_probability_sources={
            "espn": {"value": BLEND, "display_name": "ESPN", "type": "model"},
        },
        raw_ei=None,
        ei_metadata=None,
        opening_home_probability=None,
        opening_away_probability=None,
        opening_home_spread=None,
        opening_over_under=None,
        opening_favorite=None,
        closing_home_probability=None,
        closing_away_probability=None,
        odds_snapshots=[],
        standings_context=None,
    )


def _odds_data():
    return {
        "captured_at": datetime.now(timezone.utc),
        "aggregated": {
            "home_probability": BOOK_CONSENSUS,
            "away_probability": round(1 - BOOK_CONSENSUS, 4),
            "home_spread": -1.5,
            "over_under": 8.5,
            "projected_home_score": 4.0,
            "projected_away_score": 5.5,
            "bookmaker_count": 7,
            "min_home_probability": BOOK_MIN,
            "max_home_probability": BOOK_MAX,
        },
        "snapshots": [],
        "all_snapshots": [],
    }


# ---------------------------------------------------------------------------


class TestTheServedPayload:
    def test_the_hero_is_the_blend_not_the_sportsbook(self):
        """Precondition, stated first so the real assertion cannot pass for the
        wrong reason (gotcha #127). If the hero silently reverted to the
        sportsbook consensus, a coherence check would pass while #1829 was
        broken again."""
        out = _format_event_with_aggregated_odds(_event(), _odds_data())
        assert out["current_odds"]["home_probability"] == pytest.approx(BLEND)
        assert out["current_odds"]["home_probability"] != pytest.approx(BOOK_CONSENSUS)

    def test_no_range_excludes_the_probability_it_sits_beside(self):
        """THE INVARIANT. Recursive over the whole payload, so it also covers any
        range a future queue adds anywhere in this object."""
        out = _format_event_with_aggregated_odds(_event(), _odds_data())
        assert find_range_violations(out) == []

    def test_the_hero_object_states_no_range_at_all(self):
        """The chosen resolution, pinned: removed, not re-derived.

        Kept separate from the invariant above deliberately — a re-derived
        envelope would satisfy the invariant while shipping the
        source-divergence display the blend ruling refuses. This is the test
        that fails if someone 'fixes' it the other way without a new ruling.
        """
        out = _format_event_with_aggregated_odds(_event(), _odds_data())
        assert "probability_range" not in out["current_odds"]

    def test_the_sportsbook_numbers_are_still_served(self):
        """The other direction (gotcha #43): removing the range must not have
        removed the sportsbook data the range was drawn from. Spread, total,
        projections and the book count are real sportsbook facts and stay."""
        odds = _format_event_with_aggregated_odds(_event(), _odds_data())["current_odds"]
        assert odds["spread"] == -1.5
        assert odds["over_under"] == 8.5
        assert odds["bookmaker_count"] == 7


class TestTheCheckItself:
    """A guard that cannot fail is worse than no guard (#127). Prove it fires."""

    def test_it_catches_the_production_disagreement(self):
        poisoned = {
            "current_odds": {
                "home_probability": BLEND,
                "probability_range": {"min": BOOK_MIN, "max": BOOK_MAX},
            }
        }
        violations = find_range_violations(poisoned)
        assert len(violations) == 1
        assert "0.2813" in violations[0]

    def test_it_accepts_a_range_that_bounds_its_own_number(self):
        """The three sites UX-P077 deliberately KEPT: the live-odds object and
        the two odds-history buckets, whose `home_probability` IS the sportsbook
        aggregate and is therefore inside the sportsbook min/max."""
        coherent = {
            "home_probability": BOOK_CONSENSUS,
            "probability_range": {"min": BOOK_MIN, "max": BOOK_MAX},
        }
        assert find_range_violations(coherent) == []

    def test_it_looks_inside_lists(self):
        nested = {"history": [{"home_probability": 0.1,
                               "probability_range": {"min": 0.5, "max": 0.6}}]}
        assert len(find_range_violations(nested)) == 1

    def test_a_null_bound_is_not_a_violation(self):
        """An unmeasured bound is absence, not a failed comparison."""
        assert find_range_violations(
            {"home_probability": 0.3, "probability_range": {"min": None, "max": None}}
        ) == []
