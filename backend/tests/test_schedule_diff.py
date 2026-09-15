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


class TestSeriesGamesAreNotDuplicates6326:
    """#6326 — teams alone is not an identity.

    MLB plays series on consecutive days, and ``schedule_coverage`` selects our
    events over a 36h window (``day_noon +/- 18h``) to catch UTC boundary
    crossings. A teams-only match therefore paired every official game with the
    NEXT day's game of the same series: the 2026-09-15 07:05Z beat reported 10
    ``duplicate_events`` of which 9 were two real games.

    The production specimen these are built from: Dodgers @ Reds
    ``15312187`` (09-14 22:40Z, completed) and ``15312651`` (09-15 22:40Z,
    scheduled) -- one official game, two legitimate fixtures.
    """

    D14 = "2026-09-14T22:40:00Z"
    D15 = "2026-09-15T22:40:00Z"

    def _og_at(self, when, dh="N", pk=824466):
        return OfficialGame(game_pk=pk, home="Cincinnati Reds",
                            away="Los Angeles Dodgers", detailed_state="Scheduled",
                            game_datetime=when, doubleheader=dh, game_number=1)

    def _ev_at(self, eid, when, status="scheduled"):
        return {"id": eid, "home_team": "Cincinnati Reds",
                "away_team": "Los Angeles Dodgers", "status": status,
                "commence_time": when}

    def test_consecutive_series_games_are_not_duplicates(self):
        # THE REGRESSION. Yesterday's completed game + today's scheduled one.
        official = [self._og_at(self.D15)]
        events = [self._ev_at(15312187, self.D14, status="completed"),
                  self._ev_at(15312651, self.D15)]
        out = diff_schedule(official, events)
        assert [t.kind for t in out] == [], (
            f"a 24h-apart series game was reported as a duplicate: {out}"
        )

    def test_the_same_game_twice_is_STILL_a_duplicate(self):
        # Not a strawman: the check must keep firing on a real duplicate. This is
        # the Giants @ Cardinals shape -- two rows at the SAME start.
        official = [self._og_at(self.D15)]
        events = [self._ev_at(1, self.D15), self._ev_at(2, self.D15)]
        out = diff_schedule(official, events)
        assert len(out) == 1 and out[0].kind == "duplicate_events"
        assert sorted(out[0].event_ids) == [1, 2]

    def test_the_matched_event_is_the_right_one_of_the_series(self):
        # Beyond "no duplicate": the state check below must run against TODAY's
        # row, not yesterday's. Yesterday's is completed; if it were the one
        # matched, this would read as a premature settle.
        official = [self._og_at(self.D15)]
        events = [self._ev_at(15312187, self.D14, status="completed"),
                  self._ev_at(15312651, self.D15, status="scheduled")]
        assert diff_schedule(official, events) == []

    def test_absent_commence_time_falls_back_to_teams_only(self):
        # Fails OPEN by design: an unparseable/missing start must not become a
        # missing_event finding. Two id-less-in-time rows still read as a dup.
        official = [self._og_at(self.D15)]
        events = [{"id": 1, "home_team": "Cincinnati Reds",
                   "away_team": "Los Angeles Dodgers", "status": "scheduled"},
                  {"id": 2, "home_team": "Cincinnati Reds",
                   "away_team": "Los Angeles Dodgers", "status": "scheduled"}]
        out = diff_schedule(official, events)
        assert len(out) == 1 and out[0].kind == "duplicate_events"

    def test_unparseable_commence_time_does_not_drop_the_event(self):
        official = [self._og_at(self.D15)]
        events = [self._ev_at(1, "not-a-timestamp")]
        # Falls open to a match, so exactly one event -> no missing_event.
        assert diff_schedule(official, events) == []

    def test_a_genuinely_absent_event_is_still_missing(self):
        # The narrowing must not silently convert "missing" into "clean".
        official = [self._og_at(self.D15)]
        events = [self._ev_at(15312187, self.D14, status="completed")]
        out = diff_schedule(official, events)
        assert len(out) == 1 and out[0].kind == "missing_event"


class TestDoubleheaderGate6326:
    """#6326 — the split-doubleheader exemption was a COMMENT, never a condition.

    ``og.doubleheader`` was parsed, carried on ``OfficialGame`` and used only to
    decorate the detail string; the ``duplicate_events`` append was
    unconditional. So the sentence "only flag when the official game is NOT a
    doubleheader" described a guard the module did not have.
    """

    WHEN = "2026-09-15T17:10:00Z"
    LATER = "2026-09-15T21:40:00Z"   # game 2 of a split DH, ~4.5h later

    def _og_dh(self, dh="S", gn=1):
        return OfficialGame(game_pk=1, home="Cubs", away="Braves",
                            detailed_state="Scheduled", game_datetime=self.WHEN,
                            doubleheader=dh, game_number=gn)

    def _ev_at(self, eid, when):
        return {"id": eid, "home_team": "Cubs", "away_team": "Braves",
                "status": "scheduled", "commence_time": when}

    def test_split_doubleheader_two_events_is_not_a_duplicate(self):
        official = [self._og_dh()]
        events = [self._ev_at(1, self.WHEN), self._ev_at(2, self.LATER)]
        assert diff_schedule(official, events) == []

    def test_doubleheader_with_three_events_is_still_a_duplicate(self):
        # The exemption is "two are legitimate", not "never flag a DH".
        official = [self._og_dh()]
        events = [self._ev_at(1, self.WHEN), self._ev_at(2, self.LATER),
                  self._ev_at(3, self.WHEN)]
        out = diff_schedule(official, events)
        assert len(out) == 1 and out[0].kind == "duplicate_events"
        assert sorted(out[0].event_ids) == [1, 2, 3]

    def test_non_doubleheader_still_flags_at_two(self):
        official = [self._og_dh(dh="N")]
        events = [self._ev_at(1, self.WHEN), self._ev_at(2, self.WHEN)]
        out = diff_schedule(official, events)
        assert len(out) == 1 and out[0].kind == "duplicate_events"
