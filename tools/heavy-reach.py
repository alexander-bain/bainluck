#!/usr/bin/env python3
"""heavy-reach.py — answer notice 48 PER CHANGED FILE, not per changed task.

    usage:  tools/heavy-reach.py [--base <sha>] [--head <sha>]
            tools/heavy-reach.py --files backend/app/utils/x.py ...
            tools/heavy-reach.py --selftest
            tools/heavy-reach.py --help

The last line of stdout is the one-line verdict `merge-gate.sh` quotes.

── WHY THIS IS A FILE ───────────────────────────────────────────────────────

Notice 48: a ship that lives in a heavy task is not live until `bainluck-heavy`
carries it. Every lane states that answer in its merge offer, and every lane
states it PER CHANGED TASK — "`backfill_winners` is not in `HEAVY_TASKS`" —
while the hazard is PER CHANGED FILE. On 2026-09-23 an offer said exactly that,
truthfully, about one of its two changed files; the other was
`app/utils/resolution_authority.py`, which `app.tasks.backfill_market_shapes`
imports and which IS a heavy member. It came out no-heavy-owed anyway, so the
offer was right by luck. `merge-gate.sh` already computes `release-required`
from the diff; this computes the heavy answer the same way.

── THE THREE WAYS THIS QUESTION IS GOT WRONG, ALL MEASURED ──────────────────

1. GREPPING THE CHANGED MODULE FOR "heavy" or for `HEAVY_TASKS`.
   The set is keyed on the registered Celery name — `app.tasks.refresh_stale_
   futures_prices` — which does not appear in `futures_price_refresh.py` at all.
   Grepping that module returns a boxing ticker and reads as a clean negative.
   (`app/utils/feed_market_quality.py`'s docstring records an earlier revision
   of itself being wrong on exactly this evidence.)

2. IMPORTING EVERY `HEAVY_TASKS` ENTRY AND ASSERTING ABSENCE FROM `sys.modules`.
   Vacuous. All 28 names are `app.tasks.<function>` and all 28 functions are
   defined in `app/tasks/__init__.py`, so splitting on `.` imports ONE module.
   The control that proves it: `app.utils.aggregation` — a module heavy code
   certainly reaches — also reads "absent". A test that clears your subject and
   a module it should convict is measuring nothing.

3. READING `HEAVY_TASKS` AS THE WHOLE HEAVY FLEET.
   It is not. A beat entry carrying `options={"queue": "heavy"}` runs on
   worker-heavy whether or not its task is a member, because `apply_async(
   queue=…)` overrules `task_routes`. Four do, and `heavy-sync.yml` already
   unions them for its own in-flight gate (its `heavy_queue_beat_tasks`); this
   script reproduces that union from the same source and the selftest pins the
   count, so the two cannot drift apart silently.

── WHY THE ANSWER IS TIERED AND NOT A BOOLEAN ───────────────────────────────

Measured over `backend/app/**` (587 modules) on 2026-09-23:

    following EVERY import, including lazy ones in function bodies :  ~79-88%
    following MODULE-LEVEL imports only                            :   17%

So a boolean "does heavy reach this file" is either non-discriminating (it says
yes to nearly every backend change, and a gate that always says yes carries no
information) or fail-open — the module-level-only reading clears
`app.utils.aggregation`, which is precisely the module the control in (2) above
proves must convict. Neither bound is usable alone, so this prints BOTH and
names the heavy functions behind each:

    CERTAIN   the module is LOADED whenever that heavy task runs — reachable
              from the task wrapper's own imports through module-level imports
              only. This is notice 48's second clause, met at the file level.
    POSSIBLE  reachable only by following a lazy import inside some function on
              the chain, so whether the task reaches you depends on which branch
              runs. Read the path and decide; do not auto-claim either answer.
    CLEAN     no heavy task reaches this file by any import, lazy ones included.

LOADED IS NOT EXERCISED, AND THE TOOL MUST NOT PRETEND OTHERWISE. The case that
set this wording: lane1b's #8132 diff changed `app/tasks/backfill_winners.py`,
and the heavy `compute_calibration_prices` imports `_compute_calibration_prices`
straight out of that file — so the file is CERTAIN-loaded on the heavy worker.
But the diff landed on `_resolve_kalshi_from_scores` /
`_resolve_kalshi_spread_total_from_scores`, and the heavy entry point calls
neither, so no heavy release was owed after all. The offer's conclusion was
right and its stated reason ("`backfill_winners` is not in `HEAVY_TASKS`") was
the wrong test — true of the task NAME, silent about the FILE. So CERTAIN does
not tell you to claim a heavy release; it names the heavy entry SYMBOL, which
turns the remaining question into one grep: does that symbol's call path reach
what you changed?

── WHAT IT CANNOT DO ────────────────────────────────────────────────────────

It reads the static import graph of `backend/app/**`. It cannot see a module
reached by a name computed at runtime. That hole was measured rather than
assumed: the only `importlib`/`__import__` call under `backend/app/tasks/**` is
`__import__("sqlalchemy")` in `grid_sentinel.py`, a third-party module, so no
app module is reached dynamically today. If that changes, CLEAN weakens to
"clean by static import" and this paragraph is the thing to update.

It also says nothing about whether heavy is BEHIND — that is
`heroku releases -a bainluck-heavy`, and convergence has been automatic since
2026-09-14. This answers "is a heavy release line owed at all".
"""

import argparse
import ast
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "backend", "app")
APP_PARENT = os.path.dirname(APP)  # backend/ — so `app.x.y` resolves under it
TASKS_INIT = os.path.join(APP, "tasks", "__init__.py")


# ─────────────────────────────────────────────────────────────────────────────
# The module graph
# ─────────────────────────────────────────────────────────────────────────────
def module_name(path):
    """backend/app/utils/x.py -> app.utils.x ; .../tasks/__init__.py -> app.tasks"""
    rel = os.path.relpath(os.path.abspath(path), APP_PARENT)
    if rel.endswith(".py"):
        rel = rel[:-3]
    parts = rel.split(os.sep)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def all_modules():
    out = {}
    for root, _dirs, files in os.walk(APP):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                out[module_name(p)] = p
    return out


def _import_nodes(node, module_level_only):
    """Import/ImportFrom nodes under `node`.

    `module_level_only` keeps only those that execute at import time: direct
    children of the module body, plus those nested in a top-level `if`/`try`
    (a `TYPE_CHECKING` guard or an optional-dependency fallback still runs the
    import statement's enclosing block at import time, and counting them is the
    fail-CLOSED direction for a safety gate).
    """
    if not module_level_only:
        return [
            n for n in ast.walk(node) if isinstance(n, (ast.Import, ast.ImportFrom))
        ]
    body = node.body if isinstance(node, ast.Module) else []
    found = []
    for n in body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            found.append(n)
        elif isinstance(n, (ast.If, ast.Try)):
            found.extend(
                s for s in ast.walk(n) if isinstance(s, (ast.Import, ast.ImportFrom))
            )
    return found


def app_imports(node, this_module, module_level_only):
    """Every `app.*` module string imported under `node`."""
    out = set()
    for n in _import_nodes(node, module_level_only):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level:  # relative — resolve against this module's package
                pkg = this_module.split(".")
                pkg = pkg[: len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                base = ".".join(pkg + ([n.module] if n.module else []))
                out.add(base)
                for a in n.names:
                    out.add(f"{base}.{a.name}")
            elif n.module:
                out.add(n.module)
                # `from app.utils.x import y` — y may itself be a submodule, so
                # offer the dotted form too and let resolve() walk it back.
                for a in n.names:
                    out.add(f"{n.module}.{a.name}")
    return {m for m in out if m.split(".")[0] == "app"}


def _parse(path):
    """Parse a file, closing it. The graph opens 587 of these in one build, so a
    bare `open(...).read()` leaks handles at a rate that matters (and CodeQL
    flags it, correctly, as "File is not always closed")."""
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def build_graph(mods):
    """(module-level graph, all-imports graph) over the app package."""

    def resolve(m):
        while m and m not in mods:
            m = m.rsplit(".", 1)[0] if "." in m else ""
        return m

    ml, everything = {}, {}
    for m, p in mods.items():
        try:
            tree = _parse(p)
        except (SyntaxError, UnicodeDecodeError):
            ml[m], everything[m] = set(), set()
            continue
        ml[m] = {r for r in (resolve(i) for i in app_imports(tree, m, True)) if r}
        everything[m] = {
            r for r in (resolve(i) for i in app_imports(tree, m, False)) if r
        }
    return ml, everything, resolve


# ─────────────────────────────────────────────────────────────────────────────
# The heavy fleet, from the app's own source
# ─────────────────────────────────────────────────────────────────────────────
def heavy_fleet(tree):
    """(HEAVY_TASKS names, beats authored queue=heavy but NOT members).

    The second half is the residual `heavy-sync.yml` names: `apply_async(
    queue=…)` overrules `task_routes`, so a beat authored onto the heavy queue
    runs there whether or not its task is a member.
    """
    members = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "HEAVY_TASKS":
                    members = {
                        e.value
                        for e in getattr(n.value, "elts", [])
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    }
    beats = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Dict):
            continue
        keys = [k.value for k in n.keys if isinstance(k, ast.Constant)]
        if "task" not in keys or "options" not in keys:
            continue
        d = dict(zip(keys, n.values))
        task, opts = d.get("task"), d.get("options")
        if not isinstance(task, ast.Constant) or not isinstance(opts, ast.Dict):
            continue
        for k, v in zip(opts.keys, opts.values):
            if (
                isinstance(k, ast.Constant)
                and k.value == "queue"
                and isinstance(v, ast.Constant)
                and v.value == "heavy"
            ):
                beats.add(task.value)
    return members, beats - members


def function_entry_symbols(tree, func_names):
    """{heavy function -> {module -> [symbols it imports from that module]}}.

    The wrapper body's `from app.tasks.<impl> import _run` names the ENTRY
    POINT. Reporting it is what keeps CERTAIN from over-claiming: "loaded by
    compute_calibration_prices via _compute_calibration_prices" is checkable in
    one grep, where a bare "heavy reaches this file" is not.
    """
    out = {}
    for n in tree.body:
        if (
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in func_names
        ):
            per_mod = {}
            for sub in ast.walk(n):
                if isinstance(sub, ast.ImportFrom) and sub.module and not sub.level:
                    if sub.module.split(".")[0] == "app":
                        per_mod.setdefault(sub.module, []).extend(
                            a.name for a in sub.names
                        )
            out[n.name] = per_mod
    return out


def function_seeds(tree, func_names):
    """{heavy function -> the app modules its own body imports}.

    The heavy wrappers in `tasks/__init__.py` are thin: the body is a lazy
    `from app.tasks.<impl> import _run` and a `_tracked_run(...)`. Those body
    imports ARE the task's entry points, so they seed the walk. Module-level
    imports of `tasks/__init__.py` are deliberately NOT seeds — that file
    imports most of the app, and counting them convicts every module for every
    task, which is the same "tells you nothing" failure as reading
    `app/tasks/__init__.py` out of an importer trace.
    """
    seeds = {}
    for n in tree.body:
        if (
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name in func_names
        ):
            seeds[n.name] = app_imports(n, "app.tasks", False)
    return seeds


def reach(seed_mods, graph, resolve):
    out, stack = set(), [r for r in (resolve(s) for s in seed_mods) if r]
    while stack:
        m = stack.pop()
        if m in out:
            continue
        out.add(m)
        stack.extend(x for x in graph.get(m, ()) if x not in out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
def analyse(changed_paths):
    mods = all_modules()
    ml, everything, resolve = build_graph(mods)
    tree = _parse(TASKS_INIT)

    members, extra_beats = heavy_fleet(tree)
    fleet = members | extra_beats
    funcs = {name.rsplit(".", 1)[1] for name in fleet}
    seeds = function_seeds(tree, funcs)
    entries = function_entry_symbols(tree, funcs)

    certain_by_fn, possible_by_fn = {}, {}
    for fn, s in seeds.items():
        certain_by_fn[fn] = reach(s, ml, resolve)
        possible_by_fn[fn] = reach(s, everything, resolve)

    rows = []
    for path in changed_paths:
        norm = path.replace("\\", "/")
        if not norm.startswith("backend/app/") or not norm.endswith(".py"):
            rows.append((path, "n/a", []))
            continue
        m = module_name(os.path.join(REPO, norm))
        # `tasks/__init__.py` defines all 28 heavy functions itself. It is not a
        # graph question and must not be reported as one.
        if m == "app.tasks":
            rows.append((path, "CERTAIN", ["<defines every heavy task>"]))
            continue
        cert = sorted(fn for fn, r in certain_by_fn.items() if m in r)
        poss = sorted(
            fn for fn, r in possible_by_fn.items() if m in r and fn not in cert
        )
        if cert:
            # Where the heavy wrapper imports this module DIRECTLY, name the
            # symbol — that is the entry point whose call path the lane greps.
            labelled = []
            for fn in cert:
                syms = entries.get(fn, {}).get(m, [])
                labelled.append(
                    f"{fn} via {'/'.join(sorted(set(syms)))}" if syms else fn
                )
            rows.append((path, "CERTAIN", labelled))
        elif poss:
            rows.append((path, "POSSIBLE", poss))
        else:
            rows.append((path, "CLEAN", []))
    return rows, members, extra_beats, seeds, len(mods)


def render(rows, members, extra_beats, nmods, verbose=True):
    if verbose:
        print(
            f"heavy fleet: {len(members)} HEAVY_TASKS members "
            f"+ {len(extra_beats)} beats authored queue=heavy "
            f"({', '.join(sorted(b.rsplit('.', 1)[1] for b in extra_beats))}) "
            f"— graph over {nmods} app modules"
        )
        print()
        for path, tier, fns in rows:
            if tier == "n/a":
                print(f"  ----      {path}  (not backend/app/**)")
            elif tier == "CLEAN":
                print(f"  CLEAN     {path}")
            elif tier == "POSSIBLE":
                # Deliberately a COUNT, not a list. POSSIBLE is the ~79% band —
                # enumerating 23 task names reads as 23 findings and is noise.
                print(
                    f"  POSSIBLE  {path}  <- {len(fns)} heavy task(s), lazy chain only"
                )
            else:
                shown = ", ".join(fns[:6]) + (
                    f" +{len(fns) - 6} more" if len(fns) > 6 else ""
                )
                print(f"  {tier:<9} {path}  <- {shown}")
        print()

    app_rows = [r for r in rows if r[1] != "n/a"]
    certain = [r for r in app_rows if r[1] == "CERTAIN"]
    possible = [r for r in app_rows if r[1] == "POSSIBLE"]
    if not app_rows:
        return "no — no backend/app/** file changed, so no heavy task can be affected"
    if certain:
        fns = sorted({f for r in certain for f in r[2]})
        return (
            f"LOADED — {len(certain)} changed file(s) run on worker-heavy: "
            f"{', '.join(fns[:4])}{' …' if len(fns) > 4 else ''}. "
            f"Loaded is not exercised: grep whether that entry symbol's call path reaches what "
            f"you changed, then state the `heroku releases -a bainluck-heavy` line, or say in "
            f"the offer why the heavy path does not reach the diff (notice 48)."
        )
    if possible:
        return (
            f"POSSIBLE — no changed file is loaded outright by a heavy task, but {len(possible)} "
            f"are reachable down a lazy-import chain. This is the WIDE band (~79% of app modules "
            f"sit in it), so it is weak evidence either way: it does not owe a heavy release and "
            f"it does not license claiming 'not heavy' without naming why."
        )
    return (
        f"no — {len(app_rows)} changed backend/app file(s), none reachable from any of the "
        f"{len(members) + len(extra_beats)} heavy tasks by any import, lazy ones included"
    )


# ─────────────────────────────────────────────────────────────────────────────
def selftest():
    """Controls first. An absence test without a control that convicts is not a test."""
    ok = failed = 0

    def check(label, cond, detail=""):
        nonlocal ok, failed
        if cond:
            ok += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}  {detail}")

    print("heavy-reach --selftest")
    print()
    mods = all_modules()
    ml, everything, resolve = build_graph(mods)
    tree = _parse(TASKS_INIT)
    members, extra_beats = heavy_fleet(tree)
    funcs = {n.rsplit(".", 1)[1] for n in members | extra_beats}
    seeds = function_seeds(tree, funcs)

    check(
        "HEAVY_TASKS parsed from source and non-trivial",
        len(members) >= 20,
        f"got {len(members)}",
    )
    check(
        "the heavy-queue beat residual is unioned in (heavy-sync.yml's own finding)",
        len(extra_beats) >= 1
        and "app.tasks.refresh_linked_polymarket_books" in extra_beats,
        f"got {sorted(extra_beats)}",
    )
    check(
        "every heavy task name resolves to a function defined in tasks/__init__.py",
        set(seeds) == funcs,
        f"missing {sorted(funcs - set(seeds))}",
    )

    # POSITIVE CONTROLS — each must convict, and each is here because a real
    # session got it wrong in the other direction.
    def tier(module):
        if any(module in reach(s, ml, resolve) for s in seeds.values()):
            return "CERTAIN"
        if any(module in reach(s, everything, resolve) for s in seeds.values()):
            return "POSSIBLE"
        return "CLEAN"

    check(
        "CONTROL app.utils.game_market_class convicts (int507's specimen: a shared "
        "util whose offer said 'not heavy' while calibration_sentinel imports it)",
        tier("app.utils.game_market_class") != "CLEAN",
    )
    check(
        "CONTROL app.utils.resolution_authority convicts (int511's specimen, via "
        "the heavy backfill_market_shapes)",
        tier("app.utils.resolution_authority") != "CLEAN",
    )
    check(
        "CONTROL app.utils.aggregation convicts — the module that reads 'absent' "
        "under the sys.modules test and proves that test vacuous",
        tier("app.utils.aggregation") != "CLEAN",
    )
    check(
        "CONTROL app.tasks.futures_price_refresh convicts, though the string "
        "'refresh_stale_futures_prices' never appears in it",
        tier("app.tasks.futures_price_refresh") != "CLEAN",
    )

    # NEGATIVE CONTROL — without one, a gate that convicts everything passes
    # every positive control above and is still useless.
    clean_count = sum(1 for m in mods if tier(m) == "CLEAN")
    check(
        "the graph is DISCRIMINATING — some app modules come back CLEAN",
        clean_count >= 20,
        f"only {clean_count} of {len(mods)} clean; a gate that convicts everything "
        f"passes every positive control and still says nothing",
    )
    check(
        "CONTROL app.main is CLEAN (the web entrypoint is not heavy-borne)",
        tier("app.main") == "CLEAN",
    )

    # The tiers must actually differ, or the two graphs are one graph.
    certain_n = sum(1 for m in mods if tier(m) == "CERTAIN")
    check(
        "CERTAIN and POSSIBLE are different sets (module-level vs lazy)",
        0 < certain_n < len(mods) - clean_count,
        f"certain={certain_n} clean={clean_count} of {len(mods)}",
    )

    # The renderer must not report a clean verdict for a convicting file.
    rows, mem, xb, _s, n = analyse(["backend/app/utils/resolution_authority.py"])
    verdict = render(rows, mem, xb, n, verbose=False)
    check(
        "end-to-end: int511's specimen renders a non-clean verdict",
        not verdict.startswith("no "),
        verdict,
    )
    # The case that set the CERTAIN wording. `backfill_winners` is NOT a
    # HEAVY_TASKS member and the file it lives in still runs on worker-heavy.
    rows, mem, xb, _s, n = analyse(["backend/app/tasks/backfill_winners.py"])
    label = "; ".join(rows[0][2])
    check(
        "the per-TASK answer and the per-FILE answer differ, and the tool gives the "
        "per-FILE one: backfill_winners.py is CERTAIN though its task is not a member",
        rows[0][1] == "CERTAIN" and "compute_calibration_prices" in label,
        f"{rows[0][1]} {label}",
    )
    check(
        "a CERTAIN hit names the heavy ENTRY SYMBOL, so 'loaded vs exercised' is one grep",
        "via _compute_calibration_prices" in label,
        label,
    )
    check(
        "CERTAIN does not assert a heavy release is owed — it asks for the call-path read "
        "(lane1b's #8132 was CERTAIN-loaded and owed nothing)",
        "Loaded is not exercised" in render(rows, mem, xb, n, verbose=False),
    )
    rows, mem, xb, _s, n = analyse(["frontend/app/page.tsx", "docs/x.md"])
    verdict = render(rows, mem, xb, n, verbose=False)
    check(
        "end-to-end: a frontend-only diff is answered 'no', not 'POSSIBLE'",
        verdict.startswith("no —"),
        verdict,
    )

    print()
    print(f"{ok} passed, {failed} failed")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    ap.add_argument(
        "--base", help="merge base sha (default: merge-base with origin/master)"
    )
    ap.add_argument(
        "--head", default="HEAD", help="sha to read the diff of (default HEAD)"
    )
    ap.add_argument(
        "--files", nargs="*", help="explicit repo-relative paths instead of a diff"
    )
    ap.add_argument(
        "--quiet", action="store_true", help="print only the one-line verdict"
    )
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.files:
        paths = args.files
    else:
        base = args.base
        if not base:
            base = subprocess.run(
                ["git", "-C", REPO, "merge-base", "origin/master", args.head],
                capture_output=True,
                text=True,
            ).stdout.strip()
        if not base:
            # Same empty-merge-base hazard release-required has. Say so rather
            # than printing a confident answer about a diff never read.
            print(
                "inconclusive — NO MERGE BASE in this clone, so the diff was never read "
                "(the same empty base #5456's composition scan reports as inconclusive)"
            )
            return 0
        out = subprocess.run(
            ["git", "-C", REPO, "diff", "--name-only", f"{base}..{args.head}"],
            capture_output=True,
            text=True,
        )
        paths = [p for p in out.stdout.splitlines() if p.strip()]
        # AN EMPTY DIFF IS NOT A CLEAN ANSWER, IT IS NO ANSWER. When the sha is
        # already an ancestor of origin/master the merge base IS the head, the
        # diff is empty, and "no backend/app file changed" reads as a heavy
        # verdict about a diff nobody looked at — the same shape of honesty hole
        # as release-required's empty base. Caught on this script's own first
        # live run, against a sha that had merged while it was being written.
        if not paths:
            same = (
                base
                == subprocess.run(
                    ["git", "-C", REPO, "rev-parse", args.head],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            why = (
                "this sha is already an ancestor of origin/master, so the merge base IS "
                "the head"
                if same
                else "the two commits have identical trees"
            )
            print(
                f"inconclusive — the diff is EMPTY ({why}). No file was read, so this "
                f"is not a heavy answer. Read it against the sha's own parent instead: "
                f"--base <sha>^ --head <sha>"
            )
            return 0

    rows, members, extra_beats, _seeds, nmods = analyse(paths)
    verdict = render(rows, members, extra_beats, nmods, verbose=not args.quiet)
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
