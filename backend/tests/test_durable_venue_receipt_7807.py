"""#7807 acceptance — the durable-serve receipt, and the four things it may not say.

PILLAR: TRUTH. SHIP: a recovered venue history remains available to the next
reader after the fast cache loses it.

WHAT THIS FILE IS FOR. The receipt exists because a durable serve erases its own
evidence — it rehydrates Redis, so the next read says `cache`, and the payload is
identical either way. That makes the line the only record that the fallback ever
paid, which means a WRONG line is worse than no line: an acceptance step that
reads `success` believes it. So every negative arm below is a case that must
never set `success`, and each is written as the real block `describe` would
build, not as a hand-made dict that happens to have the right keys.

The positive control is first and is deliberately the SAME block shape as the
negatives: if the guards were written to refuse everything, it fails.

The real-fallback end of this — the receipt firing after a genuine Redis
eviction, on real Postgres and real Redis, and agreeing with the payload the
reader got — is `tests/integration/test_generic_market_history_7351_real_pg_redis
.py::test_B14b`. Nothing here can prove that; a dict is not a fallback.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.utils.durable_venue_receipt import (
    RECEIPT_MARKER,
    durable_serve_receipt,
    log_durable_venue_serve,
)


def _block(**over):
    """The metadata block `_GenericVenueHistory.describe` returns, warm + durable.

    Keys and value shapes copied from `describe` itself, so a change to that
    block's vocabulary breaks these tests rather than sliding past them.
    """
    block = {
        "state": "warm",
        "tier": "durable",
        "points_served": 37,
        "outcomes_served": 2,
        "observed_from": "2026-09-19T08:01:00+00:00",
        "observed_through": "2026-09-20T03:00:00+00:00",
        "built_at": "2026-09-20T03:42:32+00:00",
        "fill_status": "ok",
        "scale": "raw",
        "unsupported_points_withheld": 0,
        "fill": "not_needed",
    }
    block.update(over)
    return block


def _receipt(block, market_id=59165099, surface="futures_history"):
    return durable_serve_receipt(block, market_id=market_id, surface=surface)


# ── the positive control ────────────────────────────────────────────────────


def test_a_durable_warm_serve_of_real_rows_is_a_success():
    receipt = _receipt(_block())

    assert receipt is not None
    assert receipt["success"] is True
    assert receipt["tier"] == "durable"
    assert receipt["market_id"] == 59165099
    assert receipt["surface"] == "futures_history"


def test_the_receipt_describes_the_block_the_response_carried():
    """Every field is READ OFF the served block — never recomputed, never guessed."""
    block = _block(
        points_served=9, outcomes_served=3, built_at="2026-09-01T00:00:00+00:00",
        fill_status="degraded", unsupported_points_withheld=4,
    )
    receipt = _receipt(block)

    assert receipt["points_served"] == block["points_served"]
    assert receipt["outcomes_served"] == block["outcomes_served"]
    assert receipt["built_at"] == block["built_at"]
    assert receipt["state"] == block["state"]
    assert receipt["fill_status"] == block["fill_status"]
    assert (
        receipt["unsupported_points_withheld"]
        == block["unsupported_points_withheld"]
    )
    # A durable serve that dropped four unsupported points is STILL a durable
    # serve. The withheld count is reported beside the served count so nobody has
    # to infer the drop from a smaller number — it does not veto the success.
    assert receipt["success"] is True


def test_a_durable_serve_names_the_build_that_served_it():
    """The acceptance step needs market + build + bank; this is the build half."""
    receipt = _receipt(_block())

    assert receipt["build"], "a receipt with no build cannot be tied to a release"
    assert isinstance(receipt["build"], str)


# ── the four negatives: none of these may record success ────────────────────


def test_a_warm_cache_writes_no_receipt_at_all():
    """The fast tier answered. There is no fallback here to have a receipt about."""
    assert _receipt(_block(tier="cache")) is None


def test_a_cold_read_writes_no_receipt_at_all():
    """Both tiers missed. `describe` reports `tier: None` — there is no serve."""
    assert _receipt(_block(tier=None, state="cold", points_served=0,
                           outcomes_served=0, built_at=None)) is None


@pytest.mark.parametrize("state", ["cold", "empty", "refused", "unavailable",
                                   "not_applicable"])
def test_only_a_warm_state_can_be_a_success(state):
    """Every non-warm state a durable read can end in, named one by one.

    Parametrized rather than asserted once on `refused`, because the guard is
    `state == "warm"` and a guard written as `state != "refused"` would pass a
    one-case test while calling an EMPTY durable read a success.
    """
    receipt = _receipt(_block(state=state))

    assert receipt is not None, "the durable tier still answered — the line is owed"
    assert receipt["success"] is False


def test_zero_served_rows_is_never_a_success():
    """A bank that produced no chart is a fallback that paid nothing."""
    receipt = _receipt(_block(points_served=0, outcomes_served=0))

    assert receipt is not None
    assert receipt["success"] is False


def test_a_bank_that_never_dated_itself_is_never_a_success():
    """No `built_at` means no bank to name, and naming the bank is the point."""
    receipt = _receipt(_block(built_at=None))

    assert receipt is not None
    assert receipt["success"] is False


def test_a_reader_scale_refusal_is_named_and_is_never_a_success():
    """`describe` rewrites the state AND appends the refusal; both are read."""
    receipt = _receipt(_block(
        state="refused",
        refusals=[{"scope": "reader", "reason": "devigged capture scale"}],
    ))

    assert receipt["success"] is False
    assert receipt["scale_refused"] == "devigged capture scale"


def test_a_payload_scope_refusal_is_not_read_as_a_reader_refusal():
    """The two scopes are different facts and the receipt keeps them apart.

    A payload-scope refusal already shows up as `state == "refused"`, which is
    what stops the success. Reporting it under `scale_refused` as well would
    claim the READER declined the scale, which it did not.
    """
    receipt = _receipt(_block(
        state="refused",
        refusals=[{"scope": "payload", "reason": "identity mismatch"}],
    ))

    assert receipt["success"] is False
    assert receipt["scale_refused"] is None


def test_a_clean_serve_says_so_rather_than_omitting_the_refusal_field():
    assert _receipt(_block())["scale_refused"] is None


def test_describe_is_what_makes_a_refused_read_report_a_refused_state():
    """The coupling the test above leans on, pinned in the code that owns it.

    `state == "warm"` only excludes a scale-refused response because `describe`
    rewrites the state when the reader refuses. That rewrite lives in a different
    file and nothing else asserts the receipt depends on it, so it is asserted
    here: if it ever stops, THIS test fails, rather than the receipt quietly
    starting to call a refused response a success.
    """
    from app.routes.futures import _GenericVenueHistory

    venue = _GenericVenueHistory()
    venue.state = "warm"
    venue.tier = "durable"
    block = venue.describe([], scale_refused="devigged capture scale")

    assert block["state"] == "refused"
    assert {"scope": "reader", "reason": "devigged capture scale"} in block["refusals"]


def test_a_reader_refusal_vetoes_a_success_on_its_own_and_not_via_the_state():
    """The second lock, and it is deliberately the one `describe` cannot trip.

    The block below — `warm` WITH a reader-scope refusal — is a shape `describe`
    does not currently build, which is exactly why this arm is written: the
    receipt must not be relying on one upstream rewrite to keep the strongest
    thing it can say off a response whose rows the reader declined.
    """
    receipt = _receipt(_block(
        state="warm",
        refusals=[{"scope": "reader", "reason": "devigged capture scale"}],
    ))

    assert receipt["scale_refused"] == "devigged capture scale"
    assert receipt["success"] is False


# ── shape and bounds ────────────────────────────────────────────────────────


def test_the_receipt_carries_no_user_or_session_data():
    """The field set is CLOSED. A receipt is not a place to add things later."""
    assert set(_receipt(_block())) == {
        "market_id", "surface", "tier", "success", "state", "built_at",
        "points_served", "outcomes_served", "scale_refused",
        "unsupported_points_withheld", "fill_status", "build",
    }


def test_a_long_refusal_reason_is_bounded():
    receipt = _receipt(_block(
        state="refused",
        refusals=[{"scope": "reader", "reason": "x" * 5000}],
    ))

    assert len(receipt["scale_refused"]) <= 120


@pytest.mark.parametrize("bad", ["12", -3, None, True, 4.5])
def test_a_count_that_is_not_a_count_reads_as_zero_and_not_as_a_success(bad):
    """Never a string, never a bool dressed as a number, never negative."""
    receipt = _receipt(_block(points_served=bad))

    assert receipt["points_served"] == 0
    assert receipt["success"] is False


def test_a_block_that_is_not_a_block_writes_nothing():
    for junk in (None, [], "warm", 7):
        assert _receipt(junk) is None


# ── the emit half ───────────────────────────────────────────────────────────


def test_the_line_is_written_at_a_level_this_apps_sink_actually_carries(caplog):
    """MEASURED, not stylistic — see the module docstring of the receipt.

    `uvicorn app.main:app` runs with no logging configuration anywhere in the
    app, so the root logger keeps level WARNING and holds no handlers (Sentry
    monkeypatches rather than attaching one). An INFO record is discarded before
    `logging.lastResort` sees it, so an INFO receipt would reach no sink at all
    and the acceptance step would read an empty log as "it never happened".
    """
    with caplog.at_level(logging.DEBUG, logger="app.utils.durable_venue_receipt"):
        log_durable_venue_serve(_block(), market_id=1, surface="futures_history")

    records = [r for r in caplog.records if RECEIPT_MARKER in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno >= logging.WARNING


def test_the_line_is_one_greppable_marker_and_one_json_object(caplog):
    with caplog.at_level(logging.WARNING, logger="app.utils.durable_venue_receipt"):
        written = log_durable_venue_serve(
            _block(), market_id=59165099, surface="futures_history"
        )

    message = caplog.records[0].getMessage()
    marker, _, body = message.partition(" ")
    assert marker == RECEIPT_MARKER
    assert json.loads(body) == written


def test_nothing_is_written_when_the_fast_tier_answered(caplog):
    with caplog.at_level(logging.DEBUG, logger="app.utils.durable_venue_receipt"):
        assert log_durable_venue_serve(
            _block(tier="cache"), market_id=1, surface="futures_history"
        ) is None

    assert not [r for r in caplog.records if RECEIPT_MARKER in r.getMessage()]


def test_a_sink_that_explodes_is_survived_and_returns_nothing(monkeypatch):
    """Instrumentation failure leaves the response identical — including this one.

    The caller ignores the return value; what matters is that nothing propagates
    out of here into a chart response.
    """
    from app.utils import durable_venue_receipt as mod

    class _Dead:
        def warning(self, *a, **k):
            raise RuntimeError("log sink is gone")

        def debug(self, *a, **k):
            raise RuntimeError("so is the fallback")

    monkeypatch.setattr(mod, "logger", _Dead())

    assert log_durable_venue_serve(
        _block(), market_id=1, surface="futures_history"
    ) is None


def test_a_receipt_that_cannot_be_built_is_survived(monkeypatch):
    from app.utils import durable_venue_receipt as mod

    def _boom(*a, **k):
        raise ValueError("no build id today")

    monkeypatch.setattr(mod, "durable_serve_receipt", _boom)

    assert log_durable_venue_serve(
        _block(), market_id=1, surface="futures_history"
    ) is None


# ── the route actually calls it ─────────────────────────────────────────────


def test_the_history_route_emits_the_receipt_from_the_block_it_returns():
    """The one hunk in `routes/futures.py`, asserted as a wiring fact.

    Reads the source rather than the import graph: `log_durable_venue_serve` is
    imported at the top of the module, so a test that only checks the name is
    bound would pass with the call site deleted.
    """
    from pathlib import Path

    import app.routes.futures as futures_route

    source = Path(futures_route.__file__).read_text()
    parts = source.split(log_durable_venue_serve.__name__ + "(", 2)
    assert len(parts) == 2, (
        "expected exactly ONE call site — the bare name also appears on the "
        "import line, which is why the open paren is part of the pattern"
    )
    arguments = parts[1].split(")")[0]
    assert 'response["venue_history"]' in arguments, (
        "the receipt must be handed the block the response carries, so it cannot "
        "describe a different read than the one the reader got"
    )
    assert 'surface="futures_history"' in arguments
