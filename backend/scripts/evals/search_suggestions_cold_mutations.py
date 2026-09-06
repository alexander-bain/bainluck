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
        "        movers_rows = []\n        if not _section_full(3):",
        "        movers_rows = []\n        if False:",
    ),
    (
        "M2",
        "section 3 never skips — the no-op 'fix', 1.14 GB back on every request",
        "        movers_rows = []\n        if not _section_full(3):",
        "        movers_rows = []\n        if True:",
    ),
    (
        "M3",
        "section 2 never skips",
        "        soon_rows = []\n        if not _section_full(2):",
        "        soon_rows = []\n        if True:",
    ),
    (
        "M4",
        "section 4 never skips",
        "        upsets_rows = []\n        if not _section_full(4):",
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
    # ---------------------------------------------------------------------
    # M8-M14 — THE CACHE HALF, RE-TARGETED BY LAT-P139 RATHER THAN RETIRED.
    #
    # Every one of these was written against the inline `_cache_key` / `_rc` /
    # `_json` block that used to live in `search_suggestions`. LAT-P139 replaced
    # that block with `utils/search_suggestions_cache` plus a mirror, so all
    # seven anchors drifted at once and `scan_mutation_residue.py` reported them
    # — which is the scanner doing its job, and the reason it is a gate.
    #
    # 🔴 THEY ARE RE-POINTED, NOT DELETED, AND THE PROPERTY IS WHAT IS PRESERVED.
    # Deleting a mutant because its anchor moved is how a battery quietly stops
    # covering the thing it was written for; LAT-P115's note ("a survivor is the
    # finding, not the mutant's fault") cuts the same way for drift. Each id
    # below keeps its original PROPERTY and gets the shape that property lives in
    # now. Two of them changed meaning where the new design changed the question,
    # and each says so on its own line.
    #
    # The oracle now runs BOTH route suites (see `SUITES`), because the mirror's
    # serve decision is pinned in the LAT-P139 file and the skip in the LAT-P124
    # one, and a route mutant should be graded by everything that guards the
    # route.
    # ---------------------------------------------------------------------
    (
        "M8",
        "the cache read is dropped — the original defect, restored",
        """    body, state = ssc.read()
    if state == "live" and body is not None:
        return body""",
        """    body, state = ssc.read()
    if False:
        return body""",
    ),
    (
        "M9",
        "the mirror is served with NO rebuild behind it — LAT-P139's meaning of "
        "M9's old property (a serve path that returns something it should not) "
        "on the new design: the stale copy is handed out until it ages past the "
        "ceiling and nothing is ever scheduled to replace it",
        # 🔴 THE ANCHOR CARRIES `ssc.read()` BECAUSE THE LINE BELOW IT IS NOT
        # UNIQUE. `if state == "live" and body is not None:` appears three times
        # in this file — the two event-page tiers read exactly the same way, on
        # purpose. The harness reported the three-match as NOT APPLIED rather
        # than mutating an unrelated tier, which is the same protection M9 and
        # M10 needed against `team_progression` before LAT-P139 moved them.
        """    body, state = ssc.read()
    if state == "live" and body is not None:""",
        """    body, state = ssc.read()
    if state in ("live", "stale_ok") and body is not None:""",
    ),
    (
        "M10",
        "the stale copy is served even when NOTHING can rebuild behind it — the "
        "fail-closed half removed. This is the new shape of M10's old property "
        "(a slot the route should have rejected reaching the reader): with no "
        "running loop the mirror would be served forever and never replaced",
        """        if _serve_stale_and_refresh(
            "search_suggestions", _rebuild_search_suggestions
        ):
            return body""",
        """        _serve_stale_and_refresh(
            "search_suggestions", _rebuild_search_suggestions
        )
        return body""",
    ),
    # 🔴 M11 AND M14 EMIGRATED. They are the only two of the seven whose property
    # is no longer a property of THIS FILE: the TTL and the key name moved into
    # `app/utils/search_suggestions_cache.py` with the tier. A mutant has to be
    # applicable to its harness's target, and this harness's target is
    # `routes/events.py`; pointing them at a second file would need the
    # two-target `SHAPES` shape for two entries, which is more machinery than
    # the facts justify.
    #
    # They are NOT dropped — they are re-homed one for one, and both are proven
    # KILLED in their new battery on the run that shipped this change:
    #
    #     M11 "the TTL is widened"      -> search_suggestions_mirror_mutations
    #                                      :the-fresh-ttl-is-widened
    #     M14 "the key is per-process"  -> search_suggestions_mirror_mutations
    #                                      :the-primary-key-is-renamed
    #
    # The denominator below therefore reads 12, not 14, and that is a move and
    # not a loss. If either line above stops being true, this comment is the
    # thing that makes the hole findable.
    (
        "M12",
        "the write is dropped — reads stay cold forever, the defect from the other side",
        """    enveloped = jsonable_encoder(ssc.stamp(response))
    ssc.write(enveloped)""",
        """    enveloped = jsonable_encoder(ssc.stamp(response))""",
    ),
    (
        "M13",
        "the slot is written with a payload that is not the one served",
        """    enveloped = jsonable_encoder(ssc.stamp(response))
    ssc.write(enveloped)""",
        """    enveloped = jsonable_encoder(ssc.stamp(response))
    ssc.write(jsonable_encoder(ssc.stamp({"suggestions": response["suggestions"][:4]})))""",
    ),
    # ---------------------------------------------------------------------
    # M15-M18 — #3685's HALF. The row stops being four AAA baseball games.
    #
    # Each of these is a plausible edit rather than a vandalism: three of the
    # four are what a later author would write if they had not read the comment
    # above the budget table, and the fourth is the shape the first draft of
    # this change actually had.
    # ---------------------------------------------------------------------
    (
        "M15",
        "section 1 is given the whole timely allowance — the row goes back to "
        "being one section's, which is what production actually served",
        "_SUGGESTION_SECTION_BUDGETS = {1: 3, 2: 2, 3: 1, 4: 1}",
        "_SUGGESTION_SECTION_BUDGETS = {1: 5, 2: 2, 3: 1, 4: 1}",
    ),
    (
        "M19",
        "the backfill reserve is sized to today's exact volume ranking — "
        "CERT-2138's finding restored: the row reaches Presidential Election "
        "Winner 2028 and stops one short of the US Open market it is named for",
        "_SUGGESTION_BACKFILL_RESERVE = 3",
        "_SUGGESTION_BACKFILL_RESERVE = 1",
    ),
    (
        "M20",
        "the reserve is applied TO the backfill instead of FOR it — section 5 "
        "can no longer fill the slots that were held open for it",
        """        if budget is None:""",
        """        if budget is None and False:""",
    ),
    (
        "M16",
        "the per-section half of the predicate is dropped — every section is "
        "back to being bounded only by the shared window, which is exactly the "
        "state the row was in on production",
        """        if section_used[section] >= budget:
            return True""",
        """        if section_used[section] >= _MAX_SUGGESTIONS:
            return True""",
    ),
    (
        "M17",
        "the tier gate comes off section 1 — AAA baseball and ninth-tier "
        "non-league football are candidates for the row again",
        """                Event.status == "live",
                Sport.key.in_(tier_12_keys),""",
        """                Event.status == "live",""",
    ),
    (
        "M18",
        "the budget is spent on the CANDIDATE rather than on the add, so two "
        "live games with the same shorter team name silently shrink the section",
        """        if key in seen_queries:
            return""",
        """        if key in seen_queries:
            if section in section_used:
                section_used[section] += 1
            return""",
    ),
]


#: LAT-P139: the oracle is BOTH route suites, not one.
#:
#: The route's guards are split across two files now — the skip and the window
#: constant in the LAT-P124 suite, the mirror's serve decision and the one-writer
#: rule in the LAT-P139 one — and a mutant of the route should be graded by
#: everything that guards the route. Running only the first would have let M8,
#: M9 and M10 survive against assertions that exist three directories away, and
#: a survivor that is really "the oracle was not looking" is the worst output
#: this battery can produce.
SUITES = [
    SUITE,
    ROOT / "tests" / "test_search_suggestions_mirror_lat_p139.py",
    # #3685: the tier gate and the per-section budget are guarded in their own
    # file, and M15-M18 are mutants of exactly those two mechanisms. Leaving it
    # out would reproduce the LAT-P139 mistake this list was written to fix —
    # a survivor that is really "the oracle was not looking".
    ROOT / "tests" / "test_search_suggestions_tier_and_budget_3685.py",
]


def _run_suite() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *[str(s) for s in SUITES], "-q", "--no-header", "-x"],
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
    print(
        "oracle: "
        + ", ".join(str(s.relative_to(ROOT)) for s in SUITES)
        + "\n"
    )

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
