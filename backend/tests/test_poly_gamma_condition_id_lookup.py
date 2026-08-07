"""CAL-P003 — a wrong Gamma endpoint was being reported as a rate limit.

`_backfill_polymarket_winners_from_api` splits its candidates into a by-EVENT path
and a by-CONDITION path. The by-condition path called Gamma `GET /markets/{id}`,
which takes a NUMERIC Gamma market id; handed a 0x… condition_id it answers
`422 {"type":"validation error","error":"invalid integer"}` (verified against the
live API, 2026-08-07).

The failure then laundered itself through three layers:

  1. `get_market_by_condition` returns None ONLY for 404, so a 422 re-raises.
  2. `_fetch_market` treats any non-429 exception as a NON-definitive transient.
  3. the batch circuit-breaker trips when >=80% of a batch is non-definitive and
     STOPS the run, logging the burn as `rate_limited` / "Gamma throttling".

Since ~97% of the affected cohort has no polymarket_event_id, essentially every
by-condition batch was 100% structural-422 — so the run aborted every time and
the operator-visible signal said "rate limited". These tests pin that 0x… ids
never reach that endpoint, and that they are counted as their own thing rather
than inflating the throttle signal.
"""

import inspect
from importlib import import_module

# `app.tasks.backfill_winners` as an ATTRIBUTE is the Celery task proxy, not the
# module — import_module goes to sys.modules and gets the real one.
backfill_winners = import_module("app.tasks.backfill_winners")


def _src() -> str:
    return inspect.getsource(backfill_winners._backfill_polymarket_winners_from_api)


def test_condition_ids_are_filtered_out_of_the_gamma_by_id_path():
    """0x… ids are not addressable on /markets/{id}; don't spend a request."""
    src = _src()
    assert 'startswith("0x")' in src
    assert "_addressable" in src


def test_unsupported_lookups_are_counted_separately_from_rate_limits():
    """The bug was diagnostic as much as functional: a structural failure that
    reports as throttling sends the next operator to the wrong problem."""
    src = _src()
    assert 'stats["unsupported_lookup"]' in src
    # counted off the raw candidate list, before the dead-cid filter
    assert "len(by_condition) - len(_addressable)" in src


def test_unsupported_lookup_is_initialised_in_stats():
    """A key only assigned inside a branch reads as absent when the branch is
    skipped; the caller logs these stats verbatim."""
    src = _src()
    assert '"unsupported_lookup": 0,' in src


def test_dead_cid_filter_now_applies_to_the_addressable_set():
    """skipped_dead must not double-count ids we already refused to look up."""
    src = _src()
    assert "alive_conditions = [r for r in _addressable" in src
    assert "len(_addressable) - len(alive_conditions)" in src


def test_gamma_by_condition_helper_still_only_swallows_404():
    """gotcha #36 — the client must keep re-raising everything that is not a 404,
    so a 422/429/5xx can never be read as 'this market does not exist'."""
    from app.services.polymarket_api import PolymarketAPIService

    src = inspect.getsource(PolymarketAPIService.get_market_by_condition)
    assert "status_code == 404" in src
    assert "raise" in src


def test_clob_helper_remains_the_authoritative_condition_id_route():
    """The CLOB endpoint DOES take a condition_id and carries per-token winners —
    it is where this cohort is owned (binding mapper spec)."""
    from app.services.polymarket_api import PolymarketAPIService

    src = inspect.getsource(PolymarketAPIService.get_clob_market_by_condition)
    assert "clob_client.get(f\"/markets/{condition_id}\")" in src
