"""#9083, the pin's third arm: a midpoint of a book that bounds nothing is not pinned.

THE SPECIMEN (discover, 2026-10-04 04:16Z). The settled page ``/events/15322620``
(Padres @ Brewers) printed "Manny Machado: 2+ home runs, marked 48% → MISS". Market
63865773 "Manny Machado: Home Runs O/U 1.5" was pinned
``{240536425: 0.485, 240536426: 0.515}`` at 00:18:43Z, while its O/U 0.5 rung in the
same capture was pinned 0.075. Read on production:

    leg    external_id          probability   yes_bid   yes_ask   last_price
    Over   0xca22…_yes           0.485         NULL      0.9800    NULL
    Under  0xca22…_no            0.515         0.0200    NULL      NULL

That is the market's ONLY snapshot, written at creation on 10/02 22:16Z, 26 hours
before the pin. The two-minute poll looks legs up by the bare condition id, so it
never reads a ``_yes``/``_no`` leg: neither the fresh-book arm nor the declined-read
arm could see this market, and the tick rule calls a 98c ask a quote. 14,524 of the
14,801 Polymarket markets pinned in the 30 hours to 04:30Z were split-token.

The predicates are #5247's ``is_empty_book_midpoint`` and #8916's
``is_bidless_empty_book_midpoint``, imported by the writer and not restated here.
These arms pin how the WRITER uses them.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as pmm
from app.tasks.prediction_market_matching import (
    _PREGAME_MARK_LEAD_MINUTES,
    _pregame_pin_outcome_probs,
)
from app.utils.polymarket_empty_book import is_empty_polymarket_book
from tests.test_live_poll_commit_boundary_5682 import (
    _Event,
    _Market,
    _now,
    _Outcome,
    _PolyService,
    _Population,
    _Session,
    _run,
)


def _leg(oid, prob, bid, ask, external_id=None):
    return SimpleNamespace(
        id=oid,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        external_id=external_id,
    )


MACHADO_CID = "0xca22d1b581a4dbe07f36d84697f0a324fef7445c88096fad3b8c47bf01641876"
MACHADO_OVER = _leg(240536425, 0.485, None, 0.98, f"{MACHADO_CID}_yes")
MACHADO_UNDER = _leg(240536426, 0.515, 0.02, None, f"{MACHADO_CID}_no")

# The same capture's O/U 0.5 rung (market 63967831): a bid-less longshot. Its
# ask says nobody sells above 15c, so 0.075 is bounded, not invented.
RUNG_CID = "0x6e5fbb0e5c0a7384177f62790c344a910ed58ca9aa3f7856ce201015cc368681"
RUNG_OVER = _leg(240879162, 0.075, None, 0.15, f"{RUNG_CID}_yes")
RUNG_UNDER = _leg(240879163, 0.925, 0.85, None, f"{RUNG_CID}_no")


class TestTheWriterRefusesTheSpecimen:
    def test_neither_leg_of_the_machado_book_is_pinned(self):
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [MACHADO_OVER, MACHADO_UNDER]
        )
        assert probs == {}
        assert refused == 2

    def test_the_tick_rule_alone_pinned_both(self):
        """Non-vacuity: the shipped arms let the specimen through. Neither book is
        empty by the tick rule, and the poll never read either leg, so before this
        arm the writer pinned 0.485 / 0.515 exactly as production shows."""
        shipped = {
            str(o.id): round(float(o.current_probability), 6)
            for o in (MACHADO_OVER, MACHADO_UNDER)
            if not is_empty_polymarket_book(o.current_yes_bid, o.current_yes_ask)
        }
        assert shipped == {"240536425": 0.485, "240536426": 0.515}

    def test_the_under_alone_is_not_refused_so_the_twin_rule_carries_it(self):
        """The Under (bid 0.02, no ask) is reached by neither predicate. Judged on
        its own row it is pinned; only its Over's refusal takes it out."""
        assert _pregame_pin_outcome_probs("polymarket", [MACHADO_UNDER]) == (
            {"240536426": 0.515},
            0,
        )

    def test_the_twin_is_refused_whichever_order_the_legs_arrive_in(self):
        assert _pregame_pin_outcome_probs(
            "polymarket", [MACHADO_UNDER, MACHADO_OVER]
        ) == ({}, 2)


class TestWhatTheWriterStillPins:
    def test_the_same_captures_longshot_rung_is_pinned(self):
        """Control from the specimen's own capture: ask 0.15 → 0.075 is out of the
        predicates' reach ([0.44, 0.51] for a bid-less book)."""
        assert _pregame_pin_outcome_probs("polymarket", [RUNG_OVER, RUNG_UNDER]) == (
            {"240879162": 0.075, "240879163": 0.925},
            0,
        )

    @pytest.mark.parametrize(
        "prob, ask",
        [(0.0025, 0.005), (0.04, 0.08), (0.06, 0.12), (0.18, 0.36)],
        ids=["half-cent", "spread-8c", "hr-12c", "5247-kept-36c"],
    )
    def test_bidless_longshots_from_production_are_pinned(self, prob, ask):
        """Shapes read on the 30-hour pin population: lone ask, mark at half of it."""
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, prob, None, ask, "c_yes")]
        )
        assert (probs, refused) == ({"1": prob}, 0)

    def test_a_wide_book_whose_price_is_off_its_middle_is_pinned(self):
        """0.77 on 0.02/0.98 (Gillingham 2nd Half O/U, pinned 10/03): far from the
        midpoint, so something other than arithmetic put it there."""
        assert _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, 0.77, 0.02, 0.98, "g_yes")]
        ) == ({"1": 0.77}, 0)

    def test_a_two_sided_wide_book_on_its_midpoint_is_refused_with_its_twin(self):
        over = _leg(1, 0.5, 0.05, 0.95, "t_yes")
        under = _leg(2, 0.5, 0.05, 0.95, "t_no")
        assert _pregame_pin_outcome_probs("polymarket", [over, under]) == ({}, 2)

    def test_a_refusal_does_not_cross_condition_ids(self):
        """A field's rungs are separate books: one phantom rung leaves alone."""
        phantom = _leg(1, 0.485, None, 0.98, "rung-a_yes")
        honest = _leg(2, 0.62, 0.61, 0.63, "rung-b_yes")
        assert _pregame_pin_outcome_probs("polymarket", [phantom, honest]) == (
            {"2": 0.62},
            1,
        )

    def test_legs_without_an_external_id_are_judged_alone(self):
        phantom = _leg(1, 0.485, None, 0.98)
        honest = _leg(2, 0.515, 0.02, None)
        assert _pregame_pin_outcome_probs("polymarket", [phantom, honest]) == (
            {"2": 0.515},
            1,
        )

    def test_a_fresh_two_sided_read_beats_the_stored_bidless_row(self):
        """CERT-3639's precedence holds for this arm: the read is the book."""
        assert _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, 0.485, None, 0.98, "c_yes")], {1: (0.47, 0.50)}
        ) == ({"1": 0.485}, 0)

    def test_kalshi_legs_are_out_of_scope(self):
        assert _pregame_pin_outcome_probs(
            "kalshi", [MACHADO_OVER, MACHADO_UNDER]
        ) == ({"240536425": 0.485, "240536426": 0.515}, 0)


# --------------------------------------------------------------------------
# through the REAL poll: split-token legs the poll never reads
# --------------------------------------------------------------------------


def _split_market(mid, cid, over, under, commence):
    market = (_Market(mid, "polymarket", f"poly-evt-{mid}"), _Event(300 + mid, commence=commence))
    legs = []
    for oid, side, (prob, bid, ask) in (
        (mid * 10, "yes", over),
        (mid * 10 + 1, "no", under),
    ):
        o = _Outcome(oid, mid, f"{cid}_{side}", "Over" if side == "yes" else "Under")
        o.current_probability, o.current_yes_bid, o.current_yes_ask = prob, bid, ask
        legs.append(o)
    return market, legs


class TestThroughTheLivePoll:
    async def test_the_machado_market_gets_no_pin_and_its_rung_does(self, monkeypatch):
        commence = _now() + timedelta(minutes=_PREGAME_MARK_LEAD_MINUTES / 2)
        m1, legs1 = _split_market(
            1, "cond-1", (0.485, None, 0.98), (0.515, 0.02, None), commence
        )
        m2, legs2 = _split_market(
            2, "cond-2", (0.075, None, 0.15), (0.925, 0.85, None), commence
        )
        journal = []
        beat = _Population([m1, m2], legs1 + legs2)
        session = _Session([beat, beat], journal=journal)
        # The venue answers for both events, under the bare condition id Gamma
        # uses. The poll's lookup is keyed on that bare id, so it matches neither
        # `_yes` nor `_no` leg: the production shape.
        poly = _PolyService(
            {
                f"poly-evt-{i}": {
                    "markets": [
                        {
                            "conditionId": f"cond-{i}",
                            "outcomePrices": '["0.62", "0.38"]',
                            "outcomes": '["Yes", "No"]',
                            "lastTradePrice": 0.62,
                            "bestBid": 0.61,
                            "bestAsk": 0.63,
                        }
                    ]
                }
                for i in (1, 2)
            },
            journal,
        )

        pins: list[dict] = []
        real_execute = session.execute

        async def _recording_execute(stmt, params=None):
            if "pregame_mark" in str(stmt) and params:
                pins.append(params)
            return await real_execute(stmt, params)

        session.execute = _recording_execute
        stats = await _run(monkeypatch, session, poly=poly)

        # Precondition: the poll read neither market's legs, so the stored rows
        # are the only evidence, as they were at 00:18:43Z.
        assert stats["outcomes_updated"] == 0
        assert float(legs1[0].current_probability) == 0.485

        assert [p["id"] for p in pins] == [2], f"pins written: {pins}"
        assert '"20": 0.075' in pins[0]["mark"]
        assert '"21": 0.925' in pins[0]["mark"]
        assert stats["pregame_marks_written"] == 1
        assert stats["pregame_mark_empty_book_legs_refused"] == 2

    def test_the_writer_imports_both_predicates_rather_than_restating_them(self):
        import inspect

        src = inspect.getsource(pmm._pregame_pin_outcome_probs)
        assert "is_empty_book_midpoint(" in src
        assert "is_bidless_empty_book_midpoint(" in src
        assert "_pin_book_key(" in src
