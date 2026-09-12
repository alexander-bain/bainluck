"""#4580 — a live card's reason must be earned by the thing it names.

Fable-5, reading tonight's NFL opener on Discover page one (2026-09-09):

    the card read "Upset brewing" while the score was 0-0 in Q1

The probability had moved (0.62 → 0.44) but nothing had happened on the field.
"Upset brewing" names the SCOREBOARD; a price switch is not a scoreboard, so the
sentence was untrue at the reader while every number behind it was correct.

This is the live-side twin of #4094, which established the same doctrine for
settled cards ("NO INTRA-GAME MOVEMENT SENTENCE ON A FINAL CARD ... the sentence
is the scoreboard restated"). The live branch was never given that discipline:

* ``highlights.get_highlight_label`` → the capsule ("Upset brewing")
* ``feed_reasons.generate_event_reason`` → the footer badge, which is the louder
  half because it uses the word *leading*: "{underdog} leading as underdog",
  returned on a price switch alone while ``home_score``/``away_score`` were
  already sitting in its own signature.

THE TRI-STATE IS THE POINT. Measured on production 2026-09-10, **41 of 64 live
events carry no score at all** (both columns NULL). A rule shaped "suppress
unless the underdog leads" would strip the label from those 41 on the strength
of a NULL — including games where the underdog really is ahead. Unknown is never
asserted in either direction; it falls back to the price sentence, which is true
from the data we do have.

Every test asserts BOTH directions. A suppression-only assertion would pass just
as well against a function that had stopped saying "Upset brewing" at all, which
would delete a real signal — the Orlando City card below is the live specimen
that must KEEP its label.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.feed_reasons import generate_event_reason
from app.utils.highlights import (
    compute_highlight,
    get_highlight_label,
    underdog_leads,
)

NOW = datetime(2026, 9, 10, 1, 30, tzinfo=timezone.utc)


def _live(
    *,
    home_score,
    away_score,
    opening_home_prob=0.62,
    current_home_prob=0.44,
):
    """A live game whose favourite switched on price, scored as given.

    Goes through the real ``compute_highlight`` so the test breaks if the
    switch classification moves, not merely if the label does. 0.62 → 0.44 is
    the opener's own move: an 18-point swing (``MAJOR_PROB_SWING`` is 0.15)
    that crosses 0.50, so it sets BOTH ``favorite_switched`` and a major
    ``probability_swing``.
    """
    return compute_highlight(
        status="live",
        commence_time=NOW - timedelta(minutes=20),
        sport_key="americanfootball_nfl",
        opening_home_prob=opening_home_prob,
        opening_away_prob=1 - opening_home_prob,
        opening_favorite="home" if opening_home_prob > 0.5 else "away",
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


class TestTheDeterminationItself:
    """``underdog_leads`` — one derivation, two consumers, no drift."""

    def test_level_game_means_nobody_leads(self):
        """0-0 is not unknown. We know precisely that nobody is ahead."""
        assert underdog_leads(0.62, 0, 0) is False

    def test_the_underdog_ahead_is_true(self):
        """Home opened the underdog (0.38) and is ahead 3-1."""
        assert underdog_leads(0.38, 3, 1) is True

    def test_the_favourite_ahead_is_false(self):
        assert underdog_leads(0.62, 3, 1) is False

    @pytest.mark.parametrize(
        "home_score,away_score",
        [(None, None), (1, None), (None, 1)],
        ids=["both-null", "away-null", "home-null"],
    )
    def test_an_unknown_score_is_unknown_not_false(self, home_score, away_score):
        """The 41-of-64 case. Returning False here would read as 'the underdog
        is not ahead', which we have no basis to say."""
        assert underdog_leads(0.62, home_score, away_score) is None

    def test_no_opening_price_means_no_underdog_to_name(self):
        assert underdog_leads(None, 3, 1) is None

    def test_a_pick_em_has_no_underdog(self):
        """At exactly even there is no underdog for anyone to be."""
        assert underdog_leads(0.5, 3, 1) is None


class TestTheCapsule:
    """``get_highlight_label`` — the capsule on the card header."""

    def test_the_opener_does_not_say_upset_brewing_at_0_0(self):
        """THE PRODUCTION DEFECT. 0-0 in Q1, price moved 0.62 → 0.44."""
        result = _live(home_score=0, away_score=0)
        assert result.flags.favorite_switched is True, (
            "fixture no longer reproduces the defect — the card only reached "
            "'Upset brewing' because the favourite switched on price"
        )
        assert get_highlight_label(result) != "Upset brewing"

    def test_the_opener_says_what_actually_happened(self):
        """The price DID move; that is the true sentence available."""
        assert get_highlight_label(_live(home_score=0, away_score=0)) == "Odds moved"

    def test_the_underdog_actually_ahead_still_says_upset_brewing(self):
        """The other direction, and a live specimen: Orlando City 3-1 at
        Atlanta United, served on production 2026-09-10 and CORRECT."""
        result = _live(
            home_score=1,
            away_score=3,
            opening_home_prob=0.62,
            current_home_prob=0.30,
        )
        assert result.flags.favorite_switched is True
        assert get_highlight_label(result) == "Upset brewing"

    def test_the_favourite_ahead_is_not_an_upset(self):
        """Price crossed over, but the favourite is still winning on the field."""
        assert get_highlight_label(_live(home_score=3, away_score=1)) == "Odds moved"

    def test_an_unknown_score_never_claims_an_upset(self):
        """41 of 64 live rows. We cannot see the field, so we do not describe it."""
        assert get_highlight_label(_live(home_score=None, away_score=None)) == (
            "Odds moved"
        )

    def test_momentum_shift_needs_a_score_not_just_a_move(self):
        """A major swing with nothing on the scoreboard is not momentum.

        No favourite switch here (0.80 → 0.62 stays home), so this lands on the
        major-swing branch rather than the upset branch.
        """
        result = _live(
            home_score=0,
            away_score=0,
            opening_home_prob=0.80,
            current_home_prob=0.62,
        )
        assert result.flags.favorite_switched is False
        assert result.flags.probability_swing == "major"
        assert get_highlight_label(result) == "Odds moved"

    def test_momentum_shift_does_not_survive_a_score_either(self):
        """T10-1 (#5439), ppp default A — REVERSED, deliberately.

        This assertion used to read ``== "Momentum shift"`` and was #4580's
        positive control: a move AND a score was ruled to be genuine momentum.
        The permission is withdrawn. Two numbers that say the price moved and
        that the game is not level cannot establish a sequence of sporting
        events, and on production 2026-09-12 the label came out five times on
        one page — identically over a one-run game and a 17-0 rout.

        Kept here rather than deleted so the reversal is visible at the exact
        line that ratified it.
        """
        result = _live(
            home_score=14,
            away_score=3,
            opening_home_prob=0.80,
            current_home_prob=0.62,
        )
        assert result.flags.probability_swing == "major"
        assert result.flags.someone_is_leading is True
        assert get_highlight_label(result) == "Odds moved"

    def test_a_settled_upset_is_untouched(self):
        """#4094's neighbour. This guard is about LIVE cards only."""
        finished = compute_highlight(
            status="completed",
            commence_time=NOW - timedelta(hours=4),
            sport_key="americanfootball_nfl",
            opening_home_prob=0.62,
            opening_away_prob=0.38,
            opening_favorite="home",
            current_home_prob=0.02,
            current_away_prob=0.98,
            home_score=17,
            away_score=24,
            completed_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        assert get_highlight_label(finished) == "Recent upset"


class TestTheFooterBadge:
    """``generate_event_reason`` — the sentence that says *leading*."""

    def _reason(self, *, home_score, away_score, opening_home_prob=0.62):
        return generate_event_reason(
            home_team="Seattle Seahawks",
            away_team="New England Patriots",
            status="live",
            highlight_reasons=["favorite_switched", "major_prob_swing"],
            home_probability=0.44,
            away_probability=0.56,
            opening_home_prob=opening_home_prob,
            home_score=home_score,
            away_score=away_score,
        )

    def test_nobody_is_leading_at_0_0(self):
        """THE PRODUCTION DEFECT, and the word that makes it a lie."""
        assert "leading" not in self._reason(home_score=0, away_score=0)

    def test_the_0_0_card_falls_back_to_the_price_sentence(self):
        """T10-1 restated the price sentence with both endpoints; the point of
        #4580's assertion — that a 0-0 card talks about the PRICE — is
        unchanged, and is now checkable by the reader."""
        assert self._reason(home_score=0, away_score=0) == (
            "New England Patriots chance rose from 38% to 56%"
        )

    def test_the_underdog_actually_ahead_keeps_its_sentence(self):
        """The other direction — the Orlando City shape, away side ahead."""
        assert self._reason(home_score=1, away_score=3) == (
            "New England Patriots leading after starting at 38%"
        )

    def test_a_home_underdog_ahead_is_named_correctly(self):
        """The mirror, so the test cannot pass on a hard-coded side."""
        assert self._reason(
            home_score=3, away_score=1, opening_home_prob=0.38
        ) == "Seattle Seahawks leading after starting at 38%"

    def test_the_favourite_ahead_is_not_reported_as_an_underdog(self):
        assert "underdog" not in self._reason(home_score=3, away_score=1)

    def test_an_unknown_score_never_says_leading(self):
        """41 of 64 live rows carry no score."""
        assert "leading" not in self._reason(home_score=None, away_score=None)


class TestTheWiring:
    """The scoreboard has to actually ARRIVE, or the fix is inert.

    ``home_score``/``away_score`` are optional keyword arguments with ``None``
    defaults, so a call site that forgets them does not raise — it silently
    reports "score unknown" for every card, and "Upset brewing" quietly stops
    firing everywhere instead of firing correctly. That failure is invisible to
    every behavioural test above, all of which pass their own scores in.

    So these read the CALL SITES, not the logic.
    """

    @pytest.mark.parametrize(
        "module,func",
        [
            ("app.routes.feed", "compute_highlight"),
            ("app.routes.events", "compute_highlight"),
            ("app.routes.feed", "generate_event_reason"),
        ],
    )
    def test_the_scoreboard_reaches_the_producer(self, module, func):
        import ast
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        tree = ast.parse(source)

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func
        ]
        assert calls, f"{func} is no longer called in {module} — retarget this guard"

        for call in calls:
            passed = {kw.arg for kw in call.keywords}
            missing = {"home_score", "away_score"} - passed
            assert not missing, (
                f"{module} calls {func} without {sorted(missing)} at line "
                f"{call.lineno}. The argument defaults to None, so this does not "
                f"raise — it makes every card read 'score unknown' and silently "
                f"retires 'Upset brewing' instead of correcting it (#4580)."
            )
