#!/usr/bin/env python3
"""LAT-P138 — would the guard suite NOTICE if the prop-families tier stopped?

WHAT THE MUTANTS ARE FOR
------------------------
This ship has two halves and each has its own way of being wrong while looking
right.

**The predicate half.** `ILIKE ANY (ARRAY[...])` is faster than a 41-way `OR`
because Postgres plans it as one ScalarArrayOp index scan. It is faster STILL if
you also drop patterns, or stop escaping LIKE metacharacters, or narrow the
branch — and every one of those is a matching regression wearing a latency fix's
clothes. The endpoint's own numbers would improve. Half the mutants below pull
in that direction on purpose.

**The cache half.** A cache tier is the second-easiest thing here to ship broken
and never find out (a warmer is the first): the route answers 200 whether the
tier works or not, just 2.6-16.8 s instead of milliseconds, and the only symptom
is a slow page nobody is timing. Its failure modes — a key nobody reads, a
mirror never served, a rebuild dispatched per reader instead of once, a
statement timeout's empty page stored for 24 hours — all produce a healthy-
looking endpoint.

So the question is not "does the tier work". It is: **would
`tests/test_prop_families_cache_lat_p138.py` notice if it stopped?** A SURVIVOR
is a missing assertion, reported as such per mutant.

WHY THE ORACLE IS THE REAL SUITE, RUN OUT OF PROCESS
----------------------------------------------------
Re-implementing the assertions here would prove that this file's copy of them
still fails, which is worth nothing. The oracle runs the shipped pytest modules
against the mutated tree, so a mutant is killed only by an assertion that
genuinely ships. Both the new guard file AND the pre-existing contract test run:
a mutant that satisfies the new file while breaking `#1249`'s branch-split
contract is not killed, it is traded.

This harness mutates real files (its oracle is a pytest process), so it runs
inside `guarded_targets` — the shared SIGTERM-safe restore + breadcrumb manifest
from `_mutation_guard.py`. A run that dies mid-mutation announces itself instead
of leaving an edit that looks like somebody's work in progress.

Run from anywhere:  ``python3 backend/scripts/evals/prop_families_cache_mutations.py``

Exit codes (gotcha #54): `0` all mutants killed, `1` at least one SURVIVOR — a
real result, `2` the harness could not be run.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTE = ROOT / "app" / "routes" / "prop_families.py"
WARM = ROOT / "app" / "tasks" / "prop_families_warm.py"
WIRING = ROOT / "app" / "tasks" / "__init__.py"
VERDICT = ROOT / "app" / "utils" / "task_verdict.py"
TARGETS = [ROUTE, WARM, WIRING, VERDICT]

SUITE = ROOT / "tests" / "test_prop_families_cache_lat_p138.py"
CONTRACT = ROOT / "tests" / "integration" / "test_route_prop_families.py"
LEDGER = ROOT / "tests" / "test_tasks_wiring.py"

#: (id, target, description, old, new). `old` must appear EXACTLY once in its
#: target — a mutation that matches zero or many places is a harness bug,
#: reported as such and never counted as a kill.
MUTANTS: list[tuple[str, pathlib.Path, str, str, str]] = [
    # -- the predicate: put the defect back -----------------------------------
    (
        "M1",
        ROUTE,
        "revert the outcome branch to the 41-way OR — the 13,107 ms plan",
        "        branches.append((_BRANCH_OUTCOME_NAME, "
        "_ilike_any(FuturesOutcome.name, _team_pats)))",
        "        branches.append((_BRANCH_OUTCOME_NAME, "
        "or_(*[FuturesOutcome.name.ilike(p) for p in _team_pats])))",
    ),
    (
        "M2",
        ROUTE,
        "revert the market branch to the 41-way OR — the 2,990 ms plan",
        "        branches.append((_BRANCH_MARKET_NAME, "
        "_ilike_any(FuturesMarket.name, _team_pats)))",
        "        branches.append((_BRANCH_MARKET_NAME, "
        "or_(*[FuturesMarket.name.ilike(p) for p in _team_pats])))",
    ),
    # -- the predicate: go faster by answering less ---------------------------
    (
        "M3",
        ROUTE,
        "drop every roster pattern — 41 probes become 1 and the player props go "
        "with them. The endpoint gets 13 seconds faster and stops being correct.",
        """    _roster_pats: list[str] = [
        f"%{_escape_like(player)}%" for player in _roster_player_names(team)
    ]""",
        """    _roster_pats: list[str] = [
        f"%{_escape_like(player)}%" for player in []
    ]""",
    ),
    (
        "M4",
        ROUTE,
        "stop escaping LIKE metacharacters — a team called `100%` then matches "
        "the whole table",
        '        _team_pats.append(f"%{_escape_like(team.name.strip())}%")',
        '        _team_pats.append(f"%{team.name.strip()}%")',
    ),
    (
        "M5",
        ROUTE,
        "halve the roster cap — cheaper, and silently drops half the players",
        "_MAX_ROSTER_PATTERNS = 40",
        "_MAX_ROSTER_PATTERNS = 20",
    ),
    # -- the key --------------------------------------------------------------
    (
        "M6",
        ROUTE,
        "drop `cap` from the cache key — a `?limit=50` reader is served the "
        "400-row answer, or worse, poisons the key every browser reads",
        # 🔴 SPELLED CONTIGUOUSLY, NOT AS TWO IMPLICITLY-CONCATENATED FRAGMENTS.
        # `scan_mutation_residue`'s Pass B reads the harness FILE TEXT: a needle
        # split across two source lines is "absent" from this file while its
        # one-line replacement is present, which is precisely its
        # `repl present, needle absent` residue rule. LAT-P135 wrote that down,
        # LAT-P136 and LAT-P137 each re-learned it; it is fixed by spelling the
        # needle, never by narrowing the scan.
        '    return cache_keys(f"{int(team_id)}:{int(cap)}", prefix=PROP_FAMILIES_CACHE_PREFIX)',
        '    return cache_keys(f"{int(team_id)}", prefix=PROP_FAMILIES_CACHE_PREFIX)',
    ),
    (
        "M7",
        ROUTE,
        "collide with the typeahead namespace — `search_cache` made itself a "
        "SIBLING of that prefix on purpose so an operator clearing one surface "
        "with a glob cannot silently clear the other",
        # The collision namespace is `typeahead`, not `event_concept`, and that
        # is not a preference: `game_markets_shared_cache_mutations:M13` already
        # replaces a prefix with `"bainluck:event_concept:"`, so an identical
        # replacement here would sit in this file as a byte-for-byte copy of a
        # SIBLING harness's mutant and Pass B would report it as residue. That is
        # LAT-P136's finding, applied before the scan had to find it again.
        'PROP_FAMILIES_CACHE_PREFIX = "bainluck:prop_families:"',
        'PROP_FAMILIES_CACHE_PREFIX = "bainluck:typeahead:"',
    ),
    # -- the ladder -----------------------------------------------------------
    (
        "M8",
        ROUTE,
        "walk past the mirror on a miss and rebuild — the exact #1651 defect, "
        "with a 16.8 s rebuild behind it instead of a 2.7 s one",
        """    stale = read_slot(rc, keys.stale)
    if stale is not None:
        _schedule_refresh(rc, keys, team.id, cap)""",
        """    stale = read_slot(rc, keys.stale)
    if False:
        _schedule_refresh(rc, keys, team.id, cap)""",
    ),
    (
        "M9",
        ROUTE,
        "serve the mirror but never revalidate — the page freezes at 24h old and "
        "then falls off a cliff",
        """        _schedule_refresh(rc, keys, team.id, cap)
        return with_availability(stale, AVAILABILITY_STALE_OK)""",
        """        return with_availability(stale, AVAILABILITY_STALE_OK)""",
    ),
    (
        "M10",
        ROUTE,
        "dispatch without the single-flight lock — a burst of readers behind one "
        "expiry each buys its own multi-second rebuild",
        """    token = acquire_refresh_lock(rc, keys)
    if not token:
        return""",
        """    token = acquire_refresh_lock(rc, keys)
    if False:
        return""",
    ),
    (
        "M11",
        ROUTE,
        "leave the lock held when the dispatch fails — a dead broker wedges the "
        "key for REFRESH_LOCK_TTL and the next reader pays the rebuild",
        """        release_refresh_lock(rc, keys, token)


async def resolve_team""",
        """        pass


async def resolve_team""",
    ),
    (
        "M12",
        ROUTE,
        "raise the primary TTL to the mirror's — the payload is never rebuilt on "
        "a read again and the tier quietly loses its freshness half",
        "PROP_FAMILIES_PRIMARY_TTL = 900",
        "PROP_FAMILIES_PRIMARY_TTL = 86400",
    ),
    (
        "M13",
        ROUTE,
        "store the degraded build — a statement timeout's empty page goes behind "
        "the 24h mirror and the section is blank for a day",
        """    quality, reasons = take_build_quality(payload)
    if unusable:
        return payload, True""",
        """    quality, reasons = take_build_quality(payload)
    if False:
        return payload, True""",
    ),
    # -- the producer ---------------------------------------------------------
    (
        "M14",
        WARM,
        "warm a cap nobody asks for — every key write succeeds, the task reports "
        "complete, and the page is cold on every open (LAT-P001)",
        "WARM_CAP = 400",
        "WARM_CAP = 50",
    ),
    (
        "M15",
        WARM,
        "cap silently — the pass covers 200 of 207 and says nothing",
        "    truncated = max(0, selected - MAX_TEAMS_PER_PASS)",
        "    truncated = 0",
    ),
    (
        "M16",
        WARM,
        "rebuild even when a reader already holds the lock — the race the hub "
        "module warns a second producer would create, reopened, and it costs a "
        "duplicated multi-second build",
        """        token = acquire_refresh_lock(rc, keys)
        if not token:""",
        """        token = acquire_refresh_lock(rc, keys) or "unowned"
        if not token:""",
    ),
    (
        "M17",
        WARM,
        "a selection that blew up reads complete — `selected: 0` because nothing "
        "is reachable and `selected: 0` because the query died stop being "
        "different facts (gotcha #53)",
        '        return {"terminal": "failed", "selected": 0, "rebuilt": 0}',
        '        return {"terminal": "complete", "selected": 0, "rebuilt": 0}',
    ),
    (
        "M18",
        WARM,
        "a pass whose every build degraded reads complete — nothing was written, "
        "every mirror is as old as it was, and the pass claims success (#1884)",
        """    elif rebuilt or (locked_out and not failed):
        terminal = "complete\"""",
        """    elif True:
        terminal = "complete\"""",
    ),
    (
        "M18b",
        WARM,
        "never advance the cursor — every pass re-warms the same head and the "
        "tail of the list is never reached at all (gotcha #34)",
        """    if last_done is not None:
        _write_cursor(rc, last_done)""",
        """    if last_done is None:
        _write_cursor(rc, last_done)""",
    ),
    (
        "M18c",
        WARM,
        "ignore the cursor on read — same starvation, from the other end",
        """    cursor = _read_cursor(rc)
    start = 0""",
        """    cursor = -1
    start = 0""",
    ),
    (
        "M18d",
        WARM,
        "drop the budget check — the pass runs the whole list and a maxed-out "
        "reachable set walks straight through the soft limit into a SIGKILL",
        "        if time.monotonic() - started >= PASS_BUDGET_SECONDS:",
        "        if False:",
    ),
    (
        "M18e",
        WARM,
        "let one bad team wipe the pass — gotcha #42, on a loop where the "
        "survivors are the whole point",
        """        except Exception:
            # One bad team must never wipe the pass (gotcha #42).""",
        """        except ZeroDivisionError:
            # One bad team must never wipe the pass (gotcha #42).""",
    ),
    (
        "M19",
        WARM,
        "never release the refresh lock after a rebuild — one pass, then the team "
        "is un-warmable until the lock TTL lapses",
        """    finally:
        release_refresh_lock(rc, keys, token)""",
        """    finally:
        pass""",
    ),
    (
        "M20",
        WARM,
        "open the WEB process's session in a Celery task — 'attached to a "
        "different loop' at runtime, invisible to any test with the session "
        "patched out (LAT-P137 shipped this into a first draft)",
        # Anchored on the pair, not on the import alone: BOTH task functions
        # open a task session, so the single line matches twice and a harness
        # failure is not a kill.
        """    from app.tasks.base import get_task_session
    from app.utils.event_concept_cache import get_client, release_refresh_lock""",
        """    from app.services.database import async_session_maker as get_task_session
    from app.utils.event_concept_cache import get_client, release_refresh_lock""",
    ),
    (
        "M21",
        WARM,
        "unbound the inner rebuild — a wedged build runs past the task's soft "
        "limit and arrives as an untracked SIGKILL instead of a reported timeout",
        "PER_TEAM_TIMEOUT_SECONDS = 60",
        "PER_TEAM_TIMEOUT_SECONDS = 100000",
    ),
    # -- the beat -------------------------------------------------------------
    (
        "M22",
        WIRING,
        "drop the producer to every six hours — at the pessimistic build rate a "
        "maxed-out reachable set then needs 120 h to cover and teams go cold "
        "behind a 24 h mirror",
        '        "schedule": crontab(minute=53),',
        '        "schedule": crontab(minute=53, hour="*/6"),',
    ),
    (
        "M22b",
        WARM,
        "quarter the pass budget — the arithmetic stops closing and the coverage "
        "contract is broken without the cadence moving",
        "PASS_BUDGET_SECONDS = 180",
        "PASS_BUDGET_SECONDS = 40",
    ),
    (
        "M22c",
        WARM,
        "quadruple the cap — the same break from the other side: more teams to "
        "cover, same budget, same cadence",
        "MAX_TEAMS_PER_PASS = 200",
        "MAX_TEAMS_PER_PASS = 800",
    ),
    (
        "M23",
        VERDICT,
        "un-enrol the producer — its verdict goes back to a non-authoritative "
        "unknown and a pass that dispatched nothing reads GREEN",
        '    "warm_prop_families",              # terminal + selected + dispatched',
        '    # "warm_prop_families",            # terminal + selected + dispatched',
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(SUITE), str(CONTRACT), str(LEDGER),
            "-q", "--no-header", "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def _main() -> int:
    originals = {t: t.read_text() for t in TARGETS}

    print(f"denominator: {len(MUTANTS)} mutants queued")
    print(f"targets:     {' '.join(t.name for t in TARGETS)}")
    print(f"oracle:      {SUITE.name} + {CONTRACT.name} + {LEDGER.name}")

    baseline = _run_suite()
    print(
        f"baseline:    unmutated tree -> exit {baseline} "
        f"({'GREEN' if baseline == 0 else 'RED'})"
    )
    if baseline != 0:
        print("FATAL: baseline is not green; every 'killed' would be meaningless")
        return 2

    killed: list[str] = []
    survived: list[str] = []
    harness: list[str] = []

    for mid, target, desc, old, new in MUTANTS:
        original = originals[target]
        count = original.count(old)
        if count != 1:
            harness.append(mid)
            print(f"{mid:<5} HARNESS-FAIL  anchor matched {count}x in {target.name}")
            continue
        mutated = original.replace(old, new, 1)
        if mutated == original:
            harness.append(mid)
            print(f"{mid:<5} HARNESS-FAIL  replace was a no-op")
            continue
        target.write_text(mutated)
        # A mutation that fails to APPLY reports green and proves nothing.
        assert target.read_text() != original, f"{mid}: mutation did not reach disk"
        try:
            rc = _run_suite()
        finally:
            target.write_text(original)
        if rc != 0:
            killed.append(mid)
            print(f"{mid:<5} killed    {desc}")
        else:
            survived.append(mid)
            print(f"{mid:<5} SURVIVED  {desc}")

    for target in TARGETS:
        assert target.read_text() == originals[target], f"restore failed for {target}"
    print(f"restore:     all {len(TARGETS)} targets byte-identical")

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(harness)} harness failures"
    )
    if survived:
        print("SURVIVORS (each one is a missing assertion): " + ", ".join(survived))
    if harness:
        print("🔴 a harness failure is NOT a pass — the mutant never ran")
        return 2
    return 0 if not survived else 1


def main() -> int:
    with guarded_targets(
        TARGETS,
        "/tmp/lat_p138_prop_families_guard_backups",
        "prop_families_cache",
    ):
        return _main()


if __name__ == "__main__":
    sys.exit(main())
