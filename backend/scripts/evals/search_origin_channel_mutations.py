"""LAT-P118 — the suppression-that-suppresses-nothing mutation class.

WHAT A MUTANT PROVES HERE
-------------------------
A write suppression is the second-easiest thing in this repo to ship broken and
never find out — the first being a warmer, for the same reason. Its only
observable effect is that a row does NOT exist. Every way it can fail silently
produces the same green deploy, the same green task, and a `search_query_logs`
table that looks exactly like a clean one:

* the header is read under a name nobody sends       -> table looks clean
* the comparison is inverted                         -> table looks clean, and
                                                        it is PEOPLE who stopped
                                                        being counted
* the guard is dropped from one of the two exits     -> table looks clean unless
                                                        you probe a warm term
* FastAPI stops injecting the Request                -> table looks clean

Only the second of those is visible from the outside at all, and it is visible
as the *opposite* of a bug: fewer rows.

So the question is not "does the header work". It is: **would
`tests/test_search_origin_channel_p118.py` NOTICE if it stopped?** A SURVIVOR is
a missing assertion, reported as one.

WHY THE ORACLE IS THE REAL GUARD FILES, RUN OUT OF PROCESS
-----------------------------------------------------------
Re-implementing the assertions here would prove only that this file's copy of
them still fails. The oracle is a subprocess `pytest` over the shipped suites,
with this module loaded as a plugin that swaps one mutated function into
`app.routes.events` at `pytest_configure` time.

`test_search_response_cache.py` is in the oracle deliberately and not for
symmetry: M8 removes the `_suppress_search_log` arm of the guard this ship
edits, which re-opens #1866 (the warmer voting for its own head). Nothing in
LAT-P118's own file would notice, and the assertion that does notice already
exists in that older suite. A guard that only checks the newest half of a
condition is how the older half gets deleted.

NOTHING IS WRITTEN TO DISK. The mutated function is compiled UNDER THE REAL
FILENAME and exec'd into the module's own namespace, so `inspect.getsource`
still reads the unmutated file — which means the structural tests correctly
decline to react to a runtime mutant, and every kill below is a BEHAVIOURAL
kill. A harness that edits a tracked file and restores it loses the file when
the run dies mid-way, and trips `test_every_on_disk_harness_is_guarded`.

USAGE

    python3 scripts/evals/search_origin_channel_mutations.py

Exit codes (gotcha #54 — read the VALUE): `0` all mutants killed, `1` at least
one SURVIVOR (a real result), `2` the battery could not be run.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]

#: Both halves. The second is not decoration — see the module docstring.
ORACLES = [
    "tests/test_search_origin_channel_p118.py",
    "tests/test_search_response_cache.py",
]

#: Where every needle below is supposed to live. Declared even though this
#: harness never writes to disk, because `scan_mutation_residue.py`'s Pass A
#: asserts each needle is still PRESENT in its target — which is how a mutant
#: that has quietly stopped aiming at anything gets caught. A harness whose
#: needles have drifted reports 10/10 killed while testing nothing.
TARGET = BACKEND / "app/routes/events.py"

#: (id, function, needle, replacement, why a survivor would matter)
#:
#: Uniform on purpose: every mutant is a `needle`/`replacement` pair inside a
#: named function of `TARGET`. M9 mutates what is effectively a constant, and it
#: is still written as a source pair rather than a `setattr` on the module —
#: `scan_mutation_residue.py`'s Pass A harvests these tables by key and asserts
#: each needle is still PRESENT in its target, and a mutant expressed in any
#: other shape is one the residue scanner cannot see.
MUTANTS: list[dict] = [
    {
        "id": "M1-channel-always-says-person",
        "function": "_request_is_automation",
        "needle": "    if request is None:\n        return False",
        "replacement": "    if True:\n        return False",
        "why": "The channel is a no-op. Every harness goes back to voting and "
        "nothing anywhere reports a difference — the table just keeps "
        "filling, which is what it looked like before this ship.",
    },
    {
        "id": "M2-comparison-inverted",
        "function": "_request_is_automation",
        "needle": "return raw.strip().lower() != _ORIGIN_USER",
        "replacement": "return raw.strip().lower() == _ORIGIN_USER",
        "why": "The polarity flips: machines vote and PEOPLE are silenced. The "
        "row count falls, which reads as the fix working, and the head "
        "quietly becomes 100 % machine instead of 99.7 %.",
    },
    {
        "id": "M3-whitespace-not-trimmed",
        "function": "_request_is_automation",
        "needle": "return raw.strip().lower() != _ORIGIN_USER",
        "replacement": "return raw.lower() != _ORIGIN_USER",
        "why": "`X-Bainluck-Origin: user ` from any client that pads its "
        "headers is suppressed. Silent, and it removes exactly the "
        "traffic the head most needs.",
    },
    {
        "id": "M4-case-not-folded",
        "function": "_request_is_automation",
        "needle": "return raw.strip().lower() != _ORIGIN_USER",
        "replacement": "return raw.strip() != _ORIGIN_USER",
        "why": "`User` is not `user`. HTTP header VALUES are case-sensitive on "
        "the wire, so this depends on a convention no client owes us.",
    },
    {
        "id": "M5-empty-value-reads-as-a-claim",
        "function": "_request_is_automation",
        "needle": "    if not raw:\n        return False",
        "replacement": "    if raw is None:\n        return False",
        "why": "A middlebox that normalises the header to `` silently deletes a "
        "person's vote. gotcha #53 at the header level: an empty value "
        "and a stated value must not read the same.",
    },
    {
        "id": "M6-unanswerable-request-reads-as-machine",
        "function": "_request_is_automation",
        "needle": "    if request is None:\n        return False",
        "replacement": "    if request is None:\n        return True",
        "why": "Fails the WRONG way. Every in-process caller — and any route "
        "invoked without a Request — stops being counted, draining the "
        "head invisibly. Over-suppression cannot be seen by looking.",
    },
    {
        "id": "M7-origin-arm-dropped-from-the-guard",
        "function": "_record_search_query",
        "needle": "if _suppress_search_log.get() or _request_is_automation(request):",
        "replacement": "if _suppress_search_log.get():",
        "why": "The ship, removed. The header is still read by /typeahead, so "
        "the channel LOOKS alive; only /search keeps voting.",
    },
    {
        "id": "M8-contextvar-arm-dropped-from-the-guard",
        "function": "_record_search_query",
        "needle": "if _suppress_search_log.get() or _request_is_automation(request):",
        "replacement": "if _request_is_automation(request):",
        "why": "#1866 re-opened by a ship that had nothing to do with it. The "
        "warmer calls the route function directly, so it sets no header "
        "and would resume voting for its own head at ~1,900 rows a day "
        "per term. NOTHING in LAT-P118's own suite would notice.",
    },
    {
        "id": "M9-header-read-under-a-name-nobody-sends",
        "function": "_request_is_automation",
        "needle": "raw = request.headers.get(_ORIGIN_HEADER)",
        "replacement": 'raw = request.headers.get("x-bainluck-source")',
        "why": "One word wrong and the channel is inert. Every harness sends a "
        "header nobody reads; the table fills exactly as it did before, "
        "and the suppression reports nothing, because a suppression that "
        "never fires has nothing to report.",
    },
    {
        "id": "M10-typeahead-sink-stops-honouring-the-rule",
        "function": "typeahead_search",
        "needle": "if debug_evidence or debug_timing or _request_is_automation(request):",
        "replacement": "if debug_evidence or debug_timing:",
        "why": "Gotcha #128 arriving on schedule: one rule, two consumers, and "
        "the repaired copy hides the broken one. Probes stop voting in "
        "`search_query_logs` and keep voting in `search:trending:24h`, "
        "which supplies the other half of the same head.",
    },
]


def _mutated_function(mutant: dict):
    """Build the mutated function object, in memory, under the REAL filename.

    Compiling under `str(TARGET)` rather than `<mutant>` is deliberate:
    `inspect.getsource` then still reads the unmutated file, so the structural
    tests in the oracle correctly decline to react and every kill reported by
    this battery is a BEHAVIOURAL kill.
    """
    import app.routes.events as E

    name = mutant["function"]
    src = inspect.getsource(getattr(E, name))

    # `typeahead_search` carries its `@router.get(...)` decorator into
    # `getsource`. Re-executing that would register a second copy of the route
    # on the shared router, so the decorator lines are dropped — the function
    # body is what is under test, not its registration.
    lines = src.splitlines(keepends=True)
    while lines and lines[0].lstrip().startswith("@"):
        lines.pop(0)
    src = "".join(lines)

    if src.count(mutant["needle"]) != 1:
        raise SystemExit(
            f"HARNESS: needle for {mutant['id']} matched "
            f"{src.count(mutant['needle'])} times in {name}, expected exactly 1 "
            "— the source moved and this mutant is no longer aimed at anything"
        )
    mutated = src.replace(mutant["needle"], mutant["replacement"])

    ns: dict = {}
    exec(compile(mutated, str(TARGET), "exec"), E.__dict__, ns)
    return ns[name]


def _apply(mutant: dict) -> None:
    import app.routes.events as E

    setattr(E, mutant["function"], _mutated_function(mutant))


# --------------------------------------------------------------------------
# pytest plugin half — active only when $LATP118_MUTANT is set.
# --------------------------------------------------------------------------
def pytest_configure(config):  # noqa: D103 - pytest hook
    mid = os.environ.get("LATP118_MUTANT")
    if not mid:
        return
    mutant = next((m for m in MUTANTS if m["id"] == mid), None)
    if mutant is None:
        raise SystemExit(f"HARNESS: unknown mutant {mid!r}")
    _apply(mutant)


# --------------------------------------------------------------------------
# Driver half.
# --------------------------------------------------------------------------
def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("LATP118_MUTANT", None)

    print(f"LAT-P118 mutation run — oracles: {', '.join(ORACLES)}")
    print(f"{len(MUTANTS)} mutants\n")

    base = subprocess.run(
        [sys.executable, "-m", "pytest", *ORACLES, "-q"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if base.returncode != 0:
        print(f"HARNESS: baseline oracle is NOT green (exit {base.returncode}).")
        print(base.stdout[-2000:])
        return 2
    print("baseline: GREEN (exit 0)\n")

    survivors, harness_errors = [], []
    for m in MUTANTS:
        env["LATP118_MUTANT"] = m["id"]
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *ORACLES,
                "-x",
                "-q",
                "-p",
                "search_origin_channel_mutations",
            ],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        # Read the exit code BY VALUE (gotcha #124): 1 is a RESULT — the oracle
        # failed, so the mutant is dead. Anything else is the harness failing to
        # run, and a harness failure that scores as a kill is a battery that
        # reports 10/10 while testing nothing.
        if r.returncode == 1:
            print(f"{m['id']:48s} KILLED")
        elif r.returncode == 0:
            survivors.append(m)
            print(f"{m['id']:48s} SURVIVED <- missing assertion")
            print(f"     why: {m['why']}")
        else:
            harness_errors.append((m, r.returncode))
            print(f"{m['id']:48s} HARNESS ERROR (exit {r.returncode})")
            print(r.stdout[-1200:])

    print()
    if harness_errors:
        print(f"{len(harness_errors)} mutant(s) could not be run — this is not a grade.")
        return 2

    killed = len(MUTANTS) - len(survivors)
    print(f"{killed}/{len(MUTANTS)} mutants killed")
    if survivors:
        print("SURVIVORS — each is a missing assertion, not a passing grade:")
        for s in survivors:
            print(f"  - {s['id']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
