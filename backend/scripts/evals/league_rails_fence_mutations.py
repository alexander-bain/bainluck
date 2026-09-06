#!/usr/bin/env python3
"""RED-prove `tests/test_league_rails_query_plan.py` — LAT-P110, #2260.

A guard that has never been seen to fail is a guard nobody has tested. This
harness applies each mutation ALONE from a `cp` backup, runs the suite, requires
it to go RED, then restores and **sha256-verifies the restore** before the next
one — because a mutation that silently fails to revert turns every later result
into a lie (memory: a mutation must prove it applied).

Two ways this harness refuses rather than reporting a kill:

* a needle that does not appear EXACTLY ONCE in its file is an UNAPPLIED
  mutation, not a kill — the source moved and the harness is measuring nothing;
* a restore whose sha256 does not match the pristine copy aborts the whole run.

The per-mutant `cp`/sha256 loop is this harness's own bookkeeping and is NOT the
crash guard. That is `_mutation_guard.guarded_targets`, wrapped around the whole
run: `try/finally` does not survive SIGTERM (Python's default disposition
terminates without raising), which is how a mutant rode `bcdcd95f` into a branch
for a full cycle. `tests/test_mutation_guard.py` pins both halves, and its
`test_every_on_disk_harness_is_guarded` is what caught this file for opting out
— on the first full-suite run of the branch that added it.

Run from `backend/`:  python3 scripts/evals/league_rails_fence_mutations.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _mutation_guard import guarded_targets  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
ROUTE = BACKEND / "app" / "routes" / "league_futures.py"
SUITE = "tests/test_league_rails_query_plan.py"

#: (id, file, needle, replacement, why this must kill)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "M1-fence-removed",
        ROUTE,
        # Anchored on the settled rail's own condition since #3211 — both fenced
        # rails carry these two lines verbatim, so the bare pair stopped being
        # unique the moment the third rail landed. M1b covers the other one.
        "            settled_rail_condition("
        "now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),\n"
        "        )\n"
        '        .offset(literal_column("0"))\n        .subquery()',
        "            settled_rail_condition("
        "now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),\n"
        "        )\n"
        "        .subquery()",
        "the whole fix: without OFFSET 0 the planner walks ix_events_commence_time",
    ),
    (
        "M1b-unreported-fence-removed",
        ROUTE,
        "            unreported_rail_condition(\n"
        "                now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)\n"
        "            ),\n"
        "        )\n"
        '        .offset(literal_column("0"))\n        .subquery()',
        "            unreported_rail_condition(\n"
        "                now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)\n"
        "            ),\n"
        "        )\n"
        "        .subquery()",
        "#3211's rail inherited the measurement, so it inherits the guard",
    ),
    (
        "M2-fence-is-a-bind",
        ROUTE,
        # 🔴 ANCHORED ON THE SETTLED RAIL'S OWN CALL by #3211. The bare
        # `.offset(literal_column("0"))` now appears TWICE in this route — the
        # results rail and the new unreported one both carry the fence, because
        # they are the same shape of question. The harness refused the ambiguous
        # needle rather than mutating whichever came first, which is the
        # needle-integrity pass doing its job: a mutant that could land in two
        # places is not provably aimed at either.
        "        settled_rail_condition("
        "now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),\n"
        "        )\n"
        '        .offset(literal_column("0"))',
        "        settled_rail_condition("
        "now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),\n"
        "        )\n"
        "        .offset(0)",
        "fences identically but emits OFFSET $1 — not the statement measured",
    ),
    (
        # #3211's rail gets the same mutant, because it inherited the same
        # measurement and a fence nobody tests is a comment.
        "M2b-unreported-fence-is-a-bind",
        ROUTE,
        "            unreported_rail_condition(\n"
        "                now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)\n"
        "            ),\n"
        "        )\n"
        '        .offset(literal_column("0"))',
        "            unreported_rail_condition(\n"
        "                now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)\n"
        "            ),\n"
        "        )\n"
        "        .offset(0)",
        "the third rail's fence is measured too — LAT-P110 transfers to it",
    ),
    (
        "M3-order-by-pushed-inside",
        ROUTE,
        # 🔴 EXTENDED THROUGH THE LIMIT by #3211: the four lines above it are
        # now identical in both fenced rails, and `RESULTS_LIMIT` vs
        # `UNREPORTED_LIMIT` is the first token that tells them apart. Their
        # caps are DIFFERENT constants on purpose (one cap over two unequal
        # populations is the trap the third rail exists to escape), which is
        # what makes this anchor unique — and if someone ever collapses them
        # back to one number, this needle goes ambiguous and the harness says so
        # before the page silently starves a rail again.
        "    fenced_event = aliased(Event, inner)\n    return (\n        select(fenced_event)\n        .order_by(fenced_event.commence_time.desc())\n        .limit(RESULTS_LIMIT + 1)",
        "    fenced_event = aliased(Event, inner)\n    return (\n        select(fenced_event)\n        .order_by(Event.commence_time.desc())\n        .limit(RESULTS_LIMIT + 1)",
        "sorting on the base table instead of the subquery re-correlates the two",
    ),
    (
        "M4-sibling-fenced-too",
        ROUTE,
        # 🔴 RE-TARGETED by Q438 (#1207). The needle was the raw
        # `case((Event.status == "live", 0), else_=1)`, which is now
        # `live_first_order(now)` — the shared clause that applies the same
        # live-AND-started predicate `served_event_status` applies on the
        # display side, so a rail cannot sort a row as live while printing it
        # as scheduled. The MEASUREMENT this needle protects is unchanged: the
        # upcoming rail must NOT acquire the results rail's optimization fence.
        # The route keeps its Q438 comment ABOVE `.order_by(` so this needle
        # stays comment-free and does not drift on a reworded sentence.
        "        .order_by(\n            live_first_order(now),\n            Event.commence_time.asc(),\n        )",
        '        .offset(literal_column("0"))\n        .order_by(\n            live_first_order(now),\n            Event.commence_time.asc(),\n        )',
        "tidying the two rails into a matching pair undoes a measurement",
    ),
    (
        "M5-route-keeps-an-inline-copy",
        ROUTE,
        # 🔴 RE-TARGETED BY #3677 (live/082) — the third worked example of the
        # lesson in M6 and M7 below, and the scanner caught it the same way:
        # loudly, before the battery could quote a kill count it had not made.
        #
        # The needle was `_results_q = recent_results_query(sport_key, now)`.
        # #3677 gave all three rails an `also_sport_keys` keyword, because a
        # tour's TOURNAMENTS are registered as their own sport keys and
        # `Sport.key == 'tennis_atp'` — correct, present and indexed — could not
        # see a single US Open match for the whole tournament. The call site
        # grew an argument, so the needle no longer existed.
        #
        # The MUTATION is unchanged in meaning: put the exact pre-fix statement
        # back in the route while the helper stays right. What it proves is
        # unchanged too — that the route CALLS the helper — and the added
        # keyword makes it prove slightly more, since an inline copy would now
        # also have to re-implement the widened scope. The mutant's inline
        # statement is deliberately left at the pre-fix `Sport.key == sport_key`
        # form: it is the regression being guarded against, not a template.
        "        _results_q = recent_results_query(sport_key, now, also_sport_keys=_also_keys)",
        "        _results_q = (\n"
        "            select(Event)\n"
        "            .join(Sport, Sport.id == Event.sport_id)\n"
        "            .where(\n"
        "                Sport.key == sport_key,\n"
        '                Event.status.in_(["completed", "closed"]),\n'
        "                Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),\n"
        "            )\n"
        "            .order_by(Event.commence_time.desc())\n"
        "            .limit(RESULTS_LIMIT + 1)\n"
        "        )",
        "the exact pre-fix statement, back in the route while the helper stays right",
    ),
    (
        "M6-lookback-window-changed",
        ROUTE,
        # 🔴 RE-TARGETED BY #3211 (lane1/134), for the second time and for the
        # same reason M7 was re-targeted by live/056 — read that note below, it
        # is the same lesson and this file is now its second worked example.
        #
        # The needle was the bare comparison
        # `Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),`.
        # #3211 moved BOTH halves of the rail — the status vocabulary and the
        # time bound — into `utils.event_rails.recent_rail_condition`, because a
        # shared status list cannot say anything about a row that is in the
        # right status set and the wrong time window, which is exactly how a
        # `scheduled` row past its kickoff reached neither rail and took 171 US
        # Open matches off the page with it.
        #
        # So the comparison no longer exists in this route and the scanner
        # refused, correctly and loudly. The lookback is still the ROUTE's
        # decision — it is passed, not assumed, because the team page's is 30
        # days — so the mutant keeps its meaning exactly: narrow this page's
        # window while the fence and the helper both stay right.
        # And a THIRD time, hours later in the same session: the split into
        # `settled_` + `unreported_` put a second
        # `lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)` in this file, so the
        # bare keyword stopped being unique. The lookback the RESULTS rail
        # spends is what this mutant narrows, so the call it belongs to is now
        # part of the needle.
        "settled_rail_condition(now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS))",
        "settled_rail_condition(now, lookback=timedelta(days=7))",
        "the fence must not be cover for a quietly narrowed rail",
    ),
    (
        "M7-statuses-copy-pasted",
        ROUTE,
        # 🔴 REFRESHED BY THE SHIP IT MEASURES — live/056 (#2858), the follow-up
        # CERT-839 named `LIVE-056-REFRESH-LEAGUE-RAILS-M7`.
        #
        # This needle used to be the hand-written literal
        # `Event.status.in_(["completed", "closed"]),`. That rail now spends the
        # shared `RECENT_RAIL_STATUSES` — because the literal is exactly what
        # hid `suspended` from this page — so the needle no longer existed and
        # the residue scanner correctly refused.
        #
        # It refused LOUDLY rather than quietly passing, and that is the whole
        # point of the needle-integrity pass: the scanner saw the MUTANT string
        # still present (the upcoming rail legitimately contains
        # `["live", "scheduled"]`) with the ORIGINAL gone, which is
        # indistinguishable from a mutant left on disk by a SIGKILLed run. A
        # harness whose needle has drifted is measuring nothing, and this one
        # said so instead of reporting a kill it did not make.
        #
        # The MUTATION is unchanged in meaning — copy-paste the sibling
        # builder's vocabulary over this one — because that is what
        # `tests/test_league_rails_query_plan.py` kills. "The literal comes
        # back" is a different regression and is guarded where it belongs, in
        # `test_suspended_is_reachable_cert_786.py`, by a suite that has a
        # suspended row to notice its absence.
        #
        # ── AND RE-TARGETED AGAIN BY #3211 (lane1/134) ──
        #
        # `RECENT_RAIL_STATUSES` moved one level down into
        # `utils.event_rails.recent_rail_condition`, which now builds status AND
        # time together. Third drift, third refusal, and the refusal is doing
        # its job every time: the mutant string `["live", "scheduled"]` remained
        # legitimately present in the upcoming rail, so a needle-blind harness
        # would have read the drift as leftover residue.
        #
        # The mutation still means "copy-paste the sibling builder over this
        # one" — it is simply written at the level the builders now live at,
        # which makes it a STRONGER mutant than the literal swap was: it takes
        # the whole rail, statuses and window together.
        #
        # Written in the form BLACK produces (one line, 86 chars), not the form
        # that was typed. A needle spelled differently from what the formatter
        # emits is a needle that drifts the next time anyone runs `black` on
        # this route — which is the same class of drift this comment already
        # documents twice, arriving through the toolchain instead of a ship.
        # ── AND ONCE MORE, same session, after the three-rail split ──
        #
        # `recent_rail_condition` no longer exists: #3211 measured that its two
        # arms could not share one cap (the result-less rows took all eight of
        # the results rail's slots) and split it into `settled_` and
        # `unreported_`. The mutation keeps its meaning exactly — copy-paste the
        # sibling builder over this one — and is now aimed at the settled rail's
        # call, which is the one whose vocabulary a careless edit would widen.
        #
        # The REPLACEMENT carries the two following lines as well, and that is
        # not padding. Pass B of the residue scanner sweeps every changed file
        # for a mutant's replacement text, and bare `upcoming_rail_condition(
        # now),` is a genuine, shipped line of `routes/teams.py` — so the short
        # form turned the residue gate red on real source. A mutant's
        # replacement has to be unique to the site it mutates, or the scan
        # cannot tell "left behind" from "legitimately written here too".
        "            settled_rail_condition("
        "now, lookback=timedelta(days=RESULTS_LOOKBACK_DAYS)),\n"
        "        )\n"
        '        .offset(literal_column("0"))',
        "            upcoming_rail_condition(now),\n"
        "        )\n"
        '        .offset(literal_column("0"))',
        "a copy-paste between the two builders",
    ),
    (
        "M8-cap-dropped",
        ROUTE,
        ".limit(RESULTS_LIMIT + 1)",
        ".limit(RESULTS_LIMIT)",
        "the +1 is what makes the cap DECLARED rather than a silent truncation",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout[-1200:]


def _main() -> int:
    baseline_code, baseline_tail = _run_suite()
    if baseline_code != 0:
        print("ABORT: the suite is not GREEN before mutating.")
        print(baseline_tail)
        return 2
    print(f"baseline GREEN (exit {baseline_code})\n")

    pristine: dict[Path, tuple[Path, str]] = {}
    tmp = Path(tempfile.mkdtemp(prefix="lat-p110-"))
    for _, path, _, _, _ in MUTANTS:
        if path not in pristine:
            backup = tmp / path.name
            shutil.copy2(path, backup)
            pristine[path] = (backup, _sha(path))

    killed: list[str] = []
    survived: list[tuple[str, str]] = []
    unapplied: list[tuple[str, str]] = []

    try:
        for mutant_id, path, needle, replacement, why in MUTANTS:
            original = path.read_text()
            hits = original.count(needle)
            if hits != 1:
                unapplied.append(
                    (mutant_id, f"needle appears {hits} times, expected 1")
                )
                print(f"  UNAPPLIED {mutant_id}: needle x{hits}")
                continue

            path.write_text(original.replace(needle, replacement, 1))
            assert path.read_text() != original, f"{mutant_id}: write was a no-op"

            code, tail = _run_suite()
            if code == 1:
                killed.append(mutant_id)
                print(f"  KILLED    {mutant_id:<30} — {why}")
            elif code == 0:
                survived.append((mutant_id, "suite stayed GREEN"))
                print(f"  SURVIVED  {mutant_id:<30} — {why}")
            else:
                # gotcha #124: 1 is a result, anything else is a story about the
                # harness. A collection error is not a kill.
                unapplied.append(
                    (mutant_id, f"pytest exit {code} — harness, not verdict")
                )
                print(f"  HARNESS   {mutant_id:<30} exit {code}\n{tail}")

            backup, sha = pristine[path]
            shutil.copy2(backup, path)
            if _sha(path) != sha:
                print(f"FATAL: restore of {path} did not match sha256 — aborting.")
                return 3
    finally:
        for path, (backup, sha) in pristine.items():
            shutil.copy2(backup, path)
            if _sha(path) != sha:
                print(f"FATAL: final restore of {path} mismatched sha256.")
                return 3
        shutil.rmtree(tmp, ignore_errors=True)

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed · {len(survived)} survived · "
        f"{len(unapplied)} unapplied"
    )
    for mid, why in survived + unapplied:
        print(f"  ! {mid}: {why}")

    final_code, final_tail = _run_suite()
    print(f"post-restore suite exit {final_code}")
    if final_code != 0:
        print(final_tail)
        return 3
    return 0 if not survived and not unapplied else 1


def main() -> int:
    """The crash guard, outside the per-mutant bookkeeping.

    `_main`'s own `cp` + sha256 loop restores after each mutant and is the thing
    that keeps mutant N from contaminating mutant N+1. It cannot help if the
    process is killed mid-mutation, because its `finally` never runs under
    SIGTERM. `guarded_targets` registers a signal handler and an on-disk
    manifest so the next run — or `python3 scripts/evals/_mutation_guard.py
    --recover` — puts the file back.
    """
    with guarded_targets([ROUTE], "/tmp/lat_p110_fence_guard_backups", "league_rails_fence"):
        return _main()


if __name__ == "__main__":
    raise SystemExit(main())
