"""#1201 — unit tests for the MLB schedule-diff typed-transition classifier.

The sentinel invariant is: every official MLB game today ↔ exactly one of our
events. These tests pin the four transition kinds (missing / duplicate /
premature_settle / postponed) and the orientation-tolerant team match.
"""

from app.utils.schedule_diff import (
    OfficialGame,
    ScheduleTransition,
    diff_schedule,
    normalize_official_game,
    teams_match,
)


def _og(home, away, state="Scheduled", pk=1, dh="N", gn=1):
    return OfficialGame(game_pk=pk, home=home, away=away, detailed_state=state,
                        game_datetime="2026-07-22T22:40:00Z", doubleheader=dh, game_number=gn)


def _ev(eid, home, away, status="scheduled"):
    return {"id": eid, "home_team": home, "away_team": away, "status": status}


class TestTeamsMatch:
    def test_aligned(self):
        assert teams_match("Los Angeles Dodgers", "Philadelphia Phillies",
                           "Los Angeles Dodgers", "Philadelphia Phillies") is True

    def test_swapped_orientation(self):
        # Our home/away swapped relative to MLB's — still a match (gotcha #32).
        assert teams_match("Philadelphia Phillies", "Los Angeles Dodgers",
                           "Los Angeles Dodgers", "Philadelphia Phillies") is True

    def test_token_subset_match(self):
        assert teams_match("Dodgers", "Phillies",
                           "Los Angeles Dodgers", "Philadelphia Phillies") is True

    def test_no_match(self):
        assert teams_match("Yankees", "Red Sox",
                           "Los Angeles Dodgers", "Philadelphia Phillies") is False


class TestNormalizeOfficialGame:
    def test_extracts_fields(self):
        raw = {
            "gamePk": 824735,
            "gameDate": "2026-07-22T22:40:00Z",
            "doubleHeader": "S",
            "gameNumber": 2,
            "status": {"detailedState": "In Progress"},
            "teams": {
                "home": {"team": {"name": "Los Angeles Dodgers"}, "score": 6},
                "away": {"team": {"name": "Philadelphia Phillies"}, "score": 3},
            },
        }
        og = normalize_official_game(raw)
        assert og.game_pk == 824735
        assert og.home == "Los Angeles Dodgers"
        assert og.away == "Philadelphia Phillies"
        assert og.detailed_state == "In Progress"
        assert og.doubleheader == "S"
        assert og.game_number == 2

    def test_missing_fields_default(self):
        og = normalize_official_game({})
        assert og.game_pk is None
        assert og.home == "" and og.away == ""
        assert og.doubleheader == "N"
        assert og.game_number == 1


class TestDiffSchedule:
    def test_exactly_one_correct_event_yields_nothing(self):
        official = [_og("Dodgers", "Phillies", state="Scheduled")]
        events = [_ev(1, "Dodgers", "Phillies", status="scheduled")]
        assert diff_schedule(official, events) == []

    def test_missing_event(self):
        official = [_og("Dodgers", "Phillies")]
        out = diff_schedule(official, [])
        assert len(out) == 1
        assert out[0].kind == "missing_event"
        assert out[0].game_pk == 1

    def test_duplicate_events(self):
        official = [_og("Dodgers", "Phillies")]
        events = [_ev(1, "Dodgers", "Phillies"), _ev(2, "Dodgers", "Phillies")]
        out = diff_schedule(official, events)
        assert len(out) == 1
        assert out[0].kind == "duplicate_events"
        assert sorted(out[0].event_ids) == [1, 2]

    def test_premature_settle(self):
        # The #1193/#1201 class: we settled it, MLB still has it live/scheduled.
        official = [_og("Dodgers", "Phillies", state="In Progress")]
        events = [_ev(1, "Dodgers", "Phillies", status="completed")]
        out = diff_schedule(official, events)
        assert len(out) == 1
        assert out[0].kind == "premature_settle"
        assert out[0].event_ids == [1]

    def test_premature_settle_when_official_scheduled(self):
        official = [_og("Dodgers", "Phillies", state="Scheduled")]
        events = [_ev(1, "Dodgers", "Phillies", status="closed")]
        out = diff_schedule(official, events)
        assert out and out[0].kind == "premature_settle"

    def test_postponed(self):
        official = [_og("Dodgers", "Phillies", state="Postponed")]
        events = [_ev(1, "Dodgers", "Phillies", status="scheduled")]
        out = diff_schedule(official, events)
        assert len(out) == 1
        assert out[0].kind == "postponed"

    def test_postponed_already_settled_is_not_flagged(self):
        # If we already settled a postponed game, that's a distinct (settled) state;
        # the postponed transition only fires while our event is still active.
        official = [_og("Dodgers", "Phillies", state="Postponed")]
        events = [_ev(1, "Dodgers", "Phillies", status="completed")]
        out = diff_schedule(official, events)
        assert out == []

    def test_final_matching_settled_is_clean(self):
        official = [_og("Dodgers", "Phillies", state="Final")]
        events = [_ev(1, "Dodgers", "Phillies", status="completed")]
        assert diff_schedule(official, events) == []

    def test_multiple_games_mixed(self):
        official = [
            _og("Dodgers", "Phillies", state="Final", pk=1),      # clean
            _og("Yankees", "Red Sox", state="Scheduled", pk=2),   # missing
            _og("Cubs", "Cardinals", state="In Progress", pk=3),  # premature settle
        ]
        events = [
            _ev(10, "Dodgers", "Phillies", status="completed"),
            _ev(30, "Cubs", "Cardinals", status="closed"),
        ]
        out = diff_schedule(official, events)
        kinds = sorted(t.kind for t in out)
        assert kinds == ["missing_event", "premature_settle"]
