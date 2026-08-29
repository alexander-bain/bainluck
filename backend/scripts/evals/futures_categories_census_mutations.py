"""LAT-P122 — the census-that-everybody-rebuilds mutation class.

WHAT A MUTANT PROVES HERE
-------------------------
`/api/futures/categories` is the first thing `/search` asks for and the grid is
not there until it answers. It was measured on production at 1,586 ms — twice in
a row, ten seconds apart, because the tier had no cache of any kind. The fix is
a shared slot with an age-bounded mirror and one rebuild behind it.

Every way that fix can be silently wrong produces the SAME green suite and the
same 1.5 s wait, or worse — the same fast page printing counts nobody can
reproduce:

  * a per-process or per-argument key, so the "shared" slot is shared with
    nobody and the second visitor still builds;
  * a mirror consulted only when the build FAILS, which is the exact defect
    #1651 recorded for `hub.py` and #1587 for game-markets, re-introduced;
  * an unbounded mirror, so a day-old census prints "6,614 Politics" beside a
    tile that opens 6,900 markets — a formatting lie arriving through a latency
    fix, which is the trap LAT-P121 named;
  * single-flight that isn't, so one expiry releases one rebuild per Uvicorn
    worker per dyno;
  * a lock released by a non-holder (#1678 finding 1), admitting a third builder.

So the question is not "does the cache work". It is: **would
`tests/test_futures_categories_cache.py` NOTICE if it stopped?** Each mutant
breaks one property that file claims to defend, and a SURVIVOR is a missing
assertion, reported as such per mutant.

WHY THE ORACLE IS THE REAL GUARD FILE, RUN OUT OF PROCESS
---------------------------------------------------------
Re-implementing the assertions here would prove that this file's copy of them
still fails, which is worth nothing. The oracle re-execs the shipped guard module
against the mutated import, so a mutant is killed only by an assertion that
genuinely ships.

NOTHING IS WRITTEN TO DISK. Both targets are exec'd from a mutated STRING into a
throwaway module and swapped into `sys.modules` in this process. A harness that
edits a tracked file and restores it afterwards loses the file when the run dies
mid-way, and trips `test_every_on_disk_harness_is_guarded`, which keys on the
write VERB (P114-2).

TWO TARGETS, TWO TABLES. The tier's policy is in `futures_categories_cache.py`;
the serve-stale primitive this ship moved into the shared policy home is in
`event_concept_cache.py`. They are separate tables with separate target
constants rather than one table with a per-entry path, so the residue scanner's
`SHAPES` entry reads as what it is: two modules, one guard file.

USAGE

    python3 scripts/evals/futures_categories_census_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` at least one SURVIVOR — a
real result, `2` the battery could not be run.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
CENSUS = BACKEND / "app/utils/futures_categories_cache.py"
CONCEPT_CACHE = BACKEND / "app/utils/event_concept_cache.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


ORACLE = "tests/test_futures_categories_cache.py"

MODULE_PATHS = {
    "app.utils.futures_categories_cache": CENSUS,
    "app.utils.event_concept_cache": CONCEPT_CACHE,
}


# --------------------------------------------------------------------------
# Mutants against the tier's own policy: (id, needle, replacement, why, property)
# --------------------------------------------------------------------------
CENSUS_MUTATIONS: list[dict[str, str]] = [
    {
        "id": "mirror-only-when-the-build-failed",
        "needle": "    mirror = read_slot(client, slots.stale)\n    if mirror is None:\n        return None, \"miss\"",
        "replacement": "    mirror = None\n    if mirror is None:\n        return None, \"miss\"",
        "why": "Reinstates the defect class exactly: the 24 h snapshot rescues a "
        "FAILED build and does nothing at all for a COLD one, so a primary-TTL "
        "expiry costs the reader the whole 39,014-block scan with a perfectly "
        "good mirror one GET away. #1651's finding, on a third tier.",
        "property": "a primary MISS serves the mirror, not a rebuild",
    },
    {
        "id": "unbound-the-mirror",
        "needle": "STALE_SERVE_CEILING = 5",
        "replacement": "STALE_SERVE_CEILING = 100000",
        "why": "Lets a 24 h mirror serve. Every latency number improves and the "
        "grid prints a count nobody can reproduce by tapping the tile — a "
        "formatting lie shipped as a latency win.",
        "property": "the mirror is age-bounded so the grid cannot print a lie",
    },
    {
        "id": "ceiling-off-by-one-direction",
        "needle": "    if age > stale_serve_ceiling_seconds():\n        return False, \"too_old\"",
        "replacement": "    if age > stale_serve_ceiling_seconds() * 12:\n        return False, \"too_old\"",
        "why": "Keeps the ceiling but widens it by an order of magnitude — the "
        "shape a favourable reading tempts someone into. Five hours of a census "
        "that moves hourly.",
        "property": "the ceiling is the DECLARED multiple, not a looser one",
    },
    {
        "id": "serve-a-payload-that-cannot-date-itself",
        "needle": "    if age is None:",
        "replacement": "    if age is None and False:",
        "why": "Serves a mirror with no parsable `created_at` — under an age bound "
        "that cannot be evaluated. The failure mode is unbounded staleness that "
        "reports itself as fresh_enough.",
        "property": "an undateable payload is refused, not served",
    },
    {
        "id": "bake-the-serve-decision-into-the-bytes",
        "needle": "        return with_availability(primary, AVAILABILITY_LIVE), \"live\"",
        "replacement": "        return primary, \"live\"",
        "why": "Drops the serve decision on the primary path. The payload's "
        "`availability` stays the stored None, so a consumer that reads the "
        "contract's field cannot tell live from stale — and contract rule 1 says "
        "the consumer must never re-derive it from `created_at`.",
        "property": "`availability` is published on every serve path",
    },
    {
        "id": "one-key-per-process",
        "needle": "CACHE_KEY = \"all\"",
        "replacement": "CACHE_KEY = \"all-\" + str(id(logger))",
        "why": "The classic way a 'shared' cache is shared with nobody: a key that "
        "varies per process. Every write succeeds, every metric looks healthy, "
        "and the second visitor on the other Uvicorn worker still pays the scan.",
        "property": "the census has ONE key for the whole fleet",
    },
    {
        "id": "write-the-mirror-with-the-fresh-ttl",
        "needle": "    write_payload(client, keys(), enveloped, primary_ttl=FRESH_TTL)",
        "replacement": "    write_payload(client, keys(), enveloped)",
        "why": "Falls back to the shared 60 s ENVELOPE_TTL. Not wrong-wrong — but "
        "the tier's declared freshness silently becomes somebody else's number, "
        "which is the drift LAT-P121's first guard test exists to stop.",
        "property": "the primary TTL written is THIS tier's fresh TTL",
    },
    {
        "id": "a-write-failure-reports-durability",
        "needle": "    client = rc if rc is not None else get_client()\n    if client is None:\n        return False\n    write_payload",
        "replacement": "    client = rc if rc is not None else get_client()\n    if client is None:\n        return True\n    write_payload",
        "why": "Reports a write with no client as done. A caller that trusts the "
        "return value then believes the fleet has the bytes when nothing was "
        "even attempted — `write` may only claim ATTEMPTED.",
        "property": "`write` reports attempt, and never claims it with no client",
    },
    {
        "id": "a-read-failure-becomes-a-500",
        "needle": "    client = rc if rc is not None else get_client()\n    if client is None:\n        return None, \"miss\"",
        "replacement": "    client = rc if rc is not None else get_client()\n    if client is None:\n        raise RuntimeError(\"no redis\")",
        "why": "A cache that cannot be read must cost a rebuild, not an error. "
        "This turns a Redis outage into a dark Search tab — strictly worse than "
        "the slow page the ship replaced.",
        "property": "no client degrades to a build, never to a 500",
    },
    {
        "id": "stamp-a-watermark-that-was-never-computed",
        "needle": "        lifecycle_watermark=None,",
        "replacement": "        lifecycle_watermark=created_at or datetime.now(timezone.utc),",
        "why": "Publishes the BUILD time as the newest upstream fact the payload "
        "reflects. It is a fabricated freshness claim: the two are different "
        "quantities and the contract's answer for an uncomputable watermark is "
        "null, not a plausible-looking substitute.",
        "property": "the watermark is null rather than invented",
    },
]


# --------------------------------------------------------------------------
# Mutants against the serve-stale primitive this ship moved into the policy home
# --------------------------------------------------------------------------
SERVE_STALE_MUTATIONS: list[dict[str, str]] = [
    {
        "id": "single-flight-that-isnt",
        "needle": "    token = acquire_refresh_lock(client, keys)\n    if token is None:",
        "replacement": "    token = acquire_refresh_lock(client, keys) or \"unlocked\"\n    if token is None:",
        "why": "Every reader behind one expiry starts its own rebuild. The stampede "
        "is worse than the thing being fixed, and it fires precisely when the "
        "surface is busiest.",
        "property": "one expiry produces exactly ONE rebuild",
    },
    {
        "id": "release-without-owning",
        "needle": "            release_refresh_lock(client, keys, token)\n\n    task = loop.create_task(_run())",
        "replacement": "            release_refresh_lock(client, keys, \"not-my-token\")\n\n    task = loop.create_task(_run())",
        "why": "#1678 finding 1, reintroduced: a releaser that cannot name the "
        "token. The lock outlives its holder's rebuild and the next reader "
        "cannot take it, so single-flight degrades to no-flight until the TTL.",
        "property": "the lock is released by OWNER TOKEN",
    },
    {
        "id": "park-the-lock-on-a-rebuild-that-never-started",
        "needle": "        release_refresh_lock(client, keys, token)\n        return False",
        "replacement": "        return False",
        "why": "No running loop, so nothing was scheduled — but the lock is kept for "
        "REFRESH_LOCK_TTL anyway. Two minutes in which every reader is told "
        "somebody is rebuilding and nobody is.",
        "property": "a refused refresh gives its lock back",
    },
    {
        "id": "let-the-rebuild-be-garbage-collected",
        "needle": "    task = loop.create_task(_run())\n    _REFRESH_TASKS.add(task)",
        "replacement": "    task = loop.create_task(_run())\n    _REFRESH_TASKS.discard(task)",
        "why": "asyncio holds only a weak reference to a bare task. Without a strong "
        "ref the rebuild can vanish mid-flight, the mirror is never replaced, and "
        "serve-stale quietly becomes serve-stale-forever until the age ceiling "
        "starts making everyone rebuild synchronously again.",
        "property": "the rebuild is strongly referenced until it finishes",
    },
    {
        "id": "a-failed-rebuild-parks-the-lock",
        "needle": "        finally:\n            release_refresh_lock(client, keys, token)",
        "replacement": "        finally:\n            pass",
        "why": "One failing build costs REFRESH_LOCK_TTL of no refresh at all — and "
        "because the failure is caught and logged, nothing about the tier looks "
        "wrong while it happens.",
        "property": "a failed rebuild still releases the lock",
    },
    {
        "id": "serve-stale-forever-with-no-loop",
        "needle": "        release_refresh_lock(client, keys, token)\n        return False",
        "replacement": "        release_refresh_lock(client, keys, token)\n        return True",
        "why": "No loop means nothing can run behind the caller, so returning True "
        "tells it to serve a mirror that will never be replaced.",
        "property": "no loop means build synchronously, not serve stale forever",
    },
    {
        "id": "the-lock-loser-blocks",
        "needle": "        return client is not None",
        "replacement": "        return False",
        "why": "A reader that loses the lock race is told to build synchronously — "
        "so N-1 of N readers pay the scan anyway and the single-flight lock buys "
        "nothing except one saved build.",
        "property": "losing the lock race still serves the mirror",
    },
]


def read_source(path: Path) -> str:
    return path.read_text()


def apply_mutant(source: str, mutant: dict[str, str]) -> str:
    needle, replacement = mutant["needle"], mutant["replacement"]
    count = source.count(needle)
    if count != 1:
        raise AssertionError(
            f"mutant {mutant['id']!r}: anchor matched {count} times, expected exactly 1. "
            "The module was refactored — re-target the mutant rather than deleting it."
        )
    return source.replace(needle, replacement)


def load_module(source: str, name: str, path: Path):
    """Exec `source` as a standalone module. Never touches disk.

    The throwaway name is registered in `sys.modules` FOR THE DURATION OF THE
    EXEC and removed afterwards. `@dataclass` resolves its own class's module out
    of `sys.modules` while it is decorating, so a module that is not there yet
    dies with an `AttributeError` on `NoneType.__dict__` — an import-time death
    that this harness would otherwise report as a kill for every single mutant.
    """
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def oracle(dotted: str, module) -> list[str]:
    """Re-exec the shipped guard file against `module`. Returns FAILURES.

    Empty list == the property holds. A mutant is KILLED when this is non-empty.

    The guard module is RELOADED with the mutant already in `sys.modules`, so
    its own module-scope `from app.utils import ... as fcc` binds the mutant.
    Rebinding attributes after the fact — the shape the movers harness needed —
    is not enough here, because the guard file's helpers close over the module
    object at definition time.
    """
    failures: list[str] = []
    package_name, _, leaf = dotted.rpartition(".")
    package = importlib.import_module(package_name)

    saved = sys.modules.get(dotted)
    saved_attr = getattr(package, leaf, None)
    # 🔴 BOTH, and the second one is the whole battery.
    # `sys.modules[dotted] = module` alone is not enough: `from app.utils import
    # event_concept_cache as x` resolves through the PARENT PACKAGE's attribute,
    # so the guard file keeps binding the real module while the route — which
    # imports the dotted name and therefore reads `sys.modules` — gets the
    # mutant. The two then disagree about which `_REFRESH_TASKS` set exists and
    # which `get_client` a test patched, and every mutant reads as a baseline
    # failure. Found by a red baseline; recorded here so it stays fixed.
    sys.modules[dotted] = module
    setattr(package, leaf, module)
    try:
        guard = importlib.import_module("tests.test_futures_categories_cache")
        guard = importlib.reload(guard)

        for name in sorted(n for n in dir(guard) if n.startswith("test_")):
            fn = getattr(guard, name)
            if not callable(fn):
                continue
            try:
                _call_guard(guard, fn)
            except Exception as exc:  # noqa: BLE001 — a failure IS the signal
                failures.append(f"{name}: {type(exc).__name__}: {exc}"[:200])
    finally:
        if saved is not None:
            sys.modules[dotted] = saved
        else:  # pragma: no cover — the module is always importable here
            sys.modules.pop(dotted, None)
        if saved_attr is not None:
            setattr(package, leaf, saved_attr)
        importlib.reload(importlib.import_module("tests.test_futures_categories_cache"))

    return failures


def _call_guard(guard, fn):
    """Run one guard function, supplying the one fixture it uses by hand.

    The suite's only fixture is `_clear_noop_calls`, an autouse teardown. There
    is no pytest process here, so it is applied around the call explicitly —
    silently skipping it would let state leak between mutants and turn a kill
    into a survivor two mutants later.
    """
    import inspect as _inspect

    if list(_inspect.signature(fn).parameters):
        # No guard function in this suite takes an argument. If one grows a
        # fixture, this harness must learn to supply it rather than skip it.
        raise AssertionError(
            f"{fn.__name__} takes fixtures this harness does not supply — "
            "teach it the fixture; do not narrow the oracle."
        )
    guard._NOOP_CALLS.clear()
    guard.concept_cache._REFRESH_TASKS.clear()
    try:
        fn()
    finally:
        guard._NOOP_CALLS.clear()
        guard.concept_cache._REFRESH_TASKS.clear()


def _run_table(label: str, dotted: str, path: Path, table, start: int) -> tuple[int, list]:
    base = read_source(path)
    survivors = []
    for offset, mutant in enumerate(table):
        i = start + offset
        try:
            mutated = apply_mutant(base, mutant)
            module = load_module(mutated, f"{label}_mutant_{i}", path)
            failures = oracle(dotted, module)
        except AssertionError as exc:
            print(f"M{i} {mutant['id']:42s} ANCHOR DRIFT — {exc}")
            raise SystemExit(2)
        except Exception as exc:  # noqa: BLE001 — an import-time death IS a kill
            failures = [f"module failed to load: {type(exc).__name__}: {exc}"[:200]]

        if failures:
            print(f"M{i} {mutant['id']:42s} KILLED   ({len(failures)} assertion(s))")
            print(f"     property: {mutant['property']}")
            print(f"     first   : {failures[0]}")
        else:
            survivors.append(mutant)
            print(f"M{i} {mutant['id']:42s} SURVIVED <- missing assertion")
            print(f"     property: {mutant['property']}")
            print(f"     why      : {mutant['why']}")
    return start + len(table), survivors


def main() -> int:
    total = len(CENSUS_MUTATIONS) + len(SERVE_STALE_MUTATIONS)

    # 🔴 THE DENOMINATOR IS PRINTED BEFORE THE FIRST VERDICT. LAT-P120's finding:
    # a battery that announces its total only in the summary lets a run that died
    # after nine of fifteen read as a clean nine-for-nine.
    print(f"battery: {total} mutants across 2 modules, oracle {ORACLE}")

    # The unmutated modules must pass the oracle, or every kill below is
    # meaningless — a battery whose baseline is red kills nothing.
    for dotted, path in MODULE_PATHS.items():
        baseline = oracle(dotted, load_module(read_source(path), "baseline", path))
        if baseline:
            print(f"BASELINE IS RED for {dotted} — the battery proves nothing:")
            for f in baseline:
                print("   ", f)
            return 2
    print("baseline: GREEN on both modules\n")

    survivors: list[dict[str, str]] = []
    nxt, s = _run_table(
        "census", "app.utils.futures_categories_cache", CENSUS, CENSUS_MUTATIONS, 1
    )
    survivors += s
    _, s = _run_table(
        "servestale", "app.utils.event_concept_cache", CONCEPT_CACHE,
        SERVE_STALE_MUTATIONS, nxt,
    )
    survivors += s

    print()
    print(f"{total - len(survivors)}/{total} mutants killed")
    if survivors:
        print("SURVIVORS — each is a missing assertion, not a passing grade:")
        for surv in survivors:
            print(f"  - {surv['id']}: {surv['property']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
