#!/usr/bin/env python3
"""LAT-P137 mutation battery for the category-census warmer.

A guard suite that passes proves the code runs; it does not prove the code is
PINNED. Each mutant below is a plausible way this change could be broken by a
later edit — the kind of edit that looks like a simplification, or like a tidy-up
of "a derivation that could just be a number". If a mutant survives, the suite
has a hole and the fix is to add the missing assertion, NOT to delete the mutant
(LAT-P115's M7 survived and the survivor was the finding).

Three of these are the ones this battery exists for:

  * **M1 / M2 / M3 — the derived period.** The whole point of the ship is that a
    reader never meets a mirror older than `stale_serve_ceiling_seconds()`. A
    period typed as a literal, or divided by the wrong thing, still warms — it
    just stops covering the gap, silently, while every surface keeps answering
    200. That is the failure this ship exists to end, so it is the failure the
    battery spends its first three mutants on.
  * **M4 / M5 / M6 — the read-back.** A warmer that grades itself on "the build
    returned" reads GREEN through a Redis that kept nothing (gotcha #53). The
    kill has to come from a test that distinguishes a census that EXISTS from a
    census THIS RUN published.
  * **M13 — the verdict enrolment.** An unenrolled task's verdict is
    non-authoritative, so a warmer that fails every night reads `unknown`
    forever. Enrolment and terminal are one property and are mutated as one.

Mutations are applied to the real source files, the suite is run to completion,
and the files are restored — SERIALLY. Never concurrently, and never while
another pytest is in flight: `inspect.getsource` re-reads the file mid-run and a
source edit under a running suite produces phantom failures that read as real
reds.

The `try/finally` in `_main()` restores on an exception; it does NOT survive a
SIGTERM or SIGKILL. `guarded_targets` is the shared primitive that closes that
window (manifest + `--recover`).

Run:  python3 backend/scripts/evals/futures_categories_warm_mutations.py
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
WARM = ROOT / "app" / "tasks" / "futures_categories_warm.py"
TASKS = ROOT / "app" / "tasks" / "__init__.py"
VERDICT = ROOT / "app" / "utils" / "task_verdict.py"
SUITE = ROOT / "tests" / "test_futures_categories_warm_lat_p137.py"

#: (id, description, target, old, new). `old` must appear EXACTLY once in
#: `target` — a mutation that matches zero or many places is a harness bug
#: reported as such, never counted as a kill.
MUTANTS: list[tuple[str, str, pathlib.Path, str, str]] = [
    (
        "M1",
        "tolerate no missed delivery — the cadence stops covering background's jitter",
        WARM,
        "MISSED_DELIVERY_ALLOWANCE = 4",
        "MISSED_DELIVERY_ALLOWANCE = 0",
    ),
    (
        "M2",
        "multiply by the allowance instead of dividing — a warmer slower than the ceiling",
        WARM,
        "    return stale_serve_ceiling_seconds() // (MISSED_DELIVERY_ALLOWANCE + 1)",
        "    return stale_serve_ceiling_seconds() * (MISSED_DELIVERY_ALLOWANCE + 1)",
    ),
    (
        "M3",
        "freeze the period as a literal — a tightened freshness contract sails past it",
        WARM,
        "    from app.utils.futures_categories_cache import stale_serve_ceiling_seconds\n\n"
        "    return stale_serve_ceiling_seconds() // (MISSED_DELIVERY_ALLOWANCE + 1)",
        "    return 300",
    ),
    (
        "M4",
        "count any census as published — a swallowed write reads green forever",
        WARM,
        "    published = after is not None and after != before",
        "    published = after is not None",
    ),
    (
        "M5",
        "always report complete — the beat can never go red",
        WARM,
        '        "terminal": "complete" if published else "failed",',
        '        "terminal": "complete",',
    ),
    (
        "M6",
        "skip the read-back — 'the build returned' is graded as 'the reader is covered'",
        WARM,
        "    after = _census_created_at(rc)",
        '    after = "assume-it-worked"',
    ),
    (
        "M7",
        "let an unreadable cache kill the pass instead of reporting it",
        WARM,
        '    except Exception:  # noqa: BLE001 — an unreadable cache is a warm reason, not a crash\n'
        '        logger.warning("warm_futures_categories: census read failed", exc_info=True)\n'
        "        return None",
        "    except AssertionError:\n        return None",
    ),
    (
        "M8",
        "drop the bound on the build — a wedged census holds the slot to the task limit",
        WARM,
        # 🔴 SPELLED AS A TRIPLE-QUOTED LITERAL, NOT AS CONCATENATED FRAGMENTS,
        # AND THE RESIDUE SCANNER IS THE REASON. Pass B flags any file holding a
        # replacement whose needle is absent — and this replacement is a single
        # line of 40 characters, so its text appears verbatim in THIS file. With
        # the needle spelled as escaped fragments it did not, and the scan went
        # red on the harness itself. Both halves now appear contiguously here,
        # which is the `game_markets_shared_cache:M4` shape. The general rule for
        # the next author: a single-line replacement of 24+ characters needs its
        # needle written contiguously.
        """        await asyncio.wait_for(
            _rebuild_futures_categories(), timeout=BUILD_TIMEOUT_SECONDS
        )""",
        "        await _rebuild_futures_categories()",
    ),
    (
        "M9",
        "let the build's exception escape — a beat that raises loses its next fire",
        WARM,
        "    except Exception as exc:  # noqa: BLE001 — a failed warm must not fail the beat",
        "    except ValueError as exc:",
    ),
    (
        "M10",
        "warm through something other than the route's own rebuild — the bytes drift",
        WARM,
        "    from app.routes.futures import _rebuild_futures_categories",
        "    from app.routes.futures import (\n"
        "        _publish_futures_categories as _rebuild_futures_categories,\n"
        "    )",
    ),
    (
        "M11",
        "type the beat's cadence — the derivation becomes a comment",
        TASKS,
        '        "schedule": crontab(minute=f"*/{_futures_categories_warm_minutes()}"),\n'
        '        "options": {"queue": "background"},\n'
        "    },\n"
        '    "warm-typeahead": {',
        '        "schedule": crontab(minute="*/30"),\n'
        '        "options": {"queue": "background"},\n'
        "    },\n"
        '    "warm-typeahead": {',
    ),
    (
        "M12",
        "put the census build on the realtime rail — the punctual queue LAT-P115 refused",
        TASKS,
        '        "schedule": crontab(minute=f"*/{_futures_categories_warm_minutes()}"),\n'
        '        "options": {"queue": "background"},',
        '        "schedule": crontab(minute=f"*/{_futures_categories_warm_minutes()}"),\n'
        '        "options": {"queue": "realtime"},',
    ),
    (
        "M13",
        "un-enrol the task — every failure it reports becomes a non-authoritative unknown",
        VERDICT,
        '    "warm_futures_categories",         # terminal + published + created_at',
        '    "warm_futures_categories_UNENROLLED",  # terminal + published + created_at',
    ),
    (
        "M14",
        "let a queued fire outlive its replacement — two warms of the same census",
        TASKS,
        '    "warm-futures-categories": _futures_categories_warm_minutes() * 60,',
        '    "warm-futures-categories": _futures_categories_warm_minutes() * 600,',
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
        [WARM, TASKS, VERDICT],
        "/tmp/lat_p137_futures_categories_warm_guard_backups",
        "futures_categories_warm",
    ):
        return _main()


def _main() -> int:
    originals = {path: path.read_text() for path in (WARM, TASKS, VERDICT)}

    baseline = _run_suite()
    if baseline != 0:
        print(
            f"HARNESS FAILURE: the unmutated suite exits {baseline}, not 0. "
            "Nothing below is a verdict."
        )
        return 2
    # 🔴 The DENOMINATOR is printed BEFORE the first verdict, deliberately.
    # LAT-P120's battery reported `11/11 killed` over a table a third of whose
    # entries had silently failed to append; a run that prints only its kills
    # reads as a clean sweep over whatever survived the edit.
    print(
        f"baseline: suite GREEN on the unmutated tree "
        f"({len(MUTANTS)} mutants queued across {len(originals)} targets)\n"
    )

    killed, survived, broken = [], [], []
    try:
        for mid, desc, target, old, new in MUTANTS:
            original = originals[target]
            n = original.count(old)
            if n != 1:
                broken.append((mid, f"anchor matched {n} times in {target.name}"))
                print(
                    f"{mid:4} HARNESS  {desc}\n"
                    f"     anchor matched {n} times in {target.name} — not a verdict"
                )
                continue
            target.write_text(original.replace(old, new, 1))
            rc = _run_suite()
            target.write_text(original)  # restore before anything else runs
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
                    f"     pytest exit {rc} — the gate never ran"
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
