#!/usr/bin/env python3
"""LAT-P124 mutation battery for `/api/events/search-suggestions`.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — mostly the kind of edit that looks like a simplification. If a
mutant survives, the suite has a hole and the fix is to add the missing
assertion, NOT to delete the mutant (LAT-P115's M7 survived and the survivor was
the finding; LAT-P123's first pass reported 10/13 and all three findings were
its own).

🔴 WHY THIS ONE MUTATES THE FILE ON DISK RATHER THAN `exec`-ING SOURCE STRINGS.
`_mutation_guard.py` prefers the disk-free design, and LAT-P123 took it. It is
the wrong trade here. The oracle for this change is a QUERY COUNT taken through
the real route, with the real `_add`/`_window_full` closure and the real
`except Exception: pass` around every section — and LAT-P123's own finding was
that a hand-written in-process fake diverged from the live shape and let M10
survive. Using the 21-test suite verbatim as the oracle removes that class of
hole entirely: the thing that grades the mutants is the same thing that grades
the ship. The cost is a `SHAPES` entry and a `guarded_targets` manifest, both
of which exist for exactly this.

Mutations are applied SERIALLY and the file is restored between each. Never
concurrently, and never while another pytest is in flight: `inspect.getsource`
re-reads the file mid-run and a source edit under a running suite produces
phantom failures that read as real reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or a SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`).

Run:  python3 backend/scripts/evals/search_suggestions_cold_mutations.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = ROOT / "app" / "routes" / "events.py"
SUITE = ROOT / "tests" / "integration" / "test_route_search_suggestions_cold_p124.py"

#: (id, description, needle, replacement). The needle must appear EXACTLY once —
#: a mutation that matches zero or many places is a HARNESS BUG, reported as
#: such and never counted as a kill. `if not _window_full():` alone appears four
#: times at identical indentation, so every skip mutant carries its section's
#: own preceding line as part of the anchor.
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M1",
        "section 3 skips even when the window is OPEN — silently deletes movers",
        "        movers_rows = []\n        if not _window_full():",
        "        movers_rows = []\n        if False:",
    ),
    (
        "M2",
        "section 3 never skips — the no-op 'fix', 1.14 GB back on every request",
        "        movers_rows = []\n        if not _window_full():",
        "        movers_rows = []\n        if True:",
    ),
    (
        "M3",
        "section 2 never skips",
        "        soon_rows = []\n        if not _window_full():",
        "        soon_rows = []\n        if True:",
    ),
    (
        "M4",
        "section 4 never skips",
        "        upsets_rows = []\n        if not _window_full():",
        "        upsets_rows = []\n        if True:",
    ),
    (
        "M5",
        "the window grows by one — the skip stops firing at a full page of eight",
        "_MAX_SUGGESTIONS = 8",
        "_MAX_SUGGESTIONS = 9",
    ),
    (
        "M6",
        "the predicate goes strict — at exactly eight it refuses to skip",
        "        return len(suggestions) >= _MAX_SUGGESTIONS",
        "        return len(suggestions) > _MAX_SUGGESTIONS",
    ),
    (
        "M7",
        "the predicate re-hardcodes the literal — the skip and the break can drift",
        "        return len(suggestions) >= _MAX_SUGGESTIONS",
        "        return len(suggestions) >= 8",
    ),
    (
        "M8",
        "the cache read is dropped — the original defect, restored",
        "        _cached = _rc.get(_cache_key)\n"
        "        if _cached:\n"
        "            return _json.loads(_cached)\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "    now = datetime.now(timezone.utc)",
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "    now = datetime.now(timezone.utc)",
    ),
    # 🔴 M9 and M10 carry the KEY LINE in their anchors, and that is not padding.
    # Written against the read block alone they each matched TWICE — the block is
    # byte-identical to `team_progression`'s, which is the whole reason the
    # original defect was invisible to a reviewer. The harness reported them as
    # NOT APPLIED rather than skipping them, so the two-match was seen instead of
    # being quietly counted out of the denominator.
    (
        "M9",
        "the cached string is returned unparsed — the chips render as characters",
        '    _cache_key = "bainluck:search_suggestions:v1"\n'
        "    try:\n"
        "        _rc = get_redis_client()\n"
        "        _cached = _rc.get(_cache_key)\n"
        "        if _cached:\n"
        "            return _json.loads(_cached)",
        '    _cache_key = "bainluck:search_suggestions:v1"\n'
        "    try:\n"
        "        _rc = get_redis_client()\n"
        "        _cached = _rc.get(_cache_key)\n"
        "        if _cached:\n"
        "            return _cached",
    ),
    (
        "M10",
        "an unparseable slot 500s the route instead of rebuilding",
        '    _cache_key = "bainluck:search_suggestions:v1"\n'
        "    try:\n"
        "        _rc = get_redis_client()\n"
        "        _cached = _rc.get(_cache_key)\n"
        "        if _cached:\n"
        "            return _json.loads(_cached)\n"
        "    except Exception:\n"
        "        pass",
        '    _cache_key = "bainluck:search_suggestions:v1"\n'
        "    try:\n"
        "        _rc = get_redis_client()\n"
        "        _cached = _rc.get(_cache_key)\n"
        "        if _cached:\n"
        "            return _json.loads(_cached)\n"
        "    except KeyError:\n"
        "        pass",
    ),
    (
        "M11",
        "the TTL is widened to ten minutes — a baked countdown goes ten minutes wrong",
        '        _rc.setex(_cache_key, 60, _json.dumps(_response, default=str))',
        '        _rc.setex(_cache_key, 600, _json.dumps(_response, default=str))',
    ),
    # 🔴 M12's needle is a LITERAL multi-line string, not an escaped one, and
    # that is not a style choice. Its replacement is a single line, so the
    # replacement appears verbatim in this harness — and with an escaped needle
    # the needle does NOT, so `scan_mutation_residue.py` Pass B correctly
    # reported this file as holding a loose mutant. Writing the needle verbatim
    # too puts both halves in the file and clears the pair. Same lesson as
    # `cache_refresh_behind_mutations`' M5/M8, one queue later.
    (
        "M12",
        "the write is dropped — reads stay cold forever, the defect from the other side",
        """        _rc = get_redis_client()
        _rc.setex(_cache_key, 60, _json.dumps(_response, default=str))""",
        "        _rc = get_redis_client()",
    ),
    (
        "M13",
        "the slot is written with a payload that is not the one served",
        '        _rc.setex(_cache_key, 60, _json.dumps(_response, default=str))',
        '        _rc.setex(\n'
        '            _cache_key,\n'
        '            60,\n'
        '            _json.dumps({"suggestions": suggestions[:4]}, default=str),\n'
        "        )",
    ),
    (
        "M14",
        "the key is parameterised per process — one slot per worker, 2N rebuilds",
        '    _cache_key = "bainluck:search_suggestions:v1"',
        '    _cache_key = f"bainluck:search_suggestions:v1:{id(search_suggestions)}"',
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(SUITE), "-q", "--no-header", "-x"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [TARGET],
        "/tmp/lat_p124_search_suggestions_guard_backups",
        "search_suggestions_cold",
    ):
        return _main()


def _main() -> int:
    original = TARGET.read_text()

    # 🔴 THE DENOMINATOR IS PRINTED BEFORE THE FIRST VERDICT. A kill count with
    # no denominator in front of it is how a battery that skipped half its
    # mutants reads as a clean sweep.
    print(f"queued: {len(MUTANTS)} mutants against {TARGET.relative_to(ROOT)}")
    print(f"oracle: {SUITE.relative_to(ROOT)}\n")

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    print("baseline: suite GREEN on the unmutated tree\n")

    killed, survived, broken = [], [], []
    try:
        for mid, desc, old, new in MUTANTS:
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     anchor matched {n} times — NOT APPLIED, not a verdict"
                )
                continue
            TARGET.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            TARGET.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:4} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:4} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     pytest exit {rc} — the gate never ran (gotcha #54)"
                )
    finally:
        TARGET.write_text(original)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, desc in survived:
        print(f"  SURVIVOR {mid}: {desc}")
    if broken:
        for mid, why in broken:
            print(f"  BROKEN {mid}: {why}")
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
