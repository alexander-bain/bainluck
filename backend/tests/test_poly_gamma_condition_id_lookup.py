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
pmo = import_module("app.utils.pm_market_ownership")


def _src() -> str:
    return inspect.getsource(backfill_winners._backfill_polymarket_winners_from_api)


class _Row:
    """The two attributes the routing reads off a candidate market row."""

    def __init__(self, external_id, poly_event_id=None):
        self.external_id = external_id
        self.poly_event_id = poly_event_id


class TestTheRoutingItself:
    """CAL-P066 / INT-080 — these drive the real function instead of grepping it.

    The four tests here used to be ``assert "<literal expression>" in src``. One
    of them asserted on ``len(by_condition) - len(_addressable)``; CAL-P065
    rewrote that count as ``len(_handed)`` over the complementary partition of
    the same list — the identical number, by construction rather than by
    subtraction — and the test failed a merge wave over a refactor that changed
    no behaviour at all.

    That is the self-concealing shape #1791 / C-SA-1 catalogues, and it fails in
    BOTH directions: it can also pass through the exact change it exists to
    catch, because a substring surviving says nothing about whether the code
    around it still runs. Ask of any grep-test what it would do if the behaviour
    moved and the strings did not. These assert on the split and the counts.
    """

    def test_condition_ids_are_not_spent_on_the_gamma_by_id_endpoint(self):
        """0x… ids answer 422 there; they must never reach the batch loop."""
        rows = [_Row("0xabc"), _Row("12345"), _Row("0xdef")]
        routing = pmo.split_gamma_by_id_candidates(rows)

        assert [r.external_id for r in routing.addressable] == ["12345"]
        assert [r.external_id for r in routing.handed] == ["0xabc", "0xdef"]

    def test_unsupported_lookups_are_counted_separately_from_rate_limits(self):
        """The bug was diagnostic as much as functional: a structural failure
        that reports as throttling sends the next operator to the wrong problem.

        The separation is structural, not a second counter that happens to be
        incremented elsewhere: ``rate_limited`` is only ever written from a
        batch result, and a handed row is never in a batch. An all-0x candidate
        list must therefore produce a full ``unsupported_lookup`` and an EMPTY
        addressable set — nothing to batch, so nothing that can 429 and nothing
        that can trip the >=80% throttle circuit-breaker.
        """
        rows = [_Row(f"0x{i:04x}") for i in range(25)]
        routing = pmo.split_gamma_by_id_candidates(rows)

        assert routing.unsupported_lookup == 25
        assert routing.addressable == (), (
            "a structural 422 cohort that still reaches the batch loop is "
            "exactly how CAL-P003's burn reported itself as 'Gamma throttling'"
        )

    def test_the_partition_is_exhaustive_and_disjoint(self):
        """The property that makes the two ways of counting the same number.

        ``len(handed)`` (what the code reports) and ``len(rows) -
        len(addressable)`` (what the old test asserted the source text said) can
        only disagree if a row is dropped or double-counted.
        """
        rows = [_Row("0xabc"), _Row("12345"), _Row(""), _Row(None), _Row("0xdef")]
        routing = pmo.split_gamma_by_id_candidates(rows)

        assert len(routing.handed) == len(rows) - len(routing.addressable)
        recovered = {id(r) for r in routing.addressable} | {
            id(r) for r in routing.handed
        }
        assert recovered == {id(r) for r in rows}
        assert not ({id(r) for r in routing.addressable} & {id(r) for r in routing.handed})

    def test_an_unidentifiable_row_stays_addressable_rather_than_orphaned(self):
        """A blank external_id is a miss, not a mis-address.

        Routing it into the handoff would give it no owner, and an orphaned
        handoff is a ``failed`` terminal — turning an ordinary ``api_miss`` into
        a red rail. Pinned because the registry classifies blanks as
        ``SHAPE_UNRECOGNISED``, so this is one deliberate step away from what
        ``market_shape`` alone would do.
        """
        routing = pmo.split_gamma_by_id_candidates([_Row(""), _Row(None)])

        assert len(routing.addressable) == 2
        assert routing.handed == ()
        assert routing.handoff.as_payload()["orphaned"] is False

    def test_the_handoff_names_its_owner_from_the_registry(self):
        """``counted here, owned there`` is only checkable if 'there' is named."""
        routing = pmo.split_gamma_by_id_candidates([_Row("0xabc")])

        assert routing.handoff.to == pmo.RAIL_CLOB
        assert routing.handoff.to == pmo.owner_of_shape(pmo.SHAPE_CONDITION_ID)
        assert routing.handoff.count == 1

    def test_an_empty_handoff_is_not_an_orphan(self):
        """Zero handed rows must not report an owner-less handoff — that would
        make every clean run read ``failed``."""
        routing = pmo.split_gamma_by_id_candidates([_Row("12345")])

        assert routing.handoff.count == 0
        assert routing.handoff.as_payload()["orphaned"] is False
        terminal, _reason = pmo.gamma_terminal(
            markets_checked=1,
            handed_off=0,
            orphaned=pmo.handoff_payload([routing.handoff])["orphaned"],
        )
        assert terminal == "complete"


def test_the_rail_consumes_the_shared_routing():
    """The half a pure-function test cannot see: that the task calls it.

    Kept as a source assertion ON PURPOSE and scoped to the call, not to the
    arithmetic — an import-and-call is a fact about wiring, which is what greps
    are actually good for. The behaviour lives in the tests above.
    """
    src = _src()
    assert "split_gamma_by_id_candidates(by_condition)" in src
    assert "_routing.unsupported_lookup" in src


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
