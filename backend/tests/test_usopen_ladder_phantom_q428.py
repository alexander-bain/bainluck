"""Q428 — the US Open bracket grid must not print a price nobody will trade at.

═══ WHAT A USER SAW ═══

On 2026-08-28 the live ``GET /api/tournaments/us-open`` payload carried 27
monotonicity violations (17 men's, 10 women's) and every one of them rendered.
The loudest:

    Novak Djokovic   P(reach R16) = 0.710   P(reach QF) = 0.790

which says he is likelier to reach the quarter-final than the round of 16 he
must win to get there. The grid census ruling is explicit that this is a failed
critical eval.

═══ WHY IT WAS NOT A MATCHING BUG (Alex's triage ruling, 2026-08-28) ═══

Alex's instruction was to classify by LIQUIDITY first and to escalate any
violation on a reasonably liquid market as a suspected wrong-future defect,
"I strongly suspect that any market involving alcaraz or djokovic is reasonably
liquid". Measured against Gamma, that premise does not hold for this instrument
— liquidity attaches to the QUESTION, not to the player:

    Will Djokovic WIN the US Open?          lifetime $891,832   24h $18,685   spread 0.006
    Will Djokovic reach the ROUND OF 16?    lifetime $      5   24h $     0   spread 0.910

The whole 336-market round-advancement ladder turns over $6,804 in 24 hours
against the title fields' $271,350, and 264 of its 328 live markets had no
trade at all in 24 hours. Every one of the 27 violations sits on that dead
corner; none sits on a liquid market. Both markets above are correctly named
and correctly linked — the questions were verified verbatim in the DB — so
there is no wrong-future here to find.

═══ THE DEFECT THIS FILE PINS ═══

``_resolve_market_probability_with_source`` already declines a midpoint
manufactured from an untradeable book (#1578). It then grants one exception:

    Trade evidence beats a wide book ... somebody actually transacted there,
    so it is a belief even when the current quotes are garbage.

That reasoning is sound and the exception has no bound on it. "Somebody
transacted" is a claim about the PRESENT, and ``lastTradePrice`` carries no
time. On Djokovic's R16 market it was one $5 trade against a book now quoted
7c bid / 98c ask, and we published it as 71%.

The fix does not add a threshold. It makes the exception check the claim it
already rests on, using Gamma's own 24-hour window: a trade beats a wide book
when the market is still being traded. That preserves gotcha #19's case by
construction — a live blowout is being traded, which is why its book cleared —
and removes the dead-market case, which is the entire ladder.
"""

import pytest

from app.tasks.polymarket import _resolve_market_probability


def _market(**kwargs):
    """A PolymarketMarket with sensible defaults, overridden by kwargs."""
    from app.services.polymarket_api import PolymarketMarket

    defaults = {
        "condition_id": "0xtest",
        "question": "Test?",
        "outcomes": ["Yes", "No"],
        "outcome_prices": [],
        "best_bid": None,
        "best_ask": None,
        "last_trade_price": None,
        "volume_24h": None,
    }
    defaults.update(kwargs)
    return PolymarketMarket(**defaults)


class TestTheProductionSpecimens:
    """Verbatim Gamma reads, 2026-08-28 21:2x UTC."""

    def test_djokovic_reach_r16_is_declined(self):
        """conditionId 0xf5bc6a21…dccc0b. $5 lifetime volume, no trade in 24h.

        This is the cell that printed 0.710 above a 0.790 quarter-final.
        """
        m = _market(
            question="Will Novak Djokovic advance to the Round of 16 in "
                     "Men's Singles at the 2026 US Open?",
            outcome_prices=[0.525, 0.475],
            best_bid=0.07,
            best_ask=0.98,
            last_trade_price=0.71,
            volume=5.0,
            volume_24h=None,
        )
        assert _resolve_market_probability(m) is None

    def test_auger_aliassime_reach_r16_is_declined(self):
        """0xbdab8c0b…3fadb. Book 0.01/0.98, $7 of resting depth."""
        m = _market(
            outcome_prices=[0.495, 0.505],
            best_bid=0.01,
            best_ask=0.98,
            last_trade_price=0.58,
            volume_24h=None,
        )
        assert _resolve_market_probability(m) is None

    def test_de_minaur_reach_r16_is_declined(self):
        """0x…, book 0.27/0.98, $20 lifetime, no trade in 24h."""
        m = _market(
            outcome_prices=[0.625, 0.375],
            best_bid=0.27,
            best_ask=0.98,
            last_trade_price=0.26,
            volume_24h=None,
        )
        assert _resolve_market_probability(m) is None

    def test_djokovic_reach_qf_still_prices_because_it_is_still_traded(self):
        """0x234cfdf2…c8910. $321 traded in the last 24 hours.

        THE OTHER DIRECTION, and it is the sharp edge (gotcha #43). This book is
        just as wide (0.49/0.79) and the price is just as much a last trade, but
        somebody is transacting there NOW. The rule is about currency, not about
        width — width is already judged upstream — so this one survives.
        """
        m = _market(
            outcome_prices=[0.64, 0.36],
            best_bid=0.49,
            best_ask=0.79,
            last_trade_price=0.79,
            volume_24h=321.187332,
        )
        assert _resolve_market_probability(m) == pytest.approx(0.79)

    def test_a_zero_24h_volume_is_the_same_as_none(self):
        """Gamma reports both for an untraded market; neither is evidence."""
        m = _market(
            outcome_prices=[0.50, 0.50],
            best_bid=0.01,
            best_ask=0.99,
            last_trade_price=0.17,
            volume_24h=0.0,
        )
        assert _resolve_market_probability(m) is None


class TestTheBlowoutCaseSurvives:
    """gotcha #19 is the reason the escape hatch exists. It must keep working.

    "Polymarket midpoint can be stale in blowouts — wide spread ->
    lastTradePrice". A blowout is a market that has run away DURING active
    trading: the book clears because everyone is on one side, not because
    nobody is there. So it carries 24-hour volume by construction, and the
    recency test cannot reach it. These specimens make that structural claim
    a behavioural one.
    """

    def test_live_game_blowout_keeps_its_trade_price(self):
        m = _market(
            outcome_prices=[0.50, 0.50],
            best_bid=0.01,
            best_ask=0.99,
            last_trade_price=0.97,
            volume_24h=48_000.0,
        )
        assert _resolve_market_probability(m) == pytest.approx(0.97)

    def test_thinly_but_currently_traded_still_counts(self):
        """No dollar floor. One cent of turnover today beats none.

        A floor would be a knob, and the measured distribution gives no place to
        put one: 24-hour volume on this population runs continuously from $0 to
        $1,900 with no empty band. The test is presence, which is not tunable.
        """
        m = _market(
            outcome_prices=[0.48, 0.52],
            best_bid=0.02,
            best_ask=0.94,
            last_trade_price=0.06,
            volume_24h=0.01,
        )
        assert _resolve_market_probability(m) == pytest.approx(0.06)


class TestNothingElseMoves:
    """The recency test may only ever reach the wide-book last-trade branch."""

    def test_tight_book_never_consults_volume(self):
        """The Fed ladder, bid 0.55 / ask 0.57, and no 24h volume field at all."""
        m = _market(outcome_prices=[0.56, 0.44], best_bid=0.55, best_ask=0.57,
                    volume_24h=None)
        assert _resolve_market_probability(m) == pytest.approx(0.56)

    def test_model_priced_row_with_no_book_is_untouched(self):
        """DataGolf / odds_api rows carry no book, so no branch here applies."""
        m = _market(outcome_prices=[0.12, 0.88], last_trade_price=0.12,
                    volume_24h=None)
        assert _resolve_market_probability(m) == pytest.approx(0.12)

    def test_wide_book_price_that_is_not_the_midpoint_is_still_kept(self):
        """#151's ask-only case. It never enters the fabricated-midpoint branch,
        so the recency test must not touch it even with no 24h volume."""
        m = _market(outcome_prices=[0.20, 0.80], best_bid=0.01, best_ask=0.99,
                    last_trade_price=0.20, volume_24h=None)
        assert _resolve_market_probability(m) == pytest.approx(0.20)

    def test_real_edge_bucket_survives(self):
        m = _market(outcome_prices=[0.015, 0.985], best_bid=0.01, best_ask=0.02,
                    volume_24h=None)
        assert _resolve_market_probability(m) == pytest.approx(0.015)


# ═══════════════════════════════════════════════════════════════════════════
# Q428 fix 3 — the eval must not call a time gap a market disagreement
# ═══════════════════════════════════════════════════════════════════════════

from app.utils.tournament_grid import (  # noqa: E402
    CELL_DARK,
    CELL_LIVE,
    CELL_SETTLED,
    CELL_STALE,
    evaluate_monotonicity,
)


class TestAStaleCellIsNotAMarketDisagreement:
    """5 of the 27 violations compared two different MOMENTS, not two prices.

    Measured on the 2026-08-28 payload, by cell state and capture age:

        Alex de Minaur     R16 -> QF   live(0.17h) / dark(75.05h)
        Casper Ruud        R16 -> QF   live(0.17h) / dark(75.05h)
        Valentin Vacherot  QF  -> SF   dark(75.05h) / live(0.17h)
        Darwin Blanch      R16 -> QF   dark(75.05h) / live(0.17h)
        Joao Fonseca       SF  -> F    dark(72.97h) / dark(75.05h)

    P(reach QF) measured now cannot be checked against P(reach R16) measured
    three days ago; the ordering between them carries no information about
    either market. The grid ALREADY has the vocabulary for this — every cell
    states ``live`` / ``stale`` / ``dark`` and only a ``live`` cell may wear
    ``probability_is_live`` — so using it here is consistency with the surface's
    own contract rather than a new rule, and it needs no constant.

    This is not hiding the number: the cell still renders, still carries its age
    and its ``dark`` state, and still counts in ``counts``. What stops is the
    page ASSERTING that two markets disagree when it has only observed them at
    different times.
    """

    COLUMNS = [{"key": k, "short_label": k} for k in ("R16", "QF", "SF", "F")]

    def _row(self, **states):
        cells = {}
        for key, (prob, state) in states.items():
            cells[key] = {"probability": prob, "state": state}
        return [{"entity_key": "x", "display_name": "X", "cells": cells}]

    def test_de_minaur_live_r16_against_a_three_day_old_qf_is_not_reported(self):
        rows = self._row(R16=(0.26, CELL_LIVE), QF=(0.305, CELL_DARK))
        assert evaluate_monotonicity(self.COLUMNS, rows) == []

    def test_blanch_dark_r16_against_a_live_qf_is_not_reported(self):
        """Either side being old is enough; the gap has no direction."""
        rows = self._row(R16=(0.06, CELL_DARK), QF=(0.07, CELL_LIVE))
        assert evaluate_monotonicity(self.COLUMNS, rows) == []

    def test_fonseca_two_dark_cells_are_not_reported(self):
        rows = self._row(SF=(0.02, CELL_DARK), F=(0.05, CELL_DARK))
        assert evaluate_monotonicity(self.COLUMNS, rows) == []

    def test_a_stale_cell_counts_the_same_as_a_dark_one(self):
        rows = self._row(SF=(0.02, CELL_STALE), F=(0.05, CELL_LIVE))
        assert evaluate_monotonicity(self.COLUMNS, rows) == []


class TestTheEvalStillFiresOnEverythingElse:
    """gotcha #43 — suppression is the sharp edge. Assert BOTH directions."""

    COLUMNS = [{"key": k, "short_label": k} for k in ("R16", "QF", "SF", "F")]

    def _row(self, **states):
        cells = {k: {"probability": p, "state": s} for k, (p, s) in states.items()}
        return [{"entity_key": "x", "display_name": "X", "cells": cells}]

    def test_djokovic_live_against_live_is_still_a_violation(self):
        """The headline cell. Both sides fresh at 0.17h — a real failed eval,
        and it must keep being reported until the price behind it is fixed."""
        rows = self._row(R16=(0.71, CELL_LIVE), QF=(0.79, CELL_LIVE))
        [v] = evaluate_monotonicity(self.COLUMNS, rows)
        assert (v["earlier"], v["later"]) == ("R16", "QF")

    def test_a_settled_cell_is_still_compared(self):
        """``settled`` is not a freshness word — it is a terminal fact, and it
        is exactly the case where an ordering error would be worst."""
        rows = self._row(SF=(0.40, CELL_LIVE), F=(1.0, CELL_SETTLED))
        assert len(evaluate_monotonicity(self.COLUMNS, rows)) == 1

    def test_a_cell_with_no_state_at_all_is_still_compared(self):
        """Pure-logic callers pass bare probabilities. Silently skipping a cell
        that never claimed to be stale would turn this eval off for them."""
        rows = [{"entity_key": "x", "display_name": "X",
                 "cells": {"SF": {"probability": 0.04}, "F": {"probability": 0.05}}}]
        assert len(evaluate_monotonicity(self.COLUMNS, rows)) == 1

    def test_a_stale_cell_does_not_bridge_two_live_ones(self):
        """A skipped cell must not make its neighbours adjacent — that would
        compare R16 against SF and invent a violation, the mirror of the bug
        ``test_an_unpriced_cell_does_not_bridge_two_that_are`` already guards."""
        rows = self._row(R16=(0.70, CELL_LIVE), QF=(0.99, CELL_DARK),
                         SF=(0.30, CELL_LIVE))
        assert evaluate_monotonicity(self.COLUMNS, rows) == []
