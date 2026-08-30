"""LAT-P139 — the serve-a-stale-copy-of-a-clock mutation class.

WHAT A MUTANT PROVES HERE
-------------------------
This ship's whole argument is that a five-minute-old copy of the Search
zero-state is safe to serve BECAUSE the only clock-relative text in it is
re-rendered from the serving clock. Every way that argument can quietly stop
holding produces the same 200, the same well-formed JSON and the same fast
response — and a chip that says "Tips off in 12 min" about a game that started
twenty minutes ago. There is no exception, no log line and no failing request.
It is exactly the trade LAT-P122 and LAT-P123 refused: latency bought with a
formatting lie.

So the question this harness asks is not "does the renderer work". It is:
**would `tests/test_search_suggestions_mirror_lat_p139.py` NOTICE if it
stopped?** Each mutant below breaks one property that file claims to defend, and
a SURVIVOR is a missing assertion, reported as such per mutant.

WHY THE ORACLE IS THE REAL GUARD FILE, RUN IN-PROCESS AGAINST A MUTATED IMPORT
------------------------------------------------------------------------------
Re-implementing the assertions here would prove that this file's copy of them
still fails, which is worth nothing. The guard module is imported and its test
functions are called directly with the mutated tier swapped into `sys.modules`
and rebound on the guard, so the assertions executed are byte-for-byte the ones
in the repository.

🔴 SCOPE, DECLARED RATHER THAN DISCOVERED. The oracle runs the guard file's
FIXTURE-FREE tests — classes 1 to 4, which are the tier's own properties. Class
5 (`TestTheRoutesServeDecision`) takes `redis_double` and `monkeypatch`, and
supplying pytest fixtures by hand to assert things about `routes/events.py`
would be a second harness with a different target. Every mutant below is
therefore a mutation of `app/utils/search_suggestions_cache.py`, and a mutant
that only the route tests could catch is deliberately not in the table — it
would report a survivor that means "out of scope", which is the noise this
program's harnesses exist to avoid.

NOTHING IS WRITTEN TO DISK. The mutated source is exec'd into a throwaway module
and swapped into `sys.modules` in THIS process. A harness that edits a tracked
file and restores it loses the file when the run dies mid-way, and it trips
`test_every_on_disk_harness_is_guarded`, which keys on the write VERB (P114-2).
Hence `MUTATES_WORKING_TREE = False` and the `DISK_FREE` registration in
`scan_mutation_residue.py`.

USAGE

    python3 scripts/evals/search_suggestions_mirror_mutations.py

Exit codes (gotcha #54): `0` all mutants killed, `1` at least one SURVIVOR — a
real result, `2` the battery could not be run.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

#: Declared for `scan_mutation_residue.DISK_FREE`, and VERIFIED by it: every
#: mutant here is a source STRING exec'd into a throwaway module, so there is no
#: backup to restore and a SIGKILL can leave nothing behind.
MUTATES_WORKING_TREE = False

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TIER = BACKEND / "app/utils/search_suggestions_cache.py"
MODULE_NAME = "app.utils.search_suggestions_cache"
ORACLE = "tests/test_search_suggestions_mirror_lat_p139.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# --------------------------------------------------------------------------
# Mutants: id, needle, replacement, why, property
# --------------------------------------------------------------------------
MUTATIONS: list[dict[str, str]] = [
    {
        "id": "expiry-guard-truncates-to-minutes",
        "needle": "    if remaining < 0:\n        return None\n    minutes = int(remaining / 60)",
        "replacement": "    minutes = int(remaining / 60)\n    if minutes < 0:\n        return None",
        "why": "Moves the expiry test onto the truncated minute count. `int()` "
        "rounds toward zero, so a game that kicked off 59 s ago reads as 0 and "
        "prints 'Tips off in 0 min' for a full minute after kickoff.",
        "property": "the expiry test reads seconds, not truncated minutes",
    },
    {
        "id": "hour-branch-off-by-one",
        "needle": "    if minutes < 60:\n        return f\"Tips off in {minutes} min\"",
        "replacement": "    if minutes <= 60:\n        return f\"Tips off in {minutes} min\"",
        "why": "Moves the minute/hour boundary by one, so a game exactly an hour "
        "out prints 'Tips off in 60 min' where the route has always printed "
        "'Starts in 1h'. A rendered label that does not reproduce the built one "
        "is the drift that makes a mirror unserveable.",
        "property": "the render reproduces the route's original text exactly",
    },
    {
        "id": "expired-chips-are-kept",
        "needle": "        label = countdown_label(deadline, now)\n        if label is None:\n            continue",
        "replacement": "        label = countdown_label(deadline, now) or item.get(\"label\")",
        "why": "Keeps a suggestion whose game has started, falling back to the "
        "label baked at build time — i.e. serves the stored countdown verbatim, "
        "which is precisely the defect LAT-P124 refused to create.",
        "property": "a started game is dropped, never re-served with its old label",
    },
    {
        "id": "render-mutates-the-stored-artifact",
        "needle": "        item = {k: v for k, v in item.items() if k != COUNTDOWN_FIELD}",
        "replacement": "        item.pop(COUNTDOWN_FIELD, None)",
        "why": "Strips the deadline out of the caller's dict. `_publish_search_"
        "suggestions` renders the same object it writes, so the payload reaching "
        "Redis loses its deadlines and every later mirror read renders to "
        "nothing — the mirror becomes a permanent miss and the ship a no-op.",
        "property": "render is pure; the stored copy keeps its deadlines",
    },
    {
        "id": "deadline-leaks-onto-the-wire",
        "needle": "        item = {k: v for k, v in item.items() if k != COUNTDOWN_FIELD}",
        "replacement": "        item = dict(item)",
        "why": "Publishes the tier's internal deadline field to clients, changing "
        "the response contract inside a latency change.",
        "property": "the deadline is internal and never served",
    },
    {
        "id": "empty-after-render-is-servable",
        "needle": "    if not renders_to_something(payload, now):\n        return False, \"empty_after_render\"",
        "replacement": "    if False:\n        return False, \"empty_after_render\"",
        "why": "Lets a mirror whose every chip has expired be served, so a reader "
        "gets a blank zero-state that no build ever produced.",
        "property": "a mirror that renders to nothing is refused",
    },
    {
        "id": "undated-mirror-is-servable",
        "needle": "    if age is None:\n        # A payload that cannot say when it was computed",
        "replacement": "    if False:\n        # A payload that cannot say when it was computed",
        "why": "Serves a payload that cannot report its own age, under an age "
        "bound that therefore cannot be evaluated. `age` is then None and the "
        "ceiling comparison below is a TypeError inside a serve path.",
        "property": "an undated payload is refused rather than served blind",
    },
    {
        "id": "the-ceiling-becomes-an-hour",
        "needle": "STALE_SERVE_CEILING = 5",
        "replacement": "STALE_SERVE_CEILING = 60",
        "why": "Widens how stale a served copy may be from 5 minutes to an hour, "
        "and silently gives this surface a staleness law that disagrees with the "
        "two tiers on the event page.",
        "property": "the ceiling is 5x the fresh TTL and inherited, not invented",
    },
    {
        "id": "the-fresh-ttl-is-widened",
        "needle": "FRESH_TTL = 60",
        "replacement": "FRESH_TTL = 600",
        "why": "Buys latency by rebuilding ten times less often. It also silently "
        "multiplies the ceiling, which is derived from it — so one edit moves two "
        "numbers, which is why the ceiling test asserts both the product and the "
        "multiplier.",
        "property": "the fresh TTL is unchanged at 60 s",
    },
    {
        "id": "the-primary-key-is-renamed",
        "needle": 'CACHE_PREFIX = "bainluck:search_suggestions:"',
        "replacement": 'CACHE_PREFIX = "bainluck:search_suggestions_v2:"',
        "why": "Orphans every warm entry at deploy, putting the whole fleet on the "
        "13 s build at once — the failure this tier's key naming exists to avoid.",
        "property": "the primary reproduces the live production key",
    },
    {
        "id": "the-primary-is-served-unrendered",
        "needle": "            return with_availability(render(primary, now), AVAILABILITY_LIVE), \"live\"",
        "replacement": "            return with_availability(primary, AVAILABILITY_LIVE), \"live\"",
        "why": "Serves the stored bytes straight through on the fresh path, so a "
        "60 s-old primary prints a minute count up to a minute wrong — and the "
        "deadline field leaks to the client with it.",
        "property": "every serve path renders; there is one code path, not two",
    },
    {
        "id": "the-mirror-skips-its-own-checks",
        "needle": "    servable, reason = mirror_is_servable(mirror, now)\n    if not servable:",
        "replacement": "    servable, reason = mirror_is_servable(mirror, now)\n    if False:",
        "why": "Serves any mirror at all, of any age, including a day-old one — "
        "the fail-closed half removed while every test that only reads the fresh "
        "path stays green.",
        "property": "the ceiling is enforced on the read path, not just computable",
    },
    {
        "id": "write-stores-the-rendered-copy",
        "needle": "    write_payload(client, keys(), enveloped, primary_ttl=FRESH_TTL)",
        "replacement": "    write_payload(client, keys(), render(enveloped), primary_ttl=FRESH_TTL)",
        "why": "Bakes the build clock's minute count into the mirror, which is "
        "LAT-P124's objection to a mirror, reintroduced by the writer.",
        "property": "what is stored carries deadlines, not rendered text",
    },
    {
        "id": "unparseable-deadline-is-served",
        "needle": "        if deadline is None:",
        "replacement": "        if False:",
        "why": "An unparseable deadline falls through to `countdown_label(None, "
        "now)`. Whatever that does, the item's build-time label is what a reader "
        "would have got — a stored countdown served verbatim.",
        "property": "a deadline that cannot be re-rendered is dropped",
    },
]


def read_source() -> str:
    return TIER.read_text()


def apply_mutant(source: str, mutant: dict[str, str]) -> str:
    needle, replacement = mutant["needle"], mutant["replacement"]
    count = source.count(needle)
    if count != 1:
        raise AssertionError(
            f"mutant {mutant['id']!r}: anchor matched {count} times, expected exactly 1. "
            "The tier was refactored — re-target the mutant rather than deleting it."
        )
    return source.replace(needle, replacement)


def load_module(source: str, name: str):
    """Exec `source` as a standalone module. Never touches disk."""
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(TIER)
    exec(compile(source, str(TIER), "exec"), module.__dict__)
    return module


def oracle(module) -> list[str]:
    """Run the guard file's fixture-free properties against `module`.

    Returns FAILURES. Empty list == the tier holds. A mutant is KILLED when this
    is non-empty.
    """
    failures: list[str] = []
    saved = sys.modules.get(MODULE_NAME)
    sys.modules[MODULE_NAME] = module
    try:
        guard = importlib.import_module(
            "tests.test_search_suggestions_mirror_lat_p139"
        )
        importlib.reload(guard)
        guard.ssc = module

        for cls_name in (
            "TestTheCountdownIsNoLongerBaked",
            "TestTheRenderer",
            "TestTheMirrorCannotPrintAWrongTime",
            "TestTheSlots",
        ):
            cls = getattr(guard, cls_name)
            instance = cls()
            for name in sorted(n for n in dir(cls) if n.startswith("test_")):
                fn = getattr(instance, name)
                try:
                    result = fn()
                    if asyncio.iscoroutine(result):
                        asyncio.run(result)
                except Exception as exc:  # noqa: BLE001 — a failure IS the signal
                    failures.append(
                        f"{cls_name}.{name}: {type(exc).__name__}: {exc}"[:220]
                    )
    finally:
        if saved is not None:
            sys.modules[MODULE_NAME] = saved
        else:
            sys.modules.pop(MODULE_NAME, None)
    return failures


def main() -> int:
    try:
        source = read_source()
    except OSError as exc:
        print(f"BATTERY COULD NOT RUN: {exc}")
        return 2

    # The control. If the UNMUTATED tier does not pass its own guard file, every
    # "killed" below is meaningless — a mutant would be reported dead because the
    # oracle fails on everything.
    baseline = oracle(load_module(source, "ssc_baseline"))
    if baseline:
        print("BATTERY COULD NOT RUN — the unmutated tier fails its own guards:")
        for line in baseline:
            print(f"    {line}")
        return 2
    print(f"control: unmutated tier passes {ORACLE}'s fixture-free properties\n")

    survivors = []
    for mutant in MUTATIONS:
        try:
            mutated = apply_mutant(source, mutant)
        except AssertionError as exc:
            print(f"BATTERY COULD NOT RUN: {exc}")
            return 2
        try:
            module = load_module(mutated, f"ssc_{mutant['id'].replace('-', '_')}")
            failures = oracle(module)
        except Exception as exc:  # noqa: BLE001 — an import-time death IS a kill
            failures = [f"import: {type(exc).__name__}: {exc}"[:220]]
        if failures:
            print(f"KILLED   {mutant['id']}")
            print(f"         by {failures[0]}")
        else:
            survivors.append(mutant)
            print(f"SURVIVOR {mutant['id']}")
            print(f"         property left undefended: {mutant['property']}")
            print(f"         what it does: {mutant['why']}")

    print(f"\n{len(MUTATIONS) - len(survivors)}/{len(MUTATIONS)} killed")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
