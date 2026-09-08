"""#3868 / CERT-2215 — the league payload carries settlement, and ranks live first.

THE BLOCK THIS ANSWERS.  #3868's first presentation taught the Polymarket
refresh rail to read child-level settlement, which fixed the DATA and stopped
there.  CERT-2215 found the ship did not reach `/sport/tennis/atp`:
``/api/leagues/{sport_key}`` dropped ``is_winner`` and ``resolution_source``, so
a graded leg travelled as a bare ``probability: 1.0`` and the card drew it as an
ordinary "100%".

AND THE SHARPER HALF, WHICH IS A REGRESSION THE FIX WOULD HAVE CAUSED.  A
settled winner carries 1.0, and this payload is ranked by probability, and the
card renders ``top_outcomes[:6]``.  So grading the US Open men's quarterfinal
ladder would have put the eight already-through players in all six visible slots
and displaced the five still fighting for one.  The card's only live question
would have disappeared — a worse card than the stale one that started #3868.

The companion render guard is
``frontend/__tests__/components/settledLadderLegsDoNotRenderAsOdds3868.test.tsx``;
this file pins the half of the contract a rendered string cannot see (which rows
were CHOSEN, and in what order), and that file pins the half this one cannot
(that no settled leg reaches the reader as a percentage).

The fixture is real: market 59556819, read at the venue 2026-09-07 09:3xZ.
"""

from types import SimpleNamespace

from app.routes.league_futures import (
    _live_first,
    _outcome_is_settled,
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


def _settled(id_, name, won):
    return _o(
        id_,
        name,
        1.0 if won else 0.0,
        is_winner=won,
        resolution_source="api_settlement",
    )


#: US Open 2026 To Reach Quarterfinals (Men's Singles), as it stands after the
#: refresh rail grades it: five children genuinely still trading, two through,
#: four out.
QF_MENS = [
    _settled(221651252, "Carlos Alcaraz", True),
    _o(221651253, "Alexander Zverev", 0.885),
    _settled(221651256, "Ben Shelton", True),
    _o(221651260, "Learner Tien", 0.62),
    _o(221651262, "Alexander Blockx", 0.60),
    _settled(221651254, "Novak Djokovic", False),
    _o(221651261, "Francisco Cerundolo", 0.385),
    _settled(221651255, "Daniil Medvedev", False),
    _o(221651263, "Luciano Darderi", 0.135),
    _settled(221651257, "Taylor Fritz", False),
    _settled(221651267, "Felix Auger-Aliassime", False),
]


class TestWhatCountsAsSettled:
    """A GRADE, never a probability."""

    def test_a_graded_row_is_settled(self):
        assert _outcome_is_settled(_settled(1, "Alcaraz", True))
        assert _outcome_is_settled(_settled(2, "Djokovic", False))

    def test_a_soft_grader_counts_ONCE_THE_MARKET_HAS_SETTLED(self):
        """Rewritten by CERT-2222, and the rewrite is the point.

        This test used to assert that any non-empty `resolution_source` settles
        a row on a market of ANY status. That is the reading CERT-2222 blocked:
        it is how `ungradeable_result` — a RETRACTION — reached the card as
        "Lost". The assertion was pinning the defect, so loosening the code to
        keep it green would have been the regression.

        The canonical rule (#845, `can_write_winner`) is status-aware, and it is
        asserted here in BOTH directions rather than in the one that passes.
        """
        for source in ("clean_resolution", "pass2_loser", "all_losers"):
            for status in ("resolved", "closed"):
                assert _outcome_is_settled(
                    _o(1, "x", 0.0, resolution_source=source), status
                ), f"{source} must count on a {status} market"

            for status in ("open", "suspended", None):
                assert not _outcome_is_settled(
                    _o(1, "x", 0.0, resolution_source=source), status
                ), (
                    f"{source} is not tier-3, so on a {status} market it is a "
                    "premature write and must not reach the reader as a result"
                )

    def test_an_authoritative_settlement_counts_even_on_an_OPEN_market(self):
        """The ship's own path, pinned so the repair cannot swallow it.

        The Alcaraz child is `status='open'` carrying `api_settlement`. Tier 3
        is self-justifying — the venue said so — and if this went the other way
        #3868 would be un-shipped by its own repair.
        """
        assert _outcome_is_settled(
            _o(1, "Carlos Alcaraz", 1.0, resolution_source="api_settlement"), "open"
        )

    def test_a_crowned_row_with_no_source_is_settled(self):
        """Production carries one. A crowned row is settled by anyone's reading."""
        assert _outcome_is_settled(_o(1, "x", 1.0, is_winner=True))

    def test_certainty_is_not_settlement(self):
        """MEASURED: the Alcaraz leg read 0.9995 for a day BEFORE it closed.

        If this returned True on the number, a live book would be stamped with a
        result and the reader would be told a match was over while it was being
        played.
        """
        assert not _outcome_is_settled(_o(1, "Carlos Alcaraz", 0.9995))
        assert not _outcome_is_settled(_o(2, "Someone", 1.0))

    def test_is_winner_false_alone_is_not_settled(self):
        """`is_winner` is nullable with default False — FALSE cannot tell
        "lost" from "nobody has looked"."""
        assert not _outcome_is_settled(_o(1, "x", 0.4, is_winner=False))
        assert not _outcome_is_settled(_o(2, "x", 0.4, is_winner=None))


class TestASettledLegNeverTakesALiveLegsSlot:

    def test_every_open_child_precedes_every_settled_one(self):
        ordered = _live_first(_sorted_outcomes(SimpleNamespace(outcomes=QF_MENS)))
        settled_flags = [_outcome_is_settled(o) for o in ordered]
        assert settled_flags == sorted(settled_flags), (
            "a settled leg sorted ahead of a live one: the card renders the "
            "first six, so this is how the eight already-through players take "
            "every visible slot"
        )

    def test_all_five_live_contenders_survive_the_six_visible_slots(self):
        """THE REGRESSION #3868 WOULD HAVE CAUSED, in one assertion."""
        rows = _serialize_outcomes(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
        )
        visible = {r["name"] for r in rows[:6]}
        for name in (
            "Alexander Zverev",
            "Learner Tien",
            "Alexander Blockx",
            "Francisco Cerundolo",
            "Luciano Darderi",
        ):
            assert name in visible, f"{name} was displaced by a settled leg"

    def test_the_live_ones_keep_their_own_ranking(self):
        rows = _serialize_outcomes(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
        )
        live = [r for r in rows if not r["settled"]]
        probs = [r["probability"] for r in live]
        assert probs == sorted(probs, reverse=True)
        assert live[0]["name"] == "Alexander Zverev"

    def test_winners_lead_the_settled_tail(self):
        """"Who got through" is the interesting half; a tail of Losts buries it."""
        rows = _serialize_outcomes(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
        )
        tail = [r for r in rows if r["settled"]]
        winners = [r["is_winner"] for r in tail]
        assert winners == sorted(winners, reverse=True)
        assert tail[0]["name"] in ("Carlos Alcaraz", "Ben Shelton")

    def test_a_fully_live_ladder_is_ordered_exactly_as_before(self):
        """No settled rows ⇒ this function is the identity. Nothing else moves."""
        live_only = [o for o in QF_MENS if not _outcome_is_settled(o)]
        ranked = _sorted_outcomes(SimpleNamespace(outcomes=live_only))
        assert _live_first(ranked) == ranked


class TestThePayloadCarriesTheState:

    def test_every_row_declares_whether_it_is_settled(self):
        rows = _serialize_outcomes(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
        )
        assert rows
        for row in rows:
            assert "settled" in row, "the card cannot draw a state it is not sent"
            assert "is_winner" in row

    def test_a_settled_winner_and_loser_are_distinguishable(self):
        rows = {
            r["name"]: r
            for r in _serialize_outcomes(
                _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
            )
        }
        assert rows["Carlos Alcaraz"]["settled"] is True
        assert rows["Carlos Alcaraz"]["is_winner"] is True
        assert rows["Novak Djokovic"]["settled"] is True
        assert rows["Novak Djokovic"]["is_winner"] is False

    def test_an_open_child_is_not_marked_settled(self):
        rows = {
            r["name"]: r
            for r in _serialize_outcomes(
                _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
            )
        }
        assert rows["Alexander Zverev"]["settled"] is False
        assert rows["Alexander Zverev"]["probability"] == 0.885

    def test_the_ten_row_cap_is_unchanged(self):
        rows = _serialize_outcomes(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS))
        )
        assert len(rows) == 10


#: The same ladder with one leg RETRACTED: `ungradeable_result` is the state of a
#: leg whose stored loss the venue never declared (CAL-P056, #1852). The market
#: is still `open`, which is the shape the league payload actually selects.
QF_MENS_WITH_A_RETRACTION = QF_MENS + [
    _o(221651268, "Jiri Lehecka", 0.21, resolution_source="ungradeable_result"),
    _o(
        221651269,
        "Tomas Machac",
        0.18,
        is_winner=True,
        resolution_source="ungradeable_result",
    ),
]

OPEN_MARKET = SimpleNamespace(
    name="US Open 2026 To Reach Quarterfinals (Men's Singles)",
    llm_sport_category="tennis",
    status="open",
)


class TestARetractionIsNotAResult:
    """CERT-2222's finding: the defect that looks like a result.

    `ungradeable_result` asserts NO winner — it is our statement that the leg is
    unknowable, written precisely to take a fabricated loss OUT of the published
    curve. Read as "settled, and `is_winner` is not True" it reached the card as
    **Lost**, telling the reader a player was knocked out of a tournament we had
    just declared we could not grade. A stale price is wrong; this is worse,
    because it wears the costume of a result.
    """

    def test_a_retracted_leg_is_not_settled_on_an_open_market(self):
        assert not _outcome_is_settled(
            _o(1, "Jiri Lehecka", 0.21, resolution_source="ungradeable_result"),
            "open",
        )

    def test_a_retracted_leg_is_not_settled_ON_ANY_STATUS(self):
        """Refused before the status test, deliberately.

        `can_write_winner` alone would admit a retraction on a `resolved`
        market, and the retraction means the same thing whatever the market
        around it says.
        """
        for status in ("open", "suspended", "resolved", "closed", None):
            assert not _outcome_is_settled(
                _o(1, "x", 0.2, resolution_source="ungradeable_result"), status
            ), f"a retraction must not read as a grade on a {status} market"

    def test_a_retracted_leg_that_is_also_crowned_stays_live(self):
        """A contradiction, and the honest render is the live one.

        Retracted-and-crowned cannot both be true. Refusing FIRST means the
        reader is shown the still-trading percentage rather than a verdict we
        have two irreconcilable stories about.
        """
        assert not _outcome_is_settled(
            _o(1, "Tomas Machac", 0.18, is_winner=True,
               resolution_source="ungradeable_result"),
            "open",
        )

    def test_the_retracted_leg_travels_unsettled_and_keeps_its_price(self):
        """The route-through the BLOCK named, on the open + ungradeable case."""
        rows = {
            r["name"]: r
            for r in _serialize_outcomes(
                _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS_WITH_A_RETRACTION)),
                OPEN_MARKET,
            )
        }
        for name, price in (("Jiri Lehecka", 0.21), ("Tomas Machac", 0.18)):
            assert rows[name]["settled"] is False, f"{name} must not read as graded"
            assert rows[name]["probability"] == price, (
                f"{name} is still trading, so it keeps its number"
            )

    def test_the_retraction_does_not_disturb_the_real_grades(self):
        """The blast-radius control: the ship still ships.

        If the repair had been written as "trust nothing", this is the test that
        would have caught it — the genuinely settled legs must be unchanged.
        """
        rows = {
            r["name"]: r
            for r in _serialize_outcomes(
                _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS_WITH_A_RETRACTION)),
                OPEN_MARKET,
            )
        }
        assert rows["Carlos Alcaraz"]["settled"] is True
        assert rows["Carlos Alcaraz"]["is_winner"] is True
        assert rows["Novak Djokovic"]["settled"] is True
        assert rows["Novak Djokovic"]["is_winner"] is False

    def test_a_retracted_leg_is_ordered_with_the_LIVE_contenders(self):
        """Ordering follows the same predicate, so a retraction keeps its slot
        among the live rows instead of being queued into the settled tail."""
        ordered = _live_first(
            _sorted_outcomes(SimpleNamespace(outcomes=QF_MENS_WITH_A_RETRACTION)),
            "open",
        )
        names = [o.name for o in ordered]
        settled_tail_starts = min(
            names.index("Carlos Alcaraz"), names.index("Ben Shelton")
        )
        for retracted in ("Jiri Lehecka", "Tomas Machac"):
            assert names.index(retracted) < settled_tail_starts, (
                f"{retracted} is still trading and must rank among the live rows"
            )
