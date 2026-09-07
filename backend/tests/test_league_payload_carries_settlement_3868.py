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

    def test_any_grader_counts_not_only_api_settlement(self):
        for source in ("clean_resolution", "pass2_loser", "all_losers"):
            assert _outcome_is_settled(_o(1, "x", 0.0, resolution_source=source))

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
