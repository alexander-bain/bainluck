"""Invariants of the CI shard partitioner (Queue 312, Item 1).

`scripts/ci_shard.py --verify` proves the partition covers the REAL suite on
every CI run. This file proves the properties it relies on hold in general —
including for inputs the real suite does not currently exhibit, like a file with
no recorded duration or a shard count that does not divide the file count.

The property that matters is TOTALITY. A sharded suite whose partition drops a
file reports green while testing less, and nothing about that green looks wrong.
"""

import importlib.util
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "ci_shard.py"


def _load():
    spec = importlib.util.spec_from_file_location("ci_shard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci_shard = _load()


FILES = [f"tests/test_{c}.py" for c in "abcdefghijklmnopqrstuvwxyz"]


@pytest.mark.parametrize("shards", [1, 2, 3, 4, 5, 7, 26, 40])
def test_partition_is_total_and_disjoint(shards):
    """Every file lands in exactly one shard, for any shard count.

    Includes shards > len(files) (40 vs 26): over-sharding must produce empty
    bins, never duplicated or dropped work.
    """
    bins = ci_shard.partition(FILES, shards)
    assert len(bins) == shards
    flat = [f for b in bins for f in b]
    assert sorted(flat) == sorted(FILES), "a file was dropped or duplicated"
    assert len(flat) == len(set(flat)), "a file was assigned to two shards"


def test_partition_is_deterministic():
    """Two runners computing the split independently must agree.

    Each shard job recomputes the partition on its own machine. If the function
    were order- or hash-dependent, two legs could disagree about who owns a
    file, and it would be either run twice or not at all.
    """
    a = ci_shard.partition(FILES, 4)
    b = ci_shard.partition(list(reversed(FILES)), 4)
    assert a == b, "partition depends on input order"


def test_heavy_files_are_spread_not_stacked(monkeypatch):
    """LPT must not pile the slow files into one bin.

    Balance is the whole point: four shards where one holds every slow suite is
    the old 8m23s job wearing a matrix.
    """
    weights = {f: 100.0 for f in FILES[:4]}
    weights.update({f: 0.1 for f in FILES[4:]})
    monkeypatch.setattr(ci_shard, "load_durations", lambda: weights)
    bins = ci_shard.partition(FILES, 4)
    for b in bins:
        heavy = [f for f in b if weights[f] == 100.0]
        assert len(heavy) == 1, f"expected one heavy file per shard, got {heavy}"


def test_unmeasured_file_is_not_treated_as_free(monkeypatch):
    """A newly added test file has no recorded duration; it must still carry weight.

    If unknown meant zero, every new file would be packed into whichever bin the
    tie-break favoured, and the split would quietly decay as the suite grows.
    """
    monkeypatch.setattr(ci_shard, "load_durations", lambda: {})
    assert ci_shard.DEFAULT_WEIGHT > 0
    bins = ci_shard.partition(FILES, 4)
    sizes = sorted(len(b) for b in bins)
    assert sizes[-1] - sizes[0] <= 1, "equal-weight files should spread evenly"


def test_recorded_durations_file_is_present_and_parses():
    """The balance hints ship with the script and are readable.

    Not a correctness dependency — `load_durations` degrades to equal weights —
    but a corrupt file silently un-balances CI, so notice it here.
    """
    path = BACKEND / "scripts" / "ci_shard_durations.json"
    assert path.exists(), "ci_shard_durations.json missing; regenerate with --record"
    data = json.loads(path.read_text())
    files = data["files"]
    assert len(files) > 100, f"suspiciously few recorded files: {len(files)}"
    assert all(isinstance(v, (int, float)) and v >= 0 for v in files.values())


def test_every_shard_is_nonempty_at_the_configured_count():
    """At the count ci.yml actually uses, no leg may be a no-op.

    A shard that resolves to zero files passes instantly and looks like a fast
    green. The workflow guards this too; this catches it before the push.
    """
    real = ci_shard.discover_test_files()
    assert len(real) > 100, "test discovery found almost nothing"
    for i, b in enumerate(ci_shard.partition(real, 4), start=1):
        assert b, f"shard {i} of 4 is empty"


def test_q312_seeded_failure_shard_3():
    """TEMPORARY — Queue 312 acceptance #2: prove shard 3 can report red.

    Deliberate failure on a throwaway branch. Never merged to master.
    """
    assert False, "Q312 seeded failure: shard 3 must go red"
