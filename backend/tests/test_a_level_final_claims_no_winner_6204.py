"""#6204 — a finished card declares a winner over a match that ended level.

** THE PARENT'S BEHAVIOUR IS RECORDED FROM PRODUCTION, NOT FROM A SYNTHETIC RED. **
Read off `GET /api/feed?limit=100&include_futures=false&event_pct=1.0` at 2026-09-14
19:40Z. Eighteen finished cards were served; TWO of them were genuine draws, and both
announced a winner. The scores are the production `events` rows, not the payload:

    15307167  Örebro SK 1-1 Nordic United FC      'Nordic United FC won as a 56% underdog'
    15296378  Argentinos Juniors 1-1 Gimnasia LP  'Gimnasia La Plata won as a 45% underdog'

15307167 is wrong three ways in one line: Nordic United did not win, nobody did, and
56% is the HIGHER of the two numbers the same card printed (`44% · Pre-match · 56%`).

A third card asserted the word without a draw — 15304229, Chicago Fire 1-2 New England
Revolution, `'New England Revolution won as a 50% underdog'` over a row printing
`50% · Pre-match · 50%`. That one is why the underdog test below is on the PRINTED
percents and not on the probabilities: at 0.5/0.5 there is no gap to find, and #6187
measured that exact ties at full precision are real rather than rounding artefacts.

** THE TWO CAUSES. ** The winner was chosen by `if home > away / else`, and a bare
`else` swallows equality, so every level final named the away team. The `upset` tag
that admits the sentence is set in `highlights.py` off `favorite_switched`, a PRICE
flag — the scoreboard was read only to pick a side, never to ask whether there was a
winner to pick. That is #4580, whose note sits in this same function for the LIVE
sentence ("this sentence says *leading*, so the scoreboard decides it, not the price").

** WHAT IS RED ON THE PARENT. ** Every test in `TestALevelFinalClaimsNoWinner` and
`TestUnderdogIsClaimedOnlyWhenTheBoardShowsIt` — the parent emits a sentence where the
fix emits "". They pass no new parameter, so they are honest reds on the parent tree
rather than `TypeError`s. `TestAGenuineUpsetIsUnchanged` and
`TestAnUninformedCallerIsUnchanged` pass IDENTICALLY on both trees and are the guard
that this did not widen — a refusal that swallows the true sentences is the same
defect wearing the other sign.
"""

import ast
from pathlib import Path

import pytest

import app.utils.feed_reasons as fr


def reason(**overrides):
    """A settled card carrying the price-derived `upset` tag."""
    kwargs = dict(
        home_team="Home FC",
        away_team="Away FC",
        status="completed",
        highlight_reasons=["upset"],
        opening_home_prob=0.445,
        home_score=1,
        away_score=1,
        prematch_percents={"home": 44, "away": 56},
    )
    kwargs.update(overrides)
    return fr.generate_event_reason(**kwargs)


class TestALevelFinalClaimsNoWinner:
    """The ship. A card that prints a tie may not print a winner."""

    def test_the_orebro_draw_makes_no_claim(self):
        """15307167, verbatim from the 19:40Z read."""
        assert (
            reason(
                home_team="Örebro SK",
                away_team="Nordic United FC",
                home_score=1,
                away_score=1,
                prematch_percents={"home": 44, "away": 56},
            )
            == ""
        )

    def test_the_argentinos_draw_makes_no_claim(self):
        """15296378 — the other side of the ladder, so a mutant that hard-codes
        one team cannot pass both."""
        assert (
            reason(
                home_team="Argentinos Juniors",
                away_team="Gimnasia La Plata",
                opening_home_prob=0.55,
                home_score=1,
                away_score=1,
                prematch_percents={"home": 55, "away": 45},
            )
            == ""
        )

    def test_a_goalless_draw_makes_no_claim(self):
        """0-0 is the case a `>`-vs-`else` reader is least likely to picture."""
        assert reason(home_score=0, away_score=0) == ""

    def test_a_draw_does_not_fall_back_to_the_bare_string(self):
        """#4640: 'Upset result' is the same false claim with the number removed.

        The parent returns a sentence here and a later edit could 'fix' this by
        returning the bare string instead, which is why it is asserted rather
        than left to the empty-string test above.
        """
        assert reason(home_score=2, away_score=2) != "Upset result"

    def test_a_draw_makes_no_claim_even_with_no_printed_percents(self):
        """The scoreboard decides this one alone.

        `lead_is_printable` fails to today's copy when a percent is unknown, so a
        fix written only as a comparative guard would still print a winner here.
        """
        assert reason(home_score=1, away_score=1, prematch_percents=None) == ""


class TestUnderdogIsClaimedOnlyWhenTheBoardShowsIt:
    """#6187's rule, on the sentence that says `underdog`."""

    def test_a_level_board_claims_no_underdog(self):
        """15304229 — a real 1-2 away win over a row printing 50 · 50."""
        assert (
            reason(
                home_team="Chicago Fire",
                away_team="New England Revolution",
                opening_home_prob=0.5,
                home_score=1,
                away_score=2,
                prematch_percents={"home": 50, "away": 50},
            )
            == ""
        )

    def test_the_pre_match_favourite_winning_claims_no_underdog(self):
        """The favourite won. The word is simply false, draw or no draw."""
        assert (
            reason(
                opening_home_prob=0.62,
                home_score=3,
                away_score=1,
                prematch_percents={"home": 62, "away": 38},
            )
            == ""
        )

    def test_a_one_point_printed_gap_is_a_close_matchup_not_an_underdog(self):
        """This used to pin 49/51 as a real underdog: the direction test is on
        the printed percents, so a probability epsilon could not swallow it.
        That still holds — but #2753 added a SIZE bar on the same printed
        integers (`CLOSE_MATCHUP_MIN`), and a 49% side is half of a close
        matchup. The sentence declines; the card keeps its two percents.
        """
        assert (
            reason(
                opening_home_prob=0.49,
                home_score=2,
                away_score=1,
                prematch_percents={"home": 49, "away": 51},
            )
            == ""
        )


class TestAGenuineUpsetIsUnchanged:
    """Controls. Green on BOTH trees — the guard that this did not widen."""

    def test_the_6181_specimen_keeps_its_sentence(self):
        """14637256, Cowboys 20-28 Giants — the card #6181 shipped for."""
        assert (
            reason(
                home_team="New York Giants",
                away_team="Dallas Cowboys",
                opening_home_prob=0.3908,
                home_score=28,
                away_score=20,
                prematch_percents={"home": 38, "away": 62},
            )
            == "New York Giants won as a 38% underdog"
        )

    def test_an_away_upset_keeps_its_sentence(self):
        """14780147, Cardinals 26-14 — the away arm, still served."""
        assert (
            reason(
                home_team="Home FC",
                away_team="Arizona Cardinals",
                opening_home_prob=0.81,
                home_score=14,
                away_score=26,
                prematch_percents={"home": 81, "away": 19},
            )
            == "Arizona Cardinals won as a 19% underdog"
        )

    def test_a_settled_card_without_the_upset_tag_is_untouched(self):
        assert reason(highlight_reasons=[], home_score=3, away_score=1) == ""

    @pytest.mark.parametrize(
        "scores,expected",
        [
            ((1, 2), "Away FC leading after starting at 30%"),
            ((1, 1), "Away FC chance rose from 30% to 60%"),
        ],
    )
    def test_a_live_card_still_speaks_on_a_level_score(self, scores, expected):
        """A level score is the NORMAL state of a game in progress.

        The refusal above belongs to the settled block alone; a live card at 1-1
        claims no winner in the first place, so it must keep its sentence. Both
        arms of `compose_live_claim` are exercised, the second one precisely
        because it is reached ON a level score.
        """
        home_score, away_score = scores
        assert (
            reason(
                status="live",
                opening_home_prob=0.7,
                home_score=home_score,
                away_score=away_score,
                home_probability=0.4,
                away_probability=0.6,
            )
            == expected
        )


class TestAnUninformedCallerIsUnchanged:
    """Fail to today's copy. Green on both trees."""

    def test_a_caller_with_an_opening_and_no_reading_keeps_its_wording(self):
        assert (
            reason(
                opening_home_prob=0.3908,
                home_score=28,
                away_score=20,
                prematch_percents=None,
            )
            == "Home FC won as a 39% underdog"
        )

    def test_one_missing_side_still_keeps_its_wording(self):
        """`lead_is_printable` returns True when either percent is unknown."""
        assert (
            reason(
                opening_home_prob=0.3908,
                home_score=28,
                away_score=20,
                prematch_percents={"home": 38},
            )
            == "Home FC won as a 38% underdog"
        )

    def test_a_caller_with_no_scores_still_reaches_the_bare_string(self):
        """The pre-existing arm below the branch, untouched."""
        assert reason(home_score=None, away_score=None) == "Upset result"


class TestTheBranchAsksBothQuestions:
    """A source scan, because a bare `else` is what caused this.

    The behavioural tests above all pass if someone restores `else: winner =
    away_team` and adds a separate early return; this asserts the shape that
    cannot swallow equality in the first place.
    """

    SOURCE = Path(fr.__file__).read_text()

    def _settled_branch(self):
        tree = ast.parse(self.SOURCE)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "generate_event_reason"
        )
        return ast.get_source_segment(self.SOURCE, node)

    def test_the_winner_is_chosen_by_two_explicit_comparisons(self):
        body = self._settled_branch()
        assert "elif away_score > home_score:" in body, (
            "the winner is chosen by `if home > away` and a bare `else`, so a "
            "level final is declared an away win again — this is #6204"
        )

    def test_the_settled_branch_resolves_6187s_flag(self):
        body = self._settled_branch()
        assert "lead_is_printable(" in body, (
            "the `underdog` comparative is emitted unguarded, so a card can "
            "call its own printed favourite an underdog"
        )
