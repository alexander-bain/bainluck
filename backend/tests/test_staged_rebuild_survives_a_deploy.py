"""CAL-P190 (#1978, #2052) — the four properties the durable-rebuild fix rests on.

Design: ``artifacts/cal-p190/DESIGN-THE-REBUILD-SURVIVES-A-DEPLOY.md``.

The staged rebuild needs ~26 uninterrupted hours and is discarded whenever
``_main_input_fingerprint()`` moves — which it does on any edit to four
functions' SOURCE TEXT. That digest is a proxy for "did the banked rows change",
and the design replaces it, for the STAGED CURSOR only, with a digest of the
statement the units actually ran.

Every test here pins a property the design ASSUMES. None of them assert the new
behaviour, because none of it is built: they are the checks that would have to
hold before it could be, and three of the four are properties nothing in the
suite currently protects.

TEST-ONLY. Nothing under ``app/`` is touched, so ``_main_input_fingerprint()``
cannot move and this file is inert under the D-G deploy freeze
(``.claude/handoff/runner-inbox/calibration/920-freeze-window-design-work.md``).
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
# 4. The freeze-window pin -- DATED, and it carries its own removal instruction
# ---------------------------------------------------------------------------

#: ``_main_input_fingerprint()`` as the LIVE beat was running it at
#: 2026-09-01 16:00Z, reproduced by the local predictor at this branch's HEAD.
_LIVE_FINGERPRINT_2026_09_01 = "e2040f90154fae876f0fb65f5abf74c3"


def test_the_wide_fingerprint_is_unchanged_by_this_branch():
    """Nothing on this branch may move the population fingerprint.

    Two jobs, and both expire:

    * the design's layer-1 cutover is only free if the new code computes the
      SAME wide digest the stored cursor carries -- so the branch that builds it
      must not edit any of the four hashed functions; and
    * under D-G the whole lane is frozen out of calibration-source deploys. A
      red here during the freeze means somebody moved the population.

    RED FOR A LEGITIMATE REASON? Then the population genuinely changed, the
    in-flight rebuild is already lost, and this test has done its job and should
    be DELETED -- not updated to the new digest. It is a freeze-window
    instrument with a date on it, not a permanent guard.
    """
    assert _main_input_fingerprint() == _LIVE_FINGERPRINT_2026_09_01, (
        "the population fingerprint moved. If that was deliberate, the ~26-hour "
        "staged rebuild in flight on 2026-09-01 has been discarded -- see "
        "YOUR-TURN.md D-G. Delete this test rather than re-baselining it."
    )
