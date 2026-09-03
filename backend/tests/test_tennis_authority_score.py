"""lane1/064 — the authority writes the tennis SCORE through the anchor.

THE SHIP: a US Open match that says FINAL stops printing a blank result.

Measured on production 2026-09-03T04:2xZ over the 202 tennis rows carrying an
ESPN anchor, replayed against the live scoreboard through the exact functions
under test here::

    122  the row already agrees with the authority   -> nothing written
     37  settled, BLANK, and ESPN holds the result   -> filled
      1  settled with a frozen mid-match score       -> corrected
     42  ESPN has not played it yet                  -> refused `not-played`
      0  orientation unresolved

The 37 are real first-round US Open matches — Alcaraz beat Safiullin 6-4, 6-4,
6-4 — that a wall-clock staleness net closed on an Odds API session-start
default before any source published a result.  Searching "Safiullin" on the site
returned seven cards saying **FINAL** with no score and no winner on any of them.

Every fixture below is shaped on a competition read off that live board, and the
competition ids are the real ones so a payload-shape change breaks these rather
than sailing past them.  The two that carry the whole policy:

    182705  Alcaraz d. Safiullin 6-4, 6-4, 6-4  — the blank final, and the
            orientation test (ESPN lists Alcaraz FIRST; our row is Safiullin
            home, so a straight read would publish the score backwards)
    184685  O'Connell v Piros, 7-5, 6-7 RETIRED — the side ESPN flags as the
            match winner holds NO set flags, so a set count published here would
            name the loser as ahead
"""

import pytest

from app.services.espn_tennis import competition_sides, scoreboard_competitions
from app.utils.espn_tennis_anchor import (
    SCORE_NOT_A_COMPLETED_RESULT,
    SCORE_NOT_PLAYED,
    SCORE_NO_LINE,
    SCORE_ORIENTATION_UNRESOLVED,
    authority_score,
    authority_score_write,
    authority_write,
    orient_sides,
)


def _line(value, won):
    """One set on ESPN's board: a game count and ITS OWN winner flag."""
    return {"value": float(value), "winner": won}


def _side(name, games_and_flags, winner=None):
    competitor = {
        "id": "3203",
        "type": "athlete",
        "athlete": {"displayName": name, "id": "3203"},
        "linescores": [_line(v, w) for v, w in games_and_flags],
    }
    if winner is not None:
        competitor["winner"] = winner
    return competitor


def _competition(comp_id, sides, *, state="post", status_name="STATUS_FINAL",
                 period=3, date="2026-08-30T19:30Z"):
    return {
        "id": comp_id,
        "date": date,
        "status": {
            "period": period,
            "type": {
                "name": status_name,
                "state": state,
                "detail": "Final",
                "shortDetail": "Final",
            },
        },
        "competitors": sides,
    }


def _payload(competitions, slug="mens-singles", event_name="US Open"):
    return {"events": [{
        "name": event_name,
        "groupings": [{"grouping": {"slug": slug}, "competitions": competitions}],
    }]}


def _board(competition):
    """One competition, through the same reader the sync task uses."""
    return scoreboard_competitions([_payload([competition])])[0]


#: 182705 — Carlos Alcaraz d. Roman Safiullin 6-4, 6-4, 6-4.  ESPN lists the
#: WINNER first; our row has Safiullin as home.
ALCARAZ_SAFIULLIN = _competition("182705", [
    _side("Carlos Alcaraz", [(6, True), (6, True), (6, True)], winner=True),
    _side("Roman Safiullin", [(4, False), (4, False), (4, False)], winner=False),
])

#: 184685 — Zsombor Piros advanced when Christopher O'Connell retired at
#: 7-5, 6-7.  The winner holds NO set flags; the loser holds one.
OCONNELL_PIROS = _competition("184685", [
    _side("Christopher O'Connell", [(7, True), (6, False)], winner=False),
    _side("Zsombor Piros", [(5, False), (7, False)], winner=True),
], status_name="STATUS_RETIRED", period=2)

#: 184769 — Grigor Dimitrov bt Otto Virtanen w/o.  A winner flag and not one
#: line score on either side.
DIMITROV_WALKOVER = _competition("184769", [
    _side("Grigor Dimitrov", [], winner=True),
    _side("Otto Virtanen", [], winner=False),
], status_name="STATUS_WALKOVER", period=1)

#: 182706 — Dane Sweeny 7-6, 6-4 and Corentin Moutet retired in the third.  The
#: winner already HELD two sets, so this one is a real result.
MOUTET_SWEENY = _competition("182706", [
    _side("Corentin Moutet", [(6, False), (4, False), (0, False)], winner=False),
    _side("Dane Sweeny", [(7, True), (6, True), (3, False)], winner=True),
], status_name="STATUS_RETIRED")


# ═════════════════════ sets come off ESPN's own flag ═════════════════════


class TestCompetitionSides:
    def test_sets_are_counted_off_the_per_set_winner_flag(self):
        """NOT off a games comparison.  On 184685 the two disagree, and only one
        of them agrees with who advanced."""
        sides = competition_sides(OCONNELL_PIROS)
        by_name = {s["name"]: s for s in sides}
        # Games would read this 1-1 (7>5 and 7>6). ESPN awards the second set to
        # nobody, and that is the true statement.
        assert by_name["Christopher O'Connell"]["sets_won"] == 1
        assert by_name["Zsombor Piros"]["sets_won"] == 0
        assert by_name["Zsombor Piros"]["winner"] is True

    def test_a_clean_final_counts_the_same_either_way(self):
        """The control — the flag rule must not move the ordinary case."""
        sides = competition_sides(ALCARAZ_SAFIULLIN)
        assert [(s["name"], s["sets_won"]) for s in sides] == [
            ("Carlos Alcaraz", 3), ("Roman Safiullin", 0),
        ]

    def test_the_games_line_travels_with_the_count(self):
        """So a caller can print `6-4, 6-4, 6-4` without re-reading the payload."""
        sides = competition_sides(ALCARAZ_SAFIULLIN)
        assert sides[0]["games"] == [6, 6, 6]
        assert sides[1]["games"] == [4, 4, 4]

    def test_no_statement_is_none_and_not_false(self):
        """A scheduled match has no winner AND no loser."""
        upcoming = _competition("1", [
            _side("A One", []), _side("B Two", []),
        ], state="pre", status_name="STATUS_SCHEDULED")
        assert [s["winner"] for s in competition_sides(upcoming)] == [None, None]

    def test_an_unreadable_line_costs_only_itself(self):
        """gotcha #42 in miniature: one bad set never drops the other two."""
        broken = _competition("1", [
            {"athlete": {"displayName": "A One"}, "winner": True, "linescores": [
                {"value": 6.0, "winner": True},
                {"value": None, "winner": True},
                {"value": 6.0, "winner": True},
            ]},
            _side("B Two", [(4, False), (4, False), (4, False)], winner=False),
        ])
        side = competition_sides(broken)[0]
        assert side["games"] == [6, 6]
        # The flag is still counted — the set was won, we just cannot print it.
        assert side["sets_won"] == 3

    def test_the_board_read_carries_the_sides(self):
        """`scoreboard_competitions` is the anchor's whole view; the score has to
        come off the SAME read as the state that authorises writing it."""
        entry = _board(ALCARAZ_SAFIULLIN)
        assert entry["state"] == "decided"
        assert [s["sets_won"] for s in entry["sides"]] == [3, 0]


# ═══════════════════════ which side is our home ═══════════════════════


class TestOrientSides:
    def test_espn_order_is_not_our_order(self):
        """ESPN lists Alcaraz first; our row is Safiullin home.  A straight read
        would publish 3-0 to the man who lost 0-3."""
        sides = competition_sides(ALCARAZ_SAFIULLIN)
        home, away = orient_sides(["Roman Safiullin", "Carlos Alcaraz"], sides)
        assert home["name"] == "Roman Safiullin"
        assert away["name"] == "Carlos Alcaraz"

    def test_one_name_is_enough_when_the_other_is_forced(self):
        """`Caty`/`Catherine` McNally defeats `names_agree` outright and her
        opponent does not.  With two sides and one taken, the other is forced —
        the elimination that makes `pairing_anchors` sound."""
        sides = competition_sides(_competition("1", [
            _side("Catherine McNally", [(6, True), (6, True)], winner=True),
            _side("Anouk Koevermans", [(2, False), (3, False)], winner=False),
        ]))
        home, away = orient_sides(["Anouk Koevermans", "Caty McNally"], sides)
        assert home["name"] == "Anouk Koevermans"
        assert away["name"] == "Catherine McNally"

    def test_a_tie_is_refused_rather_than_flipped(self):
        """Nothing matches, so both orientations fit equally badly.  A reversed
        score is worse than no score: a blank is visibly missing."""
        sides = competition_sides(ALCARAZ_SAFIULLIN)
        assert orient_sides(["Somebody Else", "Another Person"], sides) is None

    def test_espn_home_away_is_never_read(self):
        """Ours comes from the Odds API and the two orderings are independent."""
        flipped = _competition("182705", [
            dict(_side("Carlos Alcaraz", [(6, True), (6, True), (6, True)],
                       winner=True), homeAway="home"),
            dict(_side("Roman Safiullin", [(4, False), (4, False), (4, False)],
                       winner=False), homeAway="away"),
        ])
        verdict = authority_score(
            ["Roman Safiullin", "Carlos Alcaraz"], _board(flipped)
        )
        assert (verdict["home_score"], verdict["away_score"]) == (0, 3)


# ═══════════════════ what the authority is allowed to say ═══════════════════


class TestAuthorityScore:
    def test_the_blank_final_gets_its_result(self):
        """THE SHIP.  37 rows on production hold exactly this shape."""
        verdict = authority_score(
            ["Roman Safiullin", "Carlos Alcaraz"], _board(ALCARAZ_SAFIULLIN)
        )
        assert verdict == {"home_score": 0, "away_score": 3, "reason": None}

    def test_a_retirement_whose_sets_name_the_loser_is_refused(self):
        """184685: publishing `1-0` here would put the man who LOST ahead —
        the inverted-winner defect, arriving through a column nothing doubts."""
        verdict = authority_score(
            ["Christopher O'Connell", "Zsombor Piros"], _board(OCONNELL_PIROS)
        )
        assert verdict["reason"] == SCORE_NOT_A_COMPLETED_RESULT
        assert verdict["home_score"] is None and verdict["away_score"] is None

    def test_a_retirement_the_winner_had_already_won_is_written(self):
        """182706: Sweeny held two sets when Moutet retired.  `0-2` is true and
        names the right winner; refusing it would refuse a real result because
        of how it ended."""
        verdict = authority_score(
            ["Corentin Moutet", "Dane Sweeny"], _board(MOUTET_SWEENY)
        )
        assert verdict == {"home_score": 0, "away_score": 2, "reason": None}

    def test_a_walkover_has_no_score_to_write(self):
        """A winner flag and not one line on either side — no set was played."""
        verdict = authority_score(
            ["Grigor Dimitrov", "Otto Virtanen"], _board(DIMITROV_WALKOVER)
        )
        assert verdict["reason"] == SCORE_NO_LINE

    def test_a_decided_competition_nobody_won_is_refused(self):
        """Both flags false is not a result, however good the line looks."""
        nobody = _competition("1", [
            _side("A One", [(6, True), (6, True)], winner=False),
            _side("B Two", [(4, False), (4, False)], winner=False),
        ])
        assert authority_score(["A One", "B Two"], _board(nobody))["reason"] == (
            SCORE_NOT_A_COMPLETED_RESULT
        )

    def test_an_upcoming_match_has_no_score(self):
        """42 rows on production, and the refusal is NAMED rather than silent."""
        upcoming = _competition("1", [
            _side("A One", []), _side("B Two", []),
        ], state="pre", status_name="STATUS_SCHEDULED")
        assert authority_score(["A One", "B Two"], _board(upcoming))["reason"] == (
            SCORE_NOT_PLAYED
        )

    def test_an_unresolvable_orientation_writes_nothing(self):
        verdict = authority_score(
            ["Somebody Else", "Another Person"], _board(ALCARAZ_SAFIULLIN)
        )
        assert verdict["reason"] == SCORE_ORIENTATION_UNRESOLVED

    # ── the live half: ESPN lagging the match by a set ──

    def test_a_match_espn_still_calls_pre_gets_its_running_score(self):
        """RED-FIRST, lane1/054's measured shape: Taberner v Bergs was 6-3, 3-6,
        6-2 and into a fourth set while ESPN's `state` still said `pre`.

        `play_refutes_upcoming` turns that into `in_progress` inside
        `scoreboard_competitions`, which is what entitles the score to be
        written — so the live card gets `1-2` instead of nothing, off the SAME
        contradiction the state write reads."""
        lagging = _competition("182712", [
            _side("Carlos Taberner", [(6, True), (3, False), (2, False), (1, False)]),
            _side("Zizou Bergs", [(3, False), (6, True), (6, True), (2, False)]),
        ], state="pre", status_name="STATUS_SCHEDULED", period=4)
        entry = _board(lagging)
        assert entry["state"] == "in_progress"
        assert authority_score(["Carlos Taberner", "Zizou Bergs"], entry) == {
            "home_score": 1, "away_score": 2, "reason": None,
        }

    def test_and_the_same_fixture_with_no_games_stays_silent(self):
        """THE CONTROL for the rule above.  Without a game on the board the
        competition is genuinely upcoming, and 238 of the 243 `pre` rows on the
        measured scoreboard were exactly that."""
        not_started = _competition("182712", [
            _side("Carlos Taberner", []), _side("Zizou Bergs", []),
        ], state="pre", status_name="STATUS_SCHEDULED", period=1)
        entry = _board(not_started)
        assert entry["state"] == "upcoming"
        assert authority_score(
            ["Carlos Taberner", "Zizou Bergs"], entry
        )["reason"] == SCORE_NOT_PLAYED

    def test_a_live_score_is_held_to_no_legality_rule(self):
        """`1-0` is exactly what a live second set looks like; refusing it would
        refuse the thing the live card wants."""
        one_set_in = _competition("1", [
            _side("A One", [(6, True), (2, False)]),
            _side("B Two", [(4, False), (3, False)]),
        ], state="in", status_name="STATUS_IN_PROGRESS", period=2)
        assert authority_score(["A One", "B Two"], _board(one_set_in)) == {
            "home_score": 1, "away_score": 0, "reason": None,
        }


# ═══════════════════════ changes only, and the why ═══════════════════════


class TestAuthorityScoreWrite:
    def test_a_row_that_already_agrees_is_not_touched(self):
        """122 of the 202 anchored rows, every ten minutes, forever.  A write
        here would be pure churn on rows that are already right."""
        out = authority_score_write(
            ours=["Roman Safiullin", "Carlos Alcaraz"],
            our_home_score=0, our_away_score=3,
            competition=_board(ALCARAZ_SAFIULLIN),
        )
        assert out == {"changes": {}, "reason": None}

    def test_a_blank_row_moves_both_columns(self):
        out = authority_score_write(
            ours=["Roman Safiullin", "Carlos Alcaraz"],
            our_home_score=None, our_away_score=None,
            competition=_board(ALCARAZ_SAFIULLIN),
        )
        assert out == {"changes": {"home_score": 0, "away_score": 3}, "reason": None}

    def test_the_authority_overrules_a_frozen_mid_match_score(self):
        """15293702 Jović v Frech on production: `1-0`, a score frozen by
        whichever poll was last, where ESPN says the match finished 2-0.  §R
        ranks the authority above a score feed, so this is a correction and not
        a fill."""
        jovic = _competition("182636", [
            _side("Iva Jović", [(6, True), (6, True)], winner=True),
            _side("Magdalena Frech", [(3, False), (4, False)], winner=False),
        ])
        out = authority_score_write(
            ours=["Iva Jović", "Magdalena Frech"],
            our_home_score=1, our_away_score=0,
            competition=_board(jovic),
        )
        assert out == {"changes": {"home_score": 2}, "reason": None}

    def test_a_refusal_reports_itself_and_changes_nothing(self):
        out = authority_score_write(
            ours=["Christopher O'Connell", "Zsombor Piros"],
            our_home_score=None, our_away_score=None,
            competition=_board(OCONNELL_PIROS),
        )
        assert out == {"changes": {}, "reason": SCORE_NOT_A_COMPLETED_RESULT}

    def test_agreement_and_refusal_are_told_apart(self):
        """Both produce an empty `changes`, and they mean opposite things — one
        is 'the row is right', the other is 'we declined to speak'."""
        agrees = authority_score_write(
            ours=["Roman Safiullin", "Carlos Alcaraz"],
            our_home_score=0, our_away_score=3,
            competition=_board(ALCARAZ_SAFIULLIN),
        )
        refused = authority_score_write(
            ours=["Grigor Dimitrov", "Otto Virtanen"],
            our_home_score=None, our_away_score=None,
            competition=_board(DIMITROV_WALKOVER),
        )
        assert agrees["changes"] == refused["changes"] == {}
        assert agrees["reason"] is None
        assert refused["reason"] == SCORE_NO_LINE


class TestTheTwoWritesStaySeparate:
    def test_the_state_write_never_touches_a_score(self):
        """`authority_write`'s contract is 'the columns that must move' for
        STATE, and lane1/057's guards are written against exactly that set."""
        changes = authority_write(
            our_status="closed", our_completed_at=None,
            our_commence_time=None, competition=_board(ALCARAZ_SAFIULLIN),
        )
        assert "home_score" not in changes and "away_score" not in changes

    def test_and_a_settled_row_still_gets_its_score(self):
        """THE ORDERING THAT MATTERS.  A `decided` competition leaves an already
        settled row's STATUS alone — `closed` and `completed` are both settled —
        and that is precisely the 37-row population that has been blank for
        days.  A score write gated on a status write would have skipped all of
        them."""
        board = _board(ALCARAZ_SAFIULLIN)
        assert authority_write(
            our_status="closed", our_completed_at=None,
            our_commence_time=None, competition=board,
        ).get("status") is None
        assert authority_score_write(
            ours=["Roman Safiullin", "Carlos Alcaraz"],
            our_home_score=None, our_away_score=None, competition=board,
        )["changes"] == {"home_score": 0, "away_score": 3}
