"""#6477 — a finished upset whose price never moved still earns its sentence.

THE SPECIMEN, served on production 2026-09-16 04:1xZ as card 11 of 60 at 390px:

    event 15305823   Alavés 0 - 1 Valencia   La Liga, status=completed
    win_probability_sources = {"polymarket": {"value": 0.0005, ...}}   (and nothing else)
    aggregate 0.7618 == opening 0.7618
    reason: ""            <- a hole, one card below "Baltimore Orioles won as a 44% underdog"

WHY IT COULD NEVER BE CAPTIONED. The settled sentence is admitted by `"upset" in
reasons`, which `highlights.py` appends only behind `favorite_switched` — a PRICE
event, comparing the live aggregate against `opening_favorite`. On a FINISHED game
that aggregate is not free to disagree: `compute_aggregate_probability` drops
`_EXCLUDE_WHEN_COMPLETED = {"kalshi", "polymarket"}` once the status is final, so an
event whose only speaker is a prediction market falls past Tier 1 and Tier 2 to Tier 3
— `opening_home_probability`, the very number `opening_favorite` was derived from. The
gate asks whether the opening price switched away from itself, and the answer is
structural, not empirical. 55 of the 151 decided upsets in the seven days to
2026-09-16 sat in that class, 38 of them prediction-market-only.

The class C test is the one that would have caught this before a reader did: it drives
the REAL aggregation and the REAL flag, so it fails on the mechanism rather than on a
hand-written `reasons` list that merely imitates it.
"""

import pytest

from app.utils.aggregation import compute_aggregate_probability
from app.utils.feed_reasons import generate_event_reason
from app.utils.highlights import CLOSE_MATCHUP_MIN

SPECIMEN_HOME = "Alavés"
SPECIMEN_AWAY = "Valencia"


def _sentence(
    *,
    home_score,
    away_score,
    prematch_percents,
    highlight_reasons=("recent_finish", "tier_1"),
    status="completed",
    opening_home_prob=0.7618,
    home_team=SPECIMEN_HOME,
    away_team=SPECIMEN_AWAY,
):
    """The specimen's card, with only the named field moved."""
    return generate_event_reason(
        home_team=home_team,
        away_team=away_team,
        status=status,
        highlight_reasons=list(highlight_reasons),
        home_probability=opening_home_prob,
        away_probability=(
            None if opening_home_prob is None else 1 - opening_home_prob
        ),
        opening_home_prob=opening_home_prob,
        home_score=home_score,
        away_score=away_score,
        prematch_percents=prematch_percents,
    )


# ── A. THE SPECIMEN ───────────────────────────────────────────────────────────


class TestTheSpecimen:
    def test_the_card_is_no_longer_blank(self):
        """The whole defect, in the reader's terms."""
        assert (
            _sentence(
                home_score=0, away_score=1, prematch_percents={"home": 57, "away": 18}
            )
            == "Valencia won as an 18% underdog"
        )

    def test_it_is_captioned_with_no_upset_reason_present(self):
        """`"upset"` is absent here and must stay absent — that is the point.

        If a later change makes this pass only because something started
        appending `"upset"`, the branch under test is dead and this test is
        measuring the old one.
        """
        reasons = ["recent_finish", "tier_1"]
        assert "upset" not in reasons
        assert _sentence(
            home_score=0,
            away_score=1,
            prematch_percents={"home": 57, "away": 18},
            highlight_reasons=reasons,
        )

    def test_the_sentence_states_the_percent_the_card_prints(self):
        """#4146's rule. The board says 18, so the sentence says 18 — not 24,
        which is what rounding the books' complement (1 - 0.7618) would give."""
        text = _sentence(
            home_score=0, away_score=1, prematch_percents={"home": 57, "away": 18}
        )
        assert "18%" in text
        assert "24%" not in text


# ── B. EVERY WORD OF THE SENTENCE IS CHECKED ──────────────────────────────────


class TestTheClaimsAreChecked:
    """"X won as an N% underdog" makes three claims. This branch has no price
    event standing behind any of them, so it checks all three itself."""

    def test_a_favourite_that_wins_is_not_called_an_underdog(self):
        assert (
            _sentence(
                home_score=2, away_score=0, prematch_percents={"home": 57, "away": 18}
            )
            == ""
        )

    def test_a_draw_claims_no_winner(self):
        """#6204's rule, which this branch inherits rather than re-litigates:
        a bare `else` on the scoreline declares the away team the winner of
        every level final."""
        assert (
            _sentence(
                home_score=1, away_score=1, prematch_percents={"home": 57, "away": 18}
            )
            == ""
        )

    @pytest.mark.parametrize(
        "percents",
        [
            None,
            {},
            {"home": 57, "away": None},
            {"home": None, "away": 18},
            {"home": None, "away": None},
        ],
        ids=["absent", "empty", "no-winner-pct", "no-loser-pct", "neither"],
    )
    def test_it_fails_closed_when_a_percent_is_unknown(self, percents):
        """THE ASYMMETRY IS DELIBERATE, and it is the one thing in this ship
        most likely to be "tidied" back out.

        `lead_is_printable` returns True when either percent is None — #6187's
        "the unknown case must not become a guess", which exists to keep the
        `"upset"` caller's wording verbatim. Inherited here it would print
        "won as a 76% underdog" over every unprinted favourite that ever won,
        because in this branch nothing else establishes the word.
        """
        assert _sentence(home_score=0, away_score=1, prematch_percents=percents) == ""

    def test_a_live_card_is_not_touched(self):
        """The branch is inside the completed/closed arm. A live card's copy is
        `compose_live_claim`'s and must not acquire a settled sentence."""
        text = _sentence(
            home_score=0,
            away_score=1,
            prematch_percents={"home": 57, "away": 18},
            status="live",
        )
        assert "won as" not in text


# ── C. THE MECHANISM, NOT AN IMITATION OF IT ──────────────────────────────────


class TestTheGateIsStructurallyUnreachable:
    """The tests above hand in a `reasons` list. This one derives it, so it
    fails if the real pipeline can reach the old gate after all."""

    class _Event:
        espn_win_prob_home = None

        def __init__(self, sources, opening):
            self.win_probability_sources = sources
            self.opening_home_probability = opening

    def test_a_completed_pm_only_event_aggregates_to_its_own_opening(self):
        """The whole cause in one assertion.

        Polymarket says 0.0005 — the game is over and it is right. The
        aggregate says 0.7618, the opening, because `_EXCLUDE_WHEN_COMPLETED`
        removed the only speaker and Tier 3 is `opening_home_probability`.
        `favorite_switched` compares those two numbers.
        """
        event = self._Event(
            {
                "polymarket": {
                    "value": 0.0005,
                    "updated_at": "2026-09-15T19:57:29.229205+00:00",
                },
                "betting_book_count": 2,
            },
            0.7618,
        )
        aggregate = compute_aggregate_probability(event, "completed")
        assert aggregate == pytest.approx(0.7618)
        assert aggregate == pytest.approx(float(event.opening_home_probability))

        opening_favorite = "home" if event.opening_home_probability > 0.5 else "away"
        current_favorite = "home" if aggregate > 0.5 else "away"
        assert opening_favorite == current_favorite, (
            "favorite_switched can never fire for this population, so the "
            "caption may not be gated on it"
        )


# ── D. THE MAGNITUDE BAR (#2753 is NOT re-opened on a silent population) ──────


class TestTheMagnitudeBar:
    """24 of the 55 denied upsets had the winner between 40% and 48%, which is
    #2753's open complaint verbatim ("Won as 48% underdog"). Shipping the
    widening without a bar would manufacture that class on a population that is
    currently silent."""

    @pytest.mark.parametrize("winner_pct", [10, 18, 29, 39])
    def test_a_genuine_underdog_is_captioned(self, winner_pct):
        text = _sentence(
            home_score=0,
            away_score=1,
            prematch_percents={"home": 100 - winner_pct, "away": winner_pct},
        )
        assert text.endswith(f"{winner_pct}% underdog"), text

    @pytest.mark.parametrize("winner_pct", [40, 44, 48, 49])
    def test_half_of_a_close_matchup_is_not_an_underdog(self, winner_pct):
        assert (
            _sentence(
                home_score=0,
                away_score=1,
                prematch_percents={"home": 100 - winner_pct, "away": winner_pct},
            )
            == ""
        )

    def test_the_bar_is_the_systems_own_closeness_line(self):
        """Read from `highlights.CLOSE_MATCHUP_MIN` rather than restated, so the
        bar cannot drift away from the constant that gives it its meaning — the
        point at which this module stops saying "Tight game"."""
        boundary = int(CLOSE_MATCHUP_MIN * 100)
        assert (
            _sentence(
                home_score=0,
                away_score=1,
                prematch_percents={"home": 100 - boundary, "away": boundary},
            )
            == ""
        )
        assert _sentence(
            home_score=0,
            away_score=1,
            prematch_percents={"home": 100 - (boundary - 1), "away": boundary - 1},
        )


# ── E. THE `"upset"` BRANCH IS BYTE-IDENTICAL ─────────────────────────────────


class TestNothingAboveTheNewBranchMoves:
    """The `"upset"` block returns on all four of its paths, so a card captioned
    today must be captioned identically. These are the contracts other ships
    pinned; they are restated here so a change to the new branch that reaches
    the old one fails in THIS file, next to the reasoning."""

    def test_the_price_gated_sentence_is_unchanged(self):
        assert (
            generate_event_reason(
                home_team="Dallas Cowboys",
                away_team="New York Giants",
                status="completed",
                highlight_reasons=["upset"],
                opening_home_prob=0.62,
                home_score=20,
                away_score=28,
                prematch_percents={"home": 62, "away": 38},
            )
            == "New York Giants won as a 38% underdog"
        )

    def test_the_price_gated_branch_now_holds_the_same_bar(self):
        """#2753's 49% case used to print on the `"upset"` path, pinned here so
        that staying silent was a decision on the record. #2753 answered it:
        the chip needs the winner beneath `CLOSE_MATCHUP_MIN` on the opening
        pair, and the sentence declines at the same printed bar as this
        file's branch (15318549, "Boston Red Sox won as a 49% underdog")."""
        assert (
            generate_event_reason(
                home_team="Home FC",
                away_team="Away FC",
                status="completed",
                highlight_reasons=["upset"],
                opening_home_prob=0.49,
                home_score=2,
                away_score=1,
                prematch_percents={"home": 49, "away": 51},
            )
            == ""
        )

    def test_the_price_gated_branch_still_fails_open_on_unknown_percents(self):
        """Its fail-OPEN is #6187's convention and is load-bearing for callers
        that were never taught to pass the pair. The new branch's fail-CLOSED
        must not have been implemented by changing this."""
        assert (
            generate_event_reason(
                home_team="Home FC",
                away_team="Away FC",
                status="completed",
                highlight_reasons=["upset"],
                opening_home_prob=0.62,
                home_score=0,
                away_score=1,
                prematch_percents=None,
            )
            == "Away FC won as a 38% underdog"
        )


# ── F. THE ARTICLE ────────────────────────────────────────────────────────────


class TestTheArticleFollowsTheNumber:
    """The specimen is a printed 18, so the old literal "won as a {pct}%" would
    have shipped "a 18% underdog" as the visible half of this ship."""

    @pytest.mark.parametrize(
        "pct,article", [(8, "an"), (11, "an"), (18, "an"), (19, "a"), (39, "a"), (1, "a")]
    )
    def test_the_article_is_the_one_the_percent_is_said_with(self, pct, article):
        text = _sentence(
            home_score=0,
            away_score=1,
            prematch_percents={"home": 100 - pct, "away": pct},
        )
        assert text == f"Valencia won as {article} {pct}% underdog"
