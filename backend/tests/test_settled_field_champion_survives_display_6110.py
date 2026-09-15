"""#6110 — the repaired champion must reach the page, not just the database.

WHAT WAS MEASURED, ON PRODUCTION, MINUTES AFTER THE REPAIR RAN (2026-09-15).
The #6110 mint restored the Vuelta a España 2026 winner: market ``58675941``
went from 30 legs / 0 winners to **31 legs / exactly one winner** — ``Other``,
``current_probability 1.0``, ``resolution_source 'api_settlement'`` — and the
undo predicate was never needed. Then ``GET /api/futures/58675941`` served
**30 outcomes and no winner at all**, and the page still showed thirty riders
who lost and nobody who won. The data repair was complete and the reader saw
nothing change.

``drop_dominant_field_outcomes`` had deleted it. That rule (UX-P163/164) is
correct and stays: on a market still being made, ``Other 1.0`` is a no-bid ask
(gotcha #17/#19) — not an answer, and poison in the normalization divisor, which
is how Discover came to print ``Democratic Party 43%`` against a book price of
85.5%. **But every word of that justification is about a LIVE quote.** Once the
venue settles the field, the same row is the result.

That is the third instance in one day of one shape: a justification carried from
a path where it is honest to a path where it is a lie (int368's 05:30Z ledger
row names the other two). So these tests pin BOTH halves — the carve-out, and
the live-market rule it must not weaken.

AND IT PINS BOTH DEMOTION CLAUSES. Exempting the DROP alone would have moved the
champion of a finished race from "deleted" to "last of thirty-one, behind the
page's fold": ``leader_pick_order`` pushes a dominant field row to the end and
then steps a named row over it. A carve-out that only half fires is a bug that
looks fixed in the payload count.
"""

from types import SimpleNamespace

import pytest

from app.utils.outcome_display import (
    _FIELD_DOMINANT_MIN,
    drop_dominant_field_outcomes,
    leader_pick_order,
)

MARKET_ID = 58675941
WINNER_CID = "0x7ea6d1b641377841e13d0a7e5b6fa5fc70692704b212f47ad616fd2a3de0d543"

#: Three of the thirty riders the field really holds, all correctly graded LOST.
RIDERS = ["Tadej Pogacar", "Mads Pedersen", "Wout van Aert"]


def _row(name, prob, *, is_winner=False, resolution_source="api_settlement"):
    return {
        "name": name,
        "probability": prob,
        "is_winner": is_winner,
        "resolution_source": resolution_source,
    }


def _graded_winner(o):
    """The serializer's own predicate, verbatim in shape.

    Stricter than a bare ``is_winner`` on purpose (#4788): the column is
    ``boolean NULL DEFAULT false``, so a ``True`` beside a NULL source is a row
    nobody graded.
    """
    return bool(o.get("is_winner")) and o.get("resolution_source") is not None


# ---------------------------------------------------------------------------
# The decision, in isolation
# ---------------------------------------------------------------------------


class TestASettledChampionSurvivesTheDrop:
    def test_the_graded_field_winner_is_kept(self):
        rows = [_row(n, 0.0) for n in RIDERS] + [
            _row("Other", 1.0, is_winner=True)
        ]
        kept = drop_dominant_field_outcomes(
            rows,
            lambda o: o.get("name"),
            lambda o: o.get("probability"),
            is_winner_of=_graded_winner,
        )
        assert [o["name"] for o in kept] == RIDERS + ["Other"]

    def test_without_the_predicate_it_is_still_dropped(self):
        """The default is unchanged, so no existing call site moves.

        This is also the red control for the fix: the same rows, the same
        helper, one argument apart.
        """
        rows = [_row(n, 0.0) for n in RIDERS] + [
            _row("Other", 1.0, is_winner=True)
        ]
        kept = drop_dominant_field_outcomes(
            rows, lambda o: o.get("name"), lambda o: o.get("probability")
        )
        assert "Other" not in [o["name"] for o in kept]

    def test_an_ungraded_hundred_percent_field_row_is_still_dropped(self):
        # `is_winner=True` with no `resolution_source` is the defaulted-column
        # shape #4788 is about — nobody graded it, so it is not evidence.
        rows = [_row(n, 0.5) for n in RIDERS] + [
            _row("Other", 1.0, is_winner=True, resolution_source=None)
        ]
        kept = drop_dominant_field_outcomes(
            rows,
            lambda o: o.get("name"),
            lambda o: o.get("probability"),
            is_winner_of=_graded_winner,
        )
        assert "Other" not in [o["name"] for o in kept]

    def test_the_live_no_bid_ask_this_rule_exists_for_is_untouched(self):
        """UX-P163's own specimen, market 112903, with the carve-out armed.

        `Other 1.0` here is a no-bid ask on an OPEN market and nobody graded it.
        If the carve-out ever admits this row, Discover starts halving every
        number on the card again.
        """
        rows = [
            _row("Democratic Party", 0.855, resolution_source=None),
            _row("Republican Party", 0.145, resolution_source=None),
            _row("Other", 1.0, resolution_source=None),
        ]
        kept = drop_dominant_field_outcomes(
            rows,
            lambda o: o.get("name"),
            lambda o: o.get("probability"),
            is_winner_of=_graded_winner,
        )
        assert [o["name"] for o in kept] == ["Democratic Party", "Republican Party"]

    def test_a_graded_LOSING_field_row_is_still_dropped(self):
        # Being settled is not the carve-out; being the WINNER is. A residual
        # bucket the venue settled at 0 that somehow still carries a 1.0 display
        # price is exactly the incoherence the rule is for.
        rows = [_row(n, 0.0) for n in RIDERS] + [_row("Other", 1.0)]
        kept = drop_dominant_field_outcomes(
            rows,
            lambda o: o.get("name"),
            lambda o: o.get("probability"),
            is_winner_of=_graded_winner,
        )
        assert "Other" not in [o["name"] for o in kept]

    def test_the_threshold_is_unmoved(self):
        # A field row just under the dominance line survives with or without the
        # carve-out — the fix must not be doing its work by moving the boundary.
        just_under = _row("Other", _FIELD_DOMINANT_MIN - 0.01)
        rows = [_row(n, 0.3) for n in RIDERS] + [just_under]
        for pred in (None, _graded_winner):
            kept = drop_dominant_field_outcomes(
                rows,
                lambda o: o.get("name"),
                lambda o: o.get("probability"),
                is_winner_of=pred,
            )
            assert "Other" in [o["name"] for o in kept]


class TestTheChampionIsNotMerelyKeptButLeads:
    """Surviving the drop is not the ship — being READ is."""

    def _rows(self):
        return [_row("Other", 1.0, is_winner=True)] + [
            _row(n, 0.0) for n in RIDERS
        ]

    def test_a_graded_winner_leads_the_list(self):
        out = leader_pick_order(self._rows(), is_winner_of=_graded_winner)
        assert out[0]["name"] == "Other"
        assert out[0]["is_winner"] is True

    def test_without_the_predicate_it_is_demoted_to_the_end(self):
        """The red control for the SECOND clause.

        This is what the page would have rendered if only the drop had been
        exempted: the one row that answers the question, last of the list.
        """
        out = leader_pick_order(self._rows())
        assert out[-1]["name"] == "Other"

    def test_a_live_dominant_field_row_still_never_headlines(self):
        rows = [
            _row("Other", 1.0, resolution_source=None),
            _row("Democratic Party", 0.855, resolution_source=None),
        ]
        out = leader_pick_order(rows, is_winner_of=_graded_winner)
        assert out[0]["name"] == "Democratic Party"
        assert out[-1]["name"] == "Other"


# ---------------------------------------------------------------------------
# The specimen, through the real serializer
# ---------------------------------------------------------------------------


def _outcome(i, name, prob, *, is_winner=False, resolution_source="api_settlement"):
    return SimpleNamespace(
        id=i,
        name=name,
        external_id=WINNER_CID if name == "Other" else f"0x{i:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=i,
        rank_change_24h=None,
        probability_change_24h=None,
        # The minted champion holds NO forecast on purpose (gotcha #144): the
        # curve price coalesces `calibration_probability` to
        # `opening_probability`, and we never priced a leg we never ingested.
        opening_probability=None if name == "Other" else 0.03,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        last_updated=None,
        team_id=None,
    )


def _vuelta_market(*, with_champion=True):
    """Market 58675941 as production holds it after the #6110 repair."""
    outcomes = [
        _outcome(i, f"Rider {i}", 0.0) for i in range(1, 31)
    ]
    if with_champion:
        outcomes.append(_outcome(31, "Other", 1.0, is_winner=True))
    return SimpleNamespace(
        id=MARKET_ID,
        name="Vuelta a Espana 2026: Winner",
        description=None,
        category="championship",
        source="polymarket",
        external_id="815313",
        status="resolved",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="cycling",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


@pytest.fixture
def detail():
    from app.routes.futures import _format_market_detail

    return lambda market: _format_market_detail(market, None, set())


class TestTheServedPayloadCarriesTheChampion:
    def test_the_winner_is_served_at_all(self, detail):
        """The exact defect: 31 stored, 30 served, zero winners."""
        payload = detail(_vuelta_market())
        names = [o["name"] for o in payload["outcomes"]]
        assert "Other" in names, (
            "the settled champion was dropped from the payload — 31 legs stored, "
            f"{len(names)} served, and the page shows a finished race with no winner"
        )
        assert len(names) == 31

    def test_exactly_one_winner_reaches_the_reader(self, detail):
        payload = detail(_vuelta_market())
        winners = [o for o in payload["outcomes"] if o["is_winner"]]
        assert [w["name"] for w in winners] == ["Other"]

    def test_the_champion_leads_rather_than_sitting_behind_the_fold(self, detail):
        payload = detail(_vuelta_market())
        assert payload["outcomes"][0]["name"] == "Other"

    def test_the_champion_carries_its_grade_so_the_row_can_say_WON(self, detail):
        # `OutcomeRow.outcomeRowVerdict` prints no verdict on a NULL source
        # (#4788), so a champion served without one renders as silently as one
        # that was never there.
        payload = detail(_vuelta_market())
        champion = next(o for o in payload["outcomes"] if o["is_winner"])
        assert champion["resolution_source"] == "api_settlement"

    def test_no_forecast_is_invented_for_it(self, detail):
        payload = detail(_vuelta_market())
        champion = next(o for o in payload["outcomes"] if o["is_winner"])
        assert champion["opening_probability"] is None

    def test_the_thirty_losers_are_untouched(self, detail):
        payload = detail(_vuelta_market())
        losers = [o for o in payload["outcomes"] if not o["is_winner"]]
        assert len(losers) == 30
        assert all(o["resolution_source"] == "api_settlement" for o in losers)

    def test_the_field_before_the_repair_still_serves_its_thirty(self, detail):
        # The state the page was in for a day: no winner anywhere. Nothing about
        # this carve-out should change what a winnerless field serves — ux's
        # #6301 owns what the hero does with it.
        payload = detail(_vuelta_market(with_champion=False))
        assert len(payload["outcomes"]) == 30
        assert not any(o["is_winner"] for o in payload["outcomes"])
