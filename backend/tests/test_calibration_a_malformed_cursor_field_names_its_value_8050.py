"""CAL-P1339 (#8050, #6868) — the wipe that erases the value that caused it.

**Measured on production before a line was written.** The rebuild beat ring at
``/api/admin/calibration-beat-gauges``, read 2026-09-22 22:37Z::

    11:29:47Z  resume      resumable                     banked 109 / planned 203
    12:36:50Z  invalidate  population_version_malformed  banked   0 / planned 128
    13:38:01Z  invalidate  population_version_malformed  banked   0 / planned 128
    ...
    22:37:57Z  fresh       nothing_banked                banked   0 / planned 128

One beat discarded 109 banked units and the ~75 refinement children earned
behind them, and every beat since has banked **zero**. ``/api/calibration``
still reads ``generated_at: 2026-09-15T11:16:10Z``.

**The cause could not be named.** By the time anyone read
``durable_state_snapshots`` the ``population_version`` was a well-formed
``'q271'`` again — each beat overwrites the cursor, so the offending value is
gone within the hour. ``classify_field_mismatch`` returns ``malformed`` for a
present-but-non-string-or-empty value, which is three or four quite different
corruptions (an int, an empty string, a nested dict, a bool) with three or four
quite different culprits, and the token cannot tell them apart.

So the token says WHICH FIELD was unusable and never WHAT WAS IN IT, and the
second half is the one that says whether a writer, a migration or a torn write
is the cause. This module pins that the value is read out at the one site where
it still exists.

**What is deliberately NOT here.** No gauge. The token block above
``REASON_POPULATION_VERSION_ABSENT`` fixes cursor-reason cardinality at six
*precisely* so the sampler can bank these by name (``CURSOR_PREFIX``), and
interpolating an observed value would mint a new gauge name per occurrence —
the trap that block was written to refuse. ``test_the_value_is_not_minted_into_a_token``
pins the refusal so a later editor does not "improve" this into a gauge.
"""

from __future__ import annotations

import logging

import pytest

from app.utils.calibration_phase_ledger import FRESH, INVALIDATE
from app.utils.calibration_staged_futures import (
    MALFORMED_REASON_FIELDS,
    MALFORMED_REPR_LIMIT,
    REASON_ABSENT,
    REASON_MALFORMED,
    REASON_INPUT_FINGERPRINT_MALFORMED,
    REASON_POPULATION_VERSION_MALFORMED,
    REASON_NOTHING_BANKED,
    STAGED_FUTURES_SCHEMA,
    MAIN_BUILD_TASK,
    UNIT_KEY_VM_ID,
    decode_staged_cursor_detailed,
    describe_malformed_cursor_field,
)

POPULATION = "q271"
FINGERPRINT = "deadbeef"
ROSTER = "rosterdigest"


def _payload(**overrides):
    """A cursor payload that decodes cleanly, minus whatever a test breaks."""
    base = {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": UNIT_KEY_VM_ID,
        "population_version": POPULATION,
        "input_fingerprint": FINGERPRINT,
        "generation_fingerprint": ROSTER,
        "committed_units": [],
        "accumulator": {},
    }
    base.update(overrides)
    return base


def _decode(payload):
    return decode_staged_cursor_detailed(
        payload,
        expected_population_version=POPULATION,
        expected_input_fingerprint=FINGERPRINT,
        expected_generation_fingerprint=ROSTER,
        owner="owner-a",
        generation=7,
        now=1_000.0,
    )


# --- the anti-drift half: the real classifier decides, this only explains ----
#
# Every case below takes its reason from ``decode_staged_cursor_detailed``
# rather than passing a hand-written token. A helper keyed on tokens the
# classifier no longer emits would pass a test that asserted the token directly,
# and would print nothing in production — the exact failure this file exists to
# prevent.


@pytest.mark.parametrize(
    "bad,expected_type",
    [
        (271, "int"),  # the shape a JSON round-trip of an unquoted version gives
        ("", "str"),  # present and empty: a dropped value, not a wrong one
        (False, "bool"),
        (["q271"], "list"),
        ({"v": "q271"}, "dict"),
        (3.5, "float"),
    ],
)
def test_a_malformed_population_version_is_named_with_its_type(bad, expected_type):
    _cursor, action, reason = _decode(_payload(population_version=bad))

    assert action == INVALIDATE
    assert reason == REASON_POPULATION_VERSION_MALFORMED

    described = describe_malformed_cursor_field(_payload(population_version=bad), reason)
    assert described is not None
    assert described.startswith("population_version=")
    assert expected_type in described
    assert repr(bad) in described


def test_a_malformed_input_fingerprint_is_named_too():
    payload = _payload(input_fingerprint=0)
    _cursor, action, reason = _decode(payload)

    assert action == INVALIDATE
    assert reason == REASON_INPUT_FINGERPRINT_MALFORMED

    described = describe_malformed_cursor_field(payload, reason)
    assert described == "input_fingerprint=int 0"


def test_the_empty_string_and_the_zero_do_not_read_alike():
    """``''``, ``0`` and ``'0'`` are three corruptions with near-identical reprs.

    Only the first is a shape ``new_staged_cursor`` could produce by DROPPING a
    value rather than by writing a wrong one, so an operator triaging this needs
    to tell them apart. That is why the type rides beside the repr.
    """
    empty = describe_malformed_cursor_field(
        _payload(population_version=""), REASON_POPULATION_VERSION_MALFORMED
    )
    zero = describe_malformed_cursor_field(
        _payload(population_version=0), REASON_POPULATION_VERSION_MALFORMED
    )

    assert empty == "population_version=str ''"
    assert zero == "population_version=int 0"
    assert empty != zero


# --- the declining half -------------------------------------------------------


def test_an_absent_field_is_not_described_because_it_is_not_malformed():
    """``None`` earns ``*_ABSENT``, a different token with a different culprit.

    A diagnostic that printed "the rejected value was None" here would send the
    reader hunting a corrupt writer when the honest reading is that the writer
    never said. The classifier already draws that line; this must not blur it.
    """
    payload = _payload(population_version=None)
    _cursor, action, reason = _decode(payload)

    assert action == INVALIDATE
    assert reason != REASON_POPULATION_VERSION_MALFORMED
    assert describe_malformed_cursor_field(payload, reason) is None


def test_a_wellformed_cursor_describes_nothing():
    """The control: every field is a good string, so nothing is rejected.

    The token this earns is ``nothing_banked`` rather than ``resumable`` — the
    payload's bank is empty — and that is worth keeping rather than dressing up,
    because it is the token production has carried on every beat since
    12:36:50Z. The claim under test is that a reason OUTSIDE
    ``MALFORMED_REASON_FIELDS`` describes nothing, so it is asserted that way
    rather than against one hard-coded sibling.
    """
    payload = _payload()
    _cursor, _action, reason = _decode(payload)

    assert reason == REASON_NOTHING_BANKED
    assert reason not in MALFORMED_REASON_FIELDS
    assert describe_malformed_cursor_field(payload, reason) is None


def test_an_absent_payload_describes_nothing():
    _cursor, action, reason = _decode(None)

    assert (action, reason) == (FRESH, REASON_ABSENT)
    assert describe_malformed_cursor_field(None, reason) is None


def test_a_non_mapping_payload_describes_nothing():
    """``REASON_MALFORMED`` names the whole payload; there is no field to show."""
    assert describe_malformed_cursor_field("not a payload", REASON_MALFORMED) is None
    assert (
        describe_malformed_cursor_field(
            ["not", "a", "payload"], REASON_POPULATION_VERSION_MALFORMED
        )
        is None
    )


# --- the bound ----------------------------------------------------------------


def test_a_huge_rejected_value_is_truncated_and_says_so():
    """A rejected value is a shape nothing here wrote, so it may be enormous.

    Truncating silently would be worse than not logging: the reader would take a
    clipped digest for the whole one. The original length rides along.
    """
    huge = "x" * 5_000
    described = describe_malformed_cursor_field(
        _payload(population_version={"junk": huge}),
        REASON_POPULATION_VERSION_MALFORMED,
    )

    assert described is not None
    assert "truncated from" in described
    assert len(described) < MALFORMED_REPR_LIMIT + 120
    assert huge not in described


def test_a_value_inside_the_bound_is_not_marked_truncated():
    described = describe_malformed_cursor_field(
        _payload(population_version=271), REASON_POPULATION_VERSION_MALFORMED
    )
    assert described == "population_version=int 271"
    assert "truncated" not in described


# --- the refusal this file inherits -------------------------------------------


def test_the_value_is_not_minted_into_a_token():
    """Cursor-reason cardinality stays at six; the value lives in a log line.

    The token block in ``calibration_staged_futures`` states the constraint and
    the reason for it (the sampler banks these by NAME). If a later change moves
    the observed value into a reason token, this fails and points at that block.
    """
    assert set(MALFORMED_REASON_FIELDS) == {
        REASON_POPULATION_VERSION_MALFORMED,
        REASON_INPUT_FINGERPRINT_MALFORMED,
    }
    for token, field_name in MALFORMED_REASON_FIELDS.items():
        assert token == f"{field_name}_malformed"
        # A token is a fixed string, never an interpolation of an observation.
        assert "271" not in token and "=" not in token


# --- the caller: the one site where the value still exists ---------------------


@pytest.mark.asyncio
async def test_the_beat_logs_the_rejected_value(monkeypatch, caplog):
    """The decode is pure, so the log must happen where the payload is in scope.

    Asserted through the real ``load_staged_cursor`` rather than by calling the
    helper again: the helper being right is worth nothing if nobody calls it, and
    that is precisely the half that was missing on 2026-09-22.
    """
    from types import SimpleNamespace

    from app.tasks import calibration_main_build as build

    payload = _payload(population_version=271)

    async def _fake_read(*_args, **_kwargs):
        return SimpleNamespace(
            ok=True,
            envelope=SimpleNamespace(payload=payload),
            status="ok",
            unavailable=False,
            error=None,
            error_class=None,
        )

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _fake_read
    )

    with caplog.at_level(logging.WARNING, logger=build.logger.name):
        _cursor, action, reason = await build.load_staged_cursor(
            population_version=POPULATION,
            input_fingerprint=FINGERPRINT,
            generation_fingerprint=ROSTER,
            owner="owner-a",
            generation=7,
        )

    assert (action, reason) == (INVALIDATE, REASON_POPULATION_VERSION_MALFORMED)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "population_version=int 271" in logged
    assert REASON_POPULATION_VERSION_MALFORMED in logged


@pytest.mark.asyncio
async def test_a_wellformed_beat_logs_no_rejected_value(monkeypatch, caplog):
    """The control for the one above — otherwise it cannot fail for the right reason."""
    from types import SimpleNamespace

    from app.tasks import calibration_main_build as build

    async def _fake_read(*_args, **_kwargs):
        return SimpleNamespace(
            ok=True,
            envelope=SimpleNamespace(payload=_payload()),
            status="ok",
            unavailable=False,
            error=None,
            error_class=None,
        )

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _fake_read
    )

    with caplog.at_level(logging.WARNING, logger=build.logger.name):
        _cursor, _action, reason = await build.load_staged_cursor(
            population_version=POPULATION,
            input_fingerprint=FINGERPRINT,
            generation_fingerprint=ROSTER,
            owner="owner-a",
            generation=7,
        )

    assert reason == REASON_NOTHING_BANKED
    assert "rejected value" not in "\n".join(r.getMessage() for r in caplog.records)
