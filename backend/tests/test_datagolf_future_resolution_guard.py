"""#1076: future-dated DataGolf markets must never be marked status='resolved'.

DataGolf's schedule STATUS string is unreliable (the poll itself notes "schedule
DATES are reliable even though the schedule STATUS string is not"). A bad
"completed" flag — or a colliding event_id prefix — marked The Open + NV5
pre-tournament markets resolved days BEFORE tee-off (resolution_date 2026-07-19 /
-07-26), dropping the DataGolf model from the live field/blend.

The class fix: (1) every resolution path guards on resolution_date so a market
dated to end in the future is skipped, and (2) a self-healing restore flips any
already-prematurely-resolved future-dated market back to 'open' on the next poll.

These are DB-mutating Core/ORM updates inside large async poll functions, so we
guard the invariant structurally (the repo's established idiom — see
test_datagolf_recovery.py) rather than standing up a full live-poll harness.
"""

import importlib
import inspect

datagolf = importlib.import_module("app.tasks.datagolf")


def _src(fn_name: str) -> str:
    return inspect.getsource(getattr(datagolf, fn_name))


class TestSelfHealingRestore:
    def test_restore_flips_future_dated_resolved_back_to_open(self):
        src = _src("_poll_datagolf_markets")
        # Restore query: source=datagolf, status=resolved, resolution_date in future -> open
        assert 'FuturesMarket.status == "resolved"' in src
        assert "FuturesMarket.resolution_date > restore_now" in src
        assert '.values(status="open")' in src
        assert "markets_restored" in src

    def test_restore_references_issue(self):
        assert "#1076" in _src("_poll_datagolf_markets")


class TestPreTournamentResolutionGuard:
    def test_completed_event_resolution_excludes_future_dated(self):
        src = _src("_poll_datagolf_markets")
        # The completed-event resolve must carry the not-future predicate.
        assert "FuturesMarket.resolution_date <= resolve_now" in src
        assert "FuturesMarket.resolution_date.is_(None)" in src


class TestLiveResolutionGuards:
    def test_no_inplay_stale_resolution_excludes_future_dated(self):
        src = _src("_poll_datagolf_live")
        assert "FuturesMarket.resolution_date <= resolve_now" in src

    def test_inplay_completion_skips_future_dated_markets(self):
        src = _src("_poll_datagolf_live")
        # The all-win-probs-0/1 completion path must skip future-dated markets.
        assert "market.resolution_date > now" in src
        assert "skipped_future" in src
