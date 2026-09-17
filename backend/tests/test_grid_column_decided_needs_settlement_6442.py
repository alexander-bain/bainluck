"""A grid column is DECIDED on settlement, never on one extreme price (#6442).

Reader-visible on production 2026-09-15 22:50Z, phone width: `/sport/soccer/ucl`
printed **DECIDED** over the Champions League **QF** column, a `✓` in Barcelona's
cell and `—` in the other **35** — which in a resolved column is the *eliminated*
glyph, not "no data" (`TournamentProgressionTable.tsx:583`). So the page said
Barcelona had clinched a 2026-27 quarter-final and 35 clubs were out of it, in
September, before the league phase had played its second matchday.

The column is market `59693592`, kalshi `KXUCLROUND-27QUAR`: `status='open'`,
`resolution_date` **2027-04-01**, 36 outcomes of which **one** carries a
probability (Barcelona `0.99`), `is_winner` and `resolution_source` NULL on all 36.

Two independent faults met in `_grid_column_resolved`, and each is guarded
separately below so neither can come back alone:

(a) **No coverage floor.** The loop appended only cells that HAD a value, so the
    35 empty rows were skipped rather than counted against the claim, and
    `all()` ran over a one-element list.
(b) **An extreme price read as a settlement.** `p >= 1.0 - eps` is
    `0.99 >= 0.99`, true on the boundary exactly, while the market it came from
    was still trading for another seven months. The class of #5896 / #5771: a
    near-certain price is not a grade.

Measured before the fix on all 14 live grids (2026-09-17 06:26Z): of the 33
columns the fleet serves, this is the ONLY one reading `resolved=true`. The fix
is therefore strictly restrictive in production — it turns exactly one wrong
True into False — and the "genuine decided column" cases below are guarded
synthetically because the fleet has none live to point at.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.playoffs import _grid_column_resolved, _grid_column_still_trading

NOW = datetime(2026, 9, 17, 6, 26, tzinfo=timezone.utc)

#: The real market behind the UCL quarterfinal column, read on production 22:52Z.
UCL_QF_MARKET = SimpleNamespace(
    id=59693592,
    source="kalshi",
    external_id="KXUCLROUND-27QUAR",
    name="Champions League Quarterfinals Qualifiers",
    status="open",
    resolution_date=datetime(2027, 4, 1, tzinfo=timezone.utc),
)


def _entries(market, n=1):
    """A column_data list: ``n`` ``(market, outcome)`` pairs from one market."""
    return [(market, SimpleNamespace(id=i, name=f"club-{i}")) for i in range(n)]


def _ucl_rows(barcelona_prob=0.99, clubs=36):
    """The served shape: one priced club, the rest with no cell at all."""
    rows = [{"cells": {"qf": {"merged_probability": barcelona_prob, "state": "live"}}}]
    rows += [{"cells": {}} for _ in range(clubs - 1)]
    return rows


class TestTheSpecimen:
    def test_one_priced_club_of_36_does_not_decide_the_column(self):
        assert _grid_column_resolved(
            _ucl_rows(), "qf", entries=_entries(UCL_QF_MARKET), now=NOW
        ) is False

    def test_the_coverage_floor_refuses_it_with_the_trading_gate_silent(self):
        # Fault (a) alone. Same 1-of-36 shape, but the market is settled, so
        # nothing but the coverage floor is left to object.
        settled = SimpleNamespace(status="resolved", resolution_date=None)
        assert _grid_column_resolved(
            _ucl_rows(), "qf", entries=_entries(settled), now=NOW
        ) is False

    def test_the_trading_gate_refuses_it_with_the_coverage_floor_silent(self):
        # Fault (b) alone. All 36 clubs priced, every one of them at 0 or 1 —
        # coverage is perfect and every cell is extreme — but the market is
        # open and resolves 2027-04-01, so these are quotes, not grades.
        rows = [{"cells": {"qf": {"merged_probability": 1.0, "state": "live"}}}]
        rows += [{"cells": {"qf": {"merged_probability": 0.0, "state": "live"}}} for _ in range(35)]
        assert _grid_column_resolved(
            rows, "qf", entries=_entries(UCL_QF_MARKET), now=NOW
        ) is False

    def test_barcelona_at_exactly_one_minus_epsilon_is_still_a_quote(self):
        # The boundary is what fired: 0.99 >= 1.0 - 0.01 exactly. Guard the
        # boundary itself so a later eps tweak cannot quietly re-open it.
        rows = [{"cells": {"qf": {"merged_probability": 1.0 - 0.01, "state": "live"}}} for _ in range(36)]
        assert _grid_column_resolved(
            rows, "qf", entries=_entries(UCL_QF_MARKET), now=NOW
        ) is False


class TestGenuineDecidedColumnsSurvive:
    """The fix may only remove wrong Trues — these are the Trues it must keep."""

    def _full(self, n=30, market=None):
        rows = [{"cells": {"mp": {"merged_probability": 1.0, "state": "live"}}} for _ in range(16)]
        rows += [{"cells": {"mp": {"merged_probability": 0.0, "state": "live"}}} for _ in range(n - 16)]
        return rows

    def test_a_resolved_market_with_every_team_decided_resolves(self):
        market = SimpleNamespace(status="resolved", resolution_date=datetime(2026, 6, 1, tzinfo=timezone.utc))
        assert _grid_column_resolved(self._full(), "mp", entries=_entries(market), now=NOW) is True

    def test_a_settled_kalshi_market_still_reading_open_resolves_on_its_past_close(self):
        # Gotcha #33: Kalshi markets that have settled keep `status='open'` in
        # our rows, because the poller only ever sees open markets. Gating on
        # status alone would refuse every genuinely decided Kalshi column; the
        # past `resolution_date` (close_time since CAL-P989) is what carries it.
        stuck = SimpleNamespace(status="open", resolution_date=NOW - timedelta(days=40))
        assert _grid_column_resolved(self._full(), "mp", entries=_entries(stuck), now=NOW) is True

    def test_venue_settled_cells_resolve_even_while_a_market_trades(self):
        # Settlement outranks trading: a graded cell carries its own result, so
        # an open straggler market cannot un-decide it.
        rows = [{"cells": {"mp": {"merged_probability": None, "state": "won"}}} for _ in range(6)]
        rows += [{"cells": {"mp": {"merged_probability": None, "state": "eliminated"}}} for _ in range(24)]
        assert _grid_column_resolved(
            rows, "mp", entries=_entries(UCL_QF_MARKET), now=NOW
        ) is True

    def test_nba_division_shape_at_29_of_30_still_resolves(self):
        # The lowest coverage measured on a full-league column in the fleet
        # (NBA `division`, 29/30 = 0.967). The floor must sit below it.
        rows = self._full(29) + [{"cells": {}}]
        market = SimpleNamespace(status="resolved", resolution_date=None)
        assert _grid_column_resolved(rows, "mp", entries=_entries(market), now=NOW) is True

    def test_coverage_below_the_floor_refuses(self):
        rows = self._full(26) + [{"cells": {}} for _ in range(4)]
        market = SimpleNamespace(status="resolved", resolution_date=None)
        assert _grid_column_resolved(rows, "mp", entries=_entries(market), now=NOW) is False


class TestAbsentIsNotEliminated:
    def test_a_missing_state_cell_refuses_the_column(self):
        # The register's explicit "we have no market for this entity". It is
        # present in `cells` and must count AGAINST the claim, never be skipped.
        rows = [{"cells": {"mp": {"merged_probability": 1.0, "state": "live"}}} for _ in range(29)]
        rows += [{"cells": {"mp": {"merged_probability": None, "state": "missing"}}}]
        market = SimpleNamespace(status="resolved", resolution_date=None)
        assert _grid_column_resolved(rows, "mp", entries=_entries(market), now=NOW) is False

    def test_empty_grid_and_empty_column_stay_unresolved(self):
        assert _grid_column_resolved([], "mp", entries=_entries(UCL_QF_MARKET), now=NOW) is False
        assert _grid_column_resolved(
            [{"cells": {}} for _ in range(36)], "mp", entries=_entries(UCL_QF_MARKET), now=NOW
        ) is False


class TestStillTradingPredicate:
    def test_future_close_on_an_unresolved_market_is_still_trading(self):
        assert _grid_column_still_trading(_entries(UCL_QF_MARKET), now=NOW) is True

    def test_a_resolved_status_is_never_still_trading(self):
        m = SimpleNamespace(status="resolved", resolution_date=datetime(2027, 4, 1, tzinfo=timezone.utc))
        assert _grid_column_still_trading(_entries(m), now=NOW) is False

    def test_a_null_resolution_date_cannot_contradict(self):
        # It is not evidence either way, so it does not veto; the coverage
        # floor and the all-cells-decided test still have to be satisfied.
        m = SimpleNamespace(status="open", resolution_date=None)
        assert _grid_column_still_trading(_entries(m), now=NOW) is False

    def test_a_naive_resolution_date_is_read_as_utc_not_crashed_on(self):
        m = SimpleNamespace(status="open", resolution_date=datetime(2027, 4, 1))
        assert _grid_column_still_trading(_entries(m), now=NOW) is True

    def test_one_open_market_among_many_is_enough_to_veto(self):
        done = SimpleNamespace(status="resolved", resolution_date=None)
        live = UCL_QF_MARKET
        assert _grid_column_still_trading(_entries(done) + _entries(live), now=NOW) is True

    def test_no_entries_is_no_objection(self):
        assert _grid_column_still_trading(None, now=NOW) is False
        assert _grid_column_still_trading([], now=NOW) is False
