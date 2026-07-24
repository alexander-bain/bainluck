"""THE MOMENTS ENGINE — pure join unit tests (#1168, Queue #248 Item 1).

No DB / no network — synthetic scoring plays + WP snapshots exercise the
direction / magnitude / uniqueness confidence gate (#871) and the MLB
ground-truth agreement rate.
"""

from datetime import datetime, timedelta, timezone

from app.utils.game_moments import (
    CONFIDENCE_GATE,
    agreement_rate,
    compute_moments,
    confident_moments,
    synth_scoring_plays_from_snapshots,
)

_T0 = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)


def _snap(mins, home_prob, h, a):
    return {
        "ts": _T0 + timedelta(minutes=mins),
        "home_prob": home_prob,
        "home_score": h,
        "away_score": a,
    }


class TestComputeMoments:
    def test_home_score_swings_home_prob_up_is_confident(self):
        snaps = [
            _snap(0, 0.50, 0, 0),
            _snap(10, 0.68, 1, 0),  # home scored → home prob +18 pts
        ]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees",
                  "description": "Aaron Judge homers (30)", "player_name": "Aaron Judge",
                  "period": "3rd"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox", source="espn")
        assert len(moments) == 1
        m = moments[0]
        assert m["moment_type"] == "home_run"
        assert m["prob_delta"] == 0.18
        assert m["confidence"] is not None and m["confidence"] >= CONFIDENCE_GATE
        assert m["ts"] == snaps[1]["ts"]
        assert "Aaron Judge" in m["label"] and "pts" in m["label"]

    def test_direction_inconsistent_gets_no_confidence(self):
        # away team scored but home prob went UP → not a confident cause (#871).
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.62, 0, 1)]
        plays = [{"home_score": 0, "away_score": 1, "team": "Red Sox",
                  "description": "RBI single"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        assert len(moments) == 1
        assert moments[0]["confidence"] is None
        assert moments[0]["label"] is None

    def test_below_min_delta_not_confident(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.515, 1, 0)]  # +1.5 pts only
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees",
                  "description": "sac fly"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        assert moments[0]["confidence"] is None

    def test_ambiguous_window_is_discounted(self):
        # two plays land on adjacent snapshots → ambiguous attribution → penalty.
        snaps = [_snap(0, 0.50, 0, 0), _snap(5, 0.60, 1, 0), _snap(6, 0.71, 2, 0)]
        plays = [
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": "double"},
            {"home_score": 2, "away_score": 0, "team": "Yankees", "description": "single"},
        ]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        # both direction-ok but each has a neighbor within ±1 index → discounted
        for m in moments:
            assert m["confidence"] is not None
            assert m["confidence"] < 0.5 + 0.5 * (m["prob_delta"] / 0.15)

    def test_percentage_scale_probs_coerced(self):
        snaps = [_snap(0, 50, 0, 0), _snap(10, 70, 1, 0)]  # 0..100 scale
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        assert moments[0]["prob_delta"] == 0.20

    def test_no_matching_snapshot_is_skipped(self):
        snaps = [_snap(0, 0.50, 0, 0)]
        plays = [{"home_score": 5, "away_score": 4, "team": "Yankees", "description": "HR"}]
        assert compute_moments(plays, snaps, "Yankees", "Red Sox") == []

    def test_dedupe_key_is_stable_and_scoped(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR by Judge"}]
        a = compute_moments(plays, snaps, "Yankees", "Red Sox", source="espn")[0]
        b = compute_moments(plays, snaps, "Yankees", "Red Sox", source="espn")[0]
        assert a["dedupe_key"] == b["dedupe_key"]
        assert a["dedupe_key"].startswith("espn:1-0:")


class TestSynthPlaysFromSnapshots:
    def test_score_transitions_become_plays_and_join(self):
        # MLB path: no ESPN plays; synthesize from snapshot score jumps.
        snaps = [
            _snap(0, 0.50, 0, 0),
            _snap(20, 0.66, 1, 0),  # home scored 1 → +16 pts
            _snap(50, 0.42, 1, 2),  # away scored 2 → home prob drops
        ]
        plays = synth_scoring_plays_from_snapshots(snaps, "Phillies", "Mets")
        assert [p["team"] for p in plays] == ["Phillies", "Mets"]
        assert plays[0]["home_score"] == 1 and plays[0]["away_score"] == 0
        assert "scored" in plays[0]["description"]
        # feed back into the join — the home score is a confident moment
        moments = compute_moments(plays, snaps, "Phillies", "Mets", source="mlb")
        home_m = [m for m in moments if m["actor_team"] == "Phillies"][0]
        assert home_m["confidence"] is not None and home_m["confidence"] >= CONFIDENCE_GATE
        assert home_m["prob_delta"] == 0.16

    def test_no_transitions_yields_nothing(self):
        snaps = [_snap(0, 0.5, 2, 2), _snap(10, 0.55, 2, 2)]
        assert synth_scoring_plays_from_snapshots(snaps, "A", "B") == []

    def test_run_pluralization(self):
        snaps = [_snap(0, 0.5, 0, 0), _snap(10, 0.7, 3, 0)]
        plays = synth_scoring_plays_from_snapshots(snaps, "Yanks", "Sox")
        assert "3 runs" in plays[0]["description"]


class TestConfidentMoments:
    def test_filters_below_gate_and_sorts_by_ts(self):
        moments = [
            {"ts": _T0 + timedelta(minutes=20), "confidence": 0.9},
            {"ts": _T0 + timedelta(minutes=5), "confidence": 0.6},
            {"ts": _T0, "confidence": None},
            {"ts": _T0 + timedelta(minutes=1), "confidence": 0.3},
        ]
        out = confident_moments(moments)
        assert [m["confidence"] for m in out] == [0.6, 0.9]  # 0.3 & None dropped, ts-sorted


class TestAgreementRate:
    def test_agreement_when_mlb_saw_same_swing(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees",
                  "description": "Aaron Judge homers (30)"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        mlb = [
            {"description": "Gleyber Torres grounds out", "home_win_probability": 0.50},
            {"description": "Aaron Judge homers on a fly ball", "home_win_probability": 0.69},
        ]
        rep = agreement_rate(moments, mlb)
        assert rep["checked"] == 1 and rep["agreed"] == 1 and rep["rate"] == 1.0

    def test_disagreement_when_mlb_flat(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees",
                  "description": "Aaron Judge homers (30)"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        mlb = [
            {"description": "Gleyber Torres grounds out", "home_win_probability": 0.50},
            {"description": "Aaron Judge homers on a fly ball", "home_win_probability": 0.505},
        ]
        rep = agreement_rate(moments, mlb)
        assert rep["checked"] == 1 and rep["agreed"] == 0 and rep["rate"] == 0.0

    def test_no_confident_moments_returns_none_rate(self):
        assert agreement_rate([], [])["rate"] is None
