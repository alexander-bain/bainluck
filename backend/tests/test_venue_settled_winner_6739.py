"""#6739 — a settled match stops leaving 89%–11% as its last word.

THE DEFECT, PHOTOGRAPHED ON PRODUCTION 2026-09-17 16:10Z.
``/events/15313807`` (W75 Le Neubourg: Fiona Crawley vs Naiktha Bains, six
hours past its own start) served ``status: suspended``, both scores ``null``,
``venue_settled: true`` — and ``venue_settled_result: null``. So the page drew
a **"Settled"** chip, a "Since Start" win-probability chart whose last reading
is **Crawley 89% — Bains 11%**, and a ticking "Next update: 108" — while one
screen below, on the same payload, its own moneyline read::

    Fiona Crawley vs Naiktha Bains     Fiona Crawley   100%
                                       Naiktha Bains     0%

graded ``is_winner=true, resolution_source='api_settlement'``. The venue said
who won. We said "Settled" and left a probability as the verdict.

#6381 built the channel and could only fill it from a full-scope SCORE market
(``Correct Score`` / ``Exact Match Score``) — 56 of its 426 events. Its own
docstring calls the other 370 "graded on props alone", which is true of the
score vocabulary and false of the moneyline. This file is the moneyline half.

WHY THE MARKET TEST IS THE WHOLE SHIP
-------------------------------------

A graded outcome that names one of the two players is not evidence of a match
winner. It is the shape of every set, map, half and handicap book the venue
writes, and on this population those books OUTNUMBER the moneyline. Replayed
over the 2,010 stored side-named grades on the ``suspended`` arm (production
2026-09-17): **823 admitted, 1,187 refused.** The refusals, by shape:

    ``Set Handicap: A (-1.5) vs B (+1.5)``   286 grades   spread
    ``Set 1 Winner: A vs B``                 150 grades   other
    ``A vs B: Spread``                        56 grades   spread
    ``A vs B: Method of Victory``             24 grades   other
    ``A vs B: Team Total``                    23 grades   team_prop
    ``A vs. B: Round of Victory``             18 grades   other
    ``Set 2 Winner: A vs B``                   9 grades   other
    ``A vs. B: Map 1 | Map 2 | Map 3``        18 grades   other
    ``A vs B`` / ``M15 Monastir: A vs B``    823 grades   ADMITTED

Every refusal in that table is a page that would otherwise have been told a
set, a map or a method-of-victory result was the match result.
`TestTheBooksThatAreNotTheMatch` is that table with the real names on it.

WHY THE SIDE TEST IS FUZZY, AND WHAT PAID FOR IT
------------------------------------------------

An exact name test was the first draft and it refused the specimen above:
``events.home_team_name`` is **Crawley**, the venue grades **Fiona Crawley**.
Replayed over the ``suspended`` arm it found 265 events, every one of them a
row where our spelling and the venue's happen to agree — the whole ITF
population, which is what #6739 is about, was invisible to it. The test is
`prediction_market_matching._fuzzy_team_match`, the primitive the blend already
orients its moneyline leg with on these same rows.

Loosening a name gate spends a safety net, so the widening was audited against
the market's LOSING leg before it was written (production 2026-09-17, all 8,889
settled legs on the arm): of 777 admitted events, **725 have a losing leg that
resolves to the OTHER side, 0 resolve to the same side, 52 have a losing leg
that is a draw, a spelling variant or a Polymarket prop bundle**. Zero
inversions is the measurement that permits the containment test.

That audit also found the one case containment gets wrong and #4629's
both-sides refusal cannot see — `TestTheTruncatedMatchup`.
"""

from types import SimpleNamespace

import pytest

from app.utils.venue_settlement import (
    WINNER_SENTENCE,
    _names_a_participant,
    choose_settled_score,
    choose_settled_winner,
    is_full_scope_score_market,
    settlement_from_graded_rows,
)

#: The production specimen, verbatim (``/events/15313807``, 2026-09-17).
#: 🔴 OUR ROW CARRIES THE SURNAME AND THE VENUE CARRIES THE FULL NAME. That is
#: not a quirk of this row — it is the shape of the ITF population the issue is
#: about, and it is why an exact test cannot ship.
HOME = "Crawley"
AWAY = "Bains"
VENUE_HOME = "Fiona Crawley"
VENUE_AWAY = "Naiktha Bains"
MONEYLINE = "W75 Le Neubourg: Fiona Crawley vs Naiktha Bains"

#: Measured on production 2026-09-17 over `status='suspended'` rows with no
#: score of their own, holding ≥1 positive `api_settlement` grade.
_MEASURED = {
    "events_holding_a_grade": 1121,
    "events_gaining_a_winner": 777,
    "events_already_holding_a_score": 11,
    "events_still_refused": 333,
    # The losing-leg orientation audit that permitted the containment test.
    "audited_loser_resolves_to_the_other_side": 725,
    "audited_loser_resolves_to_the_same_side": 0,
    "audited_loser_unresolvable": 52,
    # What an exact-equality side test would have found instead.
    "exact_equality_would_have_found": 265,
}


def _row(market_name, outcome_name, external_id=None):
    """One graded row in the shape the route hands the chooser."""
    return (market_name, external_id, outcome_name)


class TestTheSpecimen:
    """The photographed page, end to end through the pure half."""

    def test_the_venues_moneyline_grade_names_the_winner(self):
        """🔴 THE ASSERTION IS THE WHOLE SHIP AND IT IS SPELLED TWICE. The
        graded outcome is the venue's ``Fiona Crawley``; the sentence prints
        OUR ``Crawley``, because it renders beside our own team names. An exact
        test returns None here, which is what the first draft did."""
        assert (
            choose_settled_winner([_row(MONEYLINE, VENUE_HOME)], HOME, AWAY)
            == "Crawley wins"
        )

    def test_the_other_side_is_named_when_the_other_side_won(self):
        assert (
            choose_settled_winner([_row(MONEYLINE, VENUE_AWAY)], HOME, AWAY)
            == "Bains wins"
        )

    def test_it_is_the_score_sentence_with_the_score_dropped(self):
        """Not a new register. The field already carries ``Aryna Sabalenka wins
        2-0`` from the score vocabulary, so the winner-only case has to be the
        same sentence or the page reads as two different products."""
        assert WINNER_SENTENCE.format(participant="Aryna Sabalenka") == (
            "Aryna Sabalenka wins 2-0".removesuffix(" 2-0")
        )

    def test_the_specimens_moneyline_is_not_a_score_market(self):
        """Why #6381 served null here, stated as a test rather than as prose:
        the two vocabularies do not overlap, so this is additive."""
        assert is_full_scope_score_market(MONEYLINE) is False


class TestTheBooksThatAreNotTheMatch:
    """The 1,187 refused grades, by their real production names.

    A bare participant name is graded under every one of these. If any starts
    returning a sentence, a reader is being told a set result is a match
    result — which is the #5698 / #5743 class one layer further out.
    """

    @pytest.mark.parametrize(
        "market_name",
        [
            "Set Handicap: Fiona Crawley (-1.5) vs Naiktha Bains (+1.5)",
            "Set 1 Winner: Fiona Crawley vs Naiktha Bains",
            "Set 2 Winner: Fiona Crawley vs Naiktha Bains",
            "Fiona Crawley vs. Naiktha Bains: Map 1",
            "Fiona Crawley vs. Naiktha Bains: Map 3",
            "Game Spread: Fiona Crawley (-3.5) vs Naiktha Bains (+3.5)",
            "Spread: Fiona Crawley (-1.5)",
            "Fiona Crawley vs Naiktha Bains: Spread",
            "Fiona Crawley vs Naiktha Bains: Method of Victory",
            "Fiona Crawley vs Naiktha Bains: Team Total",
            "Fiona Crawley vs. Naiktha Bains: Round of Victory",
            "Counter-Strike: Fiona Crawley vs Naiktha Bains - Map 2 Winner",
            "Map 1 Rounds Handicap: Fiona Crawley (-12.5) vs Naiktha Bains (+12.5)",
            "Fiona Crawley vs Naiktha Bains: First Team to Score",
        ],
    )
    def test_a_side_graded_on_a_derivative_is_not_a_match_winner(self, market_name):
        assert (
            choose_settled_winner([_row(market_name, VENUE_HOME)], HOME, AWAY) is None
        )

    def test_a_derivative_does_not_poison_a_real_moneyline_beside_it(self):
        """155 of the measured events carry BOTH a set handicap and a
        moneyline. The derivative is dropped, not counted as a second winner —
        otherwise the conflict refusal below would eat the whole population."""
        graded = [
            _row(
                "Set Handicap: Fiona Crawley (-1.5) vs Naiktha Bains (+1.5)",
                VENUE_HOME,
            ),
            _row("Set 1 Winner: Fiona Crawley vs Naiktha Bains", VENUE_AWAY),
            _row(MONEYLINE, VENUE_HOME),
        ]
        assert choose_settled_winner(graded, HOME, AWAY) == "Crawley wins"

    def test_a_spread_ticker_under_a_bare_matchup_title_is_still_refused(self):
        """The name alone reads as a moneyline; only the ticker says spread.
        This is why the chooser takes the external id and not just the name."""
        graded = [
            _row("Fiona Crawley vs Naiktha Bains", VENUE_HOME, "KXATP2HSPREAD-XYZ")
        ]
        assert choose_settled_winner(graded, HOME, AWAY) is None


class TestTheRefusals:
    """Everything that is not exactly one named side is nothing."""

    def test_two_different_sides_refuse_rather_than_pick_one(self):
        """0 specimens of the 305 today, which is why it is written now. A
        duplicate event pair would put two winners on one row and a
        deterministic tiebreak would make one of them confident and wrong."""
        graded = [
            _row(MONEYLINE, VENUE_HOME),
            _row("Fiona Crawley vs Naiktha Bains", VENUE_AWAY),
        ]
        assert choose_settled_winner(graded, HOME, AWAY) is None

    def test_the_same_side_twice_is_still_one_answer(self):
        graded = [
            _row(MONEYLINE, VENUE_HOME),
            _row("Fiona Crawley vs Naiktha Bains", "Crawley"),
        ]
        assert choose_settled_winner(graded, HOME, AWAY) == "Crawley wins"

    @pytest.mark.parametrize(
        "outcome_name", ["Yes", "No", "Over 21.5", "Carlos Alcaraz", "", "   "]
    )
    def test_an_outcome_that_is_not_one_of_the_two_sides_is_nothing(
        self, outcome_name
    ):
        """Fail-closed. A moneyline whose graded outcome is ``Yes`` is a market
        this module has no standing to read a side out of, and a third party's
        name on a two-player match is a linkage defect, not a result.

        🔴 ``"Draw"`` WAS THE SEVENTH PARAMETER HERE AND IT MOVED, on purpose,
        to `TestTheDrawIsAResult`. It did not stop being refused as a SIDE —
        :func:`_names_a_participant` still answers ``None`` for it and
        `test_a_draw_is_never_reported_as_one_of_the_two_sides` pins that. What
        changed is the question this function answers: a three-way moneyline
        has three verdicts, and reading the third as "the venue said nothing"
        was the defect. Deleting the case rather than moving it would have
        retired the only assertion that a draw is not a participant.
        """
        assert choose_settled_winner([_row(MONEYLINE, outcome_name)], HOME, AWAY) is None

    def test_nothing_graded_is_nothing(self):
        assert choose_settled_winner([], HOME, AWAY) is None

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_an_event_missing_a_side_name_cannot_have_that_side_matched(
        self, missing
    ):
        """An empty participant must not match an empty or whitespace outcome
        into a winner. Both halves are stripped, so the guard has to be the
        emptiness test and not the equality."""
        assert choose_settled_winner([_row(MONEYLINE, missing)], missing, AWAY) is None

    def test_matching_is_case_and_whitespace_insensitive_but_prints_our_spelling(
        self,
    ):
        """The venue writes its own casing; the sentence sits beside our team
        names, so it is ours that renders."""
        graded = [_row(MONEYLINE, "  FIONA   CRAWLEY ")]
        assert choose_settled_winner(graded, HOME, AWAY) == "Crawley wins"


class TestTheDrawIsAResult:
    """The third verdict on a three-way moneyline (2026-09-19).

    THE DEFECT, PHOTOGRAPHED ON PRODUCTION 2026-09-19 04:46Z. Eight soccer
    matches served ``venue_settled: true`` with ``venue_settled_result: null``,
    so each page drew a bare **"Settled"** chip over a win-probability hero and
    never said what happened — while the venue had graded the draw outright.
    Read back from Kalshi's own API on two of them::

        KXUELGAME-26SEP16STUREN-TIE   Tie             finalized   result=yes
        KXUELGAME-26SEP16STUREN-STU   Sturm Graz      finalized   result=no
        KXUELGAME-26SEP16STUREN-REN   Stade Rennais   finalized   result=no

    The refusal was correct as a PARTICIPANT question and wrong as a RESULT
    one: ``Tie`` is not one of the two sides, and the caller was reading "not a
    side" as "the venue said nothing about the whole contest".

    All eight are Kalshi three-ways (``Tie``); Polymarket writes ``Draw``, and
    its one graded draw in the population sits on a ``- Halftime Result``
    market, which `test_a_halftime_draw_is_not_the_match_result` pins as
    refused by the market classifier exactly as before.
    """

    #: The 2026-09-19 replay of the shipped functions over every graded leg in
    #: the scoreless `live`/`suspended` arm, before and after.
    MEASURED = {
        "events_holding_a_grade": 1295,
        "already_rendering_a_result": 980,
        "null_result_before": 315,
        "null_result_after": 307,
        "events_changed": 8,
        "events_byte_identical": 1287,
    }

    def test_the_specimen_reports_the_draw(self):
        assert (
            choose_settled_winner(
                [_row("Sturm Graz vs Stade Rennais", "Tie")],
                "Sturm Graz",
                "Stade Rennais",
            )
            == "Draw"
        )

    @pytest.mark.parametrize("venue_word", ["Tie", "Draw", "  tie ", "DRAW"])
    def test_both_venues_spellings_and_their_casing(self, venue_word):
        """Kalshi writes ``Tie``, Polymarket writes ``Draw``. Normalised-exact
        through the same helper the score-market test uses, so the vocabulary
        cannot drift into a substring rule."""
        assert (
            choose_settled_winner(
                [_row("Gorica vs Varazdin", venue_word)], "Gorica", "Varazdin"
            )
            == "Draw"
        )

    def test_a_draw_is_never_reported_as_one_of_the_two_sides(self):
        """What the moved parametrize case used to assert, kept: the draw is a
        third verdict, NOT a participant. If this ever returns a side, the
        sentence would name a team that did not win."""
        assert _names_a_participant("Tie", "Gorica", "Varazdin") is None
        assert _names_a_participant("Draw", "Gorica", "Varazdin") is None

    def test_a_draw_and_a_side_refuse_each_other(self):
        """🔴 THE REASON THE DRAW LIVES INSIDE THE SAME SET. On a three-way
        moneyline "the venue graded Tie" and "the venue graded Sturm Graz" are
        contradictory claims about one match. Computed on a separate path and
        joined with ``or``, whichever ran first would have been published and
        the contradiction would never have been visible — which is the
        confident-wrong-answer shape this module refuses everywhere else."""
        graded = [
            _row("Sturm Graz vs Stade Rennais", "Tie"),
            _row("Sturm Graz vs Stade Rennais", "Sturm Graz"),
        ]
        assert choose_settled_winner(graded, "Sturm Graz", "Stade Rennais") is None

    def test_the_same_draw_graded_twice_is_still_one_answer(self):
        graded = [
            _row("Gorica vs Varazdin", "Tie"),
            _row("Gorica vs Varazdin", "Draw"),
        ]
        assert choose_settled_winner(graded, "Gorica", "Varazdin") == "Draw"

    def test_a_halftime_draw_is_not_the_match_result(self):
        """The live Polymarket specimen, ``/events/15312519``. Its graded
        ``Draw`` sits on ``Shan United vs. Ezra FC - Halftime Result``, which
        the classifier calls ``other`` — so the draw never reaches the verdict
        set, and that event keeps the winner its real moneyline graded. A draw
        admitted by outcome name alone would have overwritten it."""
        graded = [
            _row("Shan United vs. Ezra FC - Halftime Result", "Draw"),
            _row("Shan United vs. Ezra FC", "Shan United"),
        ]
        assert (
            choose_settled_winner(graded, "Shan United", "Ezra FC")
            == "Shan United wins"
        )

    def test_a_draw_on_a_derivative_book_is_refused_like_every_other_grade(self):
        """The draw inherits the market test whole; it is not a bypass."""
        graded = [_row("Set Handicap: A (-1.5) vs B (+1.5)", "Tie")]
        assert choose_settled_winner(graded, "A", "B") is None

    def test_a_draw_renders_the_settled_line_through_the_shared_policy(self):
        """End to end through the function both readers actually call, so the
        rails and the detail page cannot answer this row differently."""
        assert settlement_from_graded_rows(
            [_row("Carlisle vs Forest Green", "Tie")], "Carlisle", "Forest Green"
        ) == {"venue_settled": True, "venue_settled_result": "Draw"}

    def test_the_winner_path_is_untouched_by_the_widening(self):
        """1,287 of the 1,295 measured events are byte-identical after the
        change; this is that claim on the specimen the file was built around."""
        assert (
            choose_settled_winner([_row(MONEYLINE, VENUE_HOME)], HOME, AWAY)
            == "Crawley wins"
        )

    def test_the_replay_adds_up(self):
        m = self.MEASURED
        assert m["already_rendering_a_result"] + m["null_result_before"] == (
            m["events_holding_a_grade"]
        )
        assert m["null_result_before"] - m["events_changed"] == m["null_result_after"]
        assert m["events_byte_identical"] + m["events_changed"] == (
            m["events_holding_a_grade"]
        )


class TestTheScoreStillWins:
    """Precedence, asserted on the route's own expression shape."""

    def test_a_full_scope_score_beats_the_winner_sentence(self):
        """`Fiona Crawley wins 2-0` is strictly richer than `Fiona Crawley
        wins`, so the 56 events that have one must not lose it."""
        graded = [
            _row("Exact Match Score: Fiona Crawley vs Naiktha Bains", "Fiona Crawley wins 2-0"),
            _row(MONEYLINE, HOME),
        ]
        served = choose_settled_score(
            outcome_name
            for market_name, _ext, outcome_name in graded
            if is_full_scope_score_market(market_name)
        ) or choose_settled_winner(graded, HOME, AWAY)
        assert served == "Fiona Crawley wins 2-0"

    def test_the_winner_is_reached_only_when_the_score_vocabulary_is_silent(self):
        graded = [_row(MONEYLINE, VENUE_HOME)]
        served = choose_settled_score(
            outcome_name
            for market_name, _ext, outcome_name in graded
            if is_full_scope_score_market(market_name)
        ) or choose_settled_winner(graded, HOME, AWAY)
        assert served == "Crawley wins"


class TestTheServedPayload:
    """The route half: `_venue_settlement` on the specimen's rows."""

    @pytest.mark.asyncio
    async def test_the_specimen_payload_carries_the_winner(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.routes.events import _venue_settlement

        db = MagicMock()
        result = MagicMock()
        result.all.return_value = [
            ("Set 1 Winner: Fiona Crawley vs Naiktha Bains", None, VENUE_AWAY),
            (MONEYLINE, None, VENUE_HOME),
        ]
        db.execute = AsyncMock(return_value=result)
        event = SimpleNamespace(
            id=15313807, home_team_name=HOME, away_team_name=AWAY
        )

        assert await _venue_settlement(db, event) == {
            "venue_settled": True,
            "venue_settled_result": "Crawley wins",
        }

    @pytest.mark.asyncio
    async def test_a_page_with_only_derivative_grades_is_settled_with_no_result(self):
        """Acceptance 4 of #6381, unchanged: *settled* without inventing a
        result is sufficient, and it is what the 40 non-moneyline events get."""
        from unittest.mock import AsyncMock, MagicMock

        from app.routes.events import _venue_settlement

        db = MagicMock()
        result = MagicMock()
        result.all.return_value = [
            ("Set 1 Winner: Fiona Crawley vs Naiktha Bains", None, VENUE_HOME),
        ]
        db.execute = AsyncMock(return_value=result)
        event = SimpleNamespace(
            id=15313807, home_team_name=HOME, away_team_name=AWAY
        )

        assert await _venue_settlement(db, event) == {
            "venue_settled": True,
            "venue_settled_result": None,
        }


class TestTheTruncatedMatchup:
    """🔴 #4629's both-sides refusal is defeated by a 60-character cut.

    `/events/15309330`, live on production 2026-09-17. Polymarket grades the
    outcome `US Open WTA (Doubles): Siniakova/Townsend vs Montgomery/Krue` —
    its own full-matchup name, truncated. It CONTAINS the home pair and, with
    `Krueger` cut to `Krue`, does NOT contain the away pair, so the both-sides
    guard never fires and the first-named side is reported as the winner
    whoever actually won. One row in 778; the whole class.
    """

    TRUNCATED = "US Open WTA (Doubles): Siniakova/Townsend vs Montgomery/Krue"
    DOUBLES_MONEYLINE = (
        "US Open WTA (Doubles): Siniakova/Townsend vs Montgomery/Krueger"
    )

    def test_the_real_truncated_row_is_refused(self):
        assert (
            choose_settled_winner(
                [_row(self.DOUBLES_MONEYLINE, self.TRUNCATED)],
                "Siniakova/Townsend",
                "Montgomery/Krueger",
            )
            is None
        )

    def test_an_untruncated_matchup_name_is_refused_by_4629_as_before(self):
        """The guard this one backs up, asserted so a later edit cannot
        delete one of the two and keep the file green."""
        assert (
            choose_settled_winner(
                [_row(MONEYLINE, "Fiona Crawley vs. Naiktha Bains")], HOME, AWAY
            )
            is None
        )

    @pytest.mark.parametrize(
        "participant",
        [
            # `at` and a bare `v` are NOT connectors — they occur inside real
            # names, and the pattern runs on a string we are about to print.
            "Atletico Madrid",
            "Vasco da Gama",
            "Athletic Club",
            "Vitoria",
            "Pep Guardiola v2",
        ],
    )
    def test_a_real_name_is_not_mistaken_for_a_matchup(self, participant):
        assert (
            choose_settled_winner(
                [_row(f"{participant} vs Someone Else", participant)],
                participant,
                "Someone Else",
            )
            == f"{participant} wins"
        )


class TestTheMeasurementIsOnTheRecord:
    """A later narrowing has to argue with a number, not with a preference."""

    def test_the_population_adds_up(self):
        assert (
            _MEASURED["events_gaining_a_winner"]
            + _MEASURED["events_already_holding_a_score"]
            + _MEASURED["events_still_refused"]
            == _MEASURED["events_holding_a_grade"]
        )

    def test_the_orientation_audit_found_no_inversions(self):
        """The measurement that permits a containment test on a name we print
        as a verdict. If it had found one, the gate would have to be exact and
        the ITF population would have to wait for a better id."""
        assert _MEASURED["audited_loser_resolves_to_the_same_side"] == 0
        assert (
            _MEASURED["audited_loser_resolves_to_the_other_side"]
            + _MEASURED["audited_loser_unresolvable"]
            == _MEASURED["events_gaining_a_winner"]
        )

    def test_the_exact_test_would_have_missed_two_thirds_of_them(self):
        assert _MEASURED["exact_equality_would_have_found"] == 265
        assert (
            _MEASURED["exact_equality_would_have_found"]
            < _MEASURED["events_gaining_a_winner"] // 2
        )
