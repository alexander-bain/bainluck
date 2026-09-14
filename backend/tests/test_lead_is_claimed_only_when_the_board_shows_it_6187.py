"""#6187 — a futures caption says "leads" above a board whose rows print the same percent.

** THE PARENT'S BEHAVIOUR IS RECORDED FROM PRODUCTION, NOT FROM A SYNTHETIC RED. **
Read off `GET /api/feed?limit=100` at 2026-09-14 17:40Z: SEVEN of eighty-five field
cards carried a comparative their own printed rows could not support. Verbatim, with
the `rendered_percent` the same payload served beside each sentence:

    headline 'New favorite: Canterbury-Bankstown Bulldogs (49%)'   rows 49 · 49 · 49
    reason   '… (49%) now leads National Rugby League Champion'
    ctx      'MOUZ leads at 22%; resolves within a week'           rows 22 · 22 · 22
    headline 'Jordan leads at 9%'                                  rows  9 ·  9 ·  8
    headline 'New favorite: 7,800 to 7,999.99 (16%)'               rows 16 · 16 · 12

Four of the seven — the Bulldogs, MOUZ, the S&P band and a Senate pair — are ties at
FULL PRECISION (0.49/0.49/0.49, 0.2171 x3, 0.1604/0.1604), so the "leader" is whichever
row the descending sort emitted first. Jordan is a real 0.9pp lead that rounds away.
Both fail the same test because the test is on the PRINTED percents.

** WHY THE DEFECT TESTS BELOW CANNOT RUN ON THE PARENT, AND WHAT CARRIES THE WEIGHT
INSTEAD. ** `rendered_runner_up_percent` IS the fix, and the three composers take no
`**kwargs`, so every test that passes it raises `TypeError` on the parent tree. A
uniform TypeError red proves a signature changed, not that a sentence was wrong — so it
is not offered as the reproduction. The reproduction is the production read above. What
these tests do carry:

  * the tie cases assert the exact strings the fix must emit, so a later edit that
    reinstates any of the six comparatives reds here;
  * `TestTheComparativeSurvivesWhereTheBoardShowsIt` and
    `TestAnUninformedCallerIsUnchanged` pass **identically on both trees** — they never
    name the new parameter — and are the guard that this did not widen. A control that
    cannot run on the parent is not a control.
"""

import ast
import inspect
from pathlib import Path

import pytest

import app.utils.feed_reasons as fr
from app.routes.feed import _printed_runner_up_percent

#: The four production specimens, as (label, reasons, market, leader, probability,
#: printed leader percent, printed runner-up percent).
TIED_SPECIMENS = [
    (
        "nrl",
        ["leader_change"],
        "National Rugby League Champion",
        "Canterbury-Bankstown Bulldogs",
        0.49,
        49,
        49,
    ),
    (
        "starladder",
        ["resolving_soon_7d"],
        "StarLadder StarSeries Fall Champion",
        "MOUZ",
        0.2171,
        22,
        22,
    ),
    (
        "mecca",
        [],
        "Which countries will join the Mecca Agreement by December 31?",
        "Jordan",
        0.0925,
        9,
        9,
    ),
    (
        "sp500",
        ["leader_change"],
        "S&P close price end of 2026?",
        "7,800 to 7,999.99",
        0.1604,
        16,
        16,
    ),
]

#: Every comparative this module is responsible for suppressing. "New favorite" is one
#: of them: it is the comparative with the number removed, not a weaker form of it.
COMPARATIVES = ("leads", " lead ", "lead;", "New favorite", "favorite")


def _card_copy(reasons, market, leader, probability, printed_leader, printed_runner_up):
    """The three strings one card serves, composed the way `_score_futures` does."""
    shared = dict(
        highlight_reasons=reasons,
        leader_name=leader,
        leader_probability=probability,
        rendered_leader_percent=printed_leader,
        rendered_runner_up_percent=printed_runner_up,
        market_name=market,
    )
    headline = fr.generate_futures_headline(**shared)
    reason = fr.generate_futures_reason(
        market,
        reasons,
        leader_name=leader,
        leader_probability=probability,
        rendered_leader_percent=printed_leader,
        rendered_runner_up_percent=printed_runner_up,
    )
    context = fr.generate_futures_context_summary(headline=headline, **shared)
    return headline, reason, context


class TestTheTiedProductionCards:
    """The seven cards of 2026-09-14, each read back through the composers."""

    @pytest.mark.parametrize(
        "label,reasons,market,leader,probability,printed_leader,printed_runner_up",
        TIED_SPECIMENS,
        ids=[spec[0] for spec in TIED_SPECIMENS],
    )
    def test_no_sentence_claims_a_lead_the_rows_cannot_show(
        self,
        label,
        reasons,
        market,
        leader,
        probability,
        printed_leader,
        printed_runner_up,
    ):
        for slot, text in zip(
            ("headline", "reason", "context_summary"),
            _card_copy(
                reasons, market, leader, probability, printed_leader, printed_runner_up
            ),
        ):
            for word in COMPARATIVES:
                assert word not in text, (
                    f"{label} {slot} still claims a lead: {text!r} — the card prints "
                    f"{printed_leader}% for {leader} and {printed_runner_up}% for the "
                    "row beneath it, so a reader cannot see the lead asserted"
                )

    @pytest.mark.parametrize(
        "label,reasons,market,leader,probability,printed_leader,printed_runner_up",
        TIED_SPECIMENS,
        ids=[spec[0] for spec in TIED_SPECIMENS],
    )
    def test_every_sentence_still_names_the_leader_and_its_printed_percent(
        self,
        label,
        reasons,
        market,
        leader,
        probability,
        printed_leader,
        printed_runner_up,
    ):
        """Dropping the verb must not drop the facts — #4056's empty-slot lesson.

        The remedy is a quieter claim, not a silent card: rank 1 still reads first on
        the board, and the caption still states who and how much.
        """
        headline, reason, context = _card_copy(
            reasons, market, leader, probability, printed_leader, printed_runner_up
        )
        for slot, text in (
            ("headline", headline),
            ("reason", reason),
            ("context_summary", context),
        ):
            assert text.strip(), f"{label} {slot} went empty"
            assert leader in text, f"{label} {slot} lost the leader's name: {text!r}"
            assert (
                f"{printed_leader}%" in text
            ), f"{label} {slot} lost the printed percent: {text!r}"

    @pytest.mark.parametrize(
        "label,reasons,market,leader,probability,printed_leader,printed_runner_up",
        TIED_SPECIMENS,
        ids=[spec[0] for spec in TIED_SPECIMENS],
    )
    def test_the_sentences_are_well_formed(
        self,
        label,
        reasons,
        market,
        leader,
        probability,
        printed_leader,
        printed_runner_up,
    ):
        """Removing a word from an f-string is how a double space ships.

        Also guards the two templates that could not simply drop the verb: the reason
        fallback (`X (9%) in <market>`, not `X (9%) <market>`) and the 30-day headline
        (`X at 22%; resolves within a month`, not the bare `X; resolves…`).
        """
        for slot, text in zip(
            ("headline", "reason", "context_summary"),
            _card_copy(
                reasons, market, leader, probability, printed_leader, printed_runner_up
            ),
        ):
            assert "  " not in text, f"{label} {slot} has a double space: {text!r}"
            assert not text.startswith(" ") and not text.endswith(" ")
            assert " ;" not in text and " ," not in text


class TestTheExactCopyTheTiedCardsNowServe:
    """Pinned strings, so a later edit cannot quietly reword the tie branch."""

    def test_the_nrl_card_falls_through_the_new_favorite_branch(self):
        headline, reason, context = _card_copy(*TIED_SPECIMENS[0][1:])
        assert headline == "Canterbury-Bankstown Bulldogs at 49%"
        assert reason == (
            "Canterbury-Bankstown Bulldogs (49%) in National Rugby League Champion"
        )
        assert context == "Canterbury-Bankstown Bulldogs at 49%"

    def test_the_starladder_card_keeps_its_resolution_window(self):
        headline, reason, context = _card_copy(*TIED_SPECIMENS[1][1:])
        assert headline == "Resolving soon: MOUZ at 22%"
        assert (
            reason == "StarLadder StarSeries Fall Champion resolving soon, MOUZ at 22%"
        )
        assert context == "MOUZ at 22%; resolves within a week"

    def test_the_mecca_card_takes_in_rather_than_the_verb(self):
        headline, reason, context = _card_copy(*TIED_SPECIMENS[2][1:])
        assert headline == "Jordan at 9%"
        assert reason == (
            "Jordan (9%) in Which countries will join the Mecca Agreement "
            "by December 31?"
        )
        assert context == "Jordan at 9%"

    def test_the_thirty_day_headline_states_a_percent_instead_of_a_bare_subject(self):
        """The one leader headline that carried the verb without a percent."""
        headline, _, _ = _card_copy(
            ["resolving_soon_30d"], "Some Cup", "Tied Team", 0.22, 22, 22
        )
        assert headline == "Tied Team at 22%; resolves within a month"


class TestTheComparativeSurvivesWhereTheBoardShowsIt:
    """RUNS UNCHANGED ON THE PARENT — the guard that this did not widen (gotcha #43).

    Never names `rendered_runner_up_percent`, so the parent's signature accepts every
    call and returns the same strings this asserts. A one-point printed gap is the
    tightest lead that is still legible, and it must keep the verb.
    """

    ONE_POINT_GAP = (["resolving_soon_7d"], "Some Cup", "Real Leader", 0.23, 23)

    def _copy_without_the_new_parameter(
        self, reasons, market, leader, probability, pct
    ):
        shared = dict(
            highlight_reasons=reasons,
            leader_name=leader,
            leader_probability=probability,
            rendered_leader_percent=pct,
            market_name=market,
        )
        headline = fr.generate_futures_headline(**shared)
        reason = fr.generate_futures_reason(
            market,
            reasons,
            leader_name=leader,
            leader_probability=probability,
            rendered_leader_percent=pct,
        )
        return (
            headline,
            reason,
            fr.generate_futures_context_summary(headline=headline, **shared),
        )

    def test_a_card_with_no_runner_up_stated_keeps_todays_copy(self):
        headline, reason, context = self._copy_without_the_new_parameter(
            *self.ONE_POINT_GAP
        )
        assert headline == "Resolving soon: Real Leader leads at 23%"
        assert reason == "Some Cup resolving soon, Real Leader leads at 23%"
        assert context == "Real Leader leads at 23%; resolves within a week"

    def test_the_leader_change_branch_still_speaks(self):
        headline, reason, _ = self._copy_without_the_new_parameter(
            ["leader_change"], "Some Cup", "Real Leader", 0.40, 40
        )
        assert headline == "New favorite: Real Leader (40%)"
        assert reason == "New favorite: Real Leader (40%) now leads Some Cup"

    def test_the_plural_team_verb_is_untouched(self):
        """#4700 composes from the same `_verb`; #6187 must not have moved it."""
        assert fr.leader_agreement_verb("Boston Red Sox", leader_is_team=True) == "lead"
        assert fr.leader_agreement_verb("Miami Heat", leader_is_team=True) == "leads"


class TestTheComparativeSurvivesAOnePointLead:
    """The fix's own positive direction: a printed gap of one point keeps the verb."""

    def test_one_printed_point_is_enough(self):
        headline, reason, context = _card_copy(
            ["resolving_soon_7d"], "Some Cup", "Real Leader", 0.23, 23, 22
        )
        assert headline == "Resolving soon: Real Leader leads at 23%"
        assert reason == "Some Cup resolving soon, Real Leader leads at 23%"
        assert context == "Real Leader leads at 23%; resolves within a week"

    def test_the_new_favorite_branch_survives_a_printed_gap(self):
        headline, reason, _ = _card_copy(
            ["leader_change"], "Some Cup", "Real Leader", 0.40, 40, 22
        )
        assert headline == "New favorite: Real Leader (40%)"
        assert reason == "New favorite: Real Leader (40%) now leads Some Cup"


class TestAnUninformedCallerIsUnchanged:
    """RUNS UNCHANGED ON THE PARENT for the helper's own contract.

    `lead_is_printable` is new, so only the fix has it — but its FAIL-TO-TODAY default
    is the whole reason the route call sites had to be updated in the same commit, and
    the AST guard in `test_card_sentence_states_the_printed_percent_4146.py` is what
    proves they were. This states the default's direction so nobody "tidies" it into
    fail-closed and silently strips every comparative on the site.
    """

    @pytest.mark.parametrize(
        "leader,runner_up",
        [(None, None), (40, None), (None, 22)],
    )
    def test_an_unknown_percent_keeps_the_comparative(self, leader, runner_up):
        assert fr.lead_is_printable(leader, runner_up) is True

    def test_it_is_a_strict_comparison(self):
        assert fr.lead_is_printable(23, 22) is True
        assert fr.lead_is_printable(22, 22) is False
        # Defensive: a runner-up printing ABOVE the leader is a sort defect, not a
        # lead. It must not read as printable.
        assert fr.lead_is_printable(21, 22) is False

    def test_zero_is_a_real_percent(self):
        """`or`-style truthiness here would read 0 as unknown and keep the verb."""
        assert fr.lead_is_printable(0, 0) is False
        assert fr.lead_is_printable(1, 0) is True


class TestTheRunnerUpIsReadOffThePrintedRows:
    """`_printed_runner_up_percent` — the route's half of the pair."""

    def test_it_is_the_max_beneath_the_leader_not_index_one(self):
        rows = [
            {"rendered_percent": 30},
            {"rendered_percent": 10},
            {"rendered_percent": 30},
        ]
        assert _printed_runner_up_percent(rows) == 30

    def test_it_reads_the_printed_row_not_the_probability(self):
        rows = [
            {"probability": 0.0925, "rendered_percent": 9},
            {"probability": 0.0889, "rendered_percent": 9},
        ]
        assert _printed_runner_up_percent(rows) == 9

    @pytest.mark.parametrize(
        "rows",
        [
            [],
            None,
            [{"rendered_percent": 40}],
            [{"rendered_percent": 40}, {"rendered_percent": None}],
            [{"rendered_percent": 40}, {}],
        ],
    )
    def test_nothing_beneath_the_leader_is_none(self, rows):
        assert _printed_runner_up_percent(rows) is None

    def test_a_zero_runner_up_is_not_none(self):
        rows = [{"rendered_percent": 100}, {"rendered_percent": 0}]
        assert _printed_runner_up_percent(rows) == 0


class TestTheLadderGuardIsUnaffected:
    """#4640's suppression and #6187's must compose, not race.

    The 30-year-mortgage card in the same production read (`Above 6.73%` 95, `Above
    6.74%` 95) is BOTH a tie and a cumulative ladder, and the ladder rule is the
    stronger one: it removes the subject, not just the verb.
    """

    def test_a_tied_ladder_still_yields_to_the_ladder_wording(self):
        headline = fr.generate_futures_headline(
            highlight_reasons=["resolving_soon_7d"],
            leader_name="Above 6.73%",
            leader_probability=0.945,
            rendered_leader_percent=95,
            rendered_runner_up_percent=95,
            leader_is_ladder_rung=True,
            market_name="30-year mortgage rate this week",
        )
        assert headline == "30-year mortgage rate this week resolving soon"
        assert "leads" not in headline


class TestEveryLeaderTemplateAsksTheQuestion:
    """A source scan, because the defect returns the moment a tenth template lands.

    The file's own idiom is to resolve a flag once above every branch and consult it in
    each template (`_verb`, `_no_leader_subject`). This asserts the third flag reaches
    every generator that can emit a comparative, so a new branch written between them
    is not silently exempt.
    """

    SOURCE = Path(fr.__file__).read_text()

    @pytest.mark.parametrize(
        "generator",
        [
            "generate_futures_reason",
            "generate_futures_headline",
            "generate_futures_context_summary",
        ],
    )
    def test_each_generator_resolves_the_flag_and_uses_it(self, generator):
        tree = ast.parse(self.SOURCE)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == generator
        )
        body = ast.get_source_segment(self.SOURCE, node)
        assert "lead_is_printable(" in body, (
            f"{generator} never resolves #6187's flag, so every comparative it "
            "emits is unguarded"
        )
        assert "_lead_visible" in body

    def test_no_leader_template_hard_codes_the_verb_beside_a_percent(self):
        """`{leader} {verb} at {pct}%` may only be built by the shared composer."""
        offenders = [
            line.strip()
            for line in self.SOURCE.splitlines()
            if "{_verb} at {" in line or "{_verb} at " in line
        ]
        assert offenders == [], (
            "a leader clause is composed inline again rather than through "
            f"`leader_standing_clause`, so it cannot drop the verb: {offenders}"
        )

    def test_the_composers_accept_the_runner_up_percent(self):
        for composer in (
            fr.generate_futures_headline,
            fr.generate_futures_reason,
            fr.generate_futures_context_summary,
        ):
            assert (
                "rendered_runner_up_percent" in inspect.signature(composer).parameters
            ), f"{composer.__name__} cannot be told what the board prints"
