"""LAT-P115 — the warmer-that-warms-nothing mutation class.

WHAT A MUTANT PROVES HERE
-------------------------
A warmer is the single easiest thing in this codebase to ship broken and never
find out. It has no user-visible output of its own; its only observable effect
is that somebody ELSE's request was fast. Every way it can fail — writing a key
nobody reads, writing a TTL that expires before the next pass, counting a failed
shape as warmed, letting one bad shape abort the rest — produces the same green
task result and the same silent 1.4 s wait on the iOS Futures tab.

So the question this harness asks is not "does the warmer work". It is: **would
`tests/test_futures_movers_warm_p115.py` NOTICE if it stopped?** Each mutant
below breaks one property that file claims to defend, and a SURVIVOR is a
missing assertion, reported as such per mutant.

WHY THE ORACLE IS THE REAL GUARD FILE, RUN OUT OF PROCESS
---------------------------------------------------------
Re-implementing the assertions here would prove that this file's copy of them
still fails, which is worth nothing. The oracle instead runs the actual pytest
module against the mutated import, so a mutant is killed only by an assertion
that genuinely ships.

NOTHING IS WRITTEN TO DISK. The mutated source is exec'd into a throwaway module
and swapped into `sys.modules` in THIS process, around a direct call to the guard
file's test functions; the fixtures they need are supplied by hand (`_call_guard`)
because there is no pytest process to supply them. A harness that edits a tracked
file and restores it afterwards loses the file when the run dies mid-way — and
trips `test_every_on_disk_harness_is_guarded`, which keys on the write VERB and
cannot tell a temp file from a tracked one (P114-2). Removing the writes is the
right response to that gate, not loosening it.

USAGE

    python3 scripts/evals/futures_movers_warm_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` at least one SURVIVOR — a
real result, `2` the battery could not be run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
WARM = BACKEND / "app/tasks/futures_movers_warm.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# --------------------------------------------------------------------------
# Mutants: (id, needle, replacement, why, property)
# --------------------------------------------------------------------------
MUTATIONS: list[dict[str, str]] = [
    {
        "id": "warm-a-shape-nobody-asks-for",
        "needle": "WARMED_MOVERS_SHAPES: tuple[tuple[int, int], ...] = ((24, 10),)",
        "replacement": "WARMED_MOVERS_SHAPES: tuple[tuple[int, int], ...] = ((24, 20),)",
        "why": "Warms the route's default instead of the shape shipped iOS asks for. "
        "Every key write succeeds, the task reports complete, and the strip is "
        "cold on every open — the failure this whole queue is about.",
        "property": "the warmed key is the key the client reads",
    },
    {
        "id": "drop-the-producer-ttl",
        "needle": "build_and_cache_movers(hours, limit, db, rc, ttl=WARM_TTL_SECONDS)",
        "replacement": "build_and_cache_movers(hours, limit, db, rc)",
        "why": "Falls back to the route's 60 s reader TTL. The entry expires nine "
        "minutes before the producer beat can replace it, so the warmer warms "
        "a minute in ten and reports complete for all ten.",
        "property": "a producer's TTL outlives its own beat period",
    },
    {
        "id": "shorten-the-ttl-to-one-beat",
        "needle": "WARM_TTL_SECONDS = 30 * 60",
        "replacement": "WARM_TTL_SECONDS = 10 * 60",
        "why": "A TTL of exactly one beat period. `background` delivered p50 138-152 s "
        "against a declared 120 s and a max of 2,511 s (LAT-P112), so every late "
        "delivery uncovers the strip.",
        "property": "the TTL covers the delivery jitter the rail actually has",
    },
    {
        "id": "green-on-nothing",
        "needle": '    if warmed == total:\n        terminal = "complete"',
        "replacement": '    if True:\n        terminal = "complete"',
        "why": "A pass that warmed zero shapes reports `complete`. gotcha #53 exactly: "
        "'it returned' is not 'it worked', and this is the form where nobody "
        "ever finds out.",
        "property": "a pass that warmed nothing must not read green",
    },
    {
        "id": "count-the-shape-before-it-succeeds",
        "needle": "                timeout=PER_SHAPE_TIMEOUT_SECONDS,\n            )\n            warmed += 1",
        "replacement": "                timeout=PER_SHAPE_TIMEOUT_SECONDS,\n            ) if False else None\n            warmed += 1",
        "why": "Counts a shape as warmed without building it. The summary is perfect "
        "and the cache is empty.",
        "property": "`completed` counts shapes actually warmed",
    },
    {
        "id": "one-bad-shape-wipes-the-pass",
        "needle": "        except Exception as exc:  # noqa: BLE001 — one shape must not wipe the pass",
        "replacement": "        except ZeroDivisionError as exc:",
        "why": "Narrows the guard so a real build error escapes, aborting every "
        "remaining shape AND — because the caller is `update_max_movement` — "
        "putting a cache failure on the column update's error path. gotcha #42.",
        "property": "one bad shape does not wipe the pass",
    },
    {
        "id": "unbound-the-inner-operation",
        "needle": "PER_SHAPE_TIMEOUT_SECONDS = 30",
        "replacement": "PER_SHAPE_TIMEOUT_SECONDS = 100000",
        "why": "Removes the bound on the longest uninterrupted operation, so a wedged "
        "build runs into `update_max_movement`'s 120 s soft limit and takes the "
        "column update down with it as a SIGKILL rather than a reported timeout.",
        "property": "the inner op is bounded well inside the caller's budget",
    },
]


ORACLE = "tests/test_futures_movers_warm_p115.py"


def read_source() -> str:
    return WARM.read_text()


def apply_mutant(source: str, mutant: dict[str, str]) -> str:
    needle, replacement = mutant["needle"], mutant["replacement"]
    count = source.count(needle)
    if count != 1:
        raise AssertionError(
            f"mutant {mutant['id']!r}: anchor matched {count} times, expected exactly 1. "
            "The warmer was refactored — re-target the mutant rather than deleting it."
        )
    return source.replace(needle, replacement)


def load_module(source: str, name: str):
    """Exec `source` as a standalone module. Never touches disk."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(WARM)
    exec(compile(source, str(WARM), "exec"), module.__dict__)
    return module


# --------------------------------------------------------------------------
# The oracle — the SHIPPED assertions, run against the mutated module.
# --------------------------------------------------------------------------


def oracle(module) -> list[str]:
    """Run the guard file's properties against `module`. Returns FAILURES.

    Empty list == the warmer holds. A mutant is KILLED when this is non-empty.

    The guard file is imported and its test functions are called directly with
    the mutated module swapped into `sys.modules`, so the assertions executed
    are byte-for-byte the ones in the repository — not a paraphrase of them.
    """
    import app.tasks.futures_movers_warm as real_warm

    failures: list[str] = []
    saved = sys.modules["app.tasks.futures_movers_warm"]
    sys.modules["app.tasks.futures_movers_warm"] = module
    try:
        import importlib

        guard = importlib.import_module("tests.test_futures_movers_warm_p115")
        importlib.reload(guard)

        # Rebind the names the guard imported at module scope from the real
        # module, so `from ... import WARM_TTL_SECONDS` sees the mutant's value.
        guard.warm_mod = module
        guard.warm_futures_movers = module.warm_futures_movers
        guard.WARM_TTL_SECONDS = module.WARM_TTL_SECONDS
        guard.WARMED_MOVERS_SHAPES = module.WARMED_MOVERS_SHAPES
        guard.PER_SHAPE_TIMEOUT_SECONDS = module.PER_SHAPE_TIMEOUT_SECONDS

        for name in sorted(n for n in dir(guard) if n.startswith("test_")):
            fn = getattr(guard, name)
            try:
                _call_guard(guard, fn)
            except Exception as exc:  # noqa: BLE001 — a failure IS the signal
                failures.append(f"{name}: {type(exc).__name__}: {exc}"[:200])
    finally:
        sys.modules["app.tasks.futures_movers_warm"] = saved
        del real_warm

    return failures


def _call_guard(guard, fn):
    """Supply the guard's fixtures by hand — no pytest process, no disk."""
    import inspect as _inspect

    params = list(_inspect.signature(fn).parameters)
    kwargs = {}
    session = None
    for p in params:
        if p == "session":
            session = _make_session(guard)
            kwargs["session"] = session
        elif p == "rc":
            kwargs["rc"] = guard.FakeRedis()
        elif p == "monkeypatch":
            kwargs["monkeypatch"] = _MonkeyPatch()
    mp = kwargs.get("monkeypatch")
    try:
        fn(**kwargs)
    finally:
        if mp is not None:
            mp.undo()
        if session is not None:
            session.close()


def _make_session(guard):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, FuturesMarket, FuturesOutcome

    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    s = Session(eng)
    for mid in range(1, 13):
        change = round(0.90 - 0.05 * mid, 4)
        s.add(guard._market(mid, abs(change)))
        s.add(guard._outcome(mid * 1000, mid, change))
    s.commit()
    return s


class _MonkeyPatch:
    """The three `monkeypatch` operations the guard file uses, and no more."""

    def __init__(self):
        self._undo: list = []

    def setattr(self, target, name, value=None, raising=True):
        if isinstance(target, str):
            mod_name, _, attr = target.rpartition(".")
            import importlib

            obj = importlib.import_module(mod_name)
            value = name
            name = attr
        else:
            obj = target
        had = hasattr(obj, name)
        old = getattr(obj, name, None)
        setattr(obj, name, value)
        self._undo.append((obj, name, old, had))

    def undo(self):
        while self._undo:
            obj, name, old, had = self._undo.pop()
            if had:
                setattr(obj, name, old)
            else:
                delattr(obj, name)


def main() -> int:
    base = read_source()

    # The unmutated module must pass the oracle, or every kill below is
    # meaningless — a battery whose baseline is red kills nothing.
    baseline = oracle(load_module(base, "warm_baseline"))
    if baseline:
        print("BASELINE IS RED — the battery proves nothing. Failures:")
        for f in baseline:
            print("   ", f)
        return 2

    print(f"baseline: {len(MUTATIONS)} mutants, oracle {ORACLE}, GREEN\n")

    survivors = []
    for i, mutant in enumerate(MUTATIONS, 1):
        try:
            mutated = apply_mutant(base, mutant)
            module = load_module(mutated, f"warm_mutant_{i}")
            failures = oracle(module)
        except AssertionError as exc:
            print(f"M{i} {mutant['id']:38s} ANCHOR DRIFT — {exc}")
            return 2
        except Exception as exc:  # noqa: BLE001 — an import-time death IS a kill
            failures = [f"module failed to load: {type(exc).__name__}: {exc}"[:200]]

        if failures:
            print(f"M{i} {mutant['id']:38s} KILLED   ({len(failures)} assertion(s))")
            print(f"     property: {mutant['property']}")
            print(f"     first   : {failures[0]}")
        else:
            survivors.append(mutant)
            print(f"M{i} {mutant['id']:38s} SURVIVED <- missing assertion")
            print(f"     property: {mutant['property']}")
            print(f"     why      : {mutant['why']}")

    print()
    killed = len(MUTATIONS) - len(survivors)
    print(f"{killed}/{len(MUTATIONS)} mutants killed")
    if survivors:
        print("SURVIVORS — each is a missing assertion, not a passing grade:")
        for s in survivors:
            print(f"  - {s['id']}: {s['property']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
