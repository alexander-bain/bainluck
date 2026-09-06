"""live/073 — the match page says what the match was won BY, not just who won.

THE SHIP: `/events/15301243` prints `0 – 3` and, three cards below it, "the
scoreboard reports sets, this market quotes games — we did not record the games
played" over a Games map frozen on `PRE-GAME 29`.  ESPN's own board holds the
answer and always has.

Measured 2026-09-05 before a line of this was written:

    settled tennis rows, last 10 days      211
      `tennis_atp_us_open`, ESPN-anchored  104
      `tennis_wta_us_open`, ESPN-anchored  103
      unanchored                             4
    ...carrying any `box_score_data`         0

So every one of those 207 pages says the absence sentence today, and the number
it is missing was already parsed into `competition["sides"]["games"]` on a read
the tennis authority pass was already doing.

THE FIXTURE IS THE REAL ONE.  `WU_ALCARAZ` below is competition 182723 exactly
as `site.api.espn.com/.../tennis/atp/scoreboard?dates=20260904` served it on
2026-09-05 — `Alcaraz [6,6,6] winner`, `Wu [3,4,1]` — which is the specimen the
directive's before-shot was taken of.  The numbers asserted are that match's
numbers, not a shape: a test that only proves "a line renders when a line is
present" is the no-op this lane already died of once.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_tennis import scoreboard_competitions
from app.utils.espn_tennis_anchor import (
    BOX_SCORE_TENNIS_KEY,
    LINE_OBSERVED_AT_KEY,
    LINE_RAGGED,
    SCORE_NOT_A_COMPLETED_RESULT,
    SCORE_NOT_PLAYED,
    SCORE_NO_LINE,
    SCORE_ORIENTATION_UNRESOLVED,
    authority_games_line,
    games_line_write,
    line_value,
)


def _line(value, won):
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
                 period=3, date="2026-09-04T18:16Z"):
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


def _board(competition):
    """One competition through the same reader the sync task uses."""
    return scoreboard_competitions([{"events": [{
        "name": "US Open",
        "groupings": [{
            "grouping": {"slug": "mens-singles"},
            "competitions": [competition],
        }],
    }]}])[0]


#: 182723 — Carlos Alcaraz d. Wu Yibing 6-3, 6-4, 6-1.  ESPN lists the WINNER
#: first; our event 15301243 has Wu as home, so a straight read publishes the
#: line backwards.
WU_ALCARAZ = _competition("182723", [
    _side("Carlos Alcaraz", [(6, True), (6, True), (6, True)], winner=True),
    _side("Wu Yibing", [(3, False), (4, False), (1, False)], winner=False),
])

#: Our row's two names, home first, spelled the way the Odds API spells them.
OURS = ["Wu Yibing", "Carlos Alcaraz"]


class TestTheLineIsTheRealMatch:
    def test_the_specimen_page_gets_its_score(self):
        """6-3, 6-4, 6-1 to Alcaraz — in OUR order, which is Wu first."""
        verdict = authority_games_line(OURS, _board(WU_ALCARAZ))

        assert verdict["reason"] is None
        assert verdict["sets"] == [[3, 6], [4, 6], [1, 6]]
        assert verdict["home_games"] == 8
        assert verdict["away_games"] == 18

    def test_the_total_is_what_the_games_map_needs(self):
        """26 games played, against the 29 the market quoted pre-game.

        The Games map on this page draws a dial `0 · 17 · 34+` with a single
        `PRE-GAME 29` marker on it.  This is the number that puts a FINAL beside
        it, and it has to be the sum of BOTH sides — a total-games market counts
        every game, not the winner's.
        """
        verdict = authority_games_line(OURS, _board(WU_ALCARAZ))

        assert verdict["home_games"] + verdict["away_games"] == 26

    def test_our_order_is_not_espns_order(self):
        """The same payload, our two names the other way up, reverses the line.

        ESPN's `homeAway` is never read (see `orient_sides`); this is the one
        defect that would be worse than the absence sentence it replaces —
        a page confidently printing the loser's games as the winner's.
        """
        verdict = authority_games_line(
            ["Carlos Alcaraz", "Wu Yibing"], _board(WU_ALCARAZ)
        )

        assert verdict["sets"] == [[6, 3], [6, 4], [6, 1]]
        assert verdict["home_games"] == 18

    def test_a_match_in_progress_gets_the_sets_so_far(self):
        """One set and a break up is a line, and the live card wants it."""
        in_play = _competition("182999", [
            _side("Carlos Alcaraz", [(6, True), (3, None)]),
            _side("Wu Yibing", [(3, False), (1, None)]),
        ], state="in", status_name="STATUS_IN_PROGRESS", period=2)

        verdict = authority_games_line(OURS, _board(in_play))

        assert verdict["reason"] is None
        assert verdict["sets"] == [[3, 6], [1, 3]]
        assert verdict["home_games"] + verdict["away_games"] == 13


class TestTheLineRidesTheScore:
    """Every refusal `authority_score` makes, this makes — same reason string.

    The hero prints the set score and the line prints the games under it.  A
    rule that let one through while refusing the other would put a set-by-set
    line beside a blank hero and make one page argue with itself.
    """

    def test_an_upcoming_match_has_no_line(self):
        upcoming = _competition("182998", [
            _side("Carlos Alcaraz", []),
            _side("Wu Yibing", []),
        ], state="pre", status_name="STATUS_SCHEDULED", period=1)

        verdict = authority_games_line(OURS, _board(upcoming))

        assert verdict["reason"] == SCORE_NOT_PLAYED
        assert verdict["sets"] == []
        assert verdict["home_games"] is None

    def test_a_walkover_has_no_games_to_print(self):
        """184769's shape: a winner flag and not one line score on either side.

        `no-line` and `0-0` are the same silence to a reader and only one of
        them is a score (gotcha #53).
        """
        walkover = _competition("184769", [
            _side("Grigor Dimitrov", [], winner=True),
            _side("Otto Virtanen", [], winner=False),
        ], status_name="STATUS_WALKOVER", period=1)

        verdict = authority_games_line(
            ["Grigor Dimitrov", "Otto Virtanen"], _board(walkover)
        )

        assert verdict["reason"] == SCORE_NO_LINE
        assert verdict["sets"] == []

    def test_a_retirement_the_sets_cannot_describe_gets_no_line_either(self):
        """184685: the side ESPN flags as winner holds NO set flags.

        The games are real games that were really played, and they are still
        refused — because the hero above them is refused, and `6-7, 7-5` under
        a hero with no result at all is half an answer.  When that row gets a
        set score it gets its line in the same pass.
        """
        retired = _competition("184685", [
            _side("Christopher O'Connell", [(7, True), (6, False)], winner=False),
            _side("Zsombor Piros", [(5, False), (7, False)], winner=True),
        ], status_name="STATUS_RETIRED", period=2)

        verdict = authority_games_line(
            ["Christopher O'Connell", "Zsombor Piros"], _board(retired)
        )

        assert verdict["reason"] == SCORE_NOT_A_COMPLETED_RESULT
        assert verdict["sets"] == []

    def test_a_retirement_the_winner_had_already_won_does_get_its_line(self):
        """182706: Sweeny held 7-6, 6-4 when Moutet retired at 0-3 in the third.

        The counterpart to the test above, and the reason the rule is stated as
        "rides the score" rather than "refuses retirements": this one IS a
        result, so its games print too — the abandoned set included, because it
        was played.
        """
        retired = _competition("182706", [
            _side("Corentin Moutet", [(6, False), (4, False), (0, False)], winner=False),
            _side("Dane Sweeny", [(7, True), (6, True), (3, False)], winner=True),
        ], status_name="STATUS_RETIRED")

        verdict = authority_games_line(
            ["Corentin Moutet", "Dane Sweeny"], _board(retired)
        )

        assert verdict["reason"] is None
        assert verdict["sets"] == [[6, 7], [4, 6], [0, 3]]

    def test_two_names_we_cannot_place_write_nothing(self):
        verdict = authority_games_line(
            ["Someone Else", "Nobody Here"], _board(WU_ALCARAZ)
        )

        assert verdict["reason"] == SCORE_ORIENTATION_UNRESOLVED

    def test_two_sides_reporting_different_set_counts_are_refused(self):
        """A mid-write read of the scoreboard is not a line.

        Pairing the common prefix would print a set the other player has not
        been credited with.  Reached through a value that does not parse, which
        is how a real payload produces it: `competition_sides` keeps the set's
        winner FLAG and drops its unreadable value, so the two lists come back
        different lengths and the set score still counts correctly.
        """
        ragged = _competition("182997", [
            _side("Carlos Alcaraz", [(6, True), (6, True)], winner=True),
            {
                "id": "3203",
                "type": "athlete",
                "athlete": {"displayName": "Wu Yibing"},
                "winner": False,
                "linescores": [{"value": "n/a", "winner": False},
                               {"value": 4.0, "winner": False}],
            },
        ], period=2)

        verdict = authority_games_line(OURS, _board(ragged))

        assert verdict["reason"] == LINE_RAGGED
        assert verdict["sets"] == []


class TestWhatGetsStored:
    def test_the_row_gets_the_whole_column_back(self):
        write = games_line_write(
            ours=OURS, our_box_score_data=None, competition=_board(WU_ALCARAZ)
        )

        assert write["reason"] is None
        assert write["box_score_data"] == {
            BOX_SCORE_TENNIS_KEY: {
                "sets": [[3, 6], [4, 6], [1, 6]],
                "home_games": 8,
                "away_games": 18,
                "source": "espn",
            }
        }

    def test_a_neighbour_key_survives_the_merge(self):
        """`box_score_data` is shared. `scoring_plays` and `players` are other
        writers' keys and this one never touches them."""
        existing = {"scoring_plays": [{"period": 1}], "players": {"home": []}}

        write = games_line_write(
            ours=OURS, our_box_score_data=existing, competition=_board(WU_ALCARAZ)
        )

        assert write["box_score_data"]["scoring_plays"] == [{"period": 1}]
        assert write["box_score_data"]["players"] == {"home": []}
        assert write["box_score_data"][BOX_SCORE_TENNIS_KEY]["home_games"] == 8

    def test_the_dict_handed_in_is_never_mutated(self):
        """A JSONB written by mutating the dict SQLAlchemy already holds does
        not flush (gotcha #4).  The caller assigns the return value, and this is
        the arm that proves there is nothing else to assign."""
        existing = {"scoring_plays": []}

        games_line_write(
            ours=OURS, our_box_score_data=existing, competition=_board(WU_ALCARAZ)
        )

        assert existing == {"scoring_plays": []}

    def test_a_row_that_already_says_this_is_not_rewritten(self):
        """The pass runs on a beat.  An unchanged line must not rewrite 200
        JSONB values every cycle, and `line_writes` must stay a count of
        movement rather than of rows considered."""
        first = games_line_write(
            ours=OURS, our_box_score_data=None, competition=_board(WU_ALCARAZ)
        )
        again = games_line_write(
            ours=OURS,
            our_box_score_data=first["box_score_data"],
            competition=_board(WU_ALCARAZ),
        )

        assert again["box_score_data"] is None
        assert again["reason"] is None

    def test_a_line_that_moved_is_written_over(self):
        """A live match's line grows.  Yesterday's stored value is not a reason
        to keep printing it."""
        one_set = _competition("182723", [
            _side("Carlos Alcaraz", [(6, True)]),
            _side("Wu Yibing", [(3, False)]),
        ], state="in", status_name="STATUS_IN_PROGRESS", period=1)

        stored = games_line_write(
            ours=OURS, our_box_score_data=None, competition=_board(one_set)
        )["box_score_data"]
        moved = games_line_write(
            ours=OURS, our_box_score_data=stored, competition=_board(WU_ALCARAZ)
        )

        assert moved["box_score_data"][BOX_SCORE_TENNIS_KEY]["sets"] == [
            [3, 6], [4, 6], [1, 6]
        ]

    def test_a_refusal_leaves_the_column_alone(self):
        """Not "writes an empty line" — leaves it. A row we cannot speak for
        keeps whatever it had, including nothing."""
        upcoming = _competition("182998", [
            _side("Carlos Alcaraz", []),
            _side("Wu Yibing", []),
        ], state="pre", status_name="STATUS_SCHEDULED", period=1)

        write = games_line_write(
            ours=OURS,
            our_box_score_data={"scoring_plays": [1]},
            competition=_board(upcoming),
        )

        assert write["box_score_data"] is None
        assert write["reason"] == SCORE_NOT_PLAYED

    @pytest.mark.parametrize("junk", ["", [], 0, "a string"])
    def test_a_column_holding_something_that_is_not_a_dict_is_replaced(self, junk):
        write = games_line_write(
            ours=OURS, our_box_score_data=junk, competition=_board(WU_ALCARAZ)
        )

        assert write["box_score_data"] == {
            BOX_SCORE_TENNIS_KEY: {
                "sets": [[3, 6], [4, 6], [1, 6]],
                "home_games": 8,
                "away_games": 18,
                "source": "espn",
            }
        }


class TestTheBlastRadius:
    """`box_score_data IS NOT NULL` is a scan predicate in `backfill_winners`
    and `game_moments`, and this ship newly enrols ~200 tennis rows in it.

    Those readers each `.get()` their own key, so a tennis-only column is a
    no-op for them — asserted here against the exact expressions they use,
    because "it should be fine" is not a guard.
    """

    def _tennis_only(self):
        return games_line_write(
            ours=OURS, our_box_score_data=None, competition=_board(WU_ALCARAZ)
        )["box_score_data"]

    def test_the_scoring_plays_reader_sees_nothing(self):
        # `game_state_backfill._…`: (event.box_score_data or {}).get("scoring_plays", [])
        assert (self._tennis_only() or {}).get("scoring_plays", []) == []

    def test_the_player_stats_reader_sees_nothing(self):
        # gotcha #37: player stats live under the "players" key.
        assert (self._tennis_only() or {}).get("players") is None

    def test_the_column_is_still_a_dict_of_named_keys(self):
        """Not a list, not a bare line — the shape every other reader assumes."""
        column = self._tennis_only()

        assert isinstance(column, dict)
        assert set(column) == {BOX_SCORE_TENNIS_KEY}


# ═══════════════════════════════════════════════════════════════════════════
# #3242 — THE LINE SAYS HOW OLD IT IS
# ═══════════════════════════════════════════════════════════════════════════


#: 182540 mid-first-set — the shape #3242 was measured on. `state="in"` is what
#: `scoreboard_competitions` turns into `in_progress`.
IN_PLAY = _competition("182540", [
    _side("Carlos Alcaraz", [(4, False)]),
    _side("Wu Yibing", [(2, False)]),
], state="in", status_name="STATUS_IN_PROGRESS", period=1)

#: A FIXED clock. Never `now()` — an anchor that reads the wall clock makes the
#: assertion below depend on when the suite runs (gotcha #44).
OBSERVED = datetime(2026, 9, 5, 15, 22, 42, tzinfo=timezone.utc)


class TestTheInPlayLineIsStamped:
    """THE SHIP: a reader can tell whether the games count is from this minute
    or from ten minutes ago.

    Measured on production 2026-09-05: ESPN published a match's first game at
    15:12 and our page showed it at 15:22 — one full beat — under a badge
    reading `LIVE · 1s ago`, which is the win-probability write's age and not
    this number's. The page could not say better because nothing recorded when
    this line was observed.
    """

    def test_an_in_play_line_carries_when_it_was_observed(self):
        write = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(IN_PLAY),
            observed_at=OBSERVED,
        )

        line = write["box_score_data"][BOX_SCORE_TENNIS_KEY]
        assert line[LINE_OBSERVED_AT_KEY] == "2026-09-05T15:22:42+00:00"
        # and the line itself is untouched by the stamping
        assert line["sets"] == [[2, 4]]
        assert line["home_games"] == 2

    def test_a_decided_match_is_not_stamped(self):
        """A finished line is final and has no freshness to report. Stamping it
        every pass forever is the write storm this function already refuses —
        and a `Stale` chip on a match that ended on Tuesday is a lie about a
        number that is perfectly correct."""
        write = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(WU_ALCARAZ),
            observed_at=OBSERVED,
        )

        assert LINE_OBSERVED_AT_KEY not in write["box_score_data"][BOX_SCORE_TENNIS_KEY]

    def test_no_clock_no_stamp(self):
        """Every caller that is not the live pass omits `observed_at` and gets
        exactly the payload it got before this existed."""
        write = games_line_write(
            ours=OURS, our_box_score_data=None, competition=_board(IN_PLAY)
        )

        assert LINE_OBSERVED_AT_KEY not in write["box_score_data"][BOX_SCORE_TENNIS_KEY]


class TestTheStampIsAConfirmationNotAChange:
    """`observed_at` answers "when did we last CHECK", not "when did this last
    move". A change time would print `8m ago` for a score we re-confirmed
    thirty seconds ago — the opposite of the reassurance the chip is for."""

    def test_an_unchanged_in_play_line_is_re_stamped(self):
        first = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(IN_PLAY),
            observed_at=OBSERVED,
        )
        later = OBSERVED + timedelta(minutes=10)
        again = games_line_write(
            ours=OURS,
            our_box_score_data=first["box_score_data"],
            competition=_board(IN_PLAY),
            observed_at=later,
        )

        assert again["box_score_data"] is not None, (
            "an unchanged in-play line was not re-confirmed, so its age would "
            "keep growing while we were reading it every 10 minutes"
        )
        line = again["box_score_data"][BOX_SCORE_TENNIS_KEY]
        assert line[LINE_OBSERVED_AT_KEY] == later.isoformat()
        assert line["sets"] == [[2, 4]], "the value must not have moved"

    def test_a_re_stamp_is_not_counted_as_movement(self):
        """`line_writes` has always meant "the line changed". The caller counts
        on `moved` to keep it that way; folding re-stamps in would turn the
        metric into a count of live rows."""
        first = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(IN_PLAY),
            observed_at=OBSERVED,
        )
        again = games_line_write(
            ours=OURS,
            our_box_score_data=first["box_score_data"],
            competition=_board(IN_PLAY),
            observed_at=OBSERVED + timedelta(minutes=10),
        )

        assert first["moved"] is True      # it did not exist before
        assert again["moved"] is False     # same 2-4, re-confirmed

    def test_a_line_that_actually_moved_still_reports_movement(self):
        """The control. If `moved` were always False the metric would be dead in
        the other direction."""
        moved_on = _competition("182540", [
            _side("Carlos Alcaraz", [(5, False)]),
            _side("Wu Yibing", [(2, False)]),
        ], state="in", status_name="STATUS_IN_PROGRESS", period=1)

        first = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(IN_PLAY),
            observed_at=OBSERVED,
        )
        second = games_line_write(
            ours=OURS,
            our_box_score_data=first["box_score_data"],
            competition=_board(moved_on),
            observed_at=OBSERVED + timedelta(minutes=10),
        )

        assert second["moved"] is True
        assert second["box_score_data"][BOX_SCORE_TENNIS_KEY]["sets"] == [[2, 5]]

    def test_a_decided_line_that_has_not_moved_is_still_not_rewritten(self):
        """The invariant this function was built on, re-proved with the stamp in
        play: a settled row must not be rewritten every cycle."""
        first = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(WU_ALCARAZ),
            observed_at=OBSERVED,
        )
        again = games_line_write(
            ours=OURS,
            our_box_score_data=first["box_score_data"],
            competition=_board(WU_ALCARAZ),
            observed_at=OBSERVED + timedelta(minutes=10),
        )

        assert again["box_score_data"] is None
        assert again["moved"] is False

    def test_a_stamp_is_not_part_of_what_moved(self):
        """`line_value` is the one definition of "the value", used by the writer
        and asserted here so the two cannot drift."""
        stamped = {
            "sets": [[2, 4]], "home_games": 2, "away_games": 4,
            "source": "espn", LINE_OBSERVED_AT_KEY: OBSERVED.isoformat(),
        }

        assert line_value(stamped) == {
            "sets": [[2, 4]], "home_games": 2, "away_games": 4, "source": "espn",
        }
        assert line_value(None) is None


class TestTheStampCanGoStale:
    """A freshness signal that cannot report bad news is decoration.

    #3316 measured the tennis beat starved for 42.8 minutes by our own deploy
    rate. Through a stamp, that hole is 42 minutes of visibly ageing chip; the
    row is simply not re-confirmed, because nothing reached it.
    """

    def test_a_row_the_pass_never_reaches_keeps_its_old_stamp(self):
        stored = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(IN_PLAY),
            observed_at=OBSERVED,
        )["box_score_data"]

        # The pass does not run for 40 minutes: nothing calls this function, so
        # the column still holds the 15:22 stamp and the page ages it honestly.
        assert stored[BOX_SCORE_TENNIS_KEY][LINE_OBSERVED_AT_KEY] == OBSERVED.isoformat()

    def test_a_refused_row_is_not_stamped_fresh(self):
        """A refusal means we could not speak for this row. It must not come
        back wearing a current timestamp — that would launder the refusal into
        a freshness claim."""
        upcoming = _competition("182998", [
            _side("Carlos Alcaraz", []),
            _side("Wu Yibing", []),
        ], state="pre", status_name="STATUS_SCHEDULED", period=1)

        write = games_line_write(
            ours=OURS,
            our_box_score_data=None,
            competition=_board(upcoming),
            observed_at=OBSERVED,
        )

        assert write["reason"] == SCORE_NOT_PLAYED
        assert write["box_score_data"] is None
