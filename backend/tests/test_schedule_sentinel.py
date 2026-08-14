"""Tests for the Schedule Sentinel (#1796, Queue 342) — the completeness check.

    Every check we have verifies that what exists renders. Nothing verifies
    that what should exist, exists.

These lock in the four defect classes and, more importantly, the discipline that
keeps them trustworthy:

  * a game on the authority's schedule that we do not hold is MISSING — the class
    that had no detector at all;
  * a cross-wired ``team_id`` is MISATTACHED, and the test asserts EXPLICITLY that
    a names-only comparison passes the very same row (that is why #1779 survived
    every existing check);
  * a postponement is EXPLAINED, never REAL;
  * a settled game whose score is not the real score is caught, and when the score
    belongs to another real game the absorption is named;
  * an uncovered league reports as NOT COVERED rather than green.

Guard-rail discipline (each mandated by a standing gotcha):

  * **#42** — one poison league never voids its healthy siblings.
  * **#43** — every classifier is asserted in BOTH directions: the defect is
    caught AND the legitimate case is not filed.
  * **#44** — no anchor in this file branches on, or reads, the wall clock. Every
    instant is a frozen absolute constant, and ``now`` is injected everywhere, so
    ``scripts/clock_sweep.py`` is invariant across all 12 faked clocks.
  * **#53** — an empty 200 from a truth API is a response SHAPE, not an absence.
    "the schedule API returned nothing" and "there were no games" are asserted to
    be different values, not the same one.
"""

import importlib
from datetime import datetime, timedelta, timezone

# Import the MODULE explicitly — `app.tasks.schedule_sentinel` as a bare attribute
# resolves to the Celery task object of the same name registered in
# app/tasks/__init__.py, which shadows the module. importlib gets the module.
ss = importlib.import_module("app.tasks.schedule_sentinel")

# ---------------------------------------------------------------------------
# Frozen instants (gotcha #44). NOTHING here is derived from the wall clock and
# nothing branches on it: NOW is an absolute constant, and every game time is
# expressed as an OFFSET from it, so the AGE of every fixture is fixed forever.
# ---------------------------------------------------------------------------
NOW = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)     # MLB in_season
NOW_OFFSEASON = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)  # MLB offseason


def _ago(hours):
    return NOW - timedelta(hours=hours)


def _ahead(hours):
    return NOW + timedelta(hours=hours)


MLB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "mlb")
NCAAB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "ncaab")
UNCOVERED = next(s for s in ss.SCHEDULE_LEAGUES if s.truth is None)


def _truth(home, away, *, start, state="final", hs=None, aws=None, key="g1",
           raw=None, dh=False, gnum=1):
    return ss.TruthGame(key=key, home=home, away=away, start=start, state=state,
                        raw_state=raw if raw is not None else state.title(),
                        home_score=hs, away_score=aws, doubleheader=dh,
                        game_number=gnum)


def _ours(eid, home, away, *, start, status="completed", hs=None, aws=None,
          home_fk=None, away_fk=None, home_id=1, away_id=2,
          espn_id=None, statpal_id=None, external_id=None, individuated=True):
    """Our event. ``home_fk``/``away_fk`` default to the row's own names — the
    healthy case where the FK dereferences to the club the row claims.

    ``individuated`` defaults True for the same reason: a real MLB/NBA row has
    been named by some schedule provider, and a helper's default should be the
    healthy shape. When no explicit id is given it synthesizes a StatPal fixture
    id — deliberately StatPal, because that id space is neither ESPN's nor MLB
    StatsAPI's, so these fixtures still pair on NAMES (which is what the older
    tests are about) without tripping the un-individuated finding.

    Codex's C-SEN-1 specimen is the anonymous shell: pass ``individuated=False``.
    """
    if individuated and not (espn_id or statpal_id or external_id):
        statpal_id = f"fx{eid}"
    return ss.OurEvent(
        id=eid, home_name=home, away_name=away,
        home_team_id=home_id, away_team_id=away_id,
        home_fk_name=home if home_fk is None else home_fk,
        away_fk_name=away if away_fk is None else away_fk,
        status=status, home_score=hs, away_score=aws, commence_time=start,
        espn_id=espn_id, statpal_fixture_id=statpal_id, external_id=external_id,
    )


def _kinds(findings):
    out = {}
    for f in findings:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out


def _checks(findings):
    return {f["check"] for f in findings}


# ---------------------------------------------------------------------------
# Name similarity — the pairing primitive. Both directions (gotcha #43).
# ---------------------------------------------------------------------------
class TestNameSimilarity:
    def test_identical_names_match(self):
        assert ss.name_similarity("Boston Red Sox", "Boston Red Sox") == 1.0

    def test_punctuation_and_spacing_normalize(self):
        # Our stored "St.Louis Cardinals" vs statsapi's "St. Louis Cardinals".
        assert ss.name_similarity("St.Louis Cardinals", "St. Louis Cardinals") == 1.0

    def test_short_form_contains(self):
        assert ss.name_similarity("Red Sox", "Boston Red Sox") >= ss.MATCH_BAR

    def test_same_city_different_club_does_not_match(self):
        # The whole reason this is not plain token OVERLAP: overlap alone pairs
        # these on "chicago" and would hide a MISSING behind a wrong pair.
        assert ss.name_similarity("Chicago Cubs", "Chicago White Sox") < ss.MATCH_BAR
        assert ss.name_similarity("New York Mets", "New York Yankees") < ss.MATCH_BAR
        assert ss.name_similarity("Los Angeles Angels", "Los Angeles Dodgers") < ss.MATCH_BAR

    def test_empty_names_never_match(self):
        assert ss.name_similarity("", "Boston Red Sox") == 0.0
        assert ss.name_similarity(None, None) == 0.0


# ---------------------------------------------------------------------------
# Gotcha #53 — an empty 200 is a response shape, not an absence.
# ---------------------------------------------------------------------------
class TestTruthIsNeverCollapsed:
    def test_authoritative_empty_day_is_ok_with_zero_games(self):
        res = ss.parse_statsapi_payload({"totalGames": 0, "dates": []})
        assert res.ok is True
        assert res.games == []
        assert res.empty_authoritative is True
        assert res.zero_yield is True

    def test_malformed_body_is_not_ok(self):
        res = ss.parse_statsapi_payload({"messageNumber": 32, "message": "boom"})
        assert res.ok is False
        assert res.games == []

    def test_empty_and_unreadable_are_different_values(self):
        """The disambiguation itself: "there were no games" and "I could not
        look" must not be the same value. Both have zero games; only one is ok."""
        empty = ss.parse_statsapi_payload({"totalGames": 0, "dates": []})
        broken = ss.parse_statsapi_payload(None)
        assert len(empty.games) == len(broken.games) == 0
        assert empty.ok != broken.ok

    def test_espn_empty_slate_is_authoritative(self):
        res = ss.parse_espn_payload({"leagues": [{"id": "1"}], "events": []})
        assert res.ok is True and res.games == [] and res.zero_yield is True

    def test_espn_malformed_body_is_not_ok(self):
        assert ss.parse_espn_payload({"unexpected": True}).ok is False

    def test_statsapi_games_parse_with_scores_and_state(self):
        res = ss.parse_statsapi_payload({"dates": [{"date": "2026-08-11", "games": [{
            "gamePk": 822778, "gameDate": "2026-08-11T23:07:00Z",
            "status": {"detailedState": "Final"},
            "doubleHeader": "N", "gameNumber": 1,
            "teams": {"home": {"team": {"name": "Toronto Blue Jays"}, "score": 5},
                      "away": {"team": {"name": "Boston Red Sox"}, "score": 3}},
        }]}]})
        assert res.ok and len(res.games) == 1
        g = res.games[0]
        assert (g.home, g.away, g.state, g.home_score, g.away_score) == (
            "Toronto Blue Jays", "Boston Red Sox", "final", 5, 3)

    def test_one_poison_game_does_not_void_the_day(self):
        """Gotcha #42 at the parse layer."""
        res = ss.parse_statsapi_payload({"dates": [{"games": [
            {"gamePk": 1, "teams": "not-a-dict"},
            {"gamePk": 2, "gameDate": "2026-08-11T23:07:00Z",
             "status": {"detailedState": "Final"},
             "teams": {"home": {"team": {"name": "A"}, "score": 1},
                       "away": {"team": {"name": "B"}, "score": 0}}},
        ]}]})
        assert res.ok is True
        assert [g.key for g in res.games] == ["2"]


# ---------------------------------------------------------------------------
# MISSING — the class with no prior detector. Both directions (gotcha #43).
# ---------------------------------------------------------------------------
class TestMissing:
    def test_deleted_event_is_missing(self):
        """The acceptance criterion: delete a fixture event, it is caught."""
        truth = [
            _truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                   hs=5, aws=3, key="t1"),
            _truth("Atlanta Braves", "New York Mets", start=_ago(7),
                   hs=4, aws=0, key="t2"),
        ]
        ours = [_ours(1, "Atlanta Braves", "New York Mets", start=_ago(7),
                      hs=4, aws=0)]   # the Red Sox row is DELETED
        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        missing = [f for f in findings if f["kind"] == "MISSING"]
        assert len(missing) == 1
        assert "Boston Red Sox" in missing[0]["detail"]
        assert stats["unmatched_truth"] == 1

    def test_complete_slate_produces_no_findings(self):
        """The other direction: a complete, correct slate files nothing."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3)]
        ours = [_ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                      hs=5, aws=3)]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        assert findings == []

    def test_missing_is_real_and_files(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert len(classified["real"]) == 1
        assert ss.schedule_verdict(classified, covered=True) == "red"

    def test_missing_scheduled_future_game_is_still_real(self):
        """Alex's own report was a PRE-game miss: a scheduled game we do not hold
        is the defect, not just a settled one."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ahead(9),
                        state="scheduled", raw="Scheduled")]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert len(classified["real"]) == 1

    def test_partial_by_design_league_missing_is_watch_not_real(self):
        """We do not carry all ~360 D1 programs. Filing that daily is the
        cry-wolf the Grid Sentinel's mlb-66 lesson forbids."""
        truth = [_truth("Duke Blue Devils", "Kansas Jayhawks", start=_ago(7),
                        hs=70, aws=68)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], NCAAB, NOW)[0], NCAAB, NOW)
        assert classified["real"] == []
        assert len(classified["watch"]) == 1
        assert ss.schedule_verdict(classified, covered=True) == "green"

    def test_consecutive_day_series_does_not_cross_pair(self):
        """Three-game series, same matchup 24h apart, middle game missing. The
        strict stage must consume the exact pairs first, or the loose stage would
        pair day 1's row to day 2's game and hide the hole."""
        truth = [
            _truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(31), hs=2, aws=1, key="d1"),
            _truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7), hs=5, aws=3, key="d2"),
        ]
        ours = [_ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(31),
                      hs=2, aws=1)]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        missing = [f for f in findings if f["check"] == "schedule_missing"]
        assert len(missing) == 1
        assert missing[0]["truth_key"] == "d2"
        # …and the day-1 row was not misreported as mis-dated.
        assert "schedule_wrong_date" not in _checks(findings)

    def test_mis_dated_row_is_paired_and_reported_not_double_counted(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3)]
        ours = [_ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(29),
                      hs=5, aws=3)]
        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        assert _checks(findings) == {"schedule_wrong_date"}
        assert stats["unmatched_truth"] == 0 and stats["unmatched_ours"] == 0


# ---------------------------------------------------------------------------
# MISATTACHED — must DEREFERENCE the FK. This is the non-negotiable one.
# ---------------------------------------------------------------------------
class TestMisattached:
    HOME = "Cincinnati Reds"
    AWAY = "Miami Marlins"

    def _cross_wired(self):
        """#1779's exact shape, reproduced in production 2026-08-13 on event
        15191700: ``home_team_id`` resolves to 'Boston Red Sox' while
        ``home_team_name`` still reads 'Cincinnati Reds'."""
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2)]
        ours = [_ours(15191700, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      home_fk="Boston Red Sox", home_id=10709)]
        return truth, ours

    def test_cross_wired_team_id_is_caught(self):
        truth, ours = self._cross_wired()
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        mis = [f for f in findings if f["check"] == "schedule_misattached"]
        assert len(mis) == 1
        assert mis[0]["team_id"] == 10709
        assert mis[0]["fk_name"] == "Boston Red Sox"
        assert mis[0]["official"] == self.HOME
        assert mis[0]["kind"] == "MISATTACHED"

    def test_names_alone_cannot_find_it(self):
        """EXPLICIT, per the acceptance criterion. The row's own names agree with
        the authority on BOTH sides — every names-only comparison in the codebase
        passes it — and the sentinel still catches it, because it dereferences the
        FK instead of trusting the denormalised string."""
        from app.utils.schedule_diff import teams_match

        truth, ours = self._cross_wired()
        o, t = ours[0], truth[0]

        # 1. The existing shared names-only predicate passes this row.
        assert teams_match(o.home_name, o.away_name, t.home, t.away) is True
        # 2. So does this module's own name comparison, on both sides.
        assert ss.name_similarity(o.home_name, t.home) >= ss.MATCH_BAR
        assert ss.name_similarity(o.away_name, t.away) >= ss.MATCH_BAR
        # 3. The FK does NOT.
        assert ss.name_similarity(o.home_fk_name, t.home) < ss.MATCH_BAR
        # 4. And the finding says so in as many words, so a reader of the issue
        #    knows why nothing else caught it.
        mis = [f for f in ss.reconcile(truth, ours, MLB, NOW)[0]
               if f["check"] == "schedule_misattached"]
        assert mis[0]["names_agree"] is True
        assert "a name-only check passes this row" in mis[0]["detail"]

    def test_correctly_wired_team_id_is_not_flagged(self):
        """The other direction (gotcha #43)."""
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2)]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2)]
        assert "schedule_misattached" not in _checks(
            ss.reconcile(truth, ours, MLB, NOW)[0])

    def test_short_form_fk_name_is_not_a_misattachment(self):
        """'Red Sox' resolving for 'Boston Red Sox' is a naming variant, not a
        cross-wire. Flagging it would make the class untrustworthy."""
        truth = [_truth("Boston Red Sox", "Toronto Blue Jays", start=_ago(7),
                        hs=4, aws=2)]
        ours = [_ours(1, "Boston Red Sox", "Toronto Blue Jays", start=_ago(7),
                      hs=4, aws=2, home_fk="Red Sox")]
        assert "schedule_misattached" not in _checks(
            ss.reconcile(truth, ours, MLB, NOW)[0])

    def test_null_team_id_is_watch_not_a_misattachment(self):
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2)]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      home_id=None, home_fk=None)]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        classified = ss.classify_findings(findings, MLB, NOW)
        assert classified["real"] == []
        assert [f["check"] for f in classified["watch"]] == ["schedule_team_unlinked"]

    def test_home_away_reversed_is_caught(self):
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2)]
        ours = [_ours(1, self.AWAY, self.HOME, start=_ago(7), hs=2, aws=4)]
        assert "schedule_home_away_swapped" in _checks(
            ss.reconcile(truth, ours, MLB, NOW)[0])


# ---------------------------------------------------------------------------
# SCORE DISAGREEMENT on settled games (+ the #1779 absorption fingerprint).
# ---------------------------------------------------------------------------
class TestScoreDisagreement:
    def test_wrong_score_on_a_settled_game_is_caught(self):
        truth = [_truth("Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                        hs=4, aws=6)]
        ours = [_ours(1, "Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                      hs=3, aws=0)]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        score = [f for f in findings if f["check"] == "schedule_score_disagreement"]
        assert len(score) == 1 and score[0]["kind"] == "SCORE_DISAGREEMENT"

    def test_correct_score_is_not_flagged(self):
        truth = [_truth("Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                        hs=4, aws=6)]
        ours = [_ours(1, "Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                      hs=4, aws=6)]
        assert ss.reconcile(truth, ours, MLB, NOW)[0] == []

    def test_absorbed_score_names_the_game_it_came_from(self):
        """The #1779 mechanism, measured live on 2026-08-13: our Aug-12 row for
        CLE@DET carried Aug-13's in-progress score. A wrong number is a grading
        bug; ANOTHER GAME's number is an absorption, and the finding says which."""
        truth = [
            _truth("Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                   hs=4, aws=6, key="yesterday"),
            _truth("Detroit Tigers", "Cleveland Guardians", start=_ahead(11),
                   hs=3, aws=0, key="today", state="final"),
        ]
        ours = [_ours(1, "Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                      hs=3, aws=0)]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        score = [f for f in findings if f["check"] == "schedule_score_disagreement"]
        assert len(score) == 1
        assert score[0]["absorbed_from"] is not None
        assert "±28h absorption" in score[0]["detail"]

    def test_plain_wrong_score_does_not_claim_absorption(self):
        """Other direction: do not invent a diagnosis that is not supported."""
        truth = [_truth("Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                        hs=4, aws=6)]
        ours = [_ours(1, "Detroit Tigers", "Cleveland Guardians", start=_ago(7),
                      hs=9, aws=9)]
        score = [f for f in ss.reconcile(truth, ours, MLB, NOW)[0]
                 if f["check"] == "schedule_score_disagreement"]
        assert score[0]["absorbed_from"] is None

    def test_stale_live_state_after_final_is_caught(self):
        truth = [_truth("Miami Marlins", "Pittsburgh Pirates", start=_ago(21),
                        hs=8, aws=2)]
        ours = [_ours(1, "Miami Marlins", "Pittsburgh Pirates", start=_ago(21),
                      status="live", hs=8, aws=2)]
        assert "schedule_stale_state" in _checks(
            ss.reconcile(truth, ours, MLB, NOW)[0])

    def test_live_game_still_live_is_not_stale(self):
        """Other direction: a game that is genuinely in progress is fine."""
        truth = [_truth("Miami Marlins", "Pittsburgh Pirates", start=_ago(1),
                        state="live", raw="In Progress", hs=1, aws=0)]
        ours = [_ours(1, "Miami Marlins", "Pittsburgh Pirates", start=_ago(1),
                      status="live", hs=1, aws=0)]
        assert ss.reconcile(truth, ours, MLB, NOW)[0] == []

    def test_premature_settle_is_caught(self):
        truth = [_truth("Miami Marlins", "Pittsburgh Pirates", start=_ago(1),
                        state="live", raw="In Progress", hs=1, aws=0)]
        ours = [_ours(1, "Miami Marlins", "Pittsburgh Pirates", start=_ago(1),
                      status="closed", hs=1, aws=0)]
        assert "schedule_premature_settle" in _checks(
            ss.reconcile(truth, ours, MLB, NOW)[0])


# ---------------------------------------------------------------------------
# EXTRA vs DUPLICATE — ours, not in truth.
# ---------------------------------------------------------------------------
class TestExtraAndDuplicate:
    def test_two_rows_for_one_real_game_is_a_duplicate(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3)]
        ours = [
            _ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(7), hs=5, aws=3),
            _ours(2, "Toronto Blue Jays", "Boston Red Sox", start=_ago(7), hs=5, aws=3),
        ]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        dup = [f for f in findings if f["kind"] == "DUPLICATE"]
        assert len(dup) == 1 and dup[0]["event_id"] == 2
        assert "EXTRA" not in _kinds(findings)

    def test_row_matching_no_real_game_is_extra_not_duplicate(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3)]
        ours = [
            _ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(7), hs=5, aws=3),
            _ours(2, "Reno Aces", "Tacoma Rainiers", start=_ago(7), hs=1, aws=0),
        ]
        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        assert _kinds(findings) == {"EXTRA": 1}

    def test_settled_extra_with_a_published_score_is_real(self):
        """We are showing a RESULT for a game the authority says never happened."""
        ours = [_ours(2, "Reno Aces", "Tacoma Rainiers", start=_ago(7),
                      status="closed", hs=1, aws=0)]
        classified = ss.classify_findings(
            ss.reconcile([], ours, MLB, NOW)[0], MLB, NOW)
        assert len(classified["real"]) == 1
        assert classified["real"][0]["kind"] == "EXTRA"

    def test_unsettled_extra_is_watch_not_real(self):
        """Other direction: a scheduled placeholder with no published result is
        surfaced, never filed."""
        ours = [_ours(2, "Reno Aces", "Tacoma Rainiers", start=_ahead(7),
                      status="scheduled")]
        classified = ss.classify_findings(
            ss.reconcile([], ours, MLB, NOW)[0], MLB, NOW)
        assert classified["real"] == []
        assert len(classified["watch"]) == 1


# ---------------------------------------------------------------------------
# The artifact registry — EXPLAINED, not REAL.
# ---------------------------------------------------------------------------
class TestExplainedNotReal:
    def test_postponed_game_we_do_not_hold_is_explained(self):
        """The acceptance criterion. A rain-out is not a completeness defect."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        state="postponed", raw="Postponed")]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert classified["real"] == []
        assert len(classified["explained"]) == 1
        assert ss.schedule_verdict(classified, covered=True) == "green"

    def test_a_played_game_we_do_not_hold_is_still_real(self):
        """Other direction: the postponement excuse must not leak onto a game
        that actually happened."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        state="final", hs=5, aws=3)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert len(classified["real"]) == 1

    def test_postponement_not_reflected_on_our_row_is_explained(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        state="postponed", raw="Postponed")]
        ours = [_ours(1, "Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                      status="scheduled")]
        classified = ss.classify_findings(
            ss.reconcile(truth, ours, MLB, NOW)[0], MLB, NOW)
        assert classified["real"] == []
        assert [f["check"] for f in classified["explained"]] == ["schedule_postponed"]

    def test_unplayed_doubleheader_second_game_is_explained(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ahead(9),
                        state="scheduled", raw="Scheduled", dh=True, gnum=2)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert classified["real"] == []
        assert len(classified["explained"]) == 1

    def test_played_doubleheader_second_game_is_real(self):
        """Other direction: once game 2 has been PLAYED, "re-schedule pending" is
        no longer an excuse — we missed a game that happened."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        state="final", hs=5, aws=3, dh=True, gnum=2)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert len(classified["real"]) == 1


# ---------------------------------------------------------------------------
# Coverage — an uncovered league is NOT COVERED, never green.
# ---------------------------------------------------------------------------
class TestCoverageIsStatedNotAssumed:
    def test_uncovered_league_verdict_is_not_covered(self):
        empty = {"league": UNCOVERED.slug, "phase": "in_season",
                 "real": [], "explained": [], "watch": []}
        verdict = ss.schedule_verdict(empty, covered=False)
        assert verdict == ss.NOT_COVERED
        assert verdict != "green"

    def test_every_uncovered_league_declares_a_reason(self):
        for spec in ss.SCHEDULE_LEAGUES:
            if spec.truth is None:
                assert spec.uncovered_reason, f"{spec.slug} is uncovered but silent"

    def test_every_covered_league_has_a_usable_adapter(self):
        for spec in ss.SCHEDULE_LEAGUES:
            if spec.truth == "espn":
                assert spec.espn_path, f"{spec.slug} claims ESPN but has no path"
            elif spec.truth is not None:
                assert spec.truth == "mlb_statsapi"

    def test_unverified_day_is_not_green(self):
        """A day whose authority could not be READ has not been checked, and an
        unchecked day may not borrow GREEN's authority (the LAT-P017 lesson)."""
        clean = {"league": "mlb", "phase": "in_season",
                 "real": [], "explained": [], "watch": []}
        assert ss.schedule_verdict(clean, covered=True) == "green"
        assert ss.schedule_verdict(
            clean, covered=True,
            days_unverified=["2026-08-11: statsapi fetch failed"]
        ) == ss.GREEN_UNVERIFIED

    def test_real_defects_still_win_over_unverified(self):
        red = {"league": "mlb", "phase": "in_season",
               "real": [{"check": "x", "severity": "critical", "kind": "MISSING"}],
               "explained": [], "watch": []}
        assert ss.schedule_verdict(red, covered=True,
                                   days_unverified=["boom"]) == "red"


# ---------------------------------------------------------------------------
# Season windows — quiet windows explain, they never silence a played game.
# ---------------------------------------------------------------------------
class TestSeasonWindows:
    def test_offseason_does_not_excuse_a_played_game(self):
        """If the authority says a game was played, the calendar cannot excuse
        our not having it — whatever season_windows believes about the month."""
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox",
                        start=NOW_OFFSEASON - timedelta(hours=7),
                        state="final", hs=5, aws=3)]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW_OFFSEASON)[0], MLB, NOW_OFFSEASON)
        assert classified["phase"] == "offseason"
        assert len(classified["real"]) == 1

    def test_offseason_postponement_is_explained_with_a_note(self):
        truth = [_truth("Toronto Blue Jays", "Boston Red Sox",
                        start=NOW_OFFSEASON - timedelta(hours=7),
                        state="postponed", raw="Postponed")]
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW_OFFSEASON)[0], MLB, NOW_OFFSEASON)
        assert classified["real"] == []
        assert classified["explained"][0]["explained_by"]


# ---------------------------------------------------------------------------
# Window bucketing — the authority's calendar, not UTC.
# ---------------------------------------------------------------------------
class TestWindowDays:
    def test_window_is_yesterday_today_tomorrow_in_league_tz(self):
        days = ss.window_days(MLB, NOW)
        # NOW is 06:00 UTC = 02:00 ET on 2026-08-12, so the ET "today" is Aug 12.
        assert [d.isoformat() for d in days] == [
            "2026-08-11", "2026-08-12", "2026-08-13"]

    def test_league_tz_shifts_the_window(self):
        epl = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "epl")
        assert [d.isoformat() for d in ss.window_days(epl, NOW)] == [
            "2026-08-11", "2026-08-12", "2026-08-13"]


# ---------------------------------------------------------------------------
# Gotcha #42 — one poison item never voids its healthy siblings.
# ---------------------------------------------------------------------------
class TestPoisonIsolation:
    def test_one_bad_our_row_does_not_void_the_reconcile(self):
        """A row that raises on attribute access sits in the SAME pass as a
        healthy MISSING. The healthy sibling must still land (#1091's lesson)."""
        class Poison:
            id = 99

            def __getattr__(self, name):
                raise RuntimeError("poison row")

        truth = [_truth("Toronto Blue Jays", "Boston Red Sox", start=_ago(7),
                        hs=5, aws=3, key="healthy")]
        findings, _ = ss.reconcile(truth, [Poison()], MLB, NOW)  # type: ignore[list-item]
        missing = [f for f in findings if f["check"] == "schedule_missing"]
        assert [f["truth_key"] for f in missing] == ["healthy"]

    def test_classify_survives_a_malformed_finding(self):
        bad = object()
        good = ss._finding("schedule_missing", "critical", "d", kind="MISSING")
        classified = ss.classify_findings([bad, good], MLB, NOW)  # type: ignore[list-item]
        assert good in classified["real"]

    async def test_one_poison_league_leaves_its_siblings_measured(self, monkeypatch):
        """The run-level guarantee: a league that blows up is RED on its own, and
        every other league is still reconciled and reported."""
        import app.tasks.schedule_sentinel as mod

        healthy = [s for s in ss.SCHEDULE_LEAGUES if s.slug in ("mlb", "nba")]
        monkeypatch.setattr(mod, "SCHEDULE_LEAGUES", tuple(healthy))

        async def fake_run_league(client, spec, now=None):
            if spec.slug == "mlb":
                raise RuntimeError("statsapi exploded")
            return {"league": spec.slug, "window": "w", "verdict": "green",
                    "coverage": {"league": spec.slug, "covered": True,
                                 "truth": "espn"},
                    "classified": {"league": spec.slug, "phase": "offseason",
                                   "real": [], "explained": [], "watch": []},
                    "days_unverified": [], "truth_games": 0, "our_events": 0,
                    "stats": {}, "kind_counts": {}}

        monkeypatch.setattr(mod, "run_league", fake_run_league)
        monkeypatch.setattr(mod, "_load_overrides", lambda: None)

        async def fake_publish(**kwargs):
            return {"durable": "ok", "volatile": "ok"}

        monkeypatch.setattr("app.services.durable_snapshots.publish_sentinel_evidence",
                            fake_publish)

        stats = await mod._run_schedule_sentinel(file_issues=False, now=NOW)
        by_league = {lg["league"]: lg for lg in stats["leagues"]}
        assert by_league["mlb"]["verdict"] == "red"
        assert by_league["nba"]["verdict"] == "green"      # sibling survived
        assert stats["scorecard"]["leagues_total"] == 2


# ---------------------------------------------------------------------------
# Scorecard + filing.
# ---------------------------------------------------------------------------
class TestScorecardAndFiling:
    def test_fingerprint_is_stable_per_league_not_per_day(self):
        """#1796: "dedupe so a persistent hole does not file daily". A date in the
        fingerprint would file a fresh issue every morning."""
        assert ss.schedule_fingerprint("mlb") == ss.schedule_fingerprint("mlb")
        assert ss.schedule_fingerprint("mlb") != ss.schedule_fingerprint("nba")

    def test_issue_body_declares_the_dedupe_key_canonically(self):
        from app.tasks.sentinel_filing import declared_fingerprints

        real = [ss._finding("schedule_missing", "critical", "a game is gone",
                            kind="MISSING")]
        body = ss.build_schedule_issue_body({
            "classified": {"league": "mlb", "phase": "in_season", "real": real,
                           "explained": [], "watch": []},
            "window": "2026-08-11..2026-08-13", "coverage": {"truth": "mlb_statsapi"},
            "truth_games": 40, "our_events": 27,
        })
        assert ("schedule-sentinel-fingerprint",
                ss.schedule_fingerprint("mlb")) in declared_fingerprints(body)

    def test_severity_is_p1_for_a_critical_defect(self):
        assert ss.severity_for_schedule(
            [ss._finding("x", "critical", "d", kind="MISSING")]) == "P1"
        assert ss.severity_for_schedule(
            [ss._finding("x", "warning", "d", kind="MISSING")]) == "P2"

    def test_title_names_the_classes_that_fired(self):
        real = [ss._finding("a", "critical", "d", kind="MISSING"),
                ss._finding("b", "critical", "d", kind="MISATTACHED")]
        title = ss.build_schedule_issue_title("mlb", real, "2026-08-11..2026-08-13")
        assert title.startswith(ss._schedule_title_prefix("mlb"))
        assert "1 MISSING" in title and "1 MISATTACHED" in title

    def test_green_league_closes_its_canonical_issue(self, monkeypatch):
        from app.tasks import bug_report_github as gh

        closed = {}
        monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
        monkeypatch.setattr(gh, "close_issue",
                            lambda n, comment=None: closed.update(n=n))
        fp = ss.schedule_fingerprint("mlb")
        existing = [{"number": 4242,
                     "body": f"schedule-sentinel-fingerprint:{fp}  (dedupe key)"}]
        res = ss.file_schedule_issue(
            {"classified": {"league": "mlb", "phase": "in_season", "real": [],
                            "explained": [], "watch": []},
             "window": "w"},
            open_issues=existing)
        assert res["action"] == "resolved" and closed["n"] == 4242

    def test_red_league_comments_instead_of_filing_a_duplicate(self, monkeypatch):
        from app.tasks import bug_report_github as gh

        commented, created = {}, []
        monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
        monkeypatch.setattr(gh, "comment_on_issue",
                            lambda n, b: commented.update(n=n))
        monkeypatch.setattr(gh, "create_github_issue",
                            lambda *a, **k: created.append(a) or (1, "n"))
        fp = ss.schedule_fingerprint("mlb")
        existing = [{"number": 77,
                     "body": f"schedule-sentinel-fingerprint:{fp}  (dedupe key)"}]
        res = ss.file_schedule_issue(
            {"classified": {"league": "mlb", "phase": "in_season",
                            "real": [ss._finding("schedule_missing", "critical",
                                                 "d", kind="MISSING")],
                            "explained": [], "watch": []},
             "window": "w", "coverage": {"truth": "mlb_statsapi"},
             "truth_games": 40, "our_events": 27},
            open_issues=existing)
        assert res["action"] == "commented" and commented["n"] == 77
        assert created == []

    async def test_scorecard_states_coverage_as_n_of_m(self, monkeypatch):
        """The badge is "N of M leagues have a truth source", never a bare
        percentage — an uncovered league must be visible as uncovered."""
        import app.tasks.schedule_sentinel as mod

        picked = [s for s in ss.SCHEDULE_LEAGUES if s.slug in ("mlb", "npb")]
        monkeypatch.setattr(mod, "SCHEDULE_LEAGUES", tuple(picked))
        monkeypatch.setattr(mod, "_load_overrides", lambda: None)

        async def fake_run_league(client, spec, now=None):
            covered = spec.truth is not None
            return {"league": spec.slug, "window": "w",
                    "verdict": "green" if covered else mod.NOT_COVERED,
                    "coverage": {"league": spec.slug, "covered": covered,
                                 "truth": spec.truth,
                                 "reason": spec.uncovered_reason},
                    "classified": {"league": spec.slug, "phase": "in_season",
                                   "real": [], "explained": [], "watch": []},
                    "days_unverified": [], "truth_games": 0, "our_events": 0,
                    "stats": {}, "kind_counts": {}}

        monkeypatch.setattr(mod, "run_league", fake_run_league)

        async def fake_publish(**kwargs):
            return {"durable": "ok", "volatile": "ok"}

        monkeypatch.setattr("app.services.durable_snapshots.publish_sentinel_evidence",
                            fake_publish)

        stats = await mod._run_schedule_sentinel(file_issues=False, now=NOW)
        sc = stats["scorecard"]
        assert sc["coverage_label"] == "1 of 2 leagues have a truth source"
        assert sc["leagues_not_covered"] == 1
        assert sc["uncovered_leagues"][0]["league"] == "npb"
        assert sc["uncovered_leagues"][0]["reason"]
        # The uncovered league is counted OUT of the green tally, not into it.
        assert sc["leagues_green"] == 1

    async def test_uncovered_league_never_files_and_never_closes(self, monkeypatch):
        import app.tasks.schedule_sentinel as mod

        picked = [s for s in ss.SCHEDULE_LEAGUES if s.slug == "npb"]
        monkeypatch.setattr(mod, "SCHEDULE_LEAGUES", tuple(picked))
        monkeypatch.setattr(mod, "_load_overrides", lambda: None)
        calls = []
        monkeypatch.setattr(mod, "file_schedule_issue",
                            lambda *a, **k: calls.append(a) or {})
        monkeypatch.setattr("app.tasks.sentinel_filing.fetch_open_alert_issues",
                            lambda: [])

        async def fake_publish(**kwargs):
            return {"durable": "ok", "volatile": "ok"}

        monkeypatch.setattr("app.services.durable_snapshots.publish_sentinel_evidence",
                            fake_publish)

        stats = await mod._run_schedule_sentinel(file_issues=True, now=NOW)
        assert calls == []
        assert stats["scorecard"]["coverage_label"] == "0 of 1 leagues have a truth source"


# ---------------------------------------------------------------------------
# The known-answer shape: #1779's window, reconstructed from the measured facts.
# ---------------------------------------------------------------------------
class TestKnownAnswerShape:
    """Measured against production 2026-08-13 with live statsapi truth: over
    2026-08-10..08-12 the reconcile returns 13 MISSING (9 of them on Aug 11 —
    the incident's original count, exactly), 0 EXTRA, 0 DUPLICATE and 3 games
    with a wrong score. This is the shape assertion for that run: a slate held
    only in part, with the shortfall reported per game rather than as a rate."""

    def test_partial_slate_reports_each_missing_game(self):
        matchups = [
            ("Toronto Blue Jays", "Boston Red Sox"),
            ("Atlanta Braves", "New York Mets"),
            ("Minnesota Twins", "Baltimore Orioles"),
            ("St. Louis Cardinals", "Philadelphia Phillies"),
            ("Arizona Diamondbacks", "Colorado Rockies"),
            ("Athletics", "Tampa Bay Rays"),
            ("San Diego Padres", "Milwaukee Brewers"),
            ("San Francisco Giants", "Houston Astros"),
            ("Los Angeles Dodgers", "Kansas City Royals"),
        ]
        truth = [_truth(h, a, start=_ago(7 + i), hs=1, aws=0, key=f"g{i}")
                 for i, (h, a) in enumerate(matchups)]
        # We hold none of them — the Aug-11 shortfall.
        classified = ss.classify_findings(
            ss.reconcile(truth, [], MLB, NOW)[0], MLB, NOW)
        assert _kinds(classified["real"]) == {"MISSING": 9}
        assert ss.schedule_verdict(classified, covered=True) == "red"
        # Every missing game is named individually — the issue body has to be
        # actionable, not a rate.
        assert all(f["truth_key"] for f in classified["real"])


# ---------------------------------------------------------------------------
# C-SEN-1 [P1] — pairing keyed on names+time, so an id-less create can consume
# authoritative truth and report literal GREEN. Ruling 042: dereference the id.
# ---------------------------------------------------------------------------
NBA = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "nba")


class TestPairingIsKeyedOnIdentity:
    """Codex's specimen: a row nothing individuated, paired 1:1 and called green.

    THE DEFECT. ``pair_events`` scored candidates on ``name_similarity`` and a
    time bound, and ``OurEvent`` did not carry a provider id at all — so the model
    *could not express* the identity needed to reject a row. A shell with the right
    two names, the right start and correctly-wired team FKs paired against official
    truth, produced no REAL finding, no WATCH finding, and a literal ``green``.

    That is the sentinel reporting on the name-matcher. The sentinel exists to
    verify that what should exist EXISTS; a name-and-time pairing verifies that
    something SHAPED LIKE the game exists, which is the weaker claim the whole rail
    was built to stop trusting (#1796's numerator, one layer down).

    THE FIX. Three states, and the middle one is the point:

    * the truth source's id space is one we store (ESPN) and the ids agree →
      ``paired_by='id'``, verified, green;
    * our row carries SOME provider id but not in the truth's id space (MLB truth
      is a ``gamePk``, which we do not hold) → we cannot cross-reference, but the
      row is not an anonymous shell. Counted and named in the output, not a finding;
    * our row carries NO provider id at all → the pairing is UNVERIFIED. Not RED
      (nothing shows a defect) and not GREEN (nothing shows correctness) —
      ``green_unverified``, the state this module already defines for exactly this,
      and for the same LAT-P017 reason.
    """

    HOME, AWAY = "Toronto Blue Jays", "Boston Red Sox"

    def test_an_unindividuated_row_cannot_report_green(self):
        """CODEX'S SPECIMEN, unchanged: right names, right time, right team ids."""
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                        key="777001")]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      individuated=False)]

        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        classified = ss.classify_findings(findings, MLB, NOW)
        verdict = ss.schedule_verdict(classified, covered=True)

        assert stats["paired"] == 1, "the specimen must still PAIR — that is its point"
        assert verdict != "green", (
            "a row no schedule provider has ever named was paired against official "
            "truth on names and a clock, and the sentinel called it green"
        )
        assert verdict == ss.GREEN_UNVERIFIED
        assert "schedule_unverified_pairing" in _checks(findings)

    def test_the_finding_names_the_identity_it_could_not_reach(self):
        """Ruling 042 obligation 1: if only a label was available, SAY SO in the output."""
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                        key="777001")]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      individuated=False)]

        f = next(f for f in ss.reconcile(truth, ours, MLB, NOW)[0]
                 if f["check"] == "schedule_unverified_pairing")
        assert f["paired_by"] == "names"
        assert f["our_row_individuated"] is False
        assert f["truth_key"] == "777001"

    def test_an_id_paired_row_is_green(self):
        """Gotcha #43, the other direction. ESPN truth key ↔ our ``espn_id``."""
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                        key="401816469")]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="401816469")]

        findings, stats = ss.reconcile(truth, ours, NBA, NOW)
        classified = ss.classify_findings(findings, NBA, NOW)

        assert stats["paired"] == 1
        assert stats["paired_by_id"] == 1
        assert ss.schedule_verdict(classified, covered=True) == "green"
        assert "schedule_unverified_pairing" not in _checks(findings)

    def test_an_individuated_row_in_a_foreign_id_space_is_not_flagged(self):
        """No crying wolf. MLB truth is a ``gamePk``; we hold ESPN/StatPal/Odds ids.

        We cannot cross-reference those, but the row is NOT an anonymous shell —
        some provider looked at the schedule and named it. Reporting every MLB pair
        as unverified would make the state constant, and a constant is not a signal.
        """
        truth = [_truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                        key="777001")]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      espn_id="401816469", statpal_id="355179")]

        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        classified = ss.classify_findings(findings, MLB, NOW)

        assert "schedule_unverified_pairing" not in _checks(findings)
        assert ss.schedule_verdict(classified, covered=True) == "green"
        assert stats["paired_by_names_foreign_id_space"] == 1

    def test_the_id_is_consumed_before_names_ever_run(self):
        """The ordering IS the fix, not a tiebreak.

        Two ESPN truth games for the same matchup on the same day — a doubleheader.
        Our two rows carry the ESPN ids, but the CLOSER-IN-TIME row holds game 2's
        id. A names+time pass pairs each row to its nearest truth game and gets
        both backwards; identity pairs them correctly regardless of the clock.
        """
        t1 = _truth(self.HOME, self.AWAY, start=_ago(12), hs=4, aws=2,
                    key="401816469", dh=True, gnum=1)
        t2 = _truth(self.HOME, self.AWAY, start=_ago(6), hs=1, aws=0,
                    key="401816470", dh=True, gnum=2)
        # Deliberately cross-wired against the clock.
        o1 = _ours(1, self.HOME, self.AWAY, start=_ago(12), hs=1, aws=0,
                   espn_id="401816470")
        o2 = _ours(2, self.HOME, self.AWAY, start=_ago(6), hs=4, aws=2,
                   espn_id="401816469")

        paired = ss.pair_events([t1, t2], [o1, o2], "espn_id")
        by_event = {p["ours"].id: p["truth"].key for p in paired["pairs"]}

        assert by_event == {1: "401816470", 2: "401816469"}, (
            "pairing followed the clock instead of the id"
        )
        assert all(p["paired_by"] == "id" for p in paired["pairs"])

    def test_a_doubleheader_paired_only_by_names_is_never_verified(self):
        """``game_number`` is the provider's own doubleheader marker.

        When truth says two games share a matchup and a day, a names+time pairing
        is ambiguous BY CONSTRUCTION — there is no clock reading that makes it
        sound. Even an otherwise-individuated row cannot claim a verified pair.
        """
        t1 = _truth(self.HOME, self.AWAY, start=_ago(12), hs=4, aws=2,
                    key="777001", dh=True, gnum=1)
        t2 = _truth(self.HOME, self.AWAY, start=_ago(6), hs=1, aws=0,
                    key="777002", dh=True, gnum=2)
        ours = [
            _ours(1, self.HOME, self.AWAY, start=_ago(12), hs=4, aws=2,
                  statpal_id="355179"),
            _ours(2, self.HOME, self.AWAY, start=_ago(6), hs=1, aws=0,
                  statpal_id="355180"),
        ]

        findings, _ = ss.reconcile([t1, t2], ours, MLB, NOW)
        classified = ss.classify_findings(findings, MLB, NOW)

        assert _checks(findings) >= {"schedule_unverified_pairing"}
        assert ss.schedule_verdict(classified, covered=True) == ss.GREEN_UNVERIFIED
        assert classified["real"] == [], "ambiguity is not a defect — it is unverified"

    def test_unverified_pairing_never_outranks_a_real_defect(self):
        """RED still wins. An unverified pairing must not launder a MISSING game."""
        truth = [
            _truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2, key="777001"),
            _truth("New York Mets", "Atlanta Braves", start=_ago(7), hs=3, aws=1,
                   key="777002"),
        ]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      individuated=False)]

        findings, _ = ss.reconcile(truth, ours, MLB, NOW)
        classified = ss.classify_findings(findings, MLB, NOW)

        assert ss.schedule_verdict(classified, covered=True) == "red"

    def test_the_filed_issue_states_how_many_pairings_rest_on_a_label(self):
        """Ruling 042 obligation 1 lands in the OUTPUT, not a comment in the code."""
        truth = [
            _truth(self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2, key="777001"),
            _truth("New York Mets", "Atlanta Braves", start=_ago(7), hs=3, aws=1,
                   key="777002"),
        ]
        ours = [_ours(1, self.HOME, self.AWAY, start=_ago(7), hs=4, aws=2,
                      individuated=False)]
        findings, stats = ss.reconcile(truth, ours, MLB, NOW)
        body = ss.build_schedule_issue_body({
            "classified": ss.classify_findings(findings, MLB, NOW),
            "coverage": {"truth": "mlb_statsapi"}, "window": "3d",
            "truth_games": 2, "our_events": 1,
        })
        assert "could NOT be dereferenced" in body
        assert "Unverified pairings" in body
        assert stats["truth_id_space"] == "mlb_statsapi (not stored)"
