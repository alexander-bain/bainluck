"""#3617 — a card does not print a RESULT for a field nobody won.

THE BUG A READER SAW, on `/sport/tennis/wta` at 11:35Z on 2026-09-08, during the
US Open quarter-finals:

    US OPEN WOMEN SINGLES: SEMIFINALS QUALIFIERS
      #1  Maria Sakkari      15%
      #2  Paula Badosa       15%
      #3  Maja Chwalinska    15%
          Jessica Pegula     Lost
          Elena Rybakina     Lost
          Aryna Sabalenka    Lost

The top seed was playing her quarter-final that afternoon. The book had her at
69.5% to reach the semi-final. The card said she had already failed to — and
handed the 15% to three players who were out of the tournament.

WHY THE EXISTING GUARD COULD NOT CATCH IT. `_outcome_is_settled` (#3868,
CERT-2222) is right about everything it tests: it refuses to read certainty as
settlement, and it refuses to read a bare `resolution_source` as a grade. But it
answers only *is this settled*, and `can_write_winner('open', 'api_settlement')`
is True because tier-3 venue settlement is self-justifying. Told the leg is
settled, the caller has nothing left to read but `is_winner` — whose default is
exactly the FALSE that same docstring says cannot mean "lost". The guard is in
the right function and the wrong half.

THE RULE THIS FILE PINS, in two halves that are both required:

    no winner anywhere in the field   -> the stamp has nothing to be a loss against
    AND 0.20 <= its own price < 0.97  -> and the book has not eliminated it

CERT-2256 BLOCKED the first half on its own and was right: an open outright can
hold a TRUTHFUL settled loser long before anyone is crowned. A Slam ladder
eliminates players round by round and nobody wins until the final, so suppressing
on "no winner" alone takes Iga Swiatek — out of this tournament, priced 2% — and
puts her back to offering odds on a question that has been answered. That is
#3868's bug on the very card this file is fixing. `TestATerminalLoserKeepsIts
Result` is that block's named control.

The field half is not redundant either, and dropping it was the first thing
tried: a bare price band over-refuses 2,056 legs in fields that DO have a winner,
530 of them priced >= 0.97.

FIXTURES ARE REAL, read off production 2026-09-08 12:5xZ–13:0xZ by
`POST /api/admin/db-query`, market ids in each docstring. Prices are quoted to
the digit the column stores.
"""

from types import SimpleNamespace

import pytest

from app.routes.league_futures import (
    _field_has_a_winner,
    _live_first,
    _outcome_is_settled,
    _price_contradicts_a_loss,
    _serialize_outcomes,
    _sorted_outcomes,
)


def _o(id_, name, prob, *, is_winner=False, resolution_source=None):
    return SimpleNamespace(
        id=id_,
        name=name,
        current_probability=prob,
        opening_probability=None,
        rank=None,
        probability_change_24h=None,
        team_id=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
    )


def _stamped(id_, name, prob):
    """A leg badged with a tier-3 venue settlement and NOT crowned."""
    return _o(id_, name, prob, is_winner=False, resolution_source="api_settlement")


def _market(name, status, outcomes):
    return SimpleNamespace(
        name=name,
        status=status,
        llm_sport_category=None,
        outcomes=outcomes,
    )


# ---------------------------------------------------------------------------
# THE SPECIMENS
# ---------------------------------------------------------------------------

#: Market 59700049, `US Open Women Singles: Semifinals Qualifiers`, status=open,
#: tier 5, resolution_date 2026-09-21. 24 legs, **0 winners**, 21 of them badged
#: `api_settlement`. The three un-badged legs (Badosa / Sakkari / Chwalinska)
#: are the only ones that kept a percentage, and all three were already out.
SF_QUALIFIERS = [
    _stamped(1, "Jessica Pegula", 0.785),
    _stamped(2, "Aryna Sabalenka", 0.715),
    _stamped(3, "Elena Rybakina", 0.700),
    _stamped(4, "Coco Gauff", 0.625),
    _stamped(5, "Iva Jovic", 0.430),
    _stamped(6, "Mirra Andreeva", 0.375),
    _stamped(7, "Marta Kostyuk", 0.320),
    _stamped(8, "Qinwen Zheng", 0.295),
    _stamped(9, "Madison Keys", 0.240),
    _stamped(10, "Emma Navarro", 0.225),
    _stamped(11, "Linda Noskova", 0.210),
    _o(12, "Paula Badosa", 0.150),
    _o(13, "Maria Sakkari", 0.150),
    _o(14, "Maja Chwalinska", 0.150),
    _stamped(15, "Karolina Muchova", 0.140),
    _stamped(16, "Elina Svitolina", 0.110),
    _stamped(17, "Amanda Anisimova", 0.080),
    _stamped(18, "Iga Swiatek", 0.020),
    _stamped(19, "Naomi Osaka", 0.020),
    _stamped(20, "Jasmine Paolini", 0.010),
    _stamped(21, "Victoria Mboko", 0.010),
    _stamped(22, "Jelena Ostapenko", 0.010),
    _stamped(23, "Alexandra Eala", 0.010),
    _stamped(24, "Barbora Krejcikova", 0.010),
]

#: Market 3126724, `WBC Bantamweight Title on January 1, 2027`, status=open.
#: 20 legs, **0 winners**, and the badge fell on exactly the 16 legs that have a
#: PRICE. The four with no price at all are the four `_live_first` promoted to
#: the visible top of the card, so the reader's title ladder opened on two
#: em-dashes. Nothing about a January-2027 title can be settled in September.
WBC_BANTAMWEIGHT = [
    _stamped(1, "Michael Angeletti", 0.370),
    _stamped(2, "Tenshin Nasukawa", 0.210),
    _stamped(3, "Andrew Cain", 0.200),
    _stamped(4, "Takuma Inoue", 0.200),
    _stamped(5, "Riku Masuda", 0.190),
    _stamped(6, "Kenneth Llover", 0.180),
    _stamped(7, "Jason Moloney", 0.170),
    _stamped(8, "Yoshiki Takei", 0.160),
    _stamped(9, "Juan Francisco Estrada", 0.160),
    _stamped(10, "Alejandro Jair Gonzalez", 0.160),
    _stamped(11, "Petch Sor Chitpattana", 0.160),
    _stamped(12, "David Cuellar", 0.150),
    _stamped(13, "Kazuto Ioka", 0.150),
    _stamped(14, "Andrey Bonilla", 0.150),
    _stamped(15, "Katsuma Akitsugi", 0.130),
    _stamped(16, "Emmanuel Rodríguez", 0.130),
    _o(17, "David Mwale", None),
    _o(18, "Title is vacant", None),
    _o(19, "Christian Medina Jimenez", None),
    _o(20, "Jose Salas", None),
]

#: Market 60075114, `NE Patriots vs SEA Seahawks: 2nd Half Total`, status=open.
#: The issue's ORIGINAL specimen: a game that had not been played, 14 legs, **0
#: winners**, 7 badged. `is_winner` is None on four rows and False on the rest —
#: the two shapes the column uses for "nobody has looked".
NFL_SECOND_HALF_TOTAL = [
    _stamped(1, "Over 3.5 2H points scored", 0.800),
    _stamped(2, "Over 7.5 2H points scored", 0.750),
    _o(3, "Over 10.5 2H points scored", 0.710, is_winner=None),
    _stamped(4, "Over 21.5 2H points scored", 0.510),
    _o(5, "Over 22.5 2H points scored", 0.480, is_winner=None),
    _stamped(6, "Over 35.5 2H points scored", 0.250),
    _stamped(7, "Over 24.5 2H points scored", 0.210),
    _o(8, "Over 28.5 2H points scored", 0.205),
    _stamped(9, "Over 38.5 2H points scored", 0.085),
    _stamped(10, "Over 42.5 2H points scored", 0.070),
    _o(11, "Over 20.5 2H points scored", None, is_winner=None),
    _o(12, "Over 31.5 2H points scored", None, is_winner=None),
    _o(13, "Over 17.5 2H points scored", None, is_winner=None),
    _o(14, "Over 14.5 2H points scored", None, is_winner=None),
]

#: THE CONTROL, and the whole reason the rule is field-level rather than
#: per-leg. Market 108503, `Who will be Prime Minister of Slovenia after their
#: election?`, status=**open**, 7 legs, ONE crowned. Six real settled losses on
#: an open market: this card must be byte-identical after the change.
SLOVENIA_PM = [
    _o(1, "Janez Janša", 0.966, is_winner=True, resolution_source="api_settlement"),
    _stamped(2, "Jernej Vrtovec", 0.010),
    _stamped(3, "Anže Logar", 0.005),
    _stamped(4, "Robert Golob", 0.004),
    _stamped(5, "Matjaž Han", 0.001),
    _stamped(6, "Asta Vrečko", 0.001),
    _stamped(7, "Luka Mesec", 0.001),
]


# ---------------------------------------------------------------------------
# The specimens stop printing results
# ---------------------------------------------------------------------------


class TestAFieldNobodyWonPrintsNoResult:
    @pytest.mark.parametrize(
        "field,label",
        [
            (SF_QUALIFIERS, "US Open Women Singles: Semifinals Qualifiers"),
            (WBC_BANTAMWEIGHT, "WBC Bantamweight Title on January 1, 2027"),
            (NFL_SECOND_HALF_TOTAL, "NE Patriots vs SEA Seahawks: 2nd Half Total"),
        ],
    )
    def test_no_leg_the_book_still_prices_reaches_the_card_as_a_result(self, field, label):
        """Every leg the market is still quoting as a live contender loses its
        stamp. Legs the book has written off keep theirs — that half is
        `TestATerminalLoserKeepsItsResult`."""
        market = _market(label, "open", field)
        rows = _serialize_outcomes(_sorted_outcomes(market), market)
        wrongly_settled = [
            r["name"]
            for r in rows
            if r["settled"] and r["probability"] is not None and 0.20 <= r["probability"] < 0.97
        ]
        assert wrongly_settled == [], f"{label} has no winner, so it can report no live loser"

    def test_sabalenka_is_a_percentage_again_and_it_is_her_own(self):
        """The headline. Named legs, not a count: a rule that turned every row
        into a price would satisfy a count and still be wrong."""
        market = _market("US Open Women Singles: Semifinals Qualifiers", "open", SF_QUALIFIERS)
        rows = _serialize_outcomes(_sorted_outcomes(market), market)
        by_name = {r["name"]: r for r in rows}

        for name, price in [
            ("Jessica Pegula", 0.785),
            ("Aryna Sabalenka", 0.715),
            ("Elena Rybakina", 0.700),
        ]:
            assert by_name[name]["settled"] is False
            assert by_name[name]["probability"] == pytest.approx(price)

    def test_the_three_players_who_are_out_no_longer_lead_the_card(self):
        """Badosa / Sakkari / Chwalinska at 15% were `#1 #2 #3` only because
        everyone above them had been demoted into a settled tail."""
        market = _market("US Open Women Singles: Semifinals Qualifiers", "open", SF_QUALIFIERS)
        rows = _serialize_outcomes(_sorted_outcomes(market), market)

        assert [r["name"] for r in rows[:3]] == [
            "Jessica Pegula",
            "Aryna Sabalenka",
            "Elena Rybakina",
        ]
        assert "Maja Chwalinska" not in [r["name"] for r in rows[:3]]

    def test_the_boxing_ladder_stops_opening_on_two_em_dashes(self):
        """`_live_first`'s half of the same bug (#3617's second comment): the
        promoted legs were live only because nobody had stamped them, and they
        carry no price at all. The visible top must be the priced contenders."""
        market = _market("WBC Bantamweight Title on January 1, 2027", "open", WBC_BANTAMWEIGHT)
        rows = _serialize_outcomes(_sorted_outcomes(market), market)

        assert [r["name"] for r in rows[:4]] == [
            "Michael Angeletti",
            "Tenshin Nasukawa",
            "Andrew Cain",
            "Takuma Inoue",
        ]
        assert [r["probability"] for r in rows[:4]] == [
            pytest.approx(0.370),
            pytest.approx(0.210),
            pytest.approx(0.200),
            pytest.approx(0.200),
        ]
        assert all(r["settled"] is False for r in rows[:4])
        # The four em-dashes are still live legs and still shown — nobody has
        # stamped them, so nothing here claims otherwise — but they no longer
        # LEAD, which is the whole reader-visible complaint.
        assert all(r["probability"] is None for r in rows[4:8])


# ---------------------------------------------------------------------------
# CERT-2256's BLOCK, AND ITS NAMED CONTROL
# ---------------------------------------------------------------------------


class TestATerminalLoserKeepsItsResult:
    """CERT-2256: "an open ongoing outright can contain an authoritative
    `api_settlement` loser before its eventual winner is crowned."

    True, and it is this issue's own headline card. The US Open women's ladder
    eliminates players round by round and nobody is crowned until the final, so
    a field test alone erases every truthful elimination on it. The book is what
    tells the two apart: an eliminated contender is quoted at a cent or two, and
    a contender the market still rates is not.
    """

    #: Nine real eliminations on the very card #3617 is about, by name and
    #: stored price. Asserted through `_outcome_is_settled` rather than the
    #: payload BECAUSE the payload is `[:10]` and — correctly — none of these
    #: reach it once the live contenders above them are restored. The window is
    #: the ship working; the grade is what this class is about.
    @pytest.mark.parametrize(
        "name,price",
        [
            ("Iga Swiatek", 0.020),
            ("Naomi Osaka", 0.020),
            ("Jasmine Paolini", 0.010),
            ("Jelena Ostapenko", 0.010),
            ("Alexandra Eala", 0.010),
            ("Barbora Krejcikova", 0.010),
            ("Amanda Anisimova", 0.080),
            ("Elina Svitolina", 0.110),
            ("Karolina Muchova", 0.140),
        ],
    )
    def test_a_player_the_book_has_written_off_still_reads_lost(self, name, price):
        leg = next(o for o in SF_QUALIFIERS if o.name == name)
        assert leg.current_probability == pytest.approx(price), "fixture drifted"
        assert _outcome_is_settled(leg, "open", False) is True

    def test_the_same_card_does_both_things_at_once(self):
        """The point of the conjunction, in one place: ONE uncrowned field, the
        favourite restored AND the eliminated player still graded."""
        sabalenka = next(o for o in SF_QUALIFIERS if o.name == "Aryna Sabalenka")
        swiatek = next(o for o in SF_QUALIFIERS if o.name == "Iga Swiatek")

        assert _outcome_is_settled(sabalenka, "open", False) is False
        assert _outcome_is_settled(swiatek, "open", False) is True

    def test_the_eliminated_players_queue_behind_the_live_ones(self):
        """And the card still reads correctly end to end: the restored
        contenders take the visible slots and the graded tail sits behind them,
        which is #3868's own ordering contract, unchanged."""
        market = _market("US Open Women Singles: Semifinals Qualifiers", "open", SF_QUALIFIERS)
        ordered = _live_first(_sorted_outcomes(market), "open")
        names = [o.name for o in ordered]

        assert names[:3] == ["Jessica Pegula", "Aryna Sabalenka", "Elena Rybakina"]
        assert names.index("Aryna Sabalenka") < names.index("Iga Swiatek")

    def test_a_leg_that_agrees_with_its_grade_is_never_promoted(self):
        """The ceiling. A leg at 0.99 rendered as a percentage is "a graded row
        dressed as an ordinary 100%" — #3868's original bug — so the refusal
        stops below certainty even in an uncrowned field. 68 legs / 51 markets
        sit here on production; they are a data defect (#3959)."""
        field = [_stamped(1, "Certain", 0.99), _stamped(2, "Hopeless", 0.01)]
        market = _market("An uncrowned field holding a near-certainty", "open", field)
        rows = {r["name"]: r for r in _serialize_outcomes(_sorted_outcomes(market), market)}
        assert rows["Certain"]["settled"] is True
        assert rows["Hopeless"]["settled"] is True

    def test_the_floor_and_ceiling_are_half_open_at_both_ends(self):
        """Boundaries stated, so a `>` for a `>=` cannot pass silently."""
        assert _price_contradicts_a_loss(_stamped(1, "at the floor", 0.20)) is True
        assert _price_contradicts_a_loss(_stamped(2, "under it", 0.1999)) is False
        assert _price_contradicts_a_loss(_stamped(3, "under the ceiling", 0.9699)) is True
        assert _price_contradicts_a_loss(_stamped(4, "at the ceiling", 0.97)) is False

    def test_no_price_is_not_a_contradiction(self):
        """Absence of evidence (gotcha #53). The column is populated forward, so
        a null price says nothing and the grade stands."""
        assert _price_contradicts_a_loss(_o(1, "unpriced", None)) is False


# ---------------------------------------------------------------------------
# OVER-REFUSAL IS THE ONLY REAL RISK, SO IT IS WHERE THE CONTROLS ARE
# ---------------------------------------------------------------------------


class TestACoherentFieldIsUntouched:
    def test_an_open_market_with_one_winner_keeps_all_six_of_its_losses(self):
        market = _market("Who will be Prime Minister of Slovenia after their election?", "open", SLOVENIA_PM)
        rows = _serialize_outcomes(_sorted_outcomes(market), market)

        assert rows[0]["name"] == "Janez Janša"
        assert rows[0]["settled"] is True and rows[0]["is_winner"] is True
        assert all(r["settled"] is True for r in rows), "one crowned leg makes the field readable"
        assert sum(1 for r in rows if r["is_winner"] is not True) == 6

    def test_one_winner_is_enough_however_far_down_the_field_it_sits(self):
        """The truncation hazard, stated as a test. The payload window is
        `[:10]`, so coherence read off the window instead of the field would
        call this market unwon and turn twelve real results into prices.

        The winner is priced 0.0 deliberately — `_sorted_outcomes` ranks by
        probability, so it lands at index 12, outside every window there is."""
        field = [_stamped(i, f"Loser {i}", 0.9 - i / 100) for i in range(1, 13)]
        field.append(_o(99, "The actual winner", 0.0, is_winner=True, resolution_source="api_settlement"))
        market = _market("A field whose winner is priced last", "open", field)

        assert _field_has_a_winner(_sorted_outcomes(market)) is True
        rows = _serialize_outcomes(_sorted_outcomes(market), market)
        assert rows[0]["name"] == "The actual winner"
        assert all(r["settled"] is True for r in rows)

    def test_a_resolved_field_with_no_winner_is_left_exactly_as_3868_drew_it(self):
        """SCOPE. The refusal applies only where the grade rests on the SOURCE
        alone. A `resolved`/`closed` market with no winner is a different animal
        — a void — and is not this issue's population: every specimen on #3617
        is `status='open'`. Widening the scope here would silently restyle a
        cohort nobody has measured."""
        field = [_stamped(i, f"Nobody {i}", 0.1 * i) for i in range(1, 5)]
        for status in ("resolved", "closed"):
            market = _market("A void", status, field)
            rows = _serialize_outcomes(_sorted_outcomes(market), market)
            assert all(r["settled"] is True for r in rows), status

    def test_a_retraction_is_still_refused_before_anything_else(self):
        """CERT-2222's clause, re-pinned: `ungradeable_result` is a RETRACTION,
        and it must stay live even on a market this rule would otherwise leave
        alone. The new clause is inserted BELOW it, not above."""
        retracted = _o(1, "Unknowable", 0.4, resolution_source="ungradeable_result")
        winner = _o(2, "Crowned", 1.0, is_winner=True, resolution_source="api_settlement")
        market = _market("A coherent field holding a retraction", "open", [winner, retracted])
        rows = {r["name"]: r for r in _serialize_outcomes(_sorted_outcomes(market), market)}

        assert rows["Crowned"]["settled"] is True
        assert rows["Unknowable"]["settled"] is False

    def test_a_crowned_leg_is_settled_whatever_the_field_says(self):
        """The clause order matters: `is_winner is True` returns before the new
        test, so a winner can never be un-settled by its own field."""
        winner = _o(1, "Crowned", 1.0, is_winner=True, resolution_source="api_settlement")
        assert _outcome_is_settled(winner, "open", False) is True
        assert _outcome_is_settled(winner, None, False) is True


# ---------------------------------------------------------------------------
# THE PRICE IS NEVER CONSULTED
# ---------------------------------------------------------------------------


class TestTheFieldTestIsNotRedundant:
    """A bare price band was the mechanism #3617's comment named, and CERT-2256
    is the reason a bare FIELD test is not the answer either. Both halves are
    load-bearing and these tests pin the half a price band cannot do.

    Measured on production 2026-09-08: dropping the field test over-refuses
    2,056 legs in markets that DO have a winner, 530 of them priced >= 0.97 —
    those would return to the card as an ordinary "99%" for a leg the field's
    own crown contradicts, which is #3868's original bug rebuilt.
    """

    def test_a_crowned_field_keeps_every_grade_however_the_book_prices_it(self):
        """A coherent field is untouched at every price, including the band that
        would trip the contradiction test on its own."""
        crown = _o(0, "Winner", 0.99, is_winner=True, resolution_source="api_settlement")
        for price in (0.01, 0.20, 0.50, 0.85, 0.99):
            field = [crown, _stamped(1, "Loser", price)]
            market = _market("A crowned field", "open", field)
            rows = {r["name"]: r for r in _serialize_outcomes(_sorted_outcomes(market), market)}
            assert rows["Loser"]["settled"] is True, price
            assert _price_contradicts_a_loss(field[1]) is (0.20 <= price < 0.97), price

    def test_the_price_alone_never_refuses_a_grade(self):
        """The conjunction stated directly: the same leg, the same price, one
        crowned field and one uncrowned, and only the uncrowned one refuses."""
        leg = _stamped(1, "Contender", 0.62)
        assert _price_contradicts_a_loss(leg) is True
        assert _outcome_is_settled(leg, "open", True) is True
        assert _outcome_is_settled(leg, "open", False) is False

    def test_the_sub_floor_tail_of_the_boxing_ladder_is_left_alone(self):
        """Honest about what this does NOT repair: 12 of the WBC card's 16
        stamped legs sit at 0.19 and below and keep reading Lost, on a title
        that resolves in 2027. They are wrong and they are #3959's, not the
        renderer's — the book has written them off and the display has no
        second signal to argue with."""
        market = _market("WBC Bantamweight Title on January 1, 2027", "open", WBC_BANTAMWEIGHT)
        ordered = _live_first(_sorted_outcomes(market), "open")
        cheap = [o for o in ordered if o.current_probability and o.current_probability < 0.20]

        assert len(cheap) == 12
        assert all(_outcome_is_settled(o, "open", False) is True for o in cheap)


# ---------------------------------------------------------------------------
# The helper on its own
# ---------------------------------------------------------------------------


class TestFieldHasAWinner:
    def test_only_a_literal_true_counts(self):
        """`is_winner` is nullable with a False default, so None is "nobody has
        looked" and False is not a crown. Neither may make a field coherent."""
        assert _field_has_a_winner([_o(1, "a", 0.5, is_winner=None)]) is False
        assert _field_has_a_winner([_o(1, "a", 0.5, is_winner=False)]) is False
        assert _field_has_a_winner([_o(1, "a", 0.5, is_winner=True)]) is True

    def test_an_empty_field_has_no_winner(self):
        assert _field_has_a_winner([]) is False

    def test_live_first_derives_it_from_its_own_argument(self):
        """`_live_first` is reachable on its own and must not depend on a flag
        a caller remembered to compute."""
        ordered = _live_first(_sorted_outcomes(_market("x", "open", SF_QUALIFIERS)), "open")
        assert [o.name for o in ordered[:3]] == [
            "Jessica Pegula",
            "Aryna Sabalenka",
            "Elena Rybakina",
        ]
