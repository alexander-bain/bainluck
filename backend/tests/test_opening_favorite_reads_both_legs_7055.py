"""#7055 — "who was the favourite" is a question about BOTH legs.

THE PRODUCTION DEFECT, found on a D48 shop of Discover page one at 390px
2026-09-18 22:30Z and re-verified against the database 2026-09-19 00:07Z.
Event **15305206**, page one, index 11:

    Chelsea @ Brentford
    Brentford won   FINAL   Today 12:00 PM
    36%          Pre-match          39%
    Recent upset

Brentford — the 39%, the HIGHER of the card's own two numbers — won 3-0. The
chip calls that an upset directly above the row that says it was not one.

    opening_home_probability  0.3725   (Brentford)
    opening_away_probability  0.3648   (Chelsea)
    pair sum                  0.7373
    opening_favorite          'away'   <- contradicts its own two numbers

The favourite determination read the home leg alone against a two-way band
(`home > 0.52` / `home < 0.48` / else even). That assumes the away leg is
`1 - home`. Since #1011 it is not: `h2h_pair_on_the_full_board` de-vigs the
named sides over EVERY outcome the book quotes, so on a draw-priced board the
draw keeps a quarter of the mass and BOTH sides sit under 0.48 — and every such
row was recorded `away` whichever side was actually shorter.

Measured on production, the 14 days to 2026-09-18, events carrying an opening
pair:

    | family            | events | contradict own numbers | mirror case |
    |-------------------|--------|------------------------|-------------|
    | draw-priced       |  1,288 |          124           |      0      |
    | two-way (NFL, ML) |  1,461 |            0           |      0      |

Perfect separation. The mirror cannot exist: the band only ever writes `home`
when the home leg alone clears 0.52, so `favorite='home'` with a shorter away
side is unreachable.

═══ WHY #6279's GATE DID NOT CATCH IT ═══

`utils/highlights.py` carries a census justifying the `underdog_is_leading`
gate: "`opening_favorite = 'home'` with `opening_home_probability < 0.5` occurs
0 times, the mirror case 0 times, and the stored opening pair sums to >=0.98 on
every row". The last clause is FALSE for this population — these five rows sum
0.69-0.75 — and the first two are aimed at the one direction the band cannot
produce.

Worse, the gate is blind the SAME way rather than merely silent:
`underdog_leads` derived the underdog as `opening_home_prob < 0.5`, so on
Brentford it called the FAVOURITE the underdog, read its 0.9582 blend, and
returned True. The gate built to suppress false upset chips passed this one
because it inherited the assumption it was guarding against. `TestTheGateWasBlindToo`
pins that it no longer does.

═══ WHAT THIS IS NOT ═══

* **Not a rule against the chip disagreeing with the printed `Pre-match` row.**
  #6279's `TestTheAlarmSurvives` exists because on a three-way card that row can
  itself be fabricated (#6277). This reads the STORED pair, which #6238 measured
  to be the real de-vigged consensus (0.68-0.94 on 11 of 13 soccer cards), not
  the printed one.
* **Not a suppression of soccer upsets.** The old band called a 0.50/0.25 board
  `even` and so threw away a GENUINE upset's chip; the new rule chips it.
  `TestTheAlarmSurvives` pins both directions.
* **Not a data migration.** 103 of the 124 are still scheduled and
  `_maybe_set_opening_odds` rewrites them every poll until kickoff, so they heal
  themselves. The 20 already finished are frozen — and are the ones wearing the
  chip — so `compute_highlight` derives the side from the pair instead of
  trusting the stored string. Zero rows are written.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.highlights import (
    compute_highlight,
    select_live_claim,
    underdog_leads,
)
from app.utils.odds_math import FAVORITE_MARGIN, favorite_from_pair

NOW = datetime(2026, 9, 19, 0, 7, tzinfo=timezone.utc)


def _old_band(home_prob):
    """The rule this replaces, verbatim from `odds_polling.py` before the fix.

    Kept as executable code rather than prose because the whole safety claim is
    that the new form AGREES with it on every two-way board. A paraphrase could
    not be swept.
    """
    if home_prob > 0.52:
        return "home"
    if home_prob < 0.48:
        return "away"
    return "even"


#: The five finished rows carrying the chip, exactly as production stores them.
#: (id, home, away, opening_home, opening_away, home_score, away_score)
SPECIMENS = [
    (15305206, "Brentford", "Chelsea", 0.3725, 0.3648, 3, 0),
    (15308959, "LDU Quito", "Palmeiras-SP", 0.3643, 0.3260, 3, 2),
    (15311112, "Pau FC", "USL Dunkerque", 0.3893, 0.3294, 2, 0),
    (15312082, "SC Verl", "Wurzburger Kickers", 0.4694, 0.2759, 2, 1),
    (15314268, "Worcester City", "Stratford Town", 0.4678, 0.2529, 2, 1),
]


def _finished(
    *,
    opening_home_prob,
    opening_away_prob,
    current_home_prob,
    home_score,
    away_score,
    opening_favorite,
    sport_key="soccer_epl",
):
    """A finished game through the REAL `compute_highlight`.

    `completed_at` two hours back puts the row inside the 24h
    `is_recently_finished` window without the fixture having to know how that
    cascade picks its finish reference. Anchored on a fixed `NOW` and offset
    from it, never truncated off the wall clock (gotcha #44).
    """
    return compute_highlight(
        status="completed",
        commence_time=NOW - timedelta(hours=4),
        completed_at=NOW - timedelta(hours=2),
        sport_key=sport_key,
        opening_home_prob=opening_home_prob,
        opening_away_prob=opening_away_prob,
        opening_favorite=opening_favorite,
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


def _brentford(opening_favorite="away"):
    """15305206 exactly as served: home shorter, home won, stored `away`."""
    return _finished(
        opening_home_prob=0.3725,
        opening_away_prob=0.3648,
        current_home_prob=0.9582,
        home_score=3,
        away_score=0,
        opening_favorite=opening_favorite,
    )


class TestTheGeneralizationIsStrict:
    """No two-way board may move. This is the entire safety argument."""

    def test_agrees_with_the_old_band_on_every_two_way_board(self):
        """Swept, not sampled — the claim is about all of them.

        1,001 boards across the whole [0, 1] range. If the new rule disagreed
        with the old one anywhere the pair sums to 1, every NFL, MLB, NBA and
        NHL card in the product would be in scope of this change, and it would
        no longer be a repair of a soccer defect.
        """
        disagreements = []
        for i in range(1001):
            home = i / 1000
            got = favorite_from_pair(home, 1 - home)
            want = _old_band(home)
            if got != want:
                disagreements.append((home, want, got))
        assert disagreements == []

    @pytest.mark.parametrize("home", [0.48, 0.52])
    def test_holds_at_the_exact_edge_of_the_old_band(self, home):
        """The edge is a real stored value, and binary float does not hold 0.04.

        `0.52 - (1 - 0.52)` is 0.040000000000000036, so without the epsilon the
        ONE place the two forms disagree is the boundary itself — and
        `Numeric(5, 4)` can store exactly 0.5200. Swept above too; named here
        so a regression says which case broke.
        """
        assert favorite_from_pair(home, 1 - home) == "even" == _old_band(home)

    def test_the_sweep_can_actually_fail(self):
        """The sweep is only worth running if a wrong rule would trip it.

        Guards against the equivalence test passing because both sides compute
        the same thing by construction rather than because the rule is right.
        """
        wrong = [
            home / 1000
            for home in range(1001)
            if (lambda h: "home" if h > 0.5 else "away")(home / 1000)
            != _old_band(home / 1000)
        ]
        assert wrong, "a deliberately wrong rule must disagree with the old band"


class TestTheProductionSpecimens:
    """The five finished rows, with the numbers production actually holds."""

    @pytest.mark.parametrize(
        "event_id,home,away,open_home,open_away,hs,aws", SPECIMENS
    )
    def test_the_stored_string_is_contradicted_by_the_stored_numbers(
        self, event_id, home, away, open_home, open_away, hs, aws
    ):
        """Every one stored `away` while the home leg is the shorter price."""
        assert open_home > open_away, f"{event_id}: fixture no longer the defect"
        assert favorite_from_pair(open_home, open_away) != "away"

    @pytest.mark.parametrize(
        "event_id,home,away,open_home,open_away,hs,aws", SPECIMENS
    )
    def test_no_specimen_is_chipped_recent_upset(
        self, event_id, home, away, open_home, open_away, hs, aws
    ):
        """The ship: the chip is gone from all five.

        Driven through the real `compute_highlight` with the stored `away`
        string still in the payload, because that is what the database holds —
        the reader-side derivation is what has to overrule it.
        """
        result = _finished(
            opening_home_prob=open_home,
            opening_away_prob=open_away,
            current_home_prob=0.95,
            home_score=hs,
            away_score=aws,
            opening_favorite="away",
        )
        assert result.flags.is_upset is not True, f"{event_id} still chipped"
        assert "upset" not in result.reasons
        assert "favorite_switched" not in result.reasons

    def test_the_test_would_have_caught_the_defect(self):
        """The BEFORE control: the old rule chips Brentford, so this is not vacuous.

        Without this, a fixture typo that made the card unchippable for some
        unrelated reason would read as a passing fix.
        """
        assert _old_band(0.3725) == "away"
        stale = _brentford()
        # The only thing standing between this payload and the chip is the
        # derivation under test; prove the rest of the cascade still reaches it
        # by asking the same card with a legitimately-switched board.
        genuine = _finished(
            opening_home_prob=0.50,
            opening_away_prob=0.25,
            current_home_prob=0.04,
            home_score=0,
            away_score=2,
            opening_favorite="even",
        )
        assert genuine.flags.is_upset is True, (
            "the upset cascade must still be reachable, or the assertion above "
            "passes for the wrong reason"
        )
        assert stale.flags.is_upset is not True


class TestTheGateWasBlindToo:
    """#6279's `underdog_is_leading` inherited the same two-way assumption."""

    def test_brentford_underdog_is_no_longer_reported_as_leading(self):
        """The favourite won 3-0; the underdog was not ahead."""
        assert (
            underdog_leads(0.3725, 3, 0, 0.3648) is False
        ), "the shorter price winning is not the underdog leading"

    def test_the_old_call_shape_still_answers_the_old_way(self):
        """Without the away leg nothing moves — every existing caller is safe."""
        assert underdog_leads(0.3725, 3, 0) is True

    def test_the_hard_half_split_is_preserved_on_two_way_boards(self):
        """`underdog_leads` splits on a HARD 0.5, not the 0.48/0.52 band.

        A 0.52/0.48 board names a favourite here even though the chip rule
        calls it even. Borrowing FAVORITE_MARGIN would have silenced it, so
        this pins the `margin=0.0` call rather than leaving it to a comment.
        """
        assert FAVORITE_MARGIN == 0.04
        assert favorite_from_pair(0.52, 0.48) == "even"
        assert underdog_leads(0.52, 0, 1, 0.48) is True
        assert underdog_leads(0.48, 1, 0, 0.52) is True

    def test_a_true_pickem_still_has_no_underdog(self):
        assert underdog_leads(0.5, 2, 0, 0.5) is None
        assert underdog_leads(0.5, 2, 0) is None

    def test_a_level_score_is_still_a_known_no(self):
        """0-0 is `False`, not `None` — #4580's third state stays load-bearing."""
        assert underdog_leads(0.3725, 0, 0, 0.3648) is False


class TestTheAlarmSurvives:
    """Both directions. Over-suppression is the other way to get this wrong."""

    def test_a_genuine_three_way_upset_is_chipped(self):
        """Home 0.50 / away 0.25, away wins 2-0 — the favourite lost."""
        result = _finished(
            opening_home_prob=0.50,
            opening_away_prob=0.25,
            current_home_prob=0.04,
            home_score=0,
            away_score=2,
            opening_favorite="even",
        )
        assert result.flags.is_upset is True
        assert "upset" in result.reasons

    def test_that_upset_had_no_chip_before_this_fix(self):
        """The silent half of the defect, asserted rather than claimed.

        `_old_band(0.50)` is `even`, and the switch branch refuses `even`, so a
        genuine upset on a draw-priced board was thrown away. This fix restores
        it — the change is not purely a suppression.
        """
        assert _old_band(0.50) == "even"

    def test_a_two_way_upset_is_untouched(self):
        """The #6279 control, in this file, so a soccer fix cannot cost it."""
        result = _finished(
            opening_home_prob=0.61,
            opening_away_prob=0.39,
            current_home_prob=0.20,
            home_score=3,
            away_score=7,
            opening_favorite="home",
            sport_key="baseball_mlb",
        )
        assert result.flags.is_upset is True


class TestTheRefusal:
    """A missing leg is unanswerable, and the caller keeps its old behaviour."""

    def test_one_leg_is_not_enough(self):
        assert favorite_from_pair(0.3725, None) is None
        assert favorite_from_pair(None, 0.3648) is None
        assert favorite_from_pair(None, None) is None

    def test_a_row_without_its_pair_keeps_the_stored_string(self):
        """The fallback, so the repair cannot cost a chip it was not aimed at.

        Measured: 0 of the 2,724 production rows carrying an opening pair have
        one leg without the other, so this path is a guarantee rather than a
        live population — which is the reason to pin it, not to drop it.
        """
        result = _finished(
            opening_home_prob=0.61,
            opening_away_prob=None,
            current_home_prob=0.20,
            home_score=3,
            away_score=7,
            opening_favorite="home",
            sport_key="baseball_mlb",
        )
        assert result.flags.is_upset is True


class TestTheLiveCapsuleAgrees:
    """#4580: one determination, so the capsule and the flag cannot drift."""

    def test_select_live_claim_reads_the_same_pair(self):
        """A live three-way board where the FAVOURITE leads claims no upset.

        Asserted as "not `underdog_lead`" rather than "None" on purpose: this
        board has also moved 43 points, so the selector's second arm answers
        `movement`, which is a true statement about the price and none of this
        issue's business. Pinning `None` here would pin the movement threshold
        into an upset test and break on any unrelated tuning of it.
        """
        assert select_live_claim("live", 0.3725, 0.80, 3, 0, 0.3648) != "underdog_lead"

    def test_that_board_did_claim_an_underdog_lead_before_the_fix(self):
        """The BEFORE control for this class, so the assertion above is not vacuous.

        The old call shape — no away leg — reads 0.3725 as an underdog and
        claims the favourite's 3-0 lead as an upset in progress.
        """
        assert select_live_claim("live", 0.3725, 0.80, 3, 0) == "underdog_lead"

    def test_the_capsule_still_fires_for_a_real_underdog_lead(self):
        assert select_live_claim("live", 0.25, 0.60, 2, 0, 0.50) == "underdog_lead"

    def test_the_flag_and_the_capsule_answer_alike(self):
        """The drift #4580 exists to prevent, asserted on the defect's own row."""
        flag = underdog_leads(0.3725, 3, 0, 0.3648)
        capsule = select_live_claim("live", 0.3725, 0.80, 3, 0, 0.3648)
        assert flag is False and capsule != "underdog_lead"
