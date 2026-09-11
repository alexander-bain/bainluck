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

    @pytest.mark.parametrize(
        "unreadable",
        [
            # a spelled-out period — the infix branch is [1-4]H/Q/HALF only
            "Chicago Fire wins the second half by more than 1.5 goals",
            # a unit outside points/runs/goals
            "Alcaraz wins by more than 1.5 sets",
            # a period the pattern has no branch for
            "Boston wins the 3rd period by over 1.5 goals",
        ],
    )
    def test_the_guard_is_wider_than_the_grader(self, unreadable):
        """The point of a separate pattern, and why it survives CERT-2603.

        The grader now reads every margin shape production carries, so the
        temptation is to collapse the two patterns into one. They answer
        different questions: `_SPREAD_RE` asks "can I grade this leg", this asks
        "is this a margin question at all" — and only the second can be right
        about a phrasing nobody has taught the first. Every specimen here is
        unreadable and must therefore stay blank; a collapsed pair would hand
        each one to a winner fallback that grades "did this team win", stamped
        `game_score` and permanent.
        """
        assert bw._SPREAD_RE.search(unreadable) is None
        assert bw._MARGIN_CLAIM_RE.search(unreadable) is not None


class TestTheGraderReadsEveryProductionShape:
    """CERT-2603 — `_SPREAD_RE` against the shapes that actually exist.

    Measured 2026-09-11 by collapsing every digit in every 2H spread leg name
    on production: three shapes, 4,410 legs, and the pre-repair pattern read
    none of them. A reconstructor whose parser cannot read its own population
    grades nothing, which is what the first presentation of #5052 shipped.
    """

    #: (name, team, line) — the first three rows are the entire 2H population;
    #: the rest are the full-game and 1H shapes that must not regress.
    SHAPES = [
        ("Chicago Bears wins the 2H by over 9.5 points", "Chicago Bears", 9.5),
        ("GB Packers wins 2H by over 9.5 points", "GB Packers", 9.5),
        ("Bayern Munich wins the 2H by more than 1.5 goals", "Bayern Munich", 1.5),
        ("New York wins by over 29.5 points", "New York", 29.5),
        ("Detroit wins the 1H by over 9.5 points", "Detroit", 9.5),
        ("Real Madrid wins by more than 1.5 goals", "Real Madrid", 1.5),
        ("Los Angeles A wins by over 3.5 runs", "Los Angeles A", 3.5),
        ("Spurs wins 2Q by over 3.5 points", "Spurs", 3.5),
    ]

    @pytest.mark.parametrize("name,team,line", SHAPES)
    def test_the_team_and_the_line_are_read_off_the_name(self, name, team, line):
        """Both groups, because both are consumed.

        Every caller reads group(1) as the team and group(2) as the line, so a
        widening that matched but captured the margin clause into the team name
        would parse, pick no side, and silently refuse the leg.
        """
        m = bw._SPREAD_RE.search(name)
        assert m is not None
        assert m.group(1) == team
        assert float(m.group(2)) == line

    def test_a_quarter_leg_parses_but_is_never_graded_here(self):
        """The pattern reads quarters; the GATE is what refuses them.

        10,564 "wins NQ by over N points" legs exist and none has a
        reconstructor. Two independent things must stay true: this pattern may
        read them (so the team-total grader keeps refusing them), and
        `_RECONSTRUCTABLE_PERIODS` must keep them out of the resolver — because
        grading a quarter against the full-game score is #4923 verbatim.
        """
        assert bw._SPREAD_RE.search("Spurs wins 2Q by over 3.5 points") is not None
        assert bw._ticker_period("KXNBA2QSPREAD-26SEP09BOSLAL") == "2q"
        assert "2q" not in bw._RECONSTRUCTABLE_PERIODS


class TestTheTeamTotalGraderRefusesMarginLegs:
    """CERT-2603 — the other door into a fabricated verdict.

    `_team_total_outcome_is_winner` runs BEFORE the spread branch and refused
    margin legs only through `_SPREAD_RE`. `_TEAM_TOTAL_RE`'s `(.+?)` swallows
    a margin clause into the team name, so any phrasing the grader could not
    read was graded as a TEAM TOTAL — the team's score against the margin line.
    """

    def test_a_second_half_margin_leg_is_not_a_team_total(self):
        """The measured specimen, at the boundary that makes the two disagree.

        A 10–3 half: the Bears' 2H score is 10 and their 2H margin is 7, so a
        9.5 line reads True as a team total and False as the spread it is. On
        the pre-repair branch this returned True.
        """
        assert bw._team_total_outcome_is_winner(
            "Chicago Bears wins the 2H by over 9.5 points",
            "Chicago Bears", "Green Bay Packers", 10, 3,
        ) is None

    @pytest.mark.parametrize(
        "name",
        [
            # a spelled-out period, with the "by over" phrasing that makes
            # `_TEAM_TOTAL_RE` bite
            "Chicago Fire wins the second half by over 1.5 goals",
            "Chicago Fire wins in the 2nd half by over 9.5 points",
            "Chicago Fire wins the 3rd period by over 2.5 runs",
        ],
    )
    def test_the_refusal_covers_the_shapes_the_grader_cannot_read(self, name):
        """Wider than `_SPREAD_RE` on purpose — that gap WAS the leak.

        THE FIRST ASSERTION IS THE ANTI-VACUITY ONE and it is not decoration.
        The first version of this test used "by more than" phrasings, which
        `_TEAM_TOTAL_RE` cannot match at all — so the function returned None
        for an unrelated reason and the whole test passed with the guard
        DELETED. Only a name this grader would otherwise read can prove the
        refusal does anything, so each specimen asserts that it is a genuine
        bypass before asserting that it is refused.
        """
        assert bw._TEAM_TOTAL_RE.match(name) is not None, "vacuous specimen"
        assert bw._SPREAD_RE.search(name) is None, "the other guard covers this"
        assert bw._team_total_outcome_is_winner(
            name, "Chicago Fire", "Inter Miami CF", 10, 3
        ) is None

    def test_a_real_team_total_is_still_graded(self):
        """The control. A guard that refuses everything is not a guard.

        CERT-499's 56 stranded `A's` legs are what this branch exists to grade;
        over-refusing here strands them again, silently and permanently.
        """
        assert bw._team_total_outcome_is_winner(
            "Los Angeles A over 3.5 runs", "Los Angeles A", "Houston Astros", 5, 2
        ) is True
        assert bw._team_total_outcome_is_winner(
            "Houston Astros over 3.5 runs", "Los Angeles A", "Houston Astros", 5, 2
        ) is False
