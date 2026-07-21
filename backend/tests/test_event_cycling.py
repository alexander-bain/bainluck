"""Cycling adapter pure-logic tests (Queue #223 Item 3 — The Tour).

Pure helpers (name gates, slug resolution, coherence gate, concept derivation) are
unit-tested here; build_event is exercised live against production after deploy
(mirrors the F1 adapter's route-test convention)."""

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import app.utils.event_cycling as ec


def _out(name, prob, updated=None):
    return SimpleNamespace(
        name=name,
        current_probability=prob,
        last_updated=updated,
        is_winner=False,
    )


def _mkt(mid, name, outcomes):
    return SimpleNamespace(id=mid, name=name, outcomes=outcomes, source="kalshi")


TDF = re.compile(r"tour\s+de\s+france", re.IGNORECASE)


class TestNameGates:
    def test_gc_winner_field(self):
        assert ec.is_gc_winner_field_market("Tour de France Winner", TDF)

    def test_stage_is_not_gc(self):
        assert not ec.is_gc_winner_field_market("Tour de France: Stage 3 Winner", TDF)

    def test_team_is_not_gc(self):
        assert not ec.is_gc_winner_field_market("Tour de France Team Winner", TDF)

    def test_wrong_race_name_rejected(self):
        assert not ec.is_gc_winner_field_market("Giro Winner", TDF)

    def test_secondary_classifications_are_not_gc(self):
        # The live bug: these passed the winner gate and a fresher sprinter market
        # was crowned GC leader over Pogačar. They must be props, not the GC.
        for nm in (
            "Tour de France: Green Jersey Winner",
            "Tour de France Points Classification Winner",
            "Tour de France: Polka Dot Jersey Winner",
            "Tour de France White Jersey Winner",
            "Tour de France Young Rider Winner",
            "Tour de France Most Aggressive Rider Winner",
        ):
            assert not ec.is_gc_winner_field_market(nm, TDF), nm
            assert ec.is_cycling_jersey_prop(nm), nm

    def test_bare_gc_winner_survives_exclusions(self):
        assert ec.is_gc_winner_field_market("Tour de France Winner", TDF)
        assert not ec.is_cycling_jersey_prop("Tour de France Winner")

    def test_stage_and_team_classifiers(self):
        assert ec.is_stage_market("Tour de France: Stage 10 Winner")
        assert not ec.is_stage_market("Tour de France Winner")
        assert ec.is_team_classification_market("Tour de France Team Winner")
        assert not ec.is_team_classification_market("Tour de France: Stage 3 Winner")

    def test_stage_number_extraction(self):
        assert ec._stage_number("Tour de France: Stage 11 Winner") == 11
        assert ec._stage_number("Tour de France Winner") == 9999


class TestSlugResolution:
    def test_canonical_and_alias(self):
        assert ec.parse_cycling_slug("tour-de-france-2026").display == "Tour de France 2026"
        assert ec.parse_cycling_slug("tdf").slug == "tour-de-france-2026"
        assert ec.parse_cycling_slug("nope-2099") is None

    def test_slug_year(self):
        assert ec._slug_year("tour-de-france-2026") == 2026
        assert ec._slug_year("tdf") is None


class TestDeriveConcept:
    def test_derives_from_gc_market(self):
        c = ec.derive_cycling_concept("x", "Tour de France Winner", "cycling")
        assert c == {
            "key": "event:cycling:tour-de-france-2026",
            "name": "Tour de France 2026",
            "domain": "cycling",
        }

    def test_stage_market_is_not_a_concept(self):
        assert ec.derive_cycling_concept("x", "Tour de France: Stage 3 Winner", "cycling") is None

    def test_non_cycling_category_rejected(self):
        assert ec.derive_cycling_concept("x", "Tour de France Winner", "golf") is None


class TestCoherenceGate:
    def test_real_field_selected(self):
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        gc = _mkt(
            1,
            "Tour de France Winner",
            [
                _out("Tadej Pogacar", 0.945, now),
                _out("Jonas Vingegaard", 0.045, now),
                _out("Isaac Del Toro", 0.01, now),
            ],
        )
        market, real = ec._select_gc_field([gc])
        assert market is gc
        assert len(real) == 3

    def test_broken_stale_field_falls_back_but_not_none(self):
        # A field whose real prices sum far below 100% (the "Peru 47%" class): the
        # coherence gate rejects it, but the richest-real fallback still returns it so
        # a real (if imperfect) field is never dropped to an empty page.
        gc = _mkt(
            1,
            "Tour de France Winner",
            [_out("Rider A", 0.08), _out("Rider B", 0.05), _out("Rider C", 0.02)],
        )
        market, real = ec._select_gc_field([gc])
        assert market is gc  # fallback engaged
        assert len(real) == 3

    def test_single_outcome_never_qualifies(self):
        gc = _mkt(1, "Tour de France Winner", [_out("Solo", 0.99)])
        market, real = ec._select_gc_field([gc])
        assert market is None and real == []

    def test_largest_field_wins_over_fresher_small_field(self):
        # GC (many riders) must beat a fresher secondary market with a small field.
        old = datetime(2026, 7, 1, tzinfo=timezone.utc)
        new = datetime(2026, 7, 21, tzinfo=timezone.utc)
        gc = _mkt(
            1,
            "Tour de France Winner",
            [_out("Pogacar", 0.6, old), _out("Vingegaard", 0.2, old), _out("Del Toro", 0.2, old)],
        )
        small_fresh = _mkt(
            2, "Tour de France Winner", [_out("Pedersen", 0.55, new), _out("Ghirmay", 0.45, new)]
        )
        market, real = ec._select_gc_field([small_fresh, gc])
        assert market is gc and len(real) == 3

    def test_freshest_coherent_wins(self):
        old = datetime(2026, 7, 1, tzinfo=timezone.utc)
        new = datetime(2026, 7, 21, tzinfo=timezone.utc)
        stale = _mkt(
            1, "Tour de France Winner", [_out("Pogacar", 0.6, old), _out("Vingegaard", 0.4, old)]
        )
        fresh = _mkt(
            2, "Tour de France Winner", [_out("Pogacar", 0.7, new), _out("Vingegaard", 0.3, new)]
        )
        market, _ = ec._select_gc_field([stale, fresh])
        assert market is fresh


class TestNormalizationGuard:
    """A heavily-overrounded independent-binary field (Kalshi 184-way GC) must NOT be
    normalized — the raw YES price is the honest per-rider win probability. Only a
    coherent ~100% field gets normalized. (Regression: Pogačar 94.5% -> false 34%.)"""

    def test_overrounded_field_keeps_raw(self):
        # Sum ~2.8 (overround) — keep raw, favorite stays a near-lock.
        comps = [
            {"probability": 0.945, "name": "Pogacar"},
            {"probability": 0.9, "name": "noise A"},
            {"probability": 0.9, "name": "noise B"},
        ]
        _sum = sum(c["probability"] for c in comps)
        assert _sum > ec._FIELD_SUM_MAX  # would be normalized without the guard
        # emulate the guard
        from app.utils.outcome_display import normalize_display_probs

        if _sum <= ec._FIELD_SUM_MAX:
            normalize_display_probs(comps)
        assert comps[0]["probability"] == 0.945  # untouched

    def test_mild_overround_field_is_squeezed(self):
        # Sum 1.2 (mild overround, within the guard band) -> normalize squeezes to
        # ~100% (normalize_display_probs only acts on over-100% fields, gotcha #23).
        from app.utils.outcome_display import normalize_display_probs

        comps = [{"probability": 0.7, "name": "A"}, {"probability": 0.5, "name": "B"}]
        _sum = sum(c["probability"] for c in comps)  # 1.2, within FIELD_SUM_MAX
        assert _sum <= ec._FIELD_SUM_MAX
        normalize_display_probs(comps)
        assert abs(sum(c["probability"] for c in comps) - 1.0) < 0.01


class TestCyclingStatus:
    def test_settled_when_resolved(self):
        assert ec.cycling_status("resolved", None, datetime.now(timezone.utc)) == "settled"

    def test_live_within_grand_tour_window(self):
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        res = datetime(2026, 8, 9, tzinfo=timezone.utc)  # ~19 days out
        assert ec.cycling_status("open", res, now) == "live"

    def test_upcoming_when_far_out(self):
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        res = datetime(2026, 8, 9, tzinfo=timezone.utc)
        assert ec.cycling_status("open", res, now) == "upcoming"
