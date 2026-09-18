"""#6238's CAPTION arm — a live card stops quoting ``1 − home`` as the away team's price.

PILLAR: TRUTH · SHIP: a reader on page one stops being told a 20% underdog
started at 46%, and stops reading a number the venue never quoted for that team.

THE DEFECT, measured on production 2026-09-18 19:37Z (`GET /api/feed?limit=60`,
HTTP 200, anonymous, 390px LOOK in `artifacts-discover/shop-1940Z/phone-top.png`)
— page one, RANK 1, live and 2-0 to the away side:

    Elche CF @ Espanyol   (soccer_spain_la_liga, 33')
        reason / headline  "Elche CF leading after starting at 46%"
        opening_odds       home 0.5352   away 0.2040   sum 0.7392
        current_odds       home 0.2467   away 0.7533   sum 1.0000

46 is ``1 − 0.5352``: *"Espanyol does not win"* — away win OR draw — printed as
Elche's kickoff chance. The board in the SAME payload priced Elche at 0.204, so
the sentence overstated the underdog by 26 points, and the 26 points are the
draw (`opening_odds` is de-vigged three-way since #1011 and sums to 0.74).

Two things make it worse than a wrong number. The card's own duel already
WITHHOLDS this figure — #6238 shipped that withhold on the web (ux/1301), on
native (#5271) and in the payload (`utils/draw_priced_winner`), so the only
place the complement still reached a reader was the sentence underneath it.
And it flattened the better true story: a 20% side was two goals up.

THREE ARMS, ALL THREE FIXED HERE, because they are one defect wearing three
sentences and a fix to one is invisible from the others:

    underdog_lead   "{away} leading after starting at {1 − home}%"
    movement        "{away} chance rose from {1 − home}% to {away current}%"
                    — and the away CURRENT is the complement too (sum 1.0000 on
                      13 of 13 live soccer cards, measured 2026-09-16), so there
                      is nothing to substitute and the move is told from the
                      home side, which is the same move.
    major_prob_swing (upcoming) "{away} odds shifted {|Δ home|}% since open"
                    — states no level, so the only question is whose move it is.

EVERY REJECTION IS PAIRED WITH A CONTROL. A truth fix that is not paired is a
silence fix: deleting the copy passes 100% of a rejection set. Ruling 146 —
suppress the sentence, never the card — is only checkable if something asserts
what survives, so the two-way sentences are pinned byte-for-byte and the
suppressed shapes are asserted to leave a card that still has a caption path.
"""

import ast
import inspect

import pytest

# One import form for `app.routes.feed`, module-level: the AST guard below needs
# the module object for `inspect.getsource`, and mixing `import x` with
# `from x import y` in one file is a CodeQL `py/import-and-import-from` note.
import app.routes.feed as feed_module

from app.utils.feed_reasons import compose_live_claim, generate_event_reason

DRAW_SPORT = "soccer_spain_la_liga"
TWO_WAY_SPORT = "americanfootball_nfl"

# The production specimen, to the stored digit.
ELCHE_OPEN_HOME = 0.5352  # Espanyol, the favourite
ELCHE_OPEN_AWAY = 0.2040  # Elche CF, as the board priced them
ELCHE_NOW_HOME = 0.2467
ELCHE_NOW_AWAY = 0.7533  # 1 − home: the complement the duel already withholds


def live_claim(**overrides):
    """The Elche specimen, live, 2-0 to the away side, unless overridden."""
    kwargs = {
        "home_team": "Espanyol",
        "away_team": "Elche CF",
        "status": "live",
        "home_probability": ELCHE_NOW_HOME,
        "away_probability": ELCHE_NOW_AWAY,
        "opening_home_prob": ELCHE_OPEN_HOME,
        "home_score": 0,
        "away_score": 2,
        "sport": DRAW_SPORT,
        "opening_away_prob": ELCHE_OPEN_AWAY,
    }
    kwargs.update(overrides)
    return compose_live_claim(**kwargs)


class TestTheUnderdogBaseline:
    """The sentence states the underdog's OWN price, or it does not state one."""

    def test_the_production_specimen_no_longer_states_the_complement(self):
        claim = live_claim()
        assert claim is not None, "ruling 146 suppresses sentences, not this one"
        assert claim.claim_type == "underdog_lead"
        assert claim.sentence == "Elche CF leading after starting at 20%"

    def test_the_number_the_card_served_is_gone(self):
        """46% is the whole defect and it must not survive anywhere in the copy."""
        assert "46%" not in live_claim().sentence

    def test_the_claim_is_suppressed_when_the_board_priced_no_away_side(self):
        """Nothing to substitute — and `1 − home` is exactly what we refuse."""
        assert live_claim(opening_away_prob=None) is None

    def test_the_claim_is_suppressed_when_the_stored_away_is_itself_the_complement(
        self,
    ):
        """A row whose `opening_away` was derived, not quoted: 1 − 0.5352.

        `away_is_the_complement` is the house predicate for this and is reused
        rather than restated (`utils/draw_priced_winner`); a pair inside its
        [0.99, 1.01] band is one question asked twice, not two prices.
        """
        assert live_claim(opening_away_prob=1 - ELCHE_OPEN_HOME) is None

    def test_a_suppressed_underdog_sentence_still_leaves_the_card_a_caption_path(self):
        """Ruling 146. The reason falls through to the rungs below it."""
        reason = generate_event_reason(
            home_team="Espanyol",
            away_team="Elche CF",
            status="live",
            highlight_reasons=["close_matchup"],
            home_probability=ELCHE_NOW_HOME,
            away_probability=ELCHE_NOW_AWAY,
            opening_home_prob=ELCHE_OPEN_HOME,
            home_score=0,
            away_score=2,
            sport=DRAW_SPORT,
            opening_away_prob=None,
        )
        assert reason == "Tight game"

    def test_CONTROL_a_two_way_sport_keeps_the_sentence_it_always_had(self):
        """`1 − home` IS the away team's price on a two-way board.

        Passed a stored away opening as well, to pin that the substitution is
        confined to the sport where the complement is provably wrong: this
        sentence must read 46%, from `1 − 0.5352`, and not 20%.
        """
        claim = live_claim(sport=TWO_WAY_SPORT)
        assert claim is not None
        assert claim.sentence == "Elche CF leading after starting at 46%"

    def test_CONTROL_a_two_way_sport_with_no_stored_away_is_unchanged_too(self):
        claim = live_claim(sport=TWO_WAY_SPORT, opening_away_prob=None)
        assert claim is not None
        assert claim.sentence == "Elche CF leading after starting at 46%"

    def test_CONTROL_the_absent_sport_behaves_as_a_two_way_board(self):
        """The default. A caller that has not been taught the argument yet
        cannot be made WORSE by this ship — the AST guard in
        `test_live_caption_forbidden_claims_5439` is what stops it staying
        untaught."""
        claim = live_claim(sport=None, opening_away_prob=None)
        assert claim is not None
        assert claim.sentence == "Elche CF leading after starting at 46%"

    def test_CONTROL_a_home_underdog_on_a_draw_priced_board_is_untouched(self):
        """The home leg is honest (0.7937 against the books' own 0.7939 on
        #6238's Juventus row) and was never the defect. Home opened at 30% and
        is ahead; the sentence quotes the stored home number."""
        claim = live_claim(
            opening_home_prob=0.30,
            opening_away_prob=0.45,
            home_score=2,
            away_score=0,
        )
        assert claim is not None
        assert claim.sentence == "Espanyol leading after starting at 30%"


class TestTheMovementSentence:
    """Both endpoints of an away move are the complement, so the move is told
    from the side we can source."""

    def test_an_away_move_on_a_draw_priced_board_is_told_from_the_home_side(self):
        claim = live_claim(home_score=0, away_score=0)
        assert claim is not None
        assert claim.claim_type == "movement"
        assert claim.sentence == "Espanyol chance fell from 54% to 25%"

    def test_neither_complement_endpoint_survives_in_the_copy(self):
        sentence = live_claim(home_score=0, away_score=0).sentence
        assert "46%" not in sentence  # 1 − opening home
        assert "75%" not in sentence  # current away, derived the same way
        assert "Elche CF" not in sentence

    def test_CONTROL_a_home_move_on_the_same_board_is_unchanged(self):
        """The second live soccer card on the same page-one read: RC Lens @ AS
        Monaco, served "AS Monaco chance rose from 52% to 72%" with both
        numbers the honest home leg. This ship must not touch it."""
        claim = compose_live_claim(
            home_team="AS Monaco",
            away_team="RC Lens",
            status="live",
            home_probability=0.7232,
            away_probability=0.2768,
            opening_home_prob=0.5163,
            home_score=0,
            away_score=0,
            sport=DRAW_SPORT,
            opening_away_prob=0.2370,
        )
        assert claim is not None
        assert claim.sentence == "AS Monaco chance rose from 52% to 72%"

    def test_CONTROL_an_away_move_on_a_two_way_board_still_names_the_away_team(self):
        claim = live_claim(sport=TWO_WAY_SPORT, home_score=0, away_score=0)
        assert claim is not None
        assert claim.sentence == "Elche CF chance rose from 46% to 75%"


class TestTheUpcomingSwingSentence:
    """`{team} odds shifted {|Δ|}% since open` — the delta is the home leg's."""

    def _reason(self, sport, home_now):
        return generate_event_reason(
            home_team="Espanyol",
            away_team="Elche CF",
            status="scheduled",
            highlight_reasons=["major_prob_swing"],
            home_probability=home_now,
            away_probability=1 - home_now,
            opening_home_prob=ELCHE_OPEN_HOME,
            sport=sport,
            opening_away_prob=ELCHE_OPEN_AWAY,
        )

    def test_a_home_fall_on_a_draw_priced_board_is_not_attributed_to_the_away_team(
        self,
    ):
        reason = self._reason(DRAW_SPORT, 0.2467)
        assert reason == "Espanyol odds shifted 29% since open"
        assert "Elche CF" not in reason

    def test_CONTROL_a_home_rise_on_the_same_board_is_unchanged(self):
        assert self._reason(DRAW_SPORT, 0.80) == "Espanyol odds shifted 26% since open"

    def test_CONTROL_a_two_way_fall_still_names_the_away_team(self):
        """On a two-way board a 29-point home fall IS a 29-point away rise."""
        assert self._reason(TWO_WAY_SPORT, 0.2467) == (
            "Elche CF odds shifted 29% since open"
        )


class TestTheRouteFeedsTheReasonBuilderToo:
    """A mutation run wrote this test.

    The `compose_live_claim` call site is guarded by
    `test_live_caption_forbidden_claims_5439`'s AST check, and deleting the two
    new arguments there is caught. Deleting them from the
    `generate_event_reason` call six lines below it SURVIVED the first run of
    this suite: both arguments default to None, None restores the pre-fix
    behaviour, and the `headline` field would still have carried the repaired
    sentence — so every reader keyed on `headline` looks fixed while `reason`,
    which native and the snippet fallback read, quietly serves 46% again.
    """

    def test_the_reason_builder_is_fed_the_sport_and_the_stored_away_opening(self):
        tree = ast.parse(inspect.getsource(feed_module))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "generate_event_reason"
        ]
        assert calls, "routes/feed.py no longer builds an event reason (#6238)"
        for call in calls:
            passed = {kw.arg for kw in call.keywords}
            assert {
                "sport",
                "opening_away_prob",
            } <= passed, f"generate_event_reason is under-fed at line {call.lineno}"


class TestTheSentenceTravelsThroughTheReasonField:
    """`generate_event_reason` composes the same claim; the arguments have to
    reach it, not just the composer."""

    @pytest.mark.parametrize(
        "sport,expected",
        [
            (DRAW_SPORT, "Elche CF leading after starting at 20%"),
            (TWO_WAY_SPORT, "Elche CF leading after starting at 46%"),
        ],
    )
    def test_the_reason_field_carries_the_repaired_sentence(self, sport, expected):
        assert (
            generate_event_reason(
                home_team="Espanyol",
                away_team="Elche CF",
                status="live",
                highlight_reasons=["upset"],
                home_probability=ELCHE_NOW_HOME,
                away_probability=ELCHE_NOW_AWAY,
                opening_home_prob=ELCHE_OPEN_HOME,
                home_score=0,
                away_score=2,
                sport=sport,
                opening_away_prob=ELCHE_OPEN_AWAY,
            )
            == expected
        )
