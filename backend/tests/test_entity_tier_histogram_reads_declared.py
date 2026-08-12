"""The tier histogram must REPORT what the route declared (#1776 finding 2).

## The defect this pins

`entity_tier_histogram` re-ran `resolve_entity_tier` over the payload's
`sections` and reported THAT as the tier. But a route resolves over its own
census, which is a documented superset: `league_futures` adds `championship`
(the grid) and `games` (the upcoming rail), because Alex's amendment counts event
content as populated sections.

Two different inputs, so the two numbers were never answers to the same question.
Measured against production on 2026-08-11:

    histogram reported   T3 = 0   T0 = 0   no_page = 7
    routes declared      T3 = 6   T0 = 3   no_page = 3

Three cycles of findings were read off the wrong column — including "two tiers
are unreachable for the whole class", which was an artifact — and Alex's open
§11 threshold decision was scheduled against it.

Worse, the disagreement detector failed in the direction that mattered: it cried
`!! TIER DISAGREEMENT` on NBA (harmless — a boundary case) while reporting the
seven genuine ones silently as `no_page`, because a recompute that returns `None`
was indistinguishable from an entity with no page.

Spec §7 settles the ownership question: every count the page renders arrives in
the payload, and clients never derive it by measuring arrays. This script is a
client.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Load the script as a module — and REUSE a cached instance if one exists.
#
# The reuse is not tidiness. Cycle 63 shipped a suite whose plants reported
# GREEN because the tests held a different object than the one being patched, and
# a plant that cannot reach the code under test is indistinguishable from a
# passing suite. A file-spec load ALWAYS mints a fresh module, so an unconditional
# one would make this file permanently unauditable by the plant harness.
if "entity_tier_histogram" in sys.modules:
    hist = sys.modules["entity_tier_histogram"]
else:
    _SPEC = importlib.util.spec_from_file_location(
        "entity_tier_histogram",
        Path(__file__).resolve().parent.parent / "scripts" / "entity_tier_histogram.py",
    )
    hist = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(hist)
    sys.modules["entity_tier_histogram"] = hist

NOW = datetime(2026, 8, 11, 23, 0, tzinfo=timezone.utc)


def _row(prob=0.5, mid=1, canonical=None):
    return {
        "id": mid,
        "canonical_market_key": canonical or f"k{mid}",
        "top_outcomes": [{"probability": prob}],
    }


def _league_payload(*, tier, answers, dropped=0, settled=0, sections=None, games=0,
                    priced_games=0, record_n=0):
    """A league payload shaped as `league_futures.build_league` emits it."""
    return {
        "sport_key": "baseball_mlb",
        "sections": sections if sections is not None else {"awards": [_row()]},
        "tier": tier,
        "availability": "fresh",
        "pool_counts": {"answers": answers, "dropped": dropped, "settled": settled},
        "section_counts": {},
        "record_n": record_n,
        "upcoming_games": [
            {"id": i, "home_win_probability": (0.6 if i < priced_games else None)}
            for i in range(games)
        ],
    }


@pytest.fixture
def fake_get(monkeypatch):
    """Patch the name the MEASURER resolves, not the one we imported.

    Standing note 4 from cycle 63, applied: the suite that missed two planted
    defects did so because it patched a module attribute the code under test had
    already bound. `measure_league` calls the module-global `_get`, so that is
    what has to move.
    """
    box = {}

    def _install(payload):
        box["payload"] = payload
        monkeypatch.setattr(hist, "_get", lambda url, timeout=30.0: box["payload"])

    return _install


class TestTheDeclaredTierIsTheVerdict:
    def test_reports_what_the_route_declared_not_a_recompute(self, fake_get):
        """MLB: the route declares full; card sections alone are only worth T2.

        This is the exact production case. Before #1776 the row said `standard`
        and the class histogram said `T3 = 0`.
        """
        fake_get(_league_payload(tier="full", answers=53, dropped=61,
                                 sections={"awards": [_row(mid=i) for i in range(8)]},
                                 games=8))
        out = hist.measure_league("http://x", "baseball_mlb", now=NOW)

        assert out["tier"] == "full"
        assert out["tier_source"] == "declared"
        assert out["answers"] == 53
        # And the recompute survives as CONTEXT, visibly smaller.
        assert out["cards_tier"] == "standard"
        assert out["cards_answers"] < out["answers"]

    def test_declared_counts_are_read_not_recounted(self, fake_get):
        """`pool_counts` is the clause-3 counter. Re-deriving it from the array
        would under-report every drop the route already tallied."""
        fake_get(_league_payload(tier="full", answers=42, dropped=69, settled=3))
        out = hist.measure_league("http://x", "basketball_nba", now=NOW)
        assert (out["answers"], out["dropped"], out["settled"]) == (42, 69, 3)

    def test_a_T0_league_with_fixtures_is_present_not_no_page(self, fake_get):
        """Serie A, measured: 0 markets, 8 fixtures, route declares `present`.

        The recompute called this `None` and the report filed it under `no_page`
        — which reads as "this league has no page at all" when it has one, with
        eight real fixtures on it.
        """
        fake_get(_league_payload(tier="present", answers=0, dropped=8,
                                 sections={}, games=8))
        out = hist.measure_league("http://x", "soccer_italy_serie_a", now=NOW)
        assert out["tier"] == "present"
        assert out["tier_source"] == "declared"


class TestTheFallbackIsVisible:
    def test_a_route_that_declares_nothing_falls_back_AND_says_so(self, fake_get):
        """An unlabelled fallback is how the recompute became the headline."""
        payload = _league_payload(tier="full", answers=9)
        del payload["tier"]
        del payload["pool_counts"]
        fake_get(payload)

        out = hist.measure_league("http://x", "baseball_mlb", now=NOW)
        assert out["tier_source"] == "recomputed_fallback"
        assert out["tier"] == out["cards_tier"]

    def test_a_partial_envelope_is_treated_as_undeclared(self, fake_get):
        """`tier` without `pool_counts` is half an envelope; mixing a declared
        tier with recomputed counts is the two-graders bug in miniature."""
        payload = _league_payload(tier="full", answers=9)
        del payload["pool_counts"]
        fake_get(payload)
        assert hist.measure_league("http://x", "x", now=NOW)["tier_source"] == "recomputed_fallback"


class TestTheGamesColumn:
    def test_counts_how_many_fixtures_carry_a_probability(self, fake_get):
        """#1776's first half, made visible in the instrument.

        `prc` 0 against `gm` 8 is the signature of the games amendment being
        inert — which is what made the census look frozen for three cycles.
        """
        fake_get(_league_payload(tier="full", answers=53, games=8, priced_games=3))
        out = hist.measure_league("http://x", "baseball_mlb", now=NOW)
        assert out["upcoming"] == 8
        assert out["upcoming_priced"] == 3

    def test_zero_priced_is_reported_as_zero_not_omitted(self, fake_get):
        fake_get(_league_payload(tier="present", answers=0, sections={}, games=8))
        out = hist.measure_league("http://x", "soccer_italy_serie_a", now=NOW)
        assert out["upcoming"] == 8
        assert out["upcoming_priced"] == 0


class TestTheReportShape:
    def test_no_page_counts_only_routes_that_declare_no_tier(self, monkeypatch):
        declared = _league_payload(tier="present", answers=0, sections={}, games=8)
        undeclared = _league_payload(tier="full", answers=0, sections={})
        del undeclared["tier"]
        del undeclared["pool_counts"]

        seq = iter([declared, undeclared])
        monkeypatch.setattr(hist, "_get", lambda url, timeout=30.0: next(seq))
        monkeypatch.setitem(
            hist.CLASS_MEASURERS["league"], "keys", lambda: ["a", "b"]
        )
        monkeypatch.setitem(hist.CLASS_MEASURERS["league"], "unmeasurable", lambda: [])

        rep = hist.run("http://x", ["league"], now=NOW)["classes"]["league"]
        assert rep["histogram"]["present"] == 1
        # The undeclared one recomputes to None over empty sections -> no_page,
        # but it must ALSO be named as undeclared rather than silently bucketed.
        assert rep["undeclared"] == ["b"]

    def test_census_gap_is_reported_as_a_gap_not_a_disagreement(self, monkeypatch):
        """The rename is the point. These are not two graders fighting; they are
        one grader and one partial view, and calling it a disagreement sent a
        cycle chasing a parity bug that did not exist."""
        # 8 card rows in one section: enough answers for T2, never T3 (which
        # needs 3 populated sections). The declared `full` therefore MUST be
        # coming from content this side cannot see — which is the gap.
        payload = _league_payload(
            tier="full", answers=53, games=8,
            sections={"awards": [_row(mid=i) for i in range(8)]},
        )
        monkeypatch.setattr(hist, "_get", lambda url, timeout=30.0: payload)
        monkeypatch.setitem(hist.CLASS_MEASURERS["league"], "keys", lambda: ["a"])
        monkeypatch.setitem(hist.CLASS_MEASURERS["league"], "unmeasurable", lambda: [])

        rep = hist.run("http://x", ["league"], now=NOW)["classes"]["league"]
        assert "tier_disagreements" not in rep
        assert rep["census_gap"] and rep["census_gap"][0]["declared"] == "full"
        assert rep["census_gap"][0]["cards_only"] == "standard"

    def test_render_does_not_crash_on_a_mixed_report(self, monkeypatch):
        payload = _league_payload(tier="full", answers=53, games=8, priced_games=1)
        monkeypatch.setattr(hist, "_get", lambda url, timeout=30.0: payload)
        monkeypatch.setitem(hist.CLASS_MEASURERS["league"], "keys", lambda: ["a"])
        monkeypatch.setitem(hist.CLASS_MEASURERS["league"], "unmeasurable", lambda: [])
        text = hist.render(hist.run("http://x", ["league"], now=NOW))
        assert "rests on content beyond the card sections" in text
        assert "gm" in text and "prc" in text
