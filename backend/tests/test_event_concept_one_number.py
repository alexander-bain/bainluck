"""#213 / #199: the golf concept page must show ONE number per question.

The Race-to-title evolution chart reads its current value from the last point of
each competitor's `history`, which is sourced from a SINGLE snapshot-rich winner
market (`evolution_market_id`) whose raw probabilities carry the full bookmaker
overround (they sum well above 1). The leaderboard "Win" column shows the
field-renormalized cross-source BLEND (`competitor["probability"]`). Left alone
these diverge on the SAME page (The Open: Scheffler 24.5% chart vs 12.3%
leaderboard) — a "the blend is the product" violation.

`_reconcile_history_to_blend` anchors each competitor's history endpoint to its
blend so both surfaces read the same number.
"""

from app.utils.event_concept import _reconcile_history_to_blend


def _hist(*probs):
    return [
        {"timestamp": f"2026-07-1{i}T00:00:00+00:00", "probability": p}
        for i, p in enumerate(probs)
    ]


class TestReconcileHistoryToBlend:
    def test_anchors_chart_endpoint_to_leaderboard_blend(self):
        # The live Scheffler case: raw evolution series ends at 0.245, blend 0.123.
        comp = {"name": "Scottie Scheffler", "probability": 0.123,
                "history": _hist(0.15, 0.20, 0.245)}
        _reconcile_history_to_blend([comp])
        assert comp["history"][-1]["probability"] == 0.123

    def test_preserves_trend_shape_proportionally(self):
        comp = {"name": "X", "probability": 0.10, "history": _hist(0.10, 0.20)}
        _reconcile_history_to_blend([comp])
        # factor = 0.10 / 0.20 = 0.5 → the whole series scales, shape preserved.
        assert comp["history"][0]["probability"] == 0.05
        assert comp["history"][1]["probability"] == 0.10

    def test_noop_when_already_aligned(self):
        # F1/tennis: leaderboard prob IS the raw series endpoint → factor ~1.0.
        original = _hist(0.30, 0.40, 0.42)
        comp = {"name": "Verstappen", "probability": 0.42,
                "history": [dict(p) for p in original]}
        _reconcile_history_to_blend([comp])
        assert comp["history"] == original

    def test_skips_competitor_without_history(self):
        comp = {"name": "No Series", "probability": 0.30}
        _reconcile_history_to_blend([comp])  # must not raise
        assert "history" not in comp

    def test_skips_when_blend_missing_or_zero(self):
        comp = {"name": "Y", "probability": None, "history": _hist(0.1, 0.2)}
        _reconcile_history_to_blend([comp])
        assert comp["history"][-1]["probability"] == 0.2  # untouched

    def test_skips_when_last_raw_is_zero(self):
        comp = {"name": "Z", "probability": 0.10, "history": _hist(0.1, 0.0)}
        _reconcile_history_to_blend([comp])
        # last point is 0 → no safe factor, series untouched.
        assert comp["history"][-1]["probability"] == 0.0

    def test_handles_none_points_within_series(self):
        comp = {"name": "Gapped", "probability": 0.10,
                "history": [
                    {"timestamp": "2026-07-10T00:00:00+00:00", "probability": 0.30},
                    {"timestamp": "2026-07-11T00:00:00+00:00", "probability": None},
                    {"timestamp": "2026-07-12T00:00:00+00:00", "probability": 0.20},
                ]}
        _reconcile_history_to_blend([comp])
        # last non-null is 0.20 → factor 0.5; None stays None; endpoint == blend.
        assert comp["history"][0]["probability"] == 0.15
        assert comp["history"][1]["probability"] is None
        assert comp["history"][-1]["probability"] == 0.10

    def test_whole_field_reconciles_independently(self):
        comps = [
            {"name": "A", "probability": 0.123, "history": _hist(0.20, 0.245)},
            {"name": "B", "probability": 0.069, "history": _hist(0.09, 0.098)},
        ]
        _reconcile_history_to_blend(comps)
        assert comps[0]["history"][-1]["probability"] == 0.123
        assert comps[1]["history"][-1]["probability"] == 0.069

    def test_scaled_series_never_exceeds_100pct(self):
        # #1139 Cameron Young: an early raw peak (0.56) with a collapsed current
        # (blend 0.126, last_raw ~0.035 → factor ~3.6) scaled to 202.9%.
        comp = {"name": "Cameron Young", "probability": 0.126,
                "history": _hist(0.56, 0.30, 0.035)}
        _reconcile_history_to_blend([comp])
        probs = [p["probability"] for p in comp["history"]]
        assert all(p <= 1.0 for p in probs)  # never the 202.9% of #1139
        assert comp["history"][-1]["probability"] == 0.126  # anchor preserved

    def test_inflating_factor_leaves_early_points_raw(self):
        """#7560: a factor > 1 anchors the endpoint and touches nothing else.

        #1139 clamped this case to 1.0, which kept the number in range and still
        published a claim nobody measured. The raw points are real quoted prices
        and stay exactly as quoted; only the last one moves, to the blend.
        """
        comp = {"name": "Cameron Young", "probability": 0.126,
                "history": _hist(0.56, 0.30, 0.035)}
        _reconcile_history_to_blend([comp])
        assert [p["probability"] for p in comp["history"]] == [0.56, 0.30, 0.126]

    def test_inflating_factor_fabricates_no_certainty(self):
        """#7560, the production specimen, replayed.

        MotoGP Austria (`KXMOTOGPRACE-OSTE26`) 2026-09-20: Jorge Martin's served
        chart was 52 of 53 points at exactly 100% because his blend (0.55, taken
        from the live book) towered over his series' own last point. A rider is
        never 100% to win a 22-rider race that has not started.
        """
        comp = {"name": "Jorge Martin", "probability": 0.55,
                "history": _hist(0.11, 0.12, 0.10, 0.05)}
        _reconcile_history_to_blend([comp])
        probs = [p["probability"] for p in comp["history"]]
        assert 1.0 not in probs
        assert probs == [0.11, 0.12, 0.10, 0.55]

    def test_deflating_factor_still_rescales_the_whole_series(self):
        """The overround case this function exists for is untouched by #7560."""
        comp = {"name": "Scottie Scheffler", "probability": 0.123,
                "history": _hist(0.15, 0.20, 0.245)}
        _reconcile_history_to_blend([comp])
        probs = [p["probability"] for p in comp["history"]]
        assert probs == [0.0753, 0.1004, 0.123]  # shape preserved, endpoint anchored

    def test_inflating_factor_anchors_last_non_null_not_last_slot(self):
        """A trailing gap must not swallow the anchor (#7560 + #1139's None case)."""
        comp = {"name": "Gapped Up", "probability": 0.40,
                "history": [
                    {"timestamp": "2026-07-10T00:00:00+00:00", "probability": 0.30},
                    {"timestamp": "2026-07-11T00:00:00+00:00", "probability": 0.10},
                    {"timestamp": "2026-07-12T00:00:00+00:00", "probability": None},
                ]}
        _reconcile_history_to_blend([comp])
        assert [p["probability"] for p in comp["history"]] == [0.30, 0.40, None]
