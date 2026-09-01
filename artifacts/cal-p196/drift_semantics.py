#!/usr/bin/env python3
"""CAL-P196 — the two drift twins measure over DIFFERENT intervals.

Runs from anywhere; bootstraps ``backend/`` onto sys.path itself (P194 pattern).
Read-only: imports and AST only, never edits ``app/``.

Exit 0 = every claim below reproduced.

CLAIMS
------
1. ``retain_planned_units`` re-stamps EVERY kept unit's digest EVERY beat
   (``unit_digests={name: digests[name] for name in kept ...}``), so
   ``roster_drift``'s baseline is the PREVIOUS BEAT, not "when the unit ran"
   as its docstring says.
2. ``served_digests`` is never re-stamped — ``top_up_served_digests`` only ADDS
   — so ``served_drift`` IS cumulative since promotion.
3. The two functions' docstrings describe the SAME semantics and call each
   other "twin".
4. The disclosure's serving branch drops the ``advanced`` term that its own
   module docstring cites as what makes the no-threshold rule satisfiable.
5. The coverage pair is sampled ACROSS a mutation: ``served_drift`` is measured
   at retain_planned_units BEFORE ``top_up_served_digests`` runs, while
   ``staged:served_drift_uncheckable`` is computed from the POST-top-up cursor.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.utils import calibration_staged_disclosure as disc  # noqa: E402
from app.utils import calibration_staged_futures as sf  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")
    if detail:
        print(f"         {detail}")
    if not ok:
        failures.append(label)


def _body(fn) -> str:
    return inspect.getsource(fn)


print("CLAIM 1 — retain_planned_units re-stamps every kept unit every beat")
retain_src = _body(sf.retain_planned_units)
restamp = "unit_digests={name: digests[name] for name in kept if name in digests}"
check(
    "retain_planned_units unconditionally re-stamps unit_digests to the CURRENT plan",
    restamp in retain_src.replace("\n", " ").replace("  ", " ")
    or "for name in kept if name in digests" in retain_src,
    "the re-stamp is not guarded by any 'only if absent' condition",
)
# ...and the re-stamping `replace()` is at the function's TOP LEVEL — not nested
# in any `if`. (The `if dropped:` branch also passes a `unit_digests=` keyword,
# so an undiscriminating walk finds that one instead; anchor on the comprehension.)
fn_ast = ast.parse(inspect.cleandoc(retain_src)).body[0]


def _restamp_kw(node) -> bool:
    """True for the `unit_digests={... for name in kept ...}` keyword only."""
    return (
        isinstance(node, ast.keyword)
        and node.arg == "unit_digests"
        and isinstance(node.value, ast.DictComp)
        and any(
            isinstance(g.iter, ast.Name) and g.iter.id == "kept"
            for g in node.value.generators
        )
    )


nested = any(
    _restamp_kw(sub)
    for n in ast.walk(fn_ast)
    if isinstance(n, (ast.If, ast.For, ast.While, ast.Try))
    for sub in ast.walk(n)
)
top_level = any(_restamp_kw(sub) for stmt in fn_ast.body for sub in ast.walk(stmt))
check(
    "the re-stamp exists and is NOT conditional (no 'only stamp if missing' guard)",
    top_level and not nested,
    "it is the unconditional tail `return replace(...)`, so the stored "
    "baseline is always LAST BEAT's plan",
)

print("\nCLAIM 2 — served_digests is ADD-ONLY, never re-stamped")
topup_src = _body(sf.top_up_served_digests)
check(
    "top_up_served_digests only fills names ABSENT from served_digests",
    "if name not in cursor.served_digests" in topup_src,
)
check(
    "top_up_served_digests documents that it only ever ADDS",
    "only ever ADDS" in topup_src,
)
# the only other writers of served_digests are promotion and the fail-closed drop
sf_src = inspect.getsource(sf)
writers = [
    ln.strip()
    for ln in sf_src.splitlines()
    if "served_digests=" in ln and "def " not in ln
]
# 4 sites: the decoder (rehydrate, not a semantic write), promotion, the
# add-only top-up, and the fail-closed drop. None of them re-stamps.
check(
    "served_digests has 4 write sites: decode, promote, add-only top-up, drop",
    len(writers) == 4,
    " | ".join(writers),
)
check(
    "NONE of them re-stamps an existing digest to the current plan",
    not any(
        "for name in" in w and "served_digests" in w and "not in" not in w
        for w in writers
    ),
    "so served_drift's baseline survives from promotion onward = CUMULATIVE",
)

print("\nCLAIM 3 — the docstrings claim identical semantics")
roster_doc = sf.roster_drift.__doc__ or ""
served_doc = sf.served_drift.__doc__ or ""
check(
    "roster_drift's docstring says the baseline is 'when the unit ran'",
    "when the unit ran" in roster_doc and "since they were banked" in roster_doc,
)
check(
    "served_drift calls roster_drift its 'twin' with the 'Same refusal'",
    "twin" in served_doc and "Same refusal" in served_doc,
)
check(
    "...yet CLAIM 1 + CLAIM 2 make their baselines different intervals",
    True,
    "roster_drift = per-beat delta; served_drift = cumulative since promotion",
)

print("\nCLAIM 4 — the serving branch drops the 'advanced' escape term")
disc_src = _body(disc.build_disclosure)
check(
    "non-serving branch: frozen_over_drift includes the 'advanced' term",
    "frozen_over_drift = (advanced is not True) and not drift_known_zero" in disc_src,
)
check(
    "serving branch: frozen_over_drift is drift-only, no escape",
    "frozen_over_drift = not drift_known_zero" in disc_src,
)
check(
    "the module docstring justifies having NO threshold via that escape",
    "satisfiable by the ruled fix" in (disc.__doc__ or "")
    and "units_this_beat > 0" in (disc.__doc__ or ""),
    "that justification does not hold in the branch that now runs",
)

print("\nCLAIM 5 — the coverage pair is sampled across a mutation")
measure_at = retain_src.index("served_moved = served_drift(")
topup_at = retain_src.index("top_up_served_digests(cursor, digests)")
check(
    "served_drift is measured BEFORE top_up_served_digests inside retain",
    measure_at < topup_at,
    f"offset {measure_at} < {topup_at}",
)
from app.tasks import calibration_main_build as build  # noqa: E402

served_bank_src = _body(build._record_served_bank)
check(
    "served_drift_uncheckable is computed from the payload's served_digests",
    'digests = payload.get("served_digests")' in served_bank_src
    and "uncheckable = sum(1 for name in served if name not in digests)"
    in served_bank_src,
    "i.e. the POST-top-up cursor — the other half of the pair",
)

print("\n" + "=" * 68)
if failures:
    print(f"FAILED: {len(failures)}")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("ALL CLAIMS REPRODUCED")
sys.exit(0)
