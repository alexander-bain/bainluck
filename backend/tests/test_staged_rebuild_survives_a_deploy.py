"""CAL-P190 (#1978, #2052) — the four properties the durable-rebuild fix rests on.

Design: ``artifacts/cal-p190/DESIGN-THE-REBUILD-SURVIVES-A-DEPLOY.md``.

The staged rebuild needs ~26 uninterrupted hours and is discarded whenever
``_main_input_fingerprint()`` moves — which it does on any edit to four
functions' SOURCE TEXT. That digest is a proxy for "did the banked rows change",
and the design replaces it, for the STAGED CURSOR only, with a digest of the
statement the units actually ran.

Sections 1-4 are CAL-P190's and pin properties the design ASSUMES; they asserted
no new behaviour because none of it was built. **CAL-P205 (#2052) builds layer 1**
and section 5 asserts it.

CAL-P205 also re-derived section 2's coverage table, which was measured when
``_main_input_fingerprint`` hashed six values by name. CAL-P168 had since added
six more without re-deriving it — all six turn out to be covered by the emitted
statement, but "turns out" is the word that makes the table worth pinning.

The layer-1 change deliberately touches NONE of the four functions hashed by
``_main_input_fingerprint``, so the wide digest does not move and the ~26-hour
staged rebuild in flight keeps its bank across the deploy that ships this. That
is section 4's pin, and it is the cutover's whole safety argument.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys

import pytest

from app.tasks.precompute_calibration import (
    _main_futures_sql,
    _main_input_fingerprint,
)
from app.utils.calibration_staged_futures import GROUP_KEY_COLUMNS


def _sql_digest() -> str:
    return hashlib.md5(_main_futures_sql(frozen=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# 1. The statement is the same bytes in every process
# ---------------------------------------------------------------------------

_SEEDS = ("0", "1", "99991")

_CHILD = (
    "import hashlib;"
    "from app.tasks.precompute_calibration import _main_futures_sql;"
    "print(hashlib.md5(_main_futures_sql(frozen=True).encode()).hexdigest())"
)


def test_frozen_futures_sql_is_deterministic_across_processes():
    """The emitted statement must not depend on ``PYTHONHASHSEED``.

    Load-bearing TWICE, and the second reason is the one that makes this a real
    guard rather than a nicety for unbuilt work:

    * the design pins the statement's TEXT into a generation, so a text that
      varied per process would make the pin meaningless; and
    * ``_main_input_fingerprint`` ALREADY hashes values interpolated into this
      statement. Interpolating a ``set``/``frozenset`` of strings unsorted would
      make TODAY's fingerprint differ between two dynos running identical code —
      i.e. a rebuild that resets itself for no reason at all.

    Run in real subprocesses because ``PYTHONHASHSEED`` is fixed at interpreter
    start; ``os.environ`` inside this process cannot change it.
    """
    digests = {}
    for seed in _SEEDS:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        assert proc.returncode == 0, (
            f"PYTHONHASHSEED={seed} child failed (exit {proc.returncode}). "
            "A non-zero exit is a story about the harness, not a result — read "
            f"it before reading the assertion below.\n{proc.stderr[-2000:]}"
        )
        digests[seed] = proc.stdout.strip().splitlines()[-1]

    assert len(set(digests.values())) == 1, (
        "the frozen futures statement is NOT deterministic across processes: "
        f"{digests}. Something hash-ordered (a set/frozenset of strings) is "
        "interpolated into it. This breaks the staged fingerprint TODAY, not "
        "just the pinned-SQL design."
    )
    assert digests[_SEEDS[0]] == _sql_digest()


# ---------------------------------------------------------------------------
# 2. What the emitted statement covers that four functions' source does not
# ---------------------------------------------------------------------------

#: The six values ``_main_input_fingerprint`` hashes BY NAME, each one added by
#: hand after an incident in which an interpolated value moved the statement
#: while the source-text hash stood still. Its own docstring calls this "the
#: general rule this keeps re-teaching".
#:
#: ``True`` here means: mutating this value moves the EMITTED statement, so a
#: digest of the statement covers it BY CONSTRUCTION and it can never become a
#: seventh instance of that hole.
_FINGERPRINT_INPUTS: dict[str, tuple[object, bool]] = {
    "COVERAGE_CENSUS_ENABLED": (True, True),
    "NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS": ((("kalshi", "crypto"),), True),
    "MEX_NORMALIZE_THRESHOLD": (1.25, True),
    "PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS": ((("polymarket", "basketball"),), True),
    # The two DECLARATIONS. Neither reaches the statement text, so neither
    # shapes a banked row -- and the design must hash them separately rather
    # than assume the statement covers them.
    #
    #   * CALIBRATION_POPULATION_VERSION is ALREADY checked on its own branch in
    #     ``decode_staged_cursor`` (``REASON_POPULATION_VERSION``), so it needs
    #     nothing new;
    #   * REPRESENTATIVE_TIE_AUTHORITY is stamped on the published artifact, so
    #     it is a disclosure input, not a row input.
    "CALIBRATION_POPULATION_VERSION": ("q999", False),
    "REPRESENTATIVE_TIE_AUTHORITY": ("mutated-authority/v9", False),
    # CAL-P205: the table above was written when ``_main_input_fingerprint``
    # hashed SIX values by name. CAL-P168 has since added six more, and the
    # design's coverage claim was never re-derived against them. Measured the
    # same way as the original six — mutate, re-emit, compare — and all six are
    # covered by the statement, so layer 1 has no blind input.
    #
    # This is the whole reason the table is pinned in both directions: an
    # unmeasured addition to the wide digest is exactly how the narrow one would
    # silently acquire a hole.
    "PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE": (0.4242, True),
    "PAIR_SUM_TOLERANCE": (0.0777, True),
    "PLAYER_PROPS_NAME_PATTERN": ("ZZ_MUTATED_PATTERN", True),
    "PLAYER_PROPS_MIDPOINT_BAND_LO": (0.111, True),
    "PLAYER_PROPS_MIDPOINT_BAND_HI": (0.999, True),
    "PLAYER_PROPS_FORCED_DRIFT_MIN": (0.4242, True),
}


@pytest.mark.parametrize(
    ("name", "mutated", "moves_sql"),
    [(k, v[0], v[1]) for k, v in _FINGERPRINT_INPUTS.items()],
)
def test_which_fingerprint_inputs_the_emitted_statement_actually_covers(
    monkeypatch, name, mutated, moves_sql
):
    """Mutate each hashed value; assert whether the statement notices.

    Pinned in BOTH directions on purpose. A value that starts shaping the SQL
    (the ``False`` rows going ``True``) is a value that has quietly become
    row-shaping, and a value that stops (``True`` going ``False``) is a hole
    opening in the narrow digest. Either way the design's coverage claim has
    moved and this table has to be re-derived rather than trusted.
    """
    from app.tasks import precompute_calibration as pc

    before = _sql_digest()
    monkeypatch.setattr(pc, name, mutated)
    after = _sql_digest()

    assert (after != before) is moves_sql, (
        f"{name}: mutating it "
        f"{'moved' if after != before else 'did NOT move'} the emitted frozen "
        f"statement, but this table says it should "
        f"{'move' if moves_sql else 'not move'} it. Re-derive "
        "artifacts/cal-p190/DESIGN-THE-REBUILD-SURVIVES-A-DEPLOY.md section 3 "
        "before changing this line."
    )


# ---------------------------------------------------------------------------
# 3. The fold key is the statement's group key
# ---------------------------------------------------------------------------

def test_the_group_key_of_the_frozen_select_is_the_fold_key():
    """Layer 3's precondition, read off the STATEMENT rather than a constant.

    An accumulator banked under one generation is only mergeable by a later one
    if both aggregate on the same key. CAL-P190 measured that the bare leading
    columns of the final SELECT were byte-identical across the six commits
    spanning RULE E, rank 1 and the CERT-647 disclosure repair -- and found that
    nothing pinned it.

    Deliberately parsed out of the emitted text, not compared against a mirror
    of it: two declarations agreeing with each other is not coverage (the lesson
    ``DECLARED_CENSUS_COLUMNS`` was written to record).
    """
    sql = _main_futures_sql(frozen=True)
    start = sql.rfind("SELECT bucket_idx")
    assert start >= 0, (
        "could not find the final SELECT in the frozen statement. This guard "
        "cannot silently pass on a statement it failed to parse -- if the "
        "SELECT was renamed, re-point the anchor."
    )
    tail = sql[start:]
    head = tail[: tail.find(" AS ")]
    head = re.sub(r"--[^\n]*", "", head)
    head = re.sub(r"^\s*SELECT", "", head)
    # The last comma-separated token belongs to the first aliased expression.
    bare = tuple(t.strip() for t in head.split(",")[:-1] if t.strip())

    assert bare == GROUP_KEY_COLUMNS, (
        f"the frozen statement groups on {bare} but the fold merges on "
        f"{GROUP_KEY_COLUMNS}. A banked accumulator and the rows it is merged "
        "with no longer share a key."
    )


# ---------------------------------------------------------------------------
# 4. The freeze-window pin -- REMOVED 2026-09-01 by CAL-P211, on its own terms
# ---------------------------------------------------------------------------
#
# What stood here was ``test_the_wide_fingerprint_is_unchanged_by_this_branch``,
# pinning ``_main_input_fingerprint()`` to ``e2040f90154fae876f0fb65f5abf74c3``
# to protect the staged rebuild that was in flight on 2026-09-01. It carried its
# own removal instruction, quoted verbatim:
#
#     RED FOR A LEGITIMATE REASON? Then the population genuinely changed, the
#     in-flight rebuild is already lost, and this test has done its job and
#     should be DELETED -- not updated to the new digest. It is a freeze-window
#     instrument with a date on it, not a permanent guard.
#
# BOTH of its conditions are met, measured rather than asserted:
#
# * The population genuinely changed, and is now DECLARED to have changed --
#   that is the whole of CAL-P211 (``CALIBRATION_POPULATION_VERSION`` q268 ->
#   q269). The digest moves to ``45becc2c3843c69025b2696996345218``.
# * The rebuild it protected is already lost, and not by this branch. It
#   COMPLETED all 128 units at 2026-09-01 22:27 PT and the publish gate refused
#   it (``population_shrink`` -21.7%), and a refusal clears the checkpoint by
#   design. The live phase ledger records the whole thing: ``outcome.gate
#   'refuse'``, ``checkpoint_action 'invalidate'``, ``staged:units_banked 0`` --
#   under ``input_fingerprint e2040f90154fae876f0fb65f5abf74c3``, i.e. the exact
#   digest this test pinned. There is no in-flight rebuild left to protect.
#
# Re-baselining it to the new digest was explicitly ruled out by the instrument
# itself, so it is deleted rather than carried. The permanent half of its job --
# that a fingerprint move must be deliberate and declared -- now lives in
# ``tests/test_calibration_result_authority_299.py`` as the two-armed rollover
# guard, which fails closed on an undeclared or inherited dark window.


# ---------------------------------------------------------------------------
# 5. CAL-P205 layer 1 -- the staged cursor keys off the EMITTED STATEMENT
# ---------------------------------------------------------------------------
#
# Everything above this line was written by CAL-P190 as a PRECONDITION check and
# deliberately asserted no new behaviour. These assert the behaviour.

from app.tasks.precompute_calibration import staged_unit_fingerprint  # noqa: E402
from app.utils.calibration_staged_futures import (  # noqa: E402
    INVALIDATE,
    MAIN_BUILD_TASK,
    REASON_INPUT_FINGERPRINT,
    REASON_LEGACY_FINGERPRINT_ACCEPTED,
    REASON_RESUMABLE,
    RESUME,
    STAGED_FUTURES_SCHEMA,
    UNIT_KEY_VM_ID,
    decode_staged_cursor_detailed,
    encode_accumulator,
)

_WIDE = "wide-digest-as-stamped-before-layer-1"
_NARROW = "narrow-statement-digest"


def _raw(**overrides):
    raw = {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": UNIT_KEY_VM_ID,
        "population_version": "q268",
        "input_fingerprint": _WIDE,
        "generation_fingerprint": "gen-a",
        "owner": "me",
        "lease_expires_at": 0.0,
        "committed_units": ["u1"],
        "accumulator": encode_accumulator([{"bucket_idx": 1, "n": 1}], []),
        "terminal": "partial",
    }
    raw.update(overrides)
    return raw


def _decode(raw, *, legacy=_WIDE):
    return decode_staged_cursor_detailed(
        raw,
        expected_population_version="q268",
        expected_input_fingerprint=_NARROW,
        expected_generation_fingerprint="gen-a",
        owner="me",
        generation=9,
        now=100.0,
        legacy_input_fingerprint=legacy,
    )


def test_the_narrow_digest_is_not_the_wide_one():
    """If they were equal the whole layer would be a no-op wearing a new name."""
    assert staged_unit_fingerprint() != _main_input_fingerprint()


def test_the_narrow_digest_is_stable_within_a_process():
    assert staged_unit_fingerprint() == staged_unit_fingerprint()


def test_a_renderer_only_edit_moves_the_wide_digest_but_not_the_narrow_one(monkeypatch):
    """THE SHIP, as one assertion.

    ``compute_calibration_payload`` is hashed by ``_main_input_fingerprint`` and
    is NOT part of the emitted statement. Editing it -- metrics, bucket shaping,
    rendering -- today discards a ~26-hour staged rebuild. It cannot change what
    a banked unit's rows ARE, so after layer 1 it must not.
    """
    from app.tasks import precompute_calibration as pc

    before_wide, before_narrow = _main_input_fingerprint(), staged_unit_fingerprint()

    def _edited_renderer(*a, **k):  # a different function body => different source
        """Stand-in for any ordinary edit to the payload builder."""
        raise AssertionError("never called")

    monkeypatch.setattr(pc, "compute_calibration_payload", _edited_renderer)

    assert _main_input_fingerprint() != before_wide, (
        "the wide digest did not notice an edit to compute_calibration_payload; "
        "this test's premise is gone and layer 1's whole rationale needs re-deriving"
    )
    assert staged_unit_fingerprint() == before_narrow, (
        "a renderer-only edit moved the STAGED digest -- layer 1 is not buying "
        "what it claims to buy"
    )


class TestTheCutoverCostsZeroBankedUnits:
    """Design section 6, pre-registered falsifier #2.

    "Falsified by a single ``REASON_INPUT_FINGERPRINT`` on the beat immediately
    after the layer-1 deploy. This is the one that must be watched, because
    getting it wrong costs exactly the thing the change is for."
    """

    def test_a_legacy_stamped_cursor_resumes_instead_of_invalidating(self):
        _cursor, action, reason = _decode(_raw())
        assert action == RESUME
        assert reason == REASON_LEGACY_FINGERPRINT_ACCEPTED

    def test_the_resumed_cursor_keeps_its_bank(self):
        cursor, _action, _reason = _decode(_raw())
        assert cursor.committed_units == ("u1",)

    def test_the_resumed_cursor_is_re_stamped_narrow_so_the_branch_self_drains(self):
        """The compatibility branch must fire ONCE, not every beat forever."""
        cursor, _action, _reason = _decode(_raw())
        assert cursor.input_fingerprint == _NARROW

        # Feed the re-stamped cursor back in: the second beat is an ordinary
        # resume, not a legacy acceptance.
        _again, action, reason = _decode(_raw(input_fingerprint=_NARROW))
        assert (action, reason) == (RESUME, REASON_RESUMABLE)

    def test_a_cursor_already_stamped_narrow_never_reports_the_legacy_reason(self):
        _cursor, action, reason = _decode(_raw(input_fingerprint=_NARROW))
        assert (action, reason) == (RESUME, REASON_RESUMABLE)


class TestTheAcceptanceIsNarrow:
    """Control arms. An acceptance that accepts everything is not a cutover."""

    def test_a_third_unrelated_digest_still_invalidates(self):
        """Neither narrow nor legacy => the old behaviour, unchanged."""
        _cursor, action, reason = _decode(_raw(input_fingerprint="some-other-deploy"))
        assert (action, reason) == (INVALIDATE, REASON_INPUT_FINGERPRINT)

    def test_without_a_legacy_digest_the_behaviour_is_exactly_pre_layer_1(self):
        """``legacy_input_fingerprint=None`` restores the old decoder exactly.

        This is the arm that fails if the change were a blanket weakening of the
        fingerprint check rather than a scoped, self-draining cutover.
        """
        _cursor, action, reason = _decode(_raw(), legacy=None)
        assert (action, reason) == (INVALIDATE, REASON_INPUT_FINGERPRINT)

    def test_the_legacy_reason_is_distinct_from_every_other_reason(self):
        """A shared token rebuilds the ambiguity CAL-P024 removed."""
        seen = {
            _decode(_raw())[2],
            _decode(_raw(input_fingerprint=_NARROW))[2],
            _decode(_raw(input_fingerprint="other"))[2],
        }
        assert len(seen) == 3

    def test_population_version_is_still_checked_ahead_of_the_acceptance(self):
        """The legacy branch must not become a way past a population bump."""
        from app.utils.calibration_staged_futures import REASON_POPULATION_VERSION

        _cursor, action, reason = _decode(_raw(population_version="q999"))
        assert (action, reason) == (INVALIDATE, REASON_POPULATION_VERSION)
