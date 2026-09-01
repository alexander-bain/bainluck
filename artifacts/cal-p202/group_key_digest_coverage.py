#!/usr/bin/env python3
"""CAL-P202 — Q11 turned on the ONE population no sweep in this run has ever had:
the columns of the staged drift digest.

THE QUESTION (conveyor ITEM 6, standing since CAL-P191):

    "`category` IS a GROUP_KEY_COLUMNS member ... All three guards are blind to
     it."

That marker's noun is **a group-key column**. Its recorded population is **one**
column. Q11 asks what the instrument that set the marker actually enumerated,
and whether that matches the noun. Nobody has ever enumerated
``GROUP_KEY_COLUMNS`` against the digest's observable field set.

WHAT THIS MEASURES
    population  = ``GROUP_KEY_COLUMNS``, imported from the module (never copied)
    detector    = the set of ROW FIELDS the roster digest observes, extracted by
                  AST from the two places that build a roster member tuple:
                  ``generation_fingerprint`` (Stage A, global) and the plan-time
                  member builder inside ``plan_units`` (Stage B, per unit).
    verdict     = per group key: OBSERVED by the digest, or BLIND to it.

WHAT IT DOES NOT MEASURE
    Whether a BLIND column is *live* — that needs a writer that can land on a row
    already in the roster. Section 2 is a mechanical writer census over the base
    columns each blind group key derives from. It reports call sites, NOT
    defects; grading each writer is a hand read and lives in REPORT.md.

CONTROL ARMS — four, across two axes (the pattern CAL-P199..P201 earned).
    Axis A, detector sensitivity:
      A1 POSITIVE  ``source`` is in the digest tuple => must report OBSERVED.
                   A detector that calls everything BLIND fails here.
      A2 KNOWN HIT ``category`` is not => must report BLIND. This reproduces the
                   recorded hazard, which is the only reason a zero would have
                   been believable.
    Axis B, population/extractor honesty:
      B1 DISTINCTNESS the extracted digest-field set must contain ``is_grouped``,
                   which IS in the digest and is NOT a group key. Proves the
                   extractor read the digest and is not echoing the population.
      B2 PROVENANCE the population must be the module's own tuple, non-empty.
                   Proves the population cannot go stale against the source.

Runs from any cwd. Exit 0 = every control arm held.
"""

from __future__ import annotations

import ast
import inspect
import re
import subprocess
import sys
from pathlib import Path

# --- bootstrap: find the repo root from THIS file, not from cwd ---------------
_here = Path(__file__).resolve()
_root = next(p for p in _here.parents if (p / "backend" / "app").is_dir())
sys.path.insert(0, str(_root / "backend"))

from app.utils import calibration_staged_futures as sf  # noqa: E402

BACKEND = _root / "backend"


# =============================================================================
# Section 1 — the coverage measurement
# =============================================================================


def digest_observed_fields() -> tuple[set[str], dict[str, list[str]]]:
    """Row fields the roster digest can see, by AST over its two builders.

    Both builders read the row through ``_get(row, <name>)``. ``<name>`` is
    either a string literal or the module constant ``UNIT_KEY_VM_ID``; resolve
    the constant rather than special-casing it, so a rename cannot silently
    shrink the observed set.
    """
    per_site: dict[str, list[str]] = {}
    observed: set[str] = set()

    for func in (sf.generation_fingerprint, sf.plan_units):
        src = inspect.getsource(func)
        tree = ast.parse(_dedent(src))
        found: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Name) and fn.id == "_get"):
                continue
            if len(node.args) < 2:
                continue
            key = node.args[1]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.append(key.value)
            elif isinstance(key, ast.Name):
                # a module constant naming the field, e.g. UNIT_KEY_VM_ID
                resolved = getattr(sf, key.id, None)
                if isinstance(resolved, str):
                    found.append(resolved)
                else:
                    raise SystemExit(
                        f"UNRESOLVED digest field reference {key.id!r} in "
                        f"{func.__name__} — the extractor cannot see this field, "
                        "so it must not report a coverage number. "
                        "(gotcha: a source-scan guard must RAISE on what it "
                        "cannot parse.)"
                    )
            else:
                raise SystemExit(
                    f"UNPARSEABLE _get key in {func.__name__}: "
                    f"{ast.dump(key)[:120]} — refusing to report coverage."
                )
        per_site[func.__name__] = sorted(set(found))
        observed |= set(found)

    return observed, per_site


def _dedent(src: str) -> str:
    lines = src.splitlines()
    pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(l[pad:] for l in lines)


def population() -> tuple[str, ...]:
    """The group key, read off the module. Never a literal copy."""
    cols = sf.GROUP_KEY_COLUMNS
    if not isinstance(cols, tuple) or not cols:
        raise SystemExit("GROUP_KEY_COLUMNS is not a non-empty tuple")
    return cols


# =============================================================================
# Section 2 — derivation chains and a mechanical writer census
# =============================================================================

#: Each blind group key -> the base table columns its SQL expression reads.
#: Hand-read off precompute_calibration.py; the line refs are the evidence and
#: are asserted to still contain the expression (see check_derivations).
DERIVATIONS: dict[str, dict[str, object]] = {
    "bucket_idx": {
        "expr": "LEAST(FLOOR(adj_opening_probability * 10)::int, 9)",
        "anchor": ("app/tasks/precompute_calibration.py", "AS bucket_idx"),
        "base": ["calibration_probability", "opening_probability"],
        "via": "adj_opening_probability <- raw_cp = "
               "COALESCE(fo.calibration_probability, fo.opening_probability)",
    },
    "category": {
        "expr": "COALESCE(fm.llm_sport_category, 'uncategorized')",
        "anchor": ("app/tasks/precompute_calibration.py", "AS category"),
        "base": ["llm_sport_category"],
        "via": "direct",
    },
    "price_moved": {
        "expr": "fo.calibration_probability IS DISTINCT FROM fo.opening_probability",
        "anchor": ("app/tasks/precompute_calibration.py", "AS price_moved"),
        "base": ["calibration_probability", "opening_probability"],
        "via": "direct",
    },
    "is_nonexclusive_bundle": {
        "expr": "(nbm.market_id IS NOT NULL)",
        "anchor": ("app/tasks/precompute_calibration.py", "AS is_nonexclusive_bundle"),
        "base": ["is_winner"],
        "via": "nonexclusive_bundle_markets <- market_result_shape.win_count "
               "<- fo.is_winner",
    },
}


def check_derivations() -> None:
    """Every recorded anchor must still be present. A moved expression means the
    derivation table is stale and no number below it is trustworthy."""
    for key, info in DERIVATIONS.items():
        rel, needle = info["anchor"]  # type: ignore[misc]
        text = (BACKEND / rel).read_text(encoding="utf-8")
        if needle not in text:
            raise SystemExit(
                f"STALE DERIVATION: {key} anchor {needle!r} no longer in {rel}"
            )


def writer_census(base_columns: list[str]) -> dict[str, list[str]]:
    """Every ``SET <col> =`` site under app/, with its file:line."""
    out: dict[str, list[str]] = {}
    for col in base_columns:
        try:
            res = subprocess.run(
                ["grep", "-rn", "--include=*.py", f"SET {col} =", str(BACKEND / "app")],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise SystemExit(f"writer census for {col} timed out")
        hits = [
            l.split(str(BACKEND) + "/", 1)[-1].split(":")[0]
            + ":"
            + l.split(":")[1]
            for l in res.stdout.splitlines()
            if l.strip()
        ]
        out[col] = hits
    return out


# =============================================================================
# Controls
# =============================================================================


def run_controls(observed: set[str], verdicts: dict[str, str], cols: tuple[str, ...]) -> list[str]:
    failures: list[str] = []

    # A1 POSITIVE — a field genuinely in the digest must read OBSERVED.
    if verdicts.get("source") != "OBSERVED":
        failures.append(
            "A1 POSITIVE FAILED: 'source' is in the digest member tuple but the "
            f"detector reported {verdicts.get('source')!r}. The detector under-reports."
        )

    # A2 KNOWN HIT — reproduce the hazard the conveyor already recorded.
    if verdicts.get("category") != "BLIND":
        failures.append(
            "A2 KNOWN-HIT FAILED: the recorded group-key hazard ('category' is "
            f"absent from the digest) did not reproduce; got {verdicts.get('category')!r}. "
            "A sweep that cannot re-find a known hit may not report a number."
        )

    # B1 DISTINCTNESS — the extractor read the digest, not the population.
    if "is_grouped" not in observed:
        failures.append(
            "B1 DISTINCTNESS FAILED: 'is_grouped' is in the digest tuple and is "
            "NOT a group key; its absence from the extracted set means the "
            "extractor is not reading the digest."
        )
    if "is_grouped" in cols:
        failures.append(
            "B1 DISTINCTNESS FAILED: 'is_grouped' turned up IN GROUP_KEY_COLUMNS; "
            "the two sets are no longer distinct and this control is vacuous."
        )

    # B2 PROVENANCE — population is the module's, and the source literal agrees.
    src = (BACKEND / "app/utils/calibration_staged_futures.py").read_text(encoding="utf-8")
    block = re.search(
        r"GROUP_KEY_COLUMNS:[^=]*=\s*\((.*?)\)", src, re.S
    )
    if not block:
        failures.append("B2 PROVENANCE FAILED: could not locate the literal in source.")
    else:
        literal = tuple(re.findall(r'"([^"]+)"', block.group(1)))
        if literal != cols:
            failures.append(
                f"B2 PROVENANCE FAILED: source literal {literal} != imported {cols}."
            )

    return failures


# =============================================================================


def main() -> int:
    cols = population()
    observed, per_site = digest_observed_fields()
    verdicts = {c: ("OBSERVED" if c in observed else "BLIND") for c in cols}

    print("CAL-P202 — Q11 on the staged drift digest's columns")
    print("=" * 74)
    print(f"repo root : {_root}")
    print(f"cwd       : {Path.cwd()}")
    print()

    print("DIGEST — row fields observed, by builder")
    for name, fields in per_site.items():
        print(f"  {name:26s} {fields}")
    print(f"  {'UNION':26s} {sorted(observed)}")
    print()

    print("POPULATION — GROUP_KEY_COLUMNS (imported from the module)")
    for c in cols:
        print(f"  {verdicts[c]:9s}  {c}")
    blind = [c for c in cols if verdicts[c] == "BLIND"]
    print()
    print(f"  observed : {len(cols) - len(blind)}/{len(cols)}")
    print(f"  BLIND    : {len(blind)}/{len(cols)}  -> {blind}")
    print()

    recorded = {"category"}
    print("COVERAGE OF THE RECORDED MARKER")
    print(f"  the conveyor's group-key hazard names : {sorted(recorded)}")
    print(f"  group keys actually blind to the digest: {blind}")
    pct = 100.0 * len(recorded & set(blind)) / len(blind) if blind else float("nan")
    print(f"  => the recorded hazard covers {len(recorded & set(blind))}/{len(blind)}"
          f" = {pct:.1f}% of its own named population")
    print(f"  UNRECORDED : {[c for c in blind if c not in recorded]}")
    print()

    check_derivations()
    print("DERIVATIONS + WRITER CENSUS (call sites, NOT defects)")
    for c in blind:
        info = DERIVATIONS[c]
        print(f"  {c}")
        print(f"    expr : {info['expr']}")
        print(f"    via  : {info['via']}")
        census = writer_census(list(info["base"]))  # type: ignore[arg-type]
        for col, hits in census.items():
            print(f"    SET {col} = ... : {len(hits)} site(s)")
            for h in hits[:6]:
                print(f"        {h}")
            if len(hits) > 6:
                print(f"        ... and {len(hits) - 6} more")
    print()

    failures = run_controls(observed, verdicts, cols)
    print("CONTROL ARMS")
    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        print()
        print("RESULT: controls failed — the numbers above are NOT reportable.")
        return 1
    print("  PASS  A1 positive      'source' reads OBSERVED")
    print("  PASS  A2 known hit     'category' reads BLIND (hazard reproduced)")
    print("  PASS  B1 distinctness  'is_grouped' in digest, not in population")
    print("  PASS  B2 provenance    population == module literal")
    print()
    print("RESULT: all four control arms held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
