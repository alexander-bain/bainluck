"""#871 (Alex MC 2026-06-25): line-move attribution gated on EXPLANATION
confidence, not move magnitude.

The v1 dumped all context to an LLM whenever any context existed ("jumbled
vomit"). The gate must structurally prevent that: a card surfaces ONLY when
concrete evidence attributes the move. A small well-explained move CAN surface;
a large poorly-explained move must NOT.
"""

from datetime import datetime, timedelta, timezone

from app.utils.line_movement import (
    LineMovement,
    LineMovementAnalysis,
    assess_move_attribution,
    EXPLANATION_CONFIDENCE_THRESHOLD,
)

T0 = datetime(2026, 6, 25, 18, 0, tzinfo=timezone.utc)


def _move(change, magnitude=None, bm_before=6, bm_after=6):
    mag = magnitude if magnitude is not None else abs(change)
    # change > 0 → home gained, away fell;  change < 0 → home fell.
    return LineMovement(
        timestamp_start=T0,
        timestamp_end=T0 + timedelta(minutes=30),
        home_prob_before=0.50,
        home_prob_after=0.50 + change,
        change=change,
        magnitude=mag,
        direction="toward_home" if change > 0 else "toward_away",
        context="",
        bookmaker_count_before=bm_before,
        bookmaker_count_after=bm_after,
    )


def _analysis(move):
    return LineMovementAnalysis(event_id=1, movements=[move] if move else [])


class TestMoveAttribution:
    HOME, AWAY = "Boston Celtics", "Miami Heat"

    def test_small_well_explained_move_surfaces(self):
        # SMALL move (3pp), home fell, with a home-team injury → surfaces.
        a = _analysis(_move(-0.03))
        inj = [{"player_name": "Jayson Tatum", "team_name": "Boston Celtics",
                "status": "Out", "injury_type": "ankle"}]
        r = assess_move_attribution(a, injuries=inj, home_team=self.HOME, away_team=self.AWAY)
        assert r.surfaced is True
        assert "Jayson Tatum" in r.primary_cause
        assert r.evidence_type == "injury"

    def test_large_poorly_explained_move_excluded(self):
        # LARGE move (20pp) but NO concrete evidence → must NOT surface.
        a = _analysis(_move(-0.20))
        r = assess_move_attribution(a, home_team=self.HOME, away_team=self.AWAY)
        assert r.surfaced is False
        assert r.primary_cause is None

    def test_data_quality_artifact_excluded_even_with_injury(self):
        # Bookmaker count jumped 3→6 (a book entered) → artifact, confidence 0,
        # even though an injury is present.
        a = _analysis(_move(-0.10, bm_before=3, bm_after=6))
        inj = [{"player_name": "Jayson Tatum", "team_name": "Boston Celtics",
                "status": "Out", "injury_type": "ankle"}]
        r = assess_move_attribution(a, injuries=inj, home_team=self.HOME, away_team=self.AWAY)
        assert r.surfaced is False
        assert r.confidence == 0.0
        assert r.evidence_type == "data_quality_artifact"

    def test_scoring_play_surfaces_live(self):
        a = _analysis(_move(0.05))
        plays = [{"period": "Q4", "clock": "2:10", "description": "Tatum 3PT make"}]
        r = assess_move_attribution(
            a, scoring_plays=plays, home_team=self.HOME, away_team=self.AWAY,
            event_status="live",
        )
        assert r.surfaced is True
        assert "Tatum 3PT make" in r.primary_cause
        assert r.evidence_type == "scoring_play"

    def test_injury_on_gained_side_does_not_surface(self):
        # Home GAINED (change>0 → away fell); an injury to HOME points the wrong
        # way → not direction-consistent → no injury attribution.
        a = _analysis(_move(0.08))
        inj = [{"player_name": "Jayson Tatum", "team_name": "Boston Celtics",
                "status": "Out", "injury_type": "ankle"}]
        r = assess_move_attribution(a, injuries=inj, home_team=self.HOME, away_team=self.AWAY)
        assert r.surfaced is False

    def test_news_alone_below_threshold(self):
        a = _analysis(_move(-0.10))
        r = assess_move_attribution(a, news_headlines=["Some headline"],
                                    home_team=self.HOME, away_team=self.AWAY)
        assert r.confidence < EXPLANATION_CONFIDENCE_THRESHOLD
        assert r.surfaced is False

    def test_no_movements_no_attribution(self):
        r = assess_move_attribution(_analysis(None), home_team=self.HOME, away_team=self.AWAY)
        assert r.surfaced is False
        assert r.primary_cause is None
