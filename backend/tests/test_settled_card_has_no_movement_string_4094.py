"""#4094 — a FINAL card never carries an intra-game movement badge or sentence.

Alex, reading My Stuff → "Just Happened" on the phone 2026-09-08:

    every finished Red Sox game says "Line moving" and "odds shifted 46%
    during the game". Of course it did: a game starts near 50/50 and ends at
    100/0.

That "of course" is the whole class. A finished game has a major probability
swing BY CONSTRUCTION, so a movement string on a settled card is guaranteed to
appear and guaranteed to say nothing — it reports the scoreboard back as if it
were market news. Two independent producers had to be guarded, one per string:

* ``highlights.get_highlight_label`` → the blue capsule ("Line moving")
* ``feed_reasons.generate_event_reason`` → the footer badge ("… shifted N%
  during the game")

Both are server-side; the app and the web each render them verbatim, so these
tests are the guard for both surfaces.

Every test asserts BOTH directions. A settled-only assertion would pass just as
well against a function that had stopped labelling line movement at all, which
would silently delete a real pre-game signal.
"""

from datetime import datetime, timedelta, timezone

from app.utils.feed_reasons import generate_event_reason
from app.utils.highlights import (
    EventFlags,
    HighlightResult,
    compute_highlight,
    get_highlight_label,
)

NOW = datetime(2026, 9, 8, 23, 10, tzinfo=timezone.utc)


def _swung(status: str, *, hours_ago: float, **kw) -> HighlightResult:
    """A game with a major swing, in `status`, that ended `hours_ago`.

    Goes through the real `compute_highlight` so the test breaks if the swing
    classification or the finish cascade moves, not just if the label does.
    """
    commence = NOW - timedelta(hours=hours_ago + 3)
    return compute_highlight(
        status=status,
        commence_time=commence,
        sport_key="baseball_mlb",
        # 54.6% → 96% is the Cardinals @ Giants card served on production.
        opening_home_prob=0.546,
        opening_away_prob=0.454,
        current_home_prob=0.96,
        current_away_prob=0.04,
        completed_at=NOW - timedelta(hours=hours_ago),
        now=NOW,
        **kw,
    )


class TestTheLineMovingCapsule:
    """`get_highlight_label` — the blue capsule on the card header."""

    def test_a_finished_game_is_never_labelled_line_moving(self):
        """The production defect: 2 of 3 finished MLB cards wore this."""
        result = _swung("completed", hours_ago=2)
        assert result.flags.probability_swing == "major", (
            "fixture no longer reproduces the defect — a settled card only "
            "reached 'Line moving' because its swing classified as major"
        )
        assert get_highlight_label(result) != "Line moving"

    def test_a_game_finished_over_24h_ago_is_still_settled(self):
        """The sharp case, and the reason the guard reads `hours_since_finish`.

        `flags.is_recently_finished` is a 24h ELIGIBILITY window: it goes False
        again on an older game that is nonetheless just as final. A guard
        written against it would let the capsule back onto every card older
        than a day — the exact rows a reader scrolls to.
        """
        result = _swung("completed", hours_ago=40)
        assert result.flags.is_recently_finished is False
        assert result.hours_since_finish is not None
        assert get_highlight_label(result) != "Line moving"

    def test_closed_is_settled_too(self):
        """`closed` and `completed` are one state to a reader."""
        assert get_highlight_label(_swung("closed", hours_ago=2)) != "Line moving"

    def test_a_scheduled_game_still_earns_line_moving(self):
        """The other direction. Pre-game movement is a real trend.

        Without this, deleting the branch outright would pass every test above.
        """
        result = _swung("scheduled", hours_ago=-6)
        assert result.hours_since_finish is None
        assert get_highlight_label(result) == "Line moving"

    def test_the_guard_reads_the_finish_and_not_the_swing(self):
        """A settled row with no swing was never the bug; it must stay unlabelled."""
        settled_no_swing = HighlightResult(
            flags=EventFlags(probability_swing="stable"),
            hours_since_finish=2.0,
        )
        assert get_highlight_label(settled_no_swing) is None


class TestTheDuringTheGameSentence:
    """`generate_event_reason` — the footer badge."""

    def _reason(self, status: str, reasons: list[str]) -> str:
        return generate_event_reason(
            home_team="San Francisco Giants",
            away_team="St. Louis Cardinals",
            status=status,
            highlight_reasons=reasons,
            home_probability=0.96,
            away_probability=0.04,
            opening_home_prob=0.546,
            home_score=5,
            away_score=4,
        )

    def test_a_finished_game_gets_no_movement_sentence(self):
        """Served on production as "San Francisco Giants odds shifted 27%
        during the game" over a 4-5 final the same card already printed."""
        assert self._reason("completed", ["major_prob_swing"]) == ""

    def test_closed_gets_no_movement_sentence_either(self):
        assert self._reason("closed", ["major_prob_swing"]) == ""

    def test_no_settled_status_says_during_the_game(self):
        """The phrase itself is the class — pin it, not one code path."""
        for status in ("completed", "closed"):
            for reasons in (
                ["major_prob_swing"],
                ["major_prob_swing", "close_matchup"],
                ["major_prob_swing", "favorite_switched"],
            ):
                assert "during the game" not in self._reason(status, reasons)
                assert "shifted" not in self._reason(status, reasons)

    def test_an_upset_keeps_its_settled_sentence(self):
        """The one settled line that earns its place: it reads the result
        against the PRE-GAME number rather than against the final one."""
        assert self._reason("completed", ["upset", "major_prob_swing"]) == (
            "Won as 55% underdog"
        )

    def test_a_live_game_still_reports_its_movement(self):
        """The other direction. Mid-game movement is news; the game is not over."""
        assert self._reason("live", ["major_prob_swing"]) == (
            "San Francisco Giants odds shifted 41%"
        )

    def test_an_upcoming_game_still_reports_movement_since_open(self):
        assert self._reason("scheduled", ["major_prob_swing"]) == (
            "San Francisco Giants odds shifted 41% since open"
        )
