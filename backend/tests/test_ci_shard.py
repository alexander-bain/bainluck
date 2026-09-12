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

    #3497: this asserts a COUNT of unmeasured files, not a coverage ratio. A ratio
    falls on every push that adds a test file, so it decays to the floor on its own
    and reds master on no branch's change — twice in five days, both times reading
    89.90%. The count means the same thing at any suite size.

    `--verify` warns at `STALE_HINTS_WARN_UNMEASURED` and this fails at
    `STALE_HINTS_MAX_UNMEASURED`; the gap is deliberate runway, so CI asks for a
    refresh for days before anything can go red.
    """
    files = ci_shard.discover_test_files()
    weights = json.loads((BACKEND / "scripts" / "ci_shard_durations.json").read_text())["files"]
    measured, unmeasured = ci_shard.hint_coverage(files, weights)
    assert not ci_shard.hints_are_stale(unmeasured), (
        f"{unmeasured} of {len(files)} test files have no measured duration "
        f"(limit {ci_shard.STALE_HINTS_MAX_UNMEASURED}). The shards are being packed by guess "
        "and the wall clock is paying for it. Refresh from a CI run's own logs: download the "
        "four backend-tests job logs and run "
        "`python scripts/ci_shard.py --record <concatenated.log>` — Actions' timestamp prefix "
        "is stripped for you."
    )


def test_the_staleness_guard_does_not_decay_as_the_suite_grows():
    """The #3497 property itself: adding test files must not move the verdict.

    This is the regression that would have caught both master-reddening crossings.
    Under the old ratio, holding the measurements fixed and growing only the
    denominator walked coverage down to the floor and failed. The budget is a
    count, so a suite that doubles with every new file measured is still healthy,
    and one that adds unmeasured files fails only once there are genuinely too
    many of them — never because the suite got bigger.
    """
    limit = ci_shard.STALE_HINTS_MAX_UNMEASURED

    # Built through the REAL pair — `hint_coverage` then `hints_are_stale` — so
    # this fails if either the accounting or the verdict re-acquires a dependence
    # on the suite size. A local re-implementation here would pass no matter what
    # the shipped guard did.
    def stale_for(measured: int, unmeasured: int) -> bool:
        files = [f"tests/test_m{i}.py" for i in range(measured)]
        files += [f"tests/test_u{i}.py" for i in range(unmeasured)]
        weights = {f: 1.0 for f in files if f.startswith("tests/test_m")}
        got_measured, got_unmeasured = ci_shard.hint_coverage(files, weights)
        assert (got_measured, got_unmeasured) == (measured, unmeasured)
        return ci_shard.hints_are_stale(got_unmeasured)

    # Growth with everything measured is healthy at any size.
    assert not stale_for(1_000, 0) and not stale_for(20_000, 0)

    # THE REGRESSION, and the arm that would have caught both master-reddening
    # crossings. Identical absolute staleness, two suite sizes three orders of
    # magnitude apart. Under the old ratio the first passes (~99.9% covered) and
    # the second fails (~66% covered) on the SAME 10 unmeasured files.
    assert not stale_for(10_000, 10), "a big suite with 10 stale files is not stale"
    assert not stale_for(20, 10), (
        "the verdict moved when only the suite size changed — the guard has "
        "re-acquired a dependence on the denominator (#3497)"
    )

    # Genuine neglect still fails, at the same count regardless of suite size.
    assert stale_for(10_000, limit + 1)
    assert stale_for(0, limit + 1)

    # Exactly at the limit is healthy; one past it is not. Pins the boundary so a
    # `>=`/`>` slip is a failure rather than a silent one-file drift.
    assert not stale_for(100, limit)
    assert stale_for(100, limit + 1)

    # And the warning must fire strictly before the failure, or there is no runway.
    assert ci_shard.STALE_HINTS_WARN_UNMEASURED < limit
    assert ci_shard.hints_need_refresh(ci_shard.STALE_HINTS_WARN_UNMEASURED + 1)
    assert not ci_shard.hints_need_refresh(ci_shard.STALE_HINTS_WARN_UNMEASURED)


def test_record_parses_a_github_actions_log_not_just_a_local_pytest_run():
    """#3497: the remedy the guard prints has to work on the log it names.

    `--record` is advertised in the failure message as the fix, and the only log a
    lane can obtain is a downloaded Actions one — where every line is
    timestamp-prefixed. The line-anchored pattern matched none of them, so the
    tool exited 1 saying no durations were found, which reads as operator error.
    """
    local = "1.23s call     tests/test_alpha.py::TestA::test_one"
    zipped = "2026-09-11T11:49:57.5647990Z 1.23s call     tests/test_alpha.py::TestA::test_one"
    gh_cli = (
        "backend-tests (1)\tRun tests (shard 1/4)\t"
        "2026-09-11T11:49:57.5647990Z 1.23s call     tests/test_alpha.py::TestA::test_one"
    )
    bom = "﻿2026-09-11T11:49:57.5647990Z 1.23s call     tests/test_alpha.py::TestA::test_one"

    for label, line in [("local", local), ("zip", zipped), ("gh", gh_cli), ("bom", bom)]:
        assert ci_shard._strip_log_prefix(line) == local, f"{label} prefix survived stripping"

    # A line that merely looks timestamp-ish must not be mangled into a match.
    assert ci_shard._strip_log_prefix("not a duration line") == "not a duration line"
