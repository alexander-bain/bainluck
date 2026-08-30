"""LAT-P143 — the clause that changes no result and costs 13 seconds.

WHAT A MUTANT PROVES HERE
-------------------------
This ship's entire mechanism is two clauses on one statement: an `ORDER BY` and
a `LIMIT` on the typeahead outcome arm. Production, `EXPLAIN (ANALYZE, BUFFERS)`,
with those two clauses as the only difference:

    term         blocks OLD -> NEW        time OLD -> NEW
    win           273,637 -> 35,199      13,801 ms ->   477 ms
    yan            47,819 -> 30,476       5,771 ms ->   520 ms
    cremonese       1,196 ->    834         241 ms ->  16.6 ms

🔴 **AND THE ROWS ARE THE SAME ROWS.** That is the whole reason this file exists.
A `LIMIT 20` inside a query whose caller already applies `LIMIT 20` reads like
redundancy. An `ORDER BY` on what is only ever used as a set-membership arm reads
like a leftover from a copy-paste. Deleting either is the kind of tidy-up a
careful reader makes on a Friday, every behavioural test stays green, and the
dropdown goes back to timing out 43 times a day.

So the question is not "does the arm return the right markets". It is: **would
`tests/test_lat_p143_typeahead_outcome_arm.py` NOTICE if the fix were tidied
away?** A SURVIVOR is a missing assertion, reported as one.

THE TWO FAILURE DIRECTIONS, AND ONLY ONE OF THEM IS SLOW
--------------------------------------------------------
* **It stops helping.** The clauses go, the arm goes back inside the UNION, the
  two limits drift apart. Costs seconds and buffer traffic. Completely invisible
  to any test that asserts on results, because the results do not change.
* **It stops being honest.** A shed arm returns `[]` instead of `None` and the
  dropdown claims "no markets match" when it means "I could not look"; a shed
  answer is not marked degraded and gets cached for 65 s; the session is not
  recovered and every later stage dies; a real bug is swallowed as a timeout.
  Costs correctness, and some of these are *invisible in the fast direction* —
  they make things look better.

Both directions are represented below.

WHY THIS HARNESS WRITES TO DISK, WHEN `_mutation_guard` PREFERS THAT IT DID NOT
--------------------------------------------------------------------------------
The oracle's load-bearing assertions read `inspect.getsource(typeahead_search)`
and the compiled SQL, because the defect is a SHAPE and not a value. A mutant
exec'd into the module namespace leaves `inspect.getsource` reading the
unmutated file, so every structural guard would correctly decline to react and
every kill would be a false negative. The mutation has to be on disk to be seen.

It is therefore wrapped in `guarded_targets`, which restores on any exit a
process can observe, and every target is additionally SHA-256 compared against a
byte-for-byte backup at the end.

USAGE, from `backend/`:

    python3 scripts/evals/typeahead_outcome_arm_mutations.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mutation_guard import guarded_targets  # noqa: E402

EVALS = Path(__file__).resolve().parent
BACKEND = EVALS.parents[1]

#: The one file this ship edits.
TARGET = BACKEND / "app" / "routes" / "events.py"

#: The oracle. The shipped guard suite, run out of process against the mutated
#: file — never a re-implementation of its assertions here, which would only
#: prove that this file's copy of them still fails.
ORACLE = "tests/test_lat_p143_typeahead_outcome_arm.py"

MUTATES_WORKING_TREE = True

# (id, why it must die, needle, replacement)
MUTANTS: list[tuple[str, str, str, str]] = [
    # ------------------------------------------------------------------ #
    # Direction 1: it stops helping. Every one of these returns identical
    # rows and costs seconds.
    # ------------------------------------------------------------------ #
    (
        "M1-NO-ORDER-BY",
        "no ordering => no early termination => the whole match set is built again",
        """            .order_by(
                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume.desc().nulls_last(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
        """            .limit(_TYPEAHEAD_FUTURES_POOL)""",
    ),
    (
        "M2-NO-LIMIT",
        "the planner cannot stop early if nothing tells it how few rows are wanted",
        """            .limit(_TYPEAHEAD_FUTURES_POOL)
        )
    except Exception as exc:  # noqa: BLE001""",
        """        )
    except Exception as exc:  # noqa: BLE001""",
    ),
    (
        "M3-ORDERS-BY-ID",
        "ordered, cheap-looking, and a DIFFERENT twenty markets than the page wants",
        """                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume.desc().nulls_last(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
        """                FuturesMarket.id.asc(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
    ),
    (
        "M4-VOLUME-OUTRANKS-TIER",
        "the arm's top-20 is no longer a subset of the page's top-20 — recall change",
        """                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume.desc().nulls_last(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
        """                FuturesMarket.volume.desc().nulls_last(),
                FuturesMarket.market_tier.asc().nulls_last(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
    ),
    (
        "M5-NULLS-RULE-DROPPED",
        "untiered markets sort FIRST and displace the tier-1 markets the page keeps",
        """                FuturesMarket.market_tier.asc().nulls_last(),
                FuturesMarket.volume.desc().nulls_last(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
        """                FuturesMarket.market_tier.asc(),
                FuturesMarket.volume.desc(),
            )
            .limit(_TYPEAHEAD_FUTURES_POOL)""",
    ),
    (
        "M6-ARM-LIMIT-DRIFTS-FROM-PAGE-LIMIT",
        "a literal here silently narrows recall the day someone changes the page size",
        """            .limit(_TYPEAHEAD_FUTURES_POOL)
        )
    except Exception as exc:  # noqa: BLE001""",
        """            .limit(5)
        )
    except Exception as exc:  # noqa: BLE001""",
    ),
    (
        "M7-PAGE-LIMIT-DRIFTS-FROM-ARM-LIMIT",
        "the same drift from the other end — a bare literal on the final query",
        "        .limit(_TYPEAHEAD_FUTURES_POOL)\n    )\n    # LAT-P007: bound the one expensive stage",
        "        .limit(20)\n    )\n    # LAT-P007: bound the one expensive stage",
    ),
    (
        "M8-RESOLVED-IDS-NEVER-FOLDED-IN",
        "the arm runs, costs its time, and its markets never reach the dropdown",
        "                ta_futures_where.append(FuturesMarket.id.in_(_ta_outcome_ids))",
        "                pass",
    ),
    (
        "M9-TRIGRAM-GATE-DROPPED",
        "LAT-P010/P013's sub-trigram skip lost in the move — `%re%` seq-scans 3 GB again",
        "    if _has_extractable_trigram(_ta_q_compact):\n        _ta_outcome_arm = FuturesMarket.id.in_(",
        "    if True:\n        _ta_outcome_arm = FuturesMarket.id.in_(",
    ),
    (
        "M10-OPEN-FILTER-DROPPED-FROM-THE-ARM",
        "the ordering walk is only cheap because it walks the OPEN set",
        "            .where(arm, *open_now)",
        "            .where(arm)",
    ),
    # ------------------------------------------------------------------ #
    # Direction 2: it stops being honest.
    # ------------------------------------------------------------------ #
    (
        "M11-BOUND-IGNORES-THE-REQUEST-DEADLINE",
        "an arm budget that can outlive the request deadline protects nothing",
        "    bound_ms = min(_TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS, remaining_ms)",
        "    bound_ms = _TYPEAHEAD_OUTCOME_ARM_TIMEOUT_MS",
    ),
    (
        "M12-NO-FLOOR-CHECK",
        "starts a statement it already intends to cancel, on a request with no time",
        "    if bound_ms < _SEARCH_MIN_STAGE_TIMEOUT_MS:\n        return None\n",
        "",
    ),
    (
        "M13-NO-STATEMENT-TIMEOUT",
        "no SET LOCAL: the arm is unbounded again and rides the request deadline",
        '        await db.execute(text(f"SET LOCAL statement_timeout = {int(bound_ms)}"))',
        "        pass",
    ),
    (
        "M14-SHED-LOOKS-LIKE-NO-MATCHES",
        "`[]` says 'no market matches'. The truth is 'I could not look'.",
        "        await _recover_search_session(db, deadline)\n        return None",
        "        await _recover_search_session(db, deadline)\n        return []",
    ),
    (
        "M15-NO-SESSION-RECOVERY",
        "a timed-out statement aborts the transaction — every later stage then dies",
        "        await _recover_search_session(db, deadline)\n        return None",
        "        return None",
    ),
    (
        "M16-SWALLOWS-REAL-BUGS-AS-TIMEOUTS",
        "a genuine exception laundered into a quietly narrower dropdown",
        "        if not _is_query_timeout(exc):\n            raise\n        await _recover_search_session(db, deadline)",
        "        await _recover_search_session(db, deadline)",
    ),
    (
        "M17-SHED-ANSWER-IS-CACHED",
        "an incomplete dropdown pinned into Redis for 65 s — LAT-P007's exact defect",
        "            _ta_degraded = True\n        else:\n            _ta_mark(\"futures_outcome_arm\")",
        "            _ta_degraded = False\n        else:\n            _ta_mark(\"futures_outcome_arm\")",
    ),
    (
        "M18-COMPLETE-ANSWER-MARKED-DEGRADED",
        "matching no market is a COMPLETE answer; marking it degraded kills the cache",
        "        else:\n            _ta_mark(\"futures_outcome_arm\")",
        "        else:\n            _ta_degraded = True\n            _ta_mark(\"futures_outcome_arm\")",
    ),
    (
        "M19-DOUBLE-MARK-HIDES-THE-ARM-COST",
        "two marks on one path attribute the arm's whole cost to the SUCCESS label",
        '            _ta_mark("futures_outcome_arm_SHED")',
        '            _ta_mark("futures_outcome_arm")\n            _ta_mark("futures_outcome_arm_SHED")',
    ),
    (
        "M20-EVENTS-ASSEMBLE-SWALLOWS-THE-ARM",
        "mark it after the arm and the arm's seconds vanish into the previous stage",
        '    _ta_degraded = False\n    _ta_mark("events_assemble")\n    if _ta_outcome_arm is not None:',
        "    _ta_degraded = False\n    if _ta_outcome_arm is not None:",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_oracle() -> bool:
    """True when the guards PASS — i.e. the mutant SURVIVED."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", ORACLE, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    # Gotcha #54: read the exit code's VALUE. `1` is a result (tests failed);
    # anything else is a story about the harness and must not be scored.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"pytest exited {proc.returncode} — the oracle never ran:\n"
            f"{proc.stdout[-3000:]}\n{proc.stderr[-2000:]}"
        )
    return proc.returncode == 0


def main() -> int:
    if not TARGET.is_file():
        print(f"FAIL: missing target {TARGET}", file=sys.stderr)
        return 2

    original_sha = sha256(TARGET)
    original_text = TARGET.read_text()

    print("LAT-P143 mutation battery — the clause that changes no result")
    print(f"target  : {TARGET.relative_to(BACKEND)}")
    print(f"oracle  : {ORACLE}")
    print(f"mutants : {len(MUTANTS)}\n")

    killed, survived, broken = 0, [], []

    # Backups namespaced by WORKTREE: /tmp is shared across worktrees and a
    # battery here must never restore a sibling's file.
    tag = hashlib.sha256(str(BACKEND).encode()).hexdigest()[:12]
    backup = Path(f"/tmp/lat_p143_{tag}_events.py.bak")

    with guarded_targets([TARGET], backup, "lat_p143_typeahead_outcome_arm"):
        if not run_oracle():
            print("FAIL: the guards are RED before any mutation was applied.")
            return 2
        print("baseline: guards green on the unmutated tree\n")

        for mid, why, needle, replacement in MUTANTS:
            source = TARGET.read_text()
            occurrences = source.count(needle)
            if occurrences != 1:
                print(f"  {mid:<40} HARNESS FAIL — anchor appears {occurrences}x, need 1")
                broken.append(mid)
                continue

            TARGET.write_text(source.replace(needle, replacement, 1))
            if sha256(TARGET) == original_sha:
                print(f"  {mid:<40} HARNESS FAIL — edit did not change the file")
                broken.append(mid)
                TARGET.write_text(source)
                continue

            try:
                mutant_survived = run_oracle()
            finally:
                TARGET.write_text(source)
                if sha256(TARGET) != original_sha:
                    raise RuntimeError("restore did not match the original")

            if mutant_survived:
                print(f"  {mid:<40} SURVIVED  <-- {why}")
                survived.append((mid, why))
            else:
                killed += 1
                print(f"  {mid:<40} killed")

    if TARGET.read_text() != original_text or sha256(TARGET) != original_sha:
        print("FAIL: target not restored byte-for-byte", file=sys.stderr)
        return 2

    print(
        f"\n{killed}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(broken)} harness failures"
    )
    for mid, why in survived:
        print(f"  SURVIVOR {mid}: {why}")
    if broken:
        print("  harness failures make this run INCONCLUSIVE, not clean.")
    return 0 if (not survived and not broken) else 1


if __name__ == "__main__":
    sys.exit(main())
