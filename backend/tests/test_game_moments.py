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
        assert a["dedupe_key"] == b["dedupe_key"]  # identical recomputation is byte-stable
        assert a["dedupe_key"].startswith("m2:espn:")


class TestCanonicalIdentity:
    """#1445 — the v1 key (`source:h-a:description[:40]`) collided, and one
    collision crashed the writer for the whole pass. Each case here is a C59
    persistence fixture (`scripts/evals/game_moments_persistence_fixtures.json`)
    lifted to the real join."""

    def test_equal_40_char_prefix_does_not_collide(self):
        # C59 "equal-prefix-40": two distinct plays whose descriptions agree for
        # 40 characters. v1 truncated at 40 and emitted one key for both.
        prefix = "a" * 40
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": prefix + "-x"},
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": prefix + "-y"},
        ]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox", source="espn")
        keys = [m["dedupe_key"] for m in moments]
        assert len(keys) == 2 and len(set(keys)) == 2

    def test_score_correction_then_readvance_are_two_moments(self):
        # C59 "score-correction-readvance": 0-0 → 1-0 → 0-0 → 1-0 re-emits the
        # same score AND the same synthesized description. Only the play's own
        # transition time tells them apart.
        snaps = [
            _snap(0, 0.50, 0, 0),
            _snap(10, 0.68, 1, 0),
            _snap(20, 0.50, 0, 0),  # correction
            _snap(30, 0.69, 1, 0),  # re-advance
        ]
        plays = synth_scoring_plays_from_snapshots(snaps, "Phillies", "Mets")
        assert len(plays) == 2
        assert plays[0]["description"] == plays[1]["description"]  # v1's collision
        moments = compute_moments(plays, snaps, "Phillies", "Mets", source="mlb")
        keys = [m["dedupe_key"] for m in moments]
        assert len(keys) == 2 and len(set(keys)) == 2

    def test_duplicate_source_play_collapses_to_one_row(self):
        # C59 "duplicate-source-play"/"identical-rerun": the SAME play twice is a
        # rerun, not two moments — it must collapse, not crash the upsert.
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        play = {"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR"}
        moments = compute_moments([play, dict(play)], snaps, "Yankees", "Red Sox")
        assert len(moments) == 1

    def test_provider_play_id_is_preferred_identity(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR", "play_id": "abc"},
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR", "play_id": "def"},
        ]
        keys = [m["dedupe_key"] for m in compute_moments(plays, snaps, "Yankees", "Red Sox")]
        assert keys == ["m2:espn:pabc", "m2:espn:pdef"]

    def test_uniqueness_is_scoped_to_the_event(self):
        # C59 "same-key-different-events": identical keys in two events are legal;
        # the constraint carries event_id, so the key itself must not.
        from app.models import GameMoment

        cols = {
            tuple(c.name for c in con.columns)
            for con in GameMoment.__table__.constraints
            if con.name == "uq_game_moment_event_key"
        }
        assert cols == {("event_id", "dedupe_key")}


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
        # our moment: +18pt home swing. MLB series shows a matching ~+19pt swing.
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        mlb = [
            {"home_win_probability": 0.50},
            {"home_win_probability": 0.69},  # +19pt swing, within tolerance of +18
        ]
        rep = agreement_rate(moments, mlb)
        assert rep["checked"] == 1 and rep["agreed"] == 1 and rep["rate"] == 1.0

    def test_disagreement_when_mlb_flat(self):
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0)]
        plays = [{"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR"}]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        mlb = [
            {"home_win_probability": 0.50},
            {"home_win_probability": 0.505},  # flat — no comparable swing
        ]
        rep = agreement_rate(moments, mlb)
        assert rep["checked"] == 1 and rep["agreed"] == 0 and rep["rate"] == 0.0

    def test_greedy_match_does_not_double_count(self):
        # two of our moments (+18, +12); MLB has only ONE big swing → 1/2 agree
        snaps = [_snap(0, 0.50, 0, 0), _snap(10, 0.68, 1, 0), _snap(20, 0.80, 2, 0)]
        plays = [
            {"home_score": 1, "away_score": 0, "team": "Yankees", "description": "HR"},
            {"home_score": 2, "away_score": 0, "team": "Yankees", "description": "HR"},
        ]
        moments = compute_moments(plays, snaps, "Yankees", "Red Sox")
        mlb = [{"home_win_probability": 0.50}, {"home_win_probability": 0.68}]  # one +18 swing
        rep = agreement_rate(moments, mlb)
        assert rep["checked"] == 2 and rep["agreed"] == 1

    def test_no_confident_moments_returns_none_rate(self):
        assert agreement_rate([], [])["rate"] is None
