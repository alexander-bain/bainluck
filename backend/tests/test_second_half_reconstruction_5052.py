"""#5052 — a settled second half is answered, and only from a second-half score.

`_resolve_kalshi_spread_total_from_scores` refused every period but `1h`. That
refusal was #4923's first move and its comment said so in terms — "a wrong
verdict is replaced by no verdict first ... building one [for 2H] is a
follow-up". This is that follow-up: 356 settled 2H markets / 1,401 outcomes were
questions with knowable answers on which the reader saw nothing.

The arithmetic is not new and is deliberately not re-typed. `2H = final − half`
already existed in `_resolve_kalshi_period_props`; `_period_scores` is that
subtraction hoisted so the two loops cannot drift apart on what "2H" means —
the same ONE CLASSIFIER, TWO CALLERS argument `_ticker_period` makes.

What these guards are actually defending:

1. **Never the full-game score.** Every 2H specimen here is chosen so the half's
   answer DIFFERS from the match's, because a fixture where the two agree
   cannot fail (#4923's own lesson).
2. **Fail closed.** No reconstruction ⇒ no verdict, never a fallback to the
   final score. `game_score` is not in `OVERWRITABLE_WINNER_SOURCES_SQL`, so a
   wrong verdict here is PERMANENT (gotcha #21).
3. **The gate and the reconstructor cannot drift.** Adding a token to
   `_RECONSTRUCTABLE_PERIODS` without teaching `_period_scores` to rebuild it
   would grade that period against the full-game score — #4923 verbatim.

Integration-level behaviour (the resolver driven end to end, and the
`_MARGIN_CLAIM_RE` fabrication guard) lives beside its siblings in
`test_period_verdicts_4923.py`; this file is the arithmetic and the contract.
"""

import pytest

import app.tasks.backfill_winners as bw


def _halftime(pair):
    async def _fn(session, event_id):
        return pair

    return _fn


class TestPeriodScores:
    """The reconstructor, called directly."""

    async def test_no_period_is_the_final_score(self, monkeypatch):
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((99, 99)))
        assert await bw._period_scores(None, 1, None, 3, 1) == (3, 1)

    async def test_no_period_with_no_final_score_refuses(self, monkeypatch):
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, None, None, 1) is None

    async def test_first_half_is_the_halftime_score(self, monkeypatch):
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, "1h", 1, 1) == (1, 0)

    async def test_second_half_is_final_minus_halftime(self, monkeypatch):
        """Chicago Fire vs Inter Miami, 2026-09-09. Final 1–1, first half 1–0.

        Both numbers are Kalshi's own, off the sibling markets on event
        15298466 — the specimen #4923 was filed on. The second half is 0–1, so
        the HOME side leads the match on aggregate and LOSES the half. A
        reconstructor that returned the final score would return (1, 1) and is
        caught by the second element alone.
        """
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, "2h", 1, 1) == (0, 1)

    async def test_second_half_carries_overtime_with_it(self, monkeypatch):
        """Stated as a contract, not left to be discovered.

        `final − halftime` puts overtime in the second half. That is not a free
        choice here: `_resolve_kalshi_period_props` already grades 2H this way,
        and two loops in one file disagreeing about what "2H" means is the
        #4923 failure mode wearing different clothes. If Kalshi's own 2H rules
        are ever measured to exclude OT, this assertion is the one that has to
        be changed, deliberately, together with that loop.
        """
        # 24–21 final on a 10–14 half: the home side trailed at the break and
        # outscored the away side 14–7 after it.
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((10, 14)))
        assert await bw._period_scores(None, 1, "2h", 24, 21) == (14, 7)

    async def test_second_half_without_a_halftime_score_refuses(self, monkeypatch):
        async def _none(session, event_id):
            return None

        monkeypatch.setattr(bw, "_get_halftime_score", _none)
        assert await bw._period_scores(None, 1, "2h", 1, 1) is None

    async def test_second_half_without_a_final_score_refuses(self, monkeypatch):
        """A half we cannot subtract FROM is as unusable as one we cannot build."""
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, "2h", None, 1) is None
        assert await bw._period_scores(None, 1, "2h", 1, None) is None

    @pytest.mark.parametrize("period", ["1q", "2q", "3q", "4q", "f3", "f5", "f7", "rfi"])
    async def test_an_unreconstructable_period_refuses(self, monkeypatch, period):
        """The periods #5052 deliberately did NOT build.

        Returning the final score for any of these is exactly #4923. They stay
        refused and stay counted.
        """
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, period, 3, 1) is None


class TestTheGateMatchesTheReconstructor:
    """The two halves of the contract, asserted against each other."""

    def test_the_reconstructable_set_is_exactly_the_halves(self):
        assert bw._RECONSTRUCTABLE_PERIODS == frozenset({"1h", "2h"})

    @pytest.mark.parametrize("period", sorted(bw._RECONSTRUCTABLE_PERIODS))
    async def test_every_allowed_period_actually_reconstructs(
        self, monkeypatch, period
    ):
        """Adding a token to the set without teaching `_period_scores` fails HERE.

        Without this, widening the gate would silently send a new period down
        the `else` branch and grade it on the full-game score — the exact shape
        of #4923, reintroduced by a one-word edit.
        """
        monkeypatch.setattr(bw, "_get_halftime_score", _halftime((1, 0)))
        assert await bw._period_scores(None, 1, period, 3, 1) is not None

    @pytest.mark.parametrize(
        "series,period",
        [
            ("KXMLS2HTOTAL", "2h"),
            ("KXNBA2HSPREAD", "2h"),
            ("KXNCAAF2HSPREAD", "2h"),
            ("KXBUNDESLIGA2H", "2h"),
            ("KXNBA2HWINNER", "2h"),
        ],
    )
    def test_real_2h_series_classify_as_2h(self, series, period):
        """The gate is only reached if the classifier says "2h" for real tickers."""
        assert bw._ticker_period(f"{series}-26SEP09CHIMIA") == period

    def test_the_h2h_carve_out_still_is_not_a_second_half(self):
        """`KXEPLH2H` is head-to-head, about the whole game, and contains "2H".

        A false positive here does not print a wrong verdict — it grades the
        WHOLE GAME on a second-half score, which is #4923 with the arguments
        swapped. The lookbehind in `_PERIOD_SERIES_RE` is what stops it and
        this is the assertion that keeps it.
        """
        assert bw._ticker_period("KXEPLH2H-26SEP09CHIMIA") is None
        assert bw._ticker_period("KXEPLH2HFINISH-26SEP09CHIMIA") is None


class TestMarginClaimGuard:
    """`_MARGIN_CLAIM_RE` — the legs the winner fallbacks must never answer."""

    @pytest.mark.parametrize(
        "name",
        [
            # the real production phrasing, read 2026-09-11
            "Bayern Munich wins the 2H by more than 1.5 goals",
            "Chicago Fire wins the 2H by more than 1.5 goals",
            "Rutgers wins 2H by over 6.5 points",
            "Rutgers wins the 1H by over 17.5 points",
            "Boston wins by more than 2.5 runs",
        ],
    )
    def test_a_margin_leg_is_recognised(self, name):
        assert bw._MARGIN_CLAIM_RE.search(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            # genuine team-name winner legs the fallbacks SHOULD still answer
            "Chicago Fire",
            "Inter Miami CF",
            "Tie",
            "Penn",
            "California",
            # a total is not a margin claim — it has its own grader
            "Over 1.5 2H goals scored",
            "Under 2.5 goals scored",
        ],
    )
    def test_a_winner_or_total_leg_is_not_a_margin_claim(self, name):
        """The false-positive direction, and it is the costly one.

        Over-matching here does not print a wrong verdict, it DELETES a correct
        one — every one of these is a leg the fallbacks grade correctly today,
        and a guard that swallowed them would silently stop 2-outcome winner
        markets resolving at all.
        """
        assert bw._MARGIN_CLAIM_RE.search(name) is None

    def test_the_guard_is_wider_than_the_grader(self):
        """The point of a separate pattern, in one assertion.

        `_SPREAD_RE` can read 17,540 of the 21,492 1H legs and NONE of the
        4,410 2H legs (measured on production 2026-09-11) — the 2H phrasings
        all carry an infix it has no branch for. So the set of margin legs the
        grader cannot read is non-empty, and it is exactly the set that must
        not fall through to a winner fallback. #4236 is the open issue for
        teaching the grader the "by more than" form; it is NOT fixed here, and
        until it is, this guard is what keeps those legs honestly blank.
        """
        unreadable = "Bayern Munich wins the 2H by more than 1.5 goals"
        assert bw._SPREAD_RE.search(unreadable) is None
        assert bw._MARGIN_CLAIM_RE.search(unreadable) is not None
