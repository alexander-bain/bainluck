"""CAL-P049 (#1818): the Kalshi settlement-status sync, and the revert loop it ends.

The defect was not that a market failed to flip once. It was that the poll UPSERTs
``futures_markets.status`` on EVERY cycle from a vocabulary that had gone stale, so
each repair the settled-events backfill made was overwritten ~2 hours later. These
tests pin the vocabulary against the live measurement, and pin BOTH directions of
the derived status — an all-settled event resolves, and a part-settled event does
NOT — because a one-directional guard is what let the previous tuple pass review.
"""

import inspect

import pytest

from app.utils.kalshi_market_status import (
    RESULT_CARRYING_STATUSES,
    TERMINAL_STATUSES,
    all_terminal,
    has_declared_result,
    is_terminal,
)


class TestMeasuredVocabulary:
    """The sets must match what Kalshi actually returns (probed 2026-08-13)."""

    def test_result_carrying_is_exactly_determined_and_finalized(self):
        # Measured over ~2,000 nested markets: these two, and ONLY these two,
        # ever carry a ``result``. See scripts/probe_kalshi_market_status.py.
        assert RESULT_CARRYING_STATUSES == frozenset({"determined", "finalized"})

    def test_finalized_is_terminal(self):
        # The exact miss that caused #1818: the poll's tuple omitted it.
        assert is_terminal("finalized")

    def test_determined_is_terminal(self):
        # The near-miss the three sibling modules ALSO had.
        assert is_terminal("determined")

    def test_active_and_inactive_are_not_terminal(self):
        assert not is_terminal("active")
        assert not is_terminal("inactive")

    def test_closed_is_terminal_but_carries_no_result(self):
        # Deliberate asymmetry, documented in the module: ``closed`` stays in the
        # terminal set (removing it would flip all-closed events back to 'open'
        # and re-create the churn) but must never be read as a declared result.
        assert is_terminal("closed")
        assert not has_declared_result("closed")

    def test_none_and_empty_are_never_terminal(self):
        assert not is_terminal(None)
        assert not is_terminal("")
        assert not has_declared_result(None)

    def test_result_carrying_is_a_subset_of_terminal(self):
        assert RESULT_CARRYING_STATUSES <= TERMINAL_STATUSES


class TestAllTerminal:
    """Both directions. A cap/guard test that only proves one is not a guard."""

    def test_all_finalized_is_terminal(self):
        assert all_terminal(["finalized"] * 68)

    def test_mixed_finalized_and_determined_is_terminal(self):
        assert all_terminal(["finalized", "determined", "finalized"])

    def test_one_active_market_defeats_the_whole_event(self):
        # A part-settled event has NOT settled — the golf-major shape, where one
        # withdrawn player's leg lingers while the field finalizes.
        assert not all_terminal(["finalized"] * 149 + ["active"])

    def test_empty_is_not_terminal(self):
        # gotcha #53: an event with no markets is unknown, not settled. An empty
        # 200 is a response shape, and inferring settlement from it invents a fact.
        assert not all_terminal([])

    def test_unknown_future_status_defeats_the_event(self):
        # Fail closed on a value Kalshi adds later, rather than guessing.
        assert not all_terminal(["finalized", "some_new_kalshi_status"])


def _code_only(src: str) -> str:
    """Strip whole-line comments.

    #1818's acceptance requires the root cause NAMED in a comment at the fix
    site, and that comment necessarily quotes the stale tuple. So the guard has
    to read code, not prose — otherwise the fix's own explanation trips it.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


class TestPollUsesTheMeasuredSet:
    """The poll's derived status is the write that reverted everything."""

    def test_poll_no_longer_hardcodes_the_stale_tuple(self):
        from app.tasks import kalshi

        src = _code_only(inspect.getsource(kalshi._poll_kalshi_markets))
        assert '("closed", "settled")' not in src, (
            "the poll is back on the stale tuple; ``settled`` is not a Kalshi "
            "market status and ``closed`` carries no result, so this predicate "
            "rewrites finalized events to 'open' on every cycle (#1818)"
        )
        assert "all_terminal(" in src

    def test_poll_derives_resolved_only_from_all_terminal(self):
        from app.tasks import kalshi

        src = inspect.getsource(kalshi._poll_kalshi_markets)
        assert 'market_status = "resolved" if all_settled else "open"' in src
        assert "all_settled = all_terminal(" in src

    def test_ws_lifecycle_writer_uses_the_measured_set(self):
        # kalshi_ws.handle_lifecycle also writes status='resolved', so it is the
        # same class of writer and must not keep a private copy of the vocabulary.
        from app.tasks import kalshi_ws

        src = _code_only(inspect.getsource(kalshi_ws))
        assert '("closed", "settled", "finalized")' not in src
        assert "is_terminal(status)" in src

    def test_ws_shadow_uses_the_measured_set(self):
        from app.services import ws_shadow

        assert ws_shadow._SETTLED_STATUSES is TERMINAL_STATUSES


class TestRepairClassification:
    """The write half fails closed on every shape that is not a settlement."""

    @staticmethod
    def _classify(event):
        from scripts.repair_kalshi_settlement_status import _classify

        return _classify(event)

    def test_all_finalized_with_results_is_settled(self):
        event = {
            "markets": [
                {"status": "finalized", "result": "yes"},
                {"status": "finalized", "result": "no"},
            ]
        }
        verdict, detail = self._classify(event)
        assert verdict == "settled"
        assert detail["with_result"] == 2

    def test_none_is_unknown_not_absent(self):
        # gotcha #36: get_event returns None for a 404 AND for a swallowed
        # transport error, so None can never be read as "this market is gone".
        verdict, _ = self._classify(None)
        assert verdict == "unknown"

    def test_zero_markets_is_its_own_verdict(self):
        # gotcha #53 again: an empty 200 is retention or nothing-to-report, and
        # it must never fall through to "not settled" or to "settled".
        verdict, _ = self._classify({"markets": []})
        assert verdict == "no_markets"

    def test_any_active_leg_blocks_the_flip(self):
        event = {
            "markets": [
                {"status": "finalized", "result": "yes"},
                {"status": "active", "result": ""},
            ]
        }
        verdict, detail = self._classify(event)
        assert verdict == "not_settled"
        assert detail["non_terminal_statuses"] == ["active"]

    def test_all_closed_with_no_result_is_not_a_settlement(self):
        # Terminal is not declared. ``closed`` markets have no result, so there
        # is nothing for the venue-authority repair to adopt.
        event = {"markets": [{"status": "closed", "result": ""}] * 3}
        verdict, detail = self._classify(event)
        assert verdict == "not_settled"
        assert "none carries a result" in detail["reason"]

    def test_determined_without_finalized_still_settles(self):
        event = {"markets": [{"status": "determined", "result": "no"}]}
        verdict, _ = self._classify(event)
        assert verdict == "settled"


class TestRepairIsAttendedAndCapped:
    def test_cap_is_a_module_constant_not_a_parameter(self):
        from scripts import repair_kalshi_settlement_status as mod

        assert isinstance(mod.APPLY_MARKET_CAP, int)
        assert 0 < mod.APPLY_MARKET_CAP <= 200
        params = inspect.signature(mod.repair).parameters
        assert "apply" in params and params["apply"].default is False
        # The cap must not be reachable through the rail's query params.
        assert "cap" not in params and "apply_market_cap" not in params

    def test_limit_cannot_exceed_the_cap(self):
        from scripts.repair_kalshi_settlement_status import APPLY_MARKET_CAP, repair

        src = inspect.getsource(repair)
        assert "min(int(limit or APPLY_MARKET_CAP), APPLY_MARKET_CAP)" in src
        assert APPLY_MARKET_CAP > 0

    def test_registered_on_the_repair_rail(self):
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["kalshi-settlement-status"] == (
            "scripts.repair_kalshi_settlement_status",
            "repair",
        )

    def test_not_wired_to_a_beat(self):
        # ATTENDED ONLY. A stored-value repair on venue state must never run
        # unsupervised, and the beat allowlist is where that would leak in.
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule or {}
        wired = [
            name
            for name, entry in schedule.items()
            if "repair_kalshi_settlement_status" in str(entry.get("task", ""))
        ]
        assert wired == []

    def test_partial_page_is_not_reported_as_exhausted(self):
        # The zero-yield/short-page trap (gotcha #53's cousin): stopping on the
        # time budget must never read as "there was nothing left to do".
        from scripts.repair_kalshi_settlement_status import repair

        src = inspect.getsource(repair)
        assert '"exhausted": (not timed_out) and len(rows) < window' in src
        assert '"stopped_on_time_budget": timed_out' in src


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["finalized"], True),
        (["determined"], True),
        (["closed"], True),
        (["active"], False),
        (["inactive"], False),
        (["finalized", "inactive"], False),
    ],
)
def test_all_terminal_table(statuses, expected):
    assert all_terminal(statuses) is expected
