#!/usr/bin/env python3
"""LAT-P145 mutation battery: a branch timeout must not erase the other branches.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way a later edit could put the defect
back — and most of them read as a tidy-up, which is exactly why they are here.
A SURVIVOR is a hole in the suite and the fix is to add the missing assertion,
never to delete the mutant (LAT-P115's M7 survived and the survivor WAS the
finding).

The defect this pins, in one line: three branch queries shared one transaction
and one `SET LOCAL statement_timeout`, so the expiry of branch 2 lost branch 2's
rows, branch 3's turn, AND branch 1's rows — which had already been fetched. The
empty payload that came out was then correctly never cached, so every subsequent
reader paid the same 12 s for the same nothing. Measured on three NFL team pages,
production `944c466e`.

Two files are mutated, because the ship spans two:

  app/routes/prop_families.py        the branch loop, the quality call, the
                                     write decision and the mirror guard
  app/utils/event_concept_cache.py   `write_payload(mirror=…)`, which is the
                                     half that keeps a partial off a complete
                                     mirror

🔴 THREE SURVIVORS ON THE FIRST RUN, AND ALL THREE WERE EQUIVALENT MUTANTS.
Recorded rather than deleted, because "the suite has a hole" and "this mutation
cannot change behaviour" look identical from the exit code, and the next battery
will meet the same three shapes.

  M14 (was) dropped the cross-branch `_seen_oids` dedup, expecting one outcome to
      appear once per branch. It cannot be observed: `group_prop_families`
      collapses rows by entity through `_collapse_cross_source`, and a duplicate
      outcome id is the SAME database row, so it collapses onto itself. Measured
      directly — the same fixture deduped and tripled both produce
      `{n: 2, entity_count: 2, rows: [(Brian Burns, 0.06), (Dexter Lawrence,
      0.04)]}`. The dedup bounds WORK, not output; it is not a correctness
      property and no assertion could make it one. Replaced by a reachable mutant
      on the route's serve decision.

  M17 (was) made an envelope-less mirror read as `full`. Unreachable: the
      `if not isinstance(stored, dict): return False` guard above it returns
      first, and `read_slot` never yields a dict without a valid envelope — it
      rejects those as a miss. Re-pointed at that earlier guard, where the same
      property ("no mirror is not a full mirror") IS reachable, and it dies.

  M21 (was) moved `take_build_quality` below the `unusable` early return. Also
      unreachable: `build_prop_families` returns its total-loss payload from a
      branch that never records a loss, so there is nothing on it to leak.
      Re-pointed at the pop ITSELF in the shared module — `.pop` to `.get` —
      which is where the leak property actually lives, and it dies.

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

Both halves of every mutant are VERBATIM literals, never `\\n`-escaped ones.
`scan_mutation_residue.py` Pass B flags a file holding a REPLACEMENT whose NEEDLE
is absent, and an escaped needle is absent by construction.

Run:  python3 backend/scripts/evals/prop_families_partial_mutations.py
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
ROUTE = ROOT / "app" / "routes" / "prop_families.py"
CACHE = ROOT / "app" / "utils" / "event_concept_cache.py"
SUITE = ROOT / "tests" / "test_prop_families_partial_lat_p145.py"
CONTRACT = ROOT / "tests" / "test_prop_families_cache_lat_p138.py"

#: 🔴 A NEEDLE THAT APPLIES IS NOT A NEEDLE THAT CATCHES, AND M14 PROVED IT
#: (CERT-557). LAT-P164 re-pointed M14 at its OWN new line — the cold reader's
#: `budget_ms=_READER_BUDGET_MS` — and the mutant applied cleanly, so the residue
#: scanner was satisfied and nothing local complained. It also SURVIVED every
#: run, because the assertion that kills it
#: (`test_the_route_passes_the_reader_budget_and_not_something_else`) lives in
#: LAT-P164's own file and this harness never ran that file. A mutant pointed at
#: new code by a queue that did not enrol the queue's own suite is a guard that
#: catches nothing, reported as a pass.
#:
#: So the runner takes every suite that owns a line this harness mutates. The
#: rule, for whoever extends it next: **if you re-point a needle at a line your
#: queue added, add your queue's suite here in the same edit.**
BUDGET_SUITE = ROOT / "tests" / "test_prop_families_reader_budget_lat_p164.py"
COMPLETION_SUITE = ROOT / "tests" / "test_prop_families_completion_cert557.py"

#: (id, description, old, new, target). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill. The target is carried PER ENTRY
#: (the `game_markets_shared_cache_mutations` shape) because this table spans
#: two modules.
MUTANTS: list[tuple[str, str, str, str, pathlib.Path]] = [
    (
        "M1",
        "a lost branch ends the loop — branch 3 never gets its turn again",
        """            lost.append(_name)
            continue""",
        """            lost.append(_name)
            break""",
        ROUTE,
    ),
    (
        "M2",
        "drop the rollback — the next branch inherits an aborted transaction",
        """            try:
                await db.rollback()
            except Exception:""",
        """            try:
                pass
            except Exception:""",
        ROUTE,
    ),
    (
        "M3",
        "ANY loss is unusable again — the pre-P145 whole-request degrade",
        """    if len(lost) + len(deferred) == len(branches):
        return _payload([]), True""",
        """    if lost:
        return _payload([]), True""",
        ROUTE,
    ),
    (
        "M4",
        "set the timeout once, before the loop — branches 2 and 3 run unbounded",
        """            await db.execute(text(f"SET LOCAL statement_timeout = '{_timeout_ms}'"))
            _result = (await db.execute(_branch(_cond))).all()""",
        """            _result = (await db.execute(_branch(_cond))).all()""",
        ROUTE,
    ),
    (
        "M5",
        "record the loss as COSMETIC — a partial then publishes `quality: full`",
        # CERT-557 re-target: the reason string moved behind `_REASON_TIMEOUT`,
        # which is the whole point of that constant (one spelling, so the
        # deferral/timeout bound cannot be broken by a typo). The needle follows
        # the code; the MUTATION is unchanged in meaning and still kills.
        """        note_build_loss(payload, f"{_REASON_TIMEOUT}{_name}", LOSS_PARTIAL)""",
        """        note_build_loss(payload, f"{_REASON_TIMEOUT}{_name}", "cosmetic")""",
        ROUTE,
    ),
    (
        "M6",
        "do not record the loss at all — the payload lies about being complete",
        """    for _name in lost:""",
        """    for _name in []:""",
        ROUTE,
    ),
    (
        "M7",
        "the branch name drops out of the reason — 'something timed out, unknown what'",
        # CERT-557 re-target, same move as M5.
        """        note_build_loss(payload, f"{_REASON_TIMEOUT}{_name}", LOSS_PARTIAL)""",
        """        note_build_loss(payload, _REASON_TIMEOUT, LOSS_PARTIAL)""",
        ROUTE,
    ),
    (
        "M8",
        "a partial overwrites a complete mirror — a warmed team loses its content",
        """    if not mirror_is_full and not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):""",
        """    if not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):""",
        ROUTE,
    ),
    (
        "M9",
        "a partial never gets a mirror — the Giants go cold again every 15 minutes",
        """    if not mirror_is_full and not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):""",
        """    if False and not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):""",
        ROUTE,
    ),
    (
        "M10",
        "cache an EMPTY partial — a blank section frozen for 24h (gotcha #53)",
        """    if not payload.get("families"):""",
        """    if False:""",
        ROUTE,
    ),
    (
        "M11",
        "stamp every build `full` — the enum stops meaning anything",
        """        quality=quality,
        quality_reasons=reasons,""",
        """        quality=QUALITY_FULL,
        quality_reasons=reasons,""",
        ROUTE,
    ),
    (
        "M12",
        "read the team's fields live at assembly time — the gotcha #6 lazy load",
        """            "team": {"id": _team_id, "name": _team_name, "slug": _team_slug},""",
        """            "team": {"id": team.id, "name": team.name, "slug": getattr(team, "slug", None)},""",
        ROUTE,
    ),
    (
        "M13",
        "every error is filed as a budget expiry — a real query bug goes quiet",
        """            if is_statement_timeout(exc):""",
        """            if True:""",
        ROUTE,
    ),
    (
        "M14",
        "a total loss is served as a normal build — an empty page grows an envelope",
        """    payload, degraded = await build_and_cache_prop_families(
        team, db, cap, rc, budget_ms=_READER_BUDGET_MS
    )""",
        """    payload, degraded = await build_and_cache_prop_families(
        team, db, cap, rc, budget_ms=None
    )""",
        ROUTE,
    ),
    (
        "M15",
        "halve the branch budget — the ship buys its win by failing more builds",
        """_BRANCH_TIMEOUT_MS = 12000""",
        """_BRANCH_TIMEOUT_MS = 6000""",
        ROUTE,
    ),
    (
        "M16",
        "a partial with rows reports degraded — the route re-serves the mirror "
        "and the warmer counts a healthy build as failed",
        """            team.id, ",".join(reasons),
        )
    return stamped, False""",
        """            team.id, ",".join(reasons),
        )
    return stamped, True""",
        ROUTE,
    ),
    (
        "M17",
        "NO mirror counts as a full one — a partial then refuses to write the only "
        "answer there is, and the page stays uncacheable",
        """    if not isinstance(stored, dict):
        return raw, False""",
        """    if not isinstance(stored, dict):
        return raw, True""",
        ROUTE,
    ),
    (
        "M18",
        "`mirror=False` writes the mirror anyway — the flag becomes decoration",
        """        rc.setex(keys.primary, primary_ttl, encoded)
        if mirror:
            rc.setex(keys.stale, STALE_TTL, encoded)""",
        """        rc.setex(keys.primary, primary_ttl, encoded)
        if True:
            rc.setex(keys.stale, STALE_TTL, encoded)""",
        CACHE,
    ),
    (
        "M19",
        "flip the default — every OTHER customer of the tier silently loses its mirror",
        """    primary_ttl: int = ENVELOPE_TTL,
    mirror: bool = True,""",
        """    primary_ttl: int = ENVELOPE_TTL,
    mirror: bool = False,""",
        CACHE,
    ),
    (
        "M20",
        "`mirror=False` also skips the negative clear — a resolving key keeps its 404",
        """        if mirror:
            rc.setex(keys.stale, STALE_TTL, encoded)
        # A key that now resolves must not keep a negative entry behind it.
        rc.delete(keys.negative)""",
        """        if mirror:
            rc.setex(keys.stale, STALE_TTL, encoded)
            # A key that now resolves must not keep a negative entry behind it.
            rc.delete(keys.negative)""",
        CACHE,
    ),
    (
        "M21",
        "read the losses without popping them — `_build_losses` reaches Redis and "
        "the wire as an undeclared public field",
        """    losses = result.pop(BUILD_LOSS_FIELD, None)""",
        """    losses = result.get(BUILD_LOSS_FIELD, None)""",
        CACHE,
    ),
    # --- CERT-480 finding 1: the mirror decision must be atomic --------------
    (
        "M22",
        "the caller judges the mirror, then RE-READS it to write — two round trips "
        "is the check-then-act CERT-480 blocked, restored",
        """    mirror_raw, mirror_is_full = _stored_mirror(rc, keys)""",
        """    mirror_is_full = _mirror_is_full(rc, keys)
    mirror_raw = _stored_mirror(rc, keys)[0]""",
        ROUTE,
    ),
    (
        "M23",
        "the compare-and-set is anchored to `None` instead of the bytes that were "
        "judged — a fresher partial can never replace a stale one",
        """    if not mirror_is_full and not publish_mirror_if_unchanged(
        rc, keys, stamped, mirror_raw
    ):""",
        """    if not mirror_is_full and not publish_mirror_if_unchanged(
        rc, keys, stamped, None
    ):""",
        ROUTE,
    ),
    (
        "M24",
        "the absent-key precondition collapses into the byte comparison — the "
        "Giants' empty slot stops matching and never gets its first mirror",
        """            "1" if expected is None else "0",""",
        """            "0",""",
        CACHE,
    ),
    (
        "M25",
        "an unrunnable compare-and-set reports success — the caller believes a "
        "write happened that did not",
        """        logger.warning(
            "event-concept cache: conditional write failed for %s; leaving it alone", key
        )
        return False""",
        """        logger.warning(
            "event-concept cache: conditional write failed for %s; leaving it alone", key
        )
        return True""",
        CACHE,
    ),
    (
        "M26",
        "unreadable mirror bytes are reported as NO bytes — the conditional write "
        "then demands an absent key and a corrupt mirror becomes permanent",
        """    payload = decode_payload(raw)
    if payload is None:
        return raw, None""",
        """    payload = decode_payload(raw)
    if payload is None:
        return None, None""",
        CACHE,
    ),
    (
        "M27",
        "the Lua guard is deleted and the script writes unconditionally — the "
        "atomicity is decoration",
        """local current = redis.call('get', KEYS[1])
if ARGV[1] == '1' then
    if current then return 0 end
elseif current ~= ARGV[2] then
    return 0
end
redis.call('setex', KEYS[1], ARGV[3], ARGV[4])
return 1""",
        """redis.call('setex', KEYS[1], ARGV[3], ARGV[4])
return 1""",
        CACHE,
    ),
]


def _run_suite() -> int:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            str(CONTRACT),
            str(BUDGET_SUITE),
            str(COMPLETION_SUITE),
            "-q",
            "--no-header",
            "-x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    with guarded_targets(
        [ROUTE, CACHE],
        "/tmp/lat_p145_prop_families_partial_guard_backups",
        "prop_families_partial",
    ):
        return _main()


def _main() -> int:
    originals = {ROUTE: ROUTE.read_text(), CACHE: CACHE.read_text()}

    print(
        f"denominator: {len(MUTANTS)} mutants queued against "
        f"{ROUTE.name} + {CACHE.name}"
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
        for mid, desc, old, new, target in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times, expected exactly 1"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                broken.append((mid, "replacement is a no-op — NOT APPLIED"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED")
                continue
            target.write_text(mutated)
            # Prove the mutation is actually on disk before believing its result:
            # a mutant that failed to apply reports a green suite as a survivor.
            if target.read_text() != mutated:
                target.write_text(original)
                broken.append((mid, "write-back verification failed"))
                print(f"{mid:5} HARNESS  {desc}\n      NOT APPLIED on disk")
                continue
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
            if rc == 0:
                survived.append((mid, desc))
                print(f"{mid:5} SURVIVED {desc}")
            elif rc == 1:
                killed.append(mid)
                print(f"{mid:5} killed   {desc}")
            else:
                broken.append((mid, f"pytest exit {rc}"))
                print(
                    f"{mid:5} HARNESS  {desc}\n"
                    f"      pytest exit {rc} — the gate never ran"
                )
    finally:
        for path, text in originals.items():
            path.write_text(text)

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
