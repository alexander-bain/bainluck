"""Build a sport for the flip gate to refuse, instead of borrowing a real one.

**SHIP: this is #4436's substrate** (pillar: MATCHING, riding #2867 — *every game
exists on the site before any market lists it; nothing goes blank when ESPN
does*). It ships no production code and changes no reader's screen. It exists so
that the guards proving `flip_permitted` still refuses survive the next ruling.

WHY A SPECIMEN HAS TO BE CONSTRUCTED
════════════════════════════════════
`flip_permitted` refuses in a deliberate order — population, shadow stamper,
discovery pass, governing number (D63), streak, and only then the D104 ruling.
Every negative control for those branches has so far been a REAL sport borrowed
from the live config, and D104 is steadily emptying that pool: ruling a sport
removes it from the set that can still demonstrate a refusal.

It has already cost coverage once. #4493 (the NBA) turned four tests red and left
`test_a_discoverable_sport_is_unaffected_and_still_permits_at_seven` **green for
the wrong reason** — passing on the D104 branch while claiming to prove something
about seven days. Two files carry a warning about the next one:

    "that release must give these tests a synthetic sport rather than move this
     line again"                      -- test_authority_flip_switch.py

    "It will need a synthetic sport registered into the config for the duration
     of the test. Do not discover this at merge time."
                                      -- test_the_flip_gate_states_its_denominator_3071.py

This is that synthetic sport. A borrowed specimen asserts *today's config*; a
constructed one asserts *the branch*, which is what those tests are named after.

WHAT THIS DELIBERATELY DOES NOT DO
══════════════════════════════════
It does not assert that any real sport is in any particular state. That fact is
worth keeping and is worth CHANGING when a ruling changes it — so it stays its
own separate assertion, one obvious line, rather than being smuggled into a
behavioural test where a ruling silently guts it.

THE TRAP THIS HELPER EXISTS TO CENTRALISE
═════════════════════════════════════════
`SHADOW_STAMPERS`, `GOVERNING_IDENTITY_NUMBERS` and
`MEASUREMENT_POPULATION_SCOPES` are DEFINED in `app.utils.authority_agreement`
but `flip_permitted` reads them as globals of `app.config.authority_by_sport`,
which bound its own references at import time. Patching the defining module
alone leaves the gate reading the originals and the specimen silently does
nothing — a test that then "passes" has measured the real config. So the
bindings are discovered at call time across every loaded `app.*` module and
patched together, and a name that no module binds RAISES rather than no-opping.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any, Iterable, Optional

#: The module globals `flip_permitted` consults, in the order it asks them.
#: Named here rather than inferred so that a gate growing a seventh question is
#: a deliberate edit to this tuple and not a specimen that quietly under-builds.
GATE_GLOBALS: tuple[str, ...] = (
    "MEASUREMENT_POPULATION_SCOPES",
    "SHADOW_STAMPERS",
    "DISCOVERY_SCHEDULED_SPORTS",
    "GOVERNING_IDENTITY_NUMBERS",
    "FLIP_RULED_WITHOUT_STREAK",
    "AUTHORITY_BY_SPORT",
)


def _bindings(name: str) -> list[ModuleType]:
    """Every loaded `app.*` module holding its own reference to `name`.

    Discovered rather than listed: a new consumer that does
    `from app.utils.authority_agreement import SHADOW_STAMPERS` binds a seventh
    copy, and a hand-maintained list would go stale without anything failing.
    `list(...)` because importing during iteration mutates `sys.modules`.
    """
    return [
        module
        for imported, module in list(sys.modules.items())
        if imported.startswith("app.")
        and isinstance(module, ModuleType)
        and name in vars(module)
    ]


def _current(name: str) -> Any:
    """The live value of gate global `name`, to be extended rather than replaced.

    Read from the first binding: every module that imported the name holds the
    same object until this helper replaces them all in one call, so there is no
    "which copy" question to answer here — and `_patch_everywhere` is what keeps
    it that way.
    """
    bindings = _bindings(name)
    if not bindings:
        raise LookupError(f"no loaded app.* module binds {name!r}")
    return vars(bindings[0])[name]


def _patch_everywhere(monkeypatch, name: str, value: Any) -> int:
    """Rebind `name` to `value` in every module that holds it. Returns the count.

    Raises when nothing binds the name. That is the whole point: a rename in
    `authority_agreement` would otherwise leave this helper patching nobody, and
    every specimen test would keep passing against the untouched real config.
    """
    targets = _bindings(name)
    if not targets:
        raise LookupError(
            f"no loaded app.* module binds {name!r}, so a specimen built here "
            "would silently measure the real config instead. If the global was "
            "renamed, update GATE_GLOBALS in tests/authority_specimens.py."
        )
    for module in targets:
        monkeypatch.setattr(module, name, value, raising=True)
    return len(targets)


def register_specimen(
    monkeypatch,
    sport_key: str,
    *,
    stamper: bool = True,
    discovery: bool = True,
    governing: Optional[Iterable[str]] = ("ours_covered_pct",),
    ruled: bool = False,
    population: Any = None,
    authority: str = "espn",
) -> str:
    """Register `sport_key` into the flip gate's config for one test.

    Each keyword is one of `flip_permitted`'s questions, so a specimen reads as
    the state it is in rather than as a list of dictionary edits:

    * `stamper=False`   -> refused at the shadow-stamper branch
    * `discovery=False` -> refused at the discovery branch
    * `governing=None`  -> refused at the D63 branch (what `baseball_mlb` is
                           today, and what #4436 is about to stop being)
    * `ruled=True`      -> in `FLIP_RULED_WITHOUT_STREAK`, so D104 permits it
                           past the streak — but never past the branches above
    * `population=...`  -> a measurement population, the "wrong question" branch

    The default is the interesting one: a fully structural, unruled sport, which
    is the state that reaches the CLOCK and is exactly what the pool is running
    out of (`icehockey_nhl` is the last real one).

    Returns `sport_key`, so a caller can inline it into the call it is testing.
    """
    for name in GATE_GLOBALS:
        for module in _bindings(name):
            container = vars(module)[name]
            if sport_key in container:
                raise ValueError(
                    f"{sport_key!r} is already in {name} — a specimen must not "
                    "shadow a real sport, or a refusal it demonstrates could be "
                    "the real config's rather than the one this test built."
                )

    populations = dict(_current("MEASUREMENT_POPULATION_SCOPES"))
    stampers = dict(_current("SHADOW_STAMPERS"))
    discoveries = set(_current("DISCOVERY_SCHEDULED_SPORTS"))
    governings = dict(_current("GOVERNING_IDENTITY_NUMBERS"))
    ruled_keys = set(_current("FLIP_RULED_WITHOUT_STREAK"))
    authorities = dict(_current("AUTHORITY_BY_SPORT"))

    if population is not None:
        populations[sport_key] = population
    if stamper:
        stampers[sport_key] = f"stamp_{sport_key}_statpal_fixtures"
    if discovery:
        discoveries.add(sport_key)
    if governing is not None:
        governings[sport_key] = tuple(governing)
    if ruled:
        ruled_keys.add(sport_key)
    authorities[sport_key] = authority

    _patch_everywhere(monkeypatch, "MEASUREMENT_POPULATION_SCOPES", populations)
    _patch_everywhere(monkeypatch, "SHADOW_STAMPERS", stampers)
    _patch_everywhere(monkeypatch, "DISCOVERY_SCHEDULED_SPORTS", frozenset(discoveries))
    _patch_everywhere(monkeypatch, "GOVERNING_IDENTITY_NUMBERS", governings)
    _patch_everywhere(monkeypatch, "FLIP_RULED_WITHOUT_STREAK", frozenset(ruled_keys))
    _patch_everywhere(monkeypatch, "AUTHORITY_BY_SPORT", authorities)

    return sport_key
