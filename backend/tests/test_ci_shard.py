"""Invariants of the CI shard partitioner (Queue 312, Item 1).

`scripts/ci_shard.py --verify` proves the partition covers the REAL suite on
every CI run. This file proves the properties it relies on hold in general —
including for inputs the real suite does not currently exhibit, like a file with
no recorded duration or a shard count that does not divide the file count.

The property that matters is TOTALITY. A sharded suite whose partition drops a
file reports green while testing less, and nothing about that green looks wrong.
"""

import argparse
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


def test_verify_says_how_much_of_its_skew_estimate_is_actually_measured(monkeypatch, capsys):
    """A skew estimate computed from placeholders must not read as a healthy one.

    LAT-P183. `--verify` graded the packing with the SAME weights LPT packed
    against, so the two cancelled to a confident zero wherever a weight was the
    DEFAULT_WEIGHT placeholder rather than a measurement. On 2026-09-01 that was
    481 of 1,080 files, and the line printed `estimated shard skew: 0.0%` for a
    partition whose legs ran 328s / 506s / 411s / 324s on the runner — 56% real
    skew, reported as perfect balance. Nothing raised, because nothing was
    broken; the estimate simply had nothing to see.

    Two arms, because a warning that fires always is as useless as one that never
    fires: mostly-unmeasured must warn, fully-measured must not.
    """
    files = ci_shard.discover_test_files()
    monkeypatch.setattr(ci_shard, "pytest_collected_files", lambda: (files, ""))
    args = argparse.Namespace(of=4)

    # Arm 1: hints cover a small minority of the suite — the 2026-09-01 state.
    monkeypatch.setattr(ci_shard, "load_durations", lambda: {f: 1.0 for f in files[:5]})
    assert ci_shard.cmd_verify(args) == 0, "staleness is a wall-clock cost, never a failure"
    stale = capsys.readouterr().out
    assert "::warning::" in stale and "STALE" in stale
    assert "--record" in stale, "the warning must say how to fix it"
    assert "DEFAULT_WEIGHT placeholder" in stale, "the skew line must disclose its basis"

    # Arm 2: every file measured — the estimate is worth reading, so stay quiet.
    monkeypatch.setattr(ci_shard, "load_durations", lambda: {f: 1.0 for f in files})
    assert ci_shard.cmd_verify(args) == 0
    fresh = capsys.readouterr().out
    assert "STALE" not in fresh
    assert f"{len(files)}/{len(files)} measured files" in fresh


def test_the_shipped_hints_are_not_stale_right_now():
    """The state LAT-P183 left the repo in, pinned so a silent decay is visible.

    Deliberately asserts against the SAME threshold `--verify` warns on, so this
    test and CI's warning can never disagree about what stale means.
    """
    files = ci_shard.discover_test_files()
    weights = json.loads((BACKEND / "scripts" / "ci_shard_durations.json").read_text())["files"]
    measured = sum(1 for f in files if f in weights)
    coverage = 100.0 * measured / len(files)
    assert coverage >= ci_shard.STALE_HINTS_COVERAGE_PCT, (
        f"only {measured}/{len(files)} ({coverage:.0f}%) test files have a measured duration. "
        "The shards are being packed by guess and the wall clock is paying for it. "
        "Refresh from a CI run's logs: python scripts/ci_shard.py --record <log>"
    )
