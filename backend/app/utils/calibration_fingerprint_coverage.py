"""What the main build's input fingerprint actually covers — CAL-P031.

``precompute_calibration._main_input_fingerprint`` is a **wholesale cursor
invalidator**. ``decode_staged_cursor_detailed`` keeps the population version and
the input fingerprint as whole-cursor invalidators (CAL-P016 removed only the
*roster* digest) on the stated grounds that those "change what a unit MEANS
rather than which markets are in it". So the digest is the single guarantee that
a resumed generation's units were all computed against the same definition of
the population. If it fails to move when the population changes, units built
from two different definitions merge into one payload and publish as a coherent
curve — ``LATE_ARRIVAL_NOT_INVALIDATED``, the exact failure the digest exists to
prevent.

The digest is computed as ``inspect.getsource()`` over four functions plus three
values hashed explicitly. Its own docstring records this construction leaking
twice already, and states the rule it keeps re-teaching:

    hashing a function's source covers that function, never what it calls

This module makes that rule *checkable* instead of remembered. ``getsource``
returns a function's own text, so **every module-level name the source merely
references is invisible to the digest** — the text contains the NAME, and the
value it expands to at build time can change underneath it without moving a
single byte.

Two tiers, and the distinction is the whole point:

* **Cross-module** (:data:`CROSS_MODULE`) — the referenced value lives in another
  module. Ruling 009 freezes ``precompute_calibration.py`` and **nothing else**,
  so these are unguarded right now. ``CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL``
  from ``app.utils.resolution_authority`` is interpolated straight into the
  population predicate; editing that list changes which outcomes the curve is
  built from while the digest stays byte-identical.
* **Same-module** — the value lives in ``precompute_calibration.py`` itself, so
  editing it *is* a commit to the frozen file and ruling 009 currently stops it.
  That protection is **incidental and temporary**: the freeze is designed to
  lift, and on the day it does, every one of these becomes the cross-module case
  with no additional change. Recording them now is the difference between a
  known list and a rediscovery.

I/O-free and import-free with respect to the build: this reads
``precompute_calibration.py`` as TEXT and parses it with :mod:`ast`. It never
imports it, so nothing here can execute build code, and reading a frozen file is
not a commit to it (ruling 009).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

#: The build module, as a path. Read as text, never imported.
BUILD_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tasks" / "precompute_calibration.py"
)

#: The four functions whose SOURCE ``_main_input_fingerprint`` hashes.
HASHED_ROOTS: tuple[str, ...] = (
    "compute_calibration_payload",
    "_calibration_population_ctes",
    "_virtual_market_ctes",
    "_main_futures_sql",
)

#: Names ``_main_input_fingerprint`` hashes BY VALUE, so a change DOES move the
#: digest. These are the only genuinely covered inputs. Two of the three were
#: added retroactively after the hole they represented was found in production
#: (``REPRESENTATIVE_TIE_AUTHORITY``, then ``COVERAGE_CENSUS_ENABLED`` in
#: CAL-P024, found "by flipping the switch and noticing the digest did not
#: move") — which is the evidence that this list grows by incident rather than
#: by design, and the reason this module exists.
COVERED_BY_VALUE: frozenset[str] = frozenset(
    {
        "CALIBRATION_POPULATION_VERSION",
        "REPRESENTATIVE_TIE_AUTHORITY",
        "COVERAGE_CENSUS_ENABLED",
    }
)

#: Sentinel for :attr:`DigestInput.module` when the name is defined in the build
#: module itself. ``None`` would be ambiguous with "could not resolve".
SAME_MODULE = "<same-module>"


@dataclass(frozen=True)
class DigestInput:
    """One module-level name the hashed source references but does not cover.

    ``interpolated`` records whether the name is ever placed INTO a string —
    an f-string or a ``+``/``%`` concatenation — anywhere in the closure. That
    is the mechanical signature of a value that shapes emitted SQL, as opposed
    to one recorded verbatim into the payload as documentation (the
    ``*_RULE_TEXT`` family). It is deliberately reported rather than used to
    filter: a rule-text drift across a resumed generation is cosmetic where a
    predicate drift is a wrong curve, but "cosmetic" is a judgement, and this
    module's job is to report the set rather than to shrink it.
    """

    name: str
    module: str
    used_in: tuple[str, ...]
    interpolated: bool

    @property
    def is_cross_module(self) -> bool:
        """True when the value lives outside the frozen build module."""
        return self.module != SAME_MODULE


def _module_level_constants(tree: ast.Module) -> dict[str, int]:
    """UPPER_CASE module-level assignments -> their definition line."""
    found: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: Iterable[ast.expr] = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id.upper() == target.id:
                found.setdefault(target.id, node.lineno)
    return found


def _module_level_imports(tree: ast.Module) -> dict[str, str]:
    """Imported name (honouring ``as``) -> the module it came from.

    Only ``from X import Y`` forms, and only first-party ``app.*`` modules:
    a stdlib name is not a calibration input, and treating it as one would bury
    the five that matter under noise.
    """
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            if not node.module.startswith("app."):
                continue
            for alias in node.names:
                found[alias.asname or alias.name] = node.module
    return found


def _called_local_functions(node: ast.AST, known: frozenset[str]) -> set[str]:
    """Locally-defined functions called anywhere inside ``node``.

    Attribute calls are matched on the attribute name, which over-approximates
    (``x.merge_windows()`` would match a local ``merge_windows``). That is the
    correct direction to be wrong in: an over-wide closure reports a name that
    is in fact uncovered anyway, while a too-narrow one misses a real hole.
    """
    out: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute) else None
        )
        if name in known:
            out.add(name)
    return out


def closure_of(tree: ast.Module, roots: Iterable[str] = HASHED_ROOTS) -> set[str]:
    """The roots plus every locally-defined function transitively called.

    This is the set of code whose behaviour the emitted SQL depends on, against
    which the digest covers only ``roots``.
    """
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    known = frozenset(functions)
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        node = functions.get(name)
        if node is None:
            continue
        stack.extend(callee for callee in _called_local_functions(node, known) if callee not in seen)
    return seen


def _interpolated_names(node: ast.AST) -> set[str]:
    """Names placed into a string: f-string fields, or ``+``/``%`` with a str."""
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.FormattedValue):
            for inner in ast.walk(child.value):
                if isinstance(inner, ast.Name):
                    out.add(inner.id)
        elif isinstance(child, ast.BinOp) and isinstance(child.op, (ast.Add, ast.Mod)):
            operands = (child.left, child.right)
            touches_str = any(
                isinstance(side, ast.Constant) and isinstance(side.value, str)
                for side in operands
            )
            if not touches_str:
                continue
            for side in operands:
                for inner in ast.walk(side):
                    if isinstance(inner, ast.Name):
                        out.add(inner.id)
    return out


def uncovered_digest_inputs(source: str) -> dict[str, DigestInput]:
    """Module-level names the hashed closure reads that the digest does NOT cover.

    A name qualifies when it is a module-level constant or a first-party import,
    is referenced (loaded) somewhere in :func:`closure_of`, and is not in
    :data:`COVERED_BY_VALUE`.
    """
    tree = ast.parse(source)
    constants = _module_level_constants(tree)
    imports = _module_level_imports(tree)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    used_in: dict[str, set[str]] = {}
    interpolated: set[str] = set()
    for func_name in closure_of(tree):
        node = functions.get(func_name)
        if node is None:
            continue
        interpolated |= _interpolated_names(node)
        for child in ast.walk(node):
            if not (isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)):
                continue
            if child.id in COVERED_BY_VALUE:
                continue
            if child.id in imports or child.id in constants:
                used_in.setdefault(child.id, set()).add(func_name)

    return {
        name: DigestInput(
            name=name,
            module=imports.get(name, SAME_MODULE),
            used_in=tuple(sorted(sites)),
            interpolated=name in interpolated,
        )
        for name, sites in used_in.items()
    }


@lru_cache(maxsize=1)
def _build_module_source() -> str:
    return BUILD_MODULE_PATH.read_text(encoding="utf-8")


def uncovered_from_build_module() -> dict[str, DigestInput]:
    """:func:`uncovered_digest_inputs` against the real build module."""
    return uncovered_digest_inputs(_build_module_source())


def cross_module_uncovered(
    inputs: dict[str, DigestInput] | None = None,
) -> dict[str, DigestInput]:
    """The tier that ruling 009's freeze does NOT protect."""
    resolved = uncovered_from_build_module() if inputs is None else inputs
    return {name: ref for name, ref in resolved.items() if ref.is_cross_module}


#: ------------------------------------------------------------------------
#: THE RATCHET — known-uncovered values, pinned with a reason.
#:
#: Same shape and same rationale as ``frontend/typecheck-baseline.json``
#: (gotcha #10): pre-existing holes are recorded and do not fail, one MORE
#: fails, and — per that gotcha's own hard-won lesson — one FEWER fails too.
#: A baseline that only ratchets one way silently accumulates headroom, so
#: covering a value must force this list to shrink in the same commit.
#: ------------------------------------------------------------------------

#: Cross-module. UNGUARDED TODAY: ruling 009 freezes the build module and these
#: do not live in it. Every one is a live path to a mixed-generation publish.
CROSS_MODULE: dict[str, str] = {
    "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL": (
        "app.utils.resolution_authority — interpolated into the population "
        "predicate itself. Editing the eligible-source list changes WHICH "
        "outcomes the curve is built from, with no digest movement. Proven "
        "in test_calibration_fingerprint_coverage.py."
    ),
    "CALIBRATION_TRUTH_INELIGIBLE_SOURCES_SQL": (
        "app.utils.resolution_authority — truth-evidence split in the payload."
    ),
    "PRICE_DERIVED_SOURCES_SQL": (
        "app.utils.resolution_authority — truth-evidence split in the payload."
    ),
    "_COVERAGE_RUNG_KEYS": (
        "app.utils.calibration_coverage_bridge (RUNG_KEYS) — names the census "
        "columns the futures statement SELECTs. Currently inert because "
        "COVERAGE_CENSUS_ENABLED is False, and that flag IS covered by value; "
        "it becomes live the moment the census is switched back on."
    ),
    "_build_coverage_census": (
        "app.utils.calibration_coverage_bridge (build_coverage_census) — a "
        "FUNCTION, so its whole body is outside the digest. Same inertness "
        "caveat as _COVERAGE_RUNG_KEYS."
    ),
}

#: Same-module. Protected ONLY by ruling 009's freeze, which is designed to
#: lift. Not listed name-by-name with prose: the set is large and uniform, and
#: the test pins it by exact membership so any change to it is visible in the
#: diff. The tier's reason is one fact, recorded once.
SAME_MODULE_REASON = (
    "Defined in precompute_calibration.py, so editing it is a commit to the "
    "frozen file and ruling 009 currently prevents it. That protection is "
    "incidental and expires with the freeze."
)

#: Exact expected membership of the same-module tier. Pinned so the ratchet
#: binds in both directions.
SAME_MODULE_KNOWN: frozenset[str] = frozenset(
    {
        "CALIBRATION_CORRECTIONS",
        "COVERAGE_CENSUS_DISABLED_REASON",
        "DRAW_AUTHORITY_OUTCOME_NAMES",
        "DRAW_AUTHORITY_RULE_TEXT",
        "DRAW_CAPABLE_CATEGORIES",
        "ESPORTS_MULTI_BUNDLE_CATEGORY",
        "ESPORTS_MULTI_BUNDLE_RULE_TEXT",
        "EXCLUSIVITY_EVIDENCE_RULE_TEXT",
        "EXCLUSIVITY_PROVED_RELATIONS",
        "FIELD_COMPLETENESS_RULE_TEXT",
        "GOLF_PLACEHOLDER_HIGH_BAND",
        "GOLF_PLACEHOLDER_RULE_TEXT",
        "KALSHI_HOCKEY_HONEST_BAND_MAX",
        "KALSHI_LIQUIDITY_EXISTS",
        "KALSHI_LIQUIDITY_RULE_TEXT",
        "KALSHI_PROP_THRESHOLD_DEGENERATE_BAND",
        "KALSHI_PROP_THRESHOLD_NAME_RE",
        "KALSHI_PROP_THRESHOLD_RULE_TEXT",
        "MALFORMED_BINARY_RULE_TEXT",
        "MEX_NORMALIZE_RULE_TEXT",
        "MEX_NORMALIZE_THRESHOLD",
        "NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT",
        "NO_WINNER_RULE_TEXT",
        "ORPHAN_PARTITION_RULE_TEXT",
        "POLY_NEVER_TRADED",
        "POLY_PLACEHOLDER_EXCLUDE",
        "POLY_PLACEHOLDER_RULE_TEXT",
        "SOCCER_2WAY_RULE_TEXT",
        "SOURCE_LIQUIDITY_EXCLUSIONS",
        "VM_ROSTER_IS_GROUPED_PARAM",
        "VM_ROSTER_MARKET_IDS_PARAM",
        "VM_ROSTER_MARKET_INFO_EXTRA",
        "VM_ROSTER_VM_IDS_PARAM",
        "VOID_FILTER_RULE_TEXT",
        "WEATHER_WIDE_SPREAD_EXCLUDE",
        "WEATHER_WIDE_SPREAD_RULE_TEXT",
        "_COVERAGE_RUNG_PREDICATES",
        "_DEFAULT_MIN_CATEGORY_OUTCOMES",
    }
)


#: ------------------------------------------------------------------------
#: THE FIX, for whoever lifts ruling 009's freeze. NOT applied here — see below.
#: ------------------------------------------------------------------------

FIX_SEQUENCING_NOTE = """\
Covering these means adding them to `_main_input_fingerprint`, in the idiom that
function already uses for `COVERAGE_CENSUS_ENABLED` — hashed by NAME and by
VALUE, so the input is greppable rather than an incidental substring.

TWO CONSTRAINTS, EACH INDEPENDENTLY SUFFICIENT TO BLOCK IT TODAY:

1. `precompute_calibration.py` is FROZEN (ruling 009). The lift condition is a
   fresh post-CAL-P024 publish PLUS ~13 clean beats, recorded. Not met.

2. APPLYING THE FIX WIPES EVERY BANKED UNIT. Moving the digest is, by design, a
   wholesale cursor invalidation. Doing it mid-convergence destroys exactly the
   progress the fix exists to protect and restarts a multi-hour walk. As of
   2026-08-10 the build sits at 36/128 banked after 8.8 days dark.

   => Apply IMMEDIATELY AFTER a successful publish, never during a convergence.

The instinct "we found a correctness bug, fix it now" is wrong here, and it is
wrong in a way that costs the SLO. That is why this note ships beside the guard
instead of the patch.
"""
