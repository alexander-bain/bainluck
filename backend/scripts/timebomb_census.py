#!/usr/bin/env python3
"""Census the ONE dangerous intersection: a hardcoded date against a ROLLING bound.

Why this exists
---------------
On 2026-08-31 at 12:00:00Z a fixture anchored at the literal
``datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)`` crossed
``SENTINEL_MAX_AGE_S`` (30 days). ``backend-tests (2)`` went red, ``deploy``
skipped, and for fifteen hours nothing reached production behind thirteen
certified branches. No commit caused it. Time passed.

Hundreds of test files contain a hardcoded date, and **almost all of them are
harmless**: a date used as DATA — a fixture's game time, an expected string —
never goes red on its own. Fixing 500 files would be a large change that buys
nothing and risks plenty.

The dangerous shape is narrow and mechanically detectable:

    a hardcoded ABSOLUTE instant  +  a bound measured from NOW

``NOW = <literal>`` read by something that asks "is this within 30 days?" is a
bomb whose fuse is exactly as long as the bound. It passes today. It passes
tomorrow. It fails on a date nobody chose.

What this reports
-----------------
Candidates only, in tiers, so a human can size the repair before starting it.
A static scan cannot see a bound that lives in the product code the test calls,
so this DELIBERATELY over-reports and the tiers are ordered by how close the
evidence is to a proof:

``ANCHOR``   a MODULE-LEVEL constant bound to a hardcoded absolute instant.
             This is the burn's exact shape and the only tier where the literal
             is import-time fixture state fed to whatever the file exercises.
``COMPARED`` a hardcoded instant and a real-clock read meeting in one expression
             (a comparison, a subtraction, a ``timedelta`` arithmetic chain).
``ROLLING``  a hardcoded instant in a file that also names a rolling bound
             (``*_MAX_AGE*``, ``*_TTL*``, ``STALE``, ``FRESH``, ``WINDOW``,
             ``RETENTION``, ``CUTOFF``, ``days=``) and reads the real clock.

Static evidence is a CANDIDATE, never a verdict. `scripts/clock_sweep.py` is the
oracle: run a candidate at a far-future instant and see whether it changes its
mind. Only a target that passes now and fails later is a bomb.

Usage
-----
    python3 scripts/timebomb_census.py                 # summary counts
    python3 scripts/timebomb_census.py --tier ANCHOR   # list one tier
    python3 scripts/timebomb_census.py --json          # machine-readable
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

# A clock read. These are the only ways a test learns what "now" is; anything
# else it calls a date is a literal it chose.
CLOCK_ATTRS = frozenset({"now", "utcnow", "today", "time", "time_ns", "monotonic"})

# Names that mean "measured from now". A bound spelled with any of these turns a
# nearby absolute literal from data into a fuse.
ROLLING_NAME = re.compile(
    r"MAX_AGE|_AGE_S|_TTL\b|TTL_|STALE|FRESH|RETENTION|EXPIR|CUTOFF|HORIZON"
    r"|WINDOW|LOOKBACK|RECENT|WITHIN_|_DAYS\b|AGE_LIMIT",
    re.IGNORECASE,
)

# The keyword arguments that make a `timedelta` a rolling span.
SPAN_KW = frozenset({"days", "hours", "minutes", "seconds", "weeks"})

ISO_LITERAL = re.compile(r"^(19|20)\d{2}-[01]\d-[0-3]\d")


def _is_absolute_date_call(node: ast.AST) -> bool:
    """`datetime(2026, 8, 1, ...)` / `date(2026, 8, 1)` with a literal year."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
    if name not in {"datetime", "date"}:
        return False
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and isinstance(first.value, int) and first.value >= 1900


def _is_absolute_date_literal(node: ast.AST) -> bool:
    """A hardcoded instant in ANY of the shapes a fixture actually uses."""
    if _is_absolute_date_call(node):
        return True
    # `datetime.fromisoformat("2026-08-01T12:00:00Z")`, `parse("2026-...")`
    if isinstance(node, ast.Call):
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if ISO_LITERAL.match(arg.value):
                    return True
        # `datetime.fromtimestamp(1756645980)` — an epoch is an instant too.
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name in {"fromtimestamp", "utcfromtimestamp"} and node.args:
            if isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, (int, float)
            ):
                return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(ISO_LITERAL.match(node.value))
    return False


def _reads_clock(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in CLOCK_ATTRS:
                return True
    return False


def _contains_absolute(node: ast.AST) -> bool:
    return any(_is_absolute_date_literal(c) for c in ast.walk(node))


def _module_level_stores(tree: ast.AST):
    """Every name bound at MODULE SCOPE, with the value assigned.

    Scope, not depth (CERT-577): a binding under `if`/`try`/`for` executes at
    module scope exactly like a top-level one. Recurse through executable bodies
    and stop only at `def`/`class`/`lambda`, where the name is a local.
    """
    out = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                continue
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        out.append((target.id, child.value, child.lineno))
            elif isinstance(child, ast.AnnAssign) and child.value is not None:
                if isinstance(child.target, ast.Name):
                    out.append((child.target.id, child.value, child.lineno))
            walk(child)

    walk(tree)
    return out


def scan(path: pathlib.Path) -> dict | None:
    try:
        src = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        # Never silently skip. A file this cannot read is reported, not dropped
        # — an unreadable file counted as clean is how a census lies.
        return {"path": str(path), "tier": "UNREADABLE", "why": [f"{type(exc).__name__}: {exc}"]}
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return {"path": str(path), "tier": "UNPARSABLE", "why": [f"SyntaxError: {exc}"]}

    if not any(_is_absolute_date_literal(n) for n in ast.walk(tree)):
        return None  # no hardcoded instant anywhere: cannot be this class of bomb

    why: list[str] = []
    tier = None

    # --- ANCHOR: a module-level constant bound to a hardcoded instant ---------
    anchors = [
        (name, lineno)
        for name, value, lineno in _module_level_stores(tree)
        if _contains_absolute(value) and not _reads_clock(value)
    ]
    if anchors:
        tier = "ANCHOR"
        why += [f"module-level `{n}` = hardcoded instant (line {ln})" for n, ln in anchors[:4]]

    # --- COMPARED: a literal and a real clock read meeting in one expression --
    compared = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Compare, ast.BinOp)):
            parts = [node.left] + (node.comparators if isinstance(node, ast.Compare) else [node.right])
            has_lit = any(_contains_absolute(p) for p in parts)
            has_clock = any(_reads_clock(p) for p in parts)
            if has_lit and has_clock:
                compared.append(getattr(node, "lineno", 0))
    if compared:
        tier = tier or "COMPARED"
        why.append(f"literal meets a real clock read in one expression (lines {compared[:4]})")

    # --- ROLLING: a literal in a file that names a rolling bound and reads now -
    rolling_names = sorted(
        {
            n.id if isinstance(n, ast.Name) else n.attr
            for n in ast.walk(tree)
            if isinstance(n, (ast.Name, ast.Attribute))
            and ROLLING_NAME.search(n.id if isinstance(n, ast.Name) else n.attr)
        }
    )
    spans = [
        kw.arg
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) == "timedelta"
        for kw in n.keywords
        if kw.arg in SPAN_KW
    ]
    file_reads_clock = _reads_clock(tree)
    if file_reads_clock and (rolling_names or spans):
        if tier is None:
            tier = "ROLLING"
        if rolling_names:
            why.append(f"rolling bound named: {rolling_names[:5]}")
        elif spans:
            why.append(f"timedelta span present: {sorted(set(spans))}")

    if tier is None:
        return None
    return {
        "path": str(path),
        "tier": tier,
        "why": why,
        "reads_clock": file_reads_clock,
    }


TIER_ORDER = ["ANCHOR", "COMPARED", "ROLLING", "UNPARSABLE", "UNREADABLE"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", default="tests", help="directory to scan")
    p.add_argument("--tier", help="list only this tier")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    root = pathlib.Path(a.root)
    if not root.exists():
        print(f"no such path: {root}", file=sys.stderr)
        return 2

    files = sorted(root.rglob("*.py"))
    findings = [f for f in (scan(f) for f in files) if f]

    if a.json:
        print(json.dumps({"scanned": len(files), "findings": findings}, indent=2))
        return 0

    by_tier: dict[str, list[dict]] = {t: [] for t in TIER_ORDER}
    for f in findings:
        by_tier[f["tier"]].append(f)

    if a.tier:
        for f in by_tier.get(a.tier.upper(), []):
            print(f"{f['path']}")
            for w in f["why"]:
                print(f"    {w}")
        return 0

    print(f"scanned {len(files)} .py files under {root}")
    print("  files containing ANY hardcoded absolute instant: see tiers below")
    for t in TIER_ORDER:
        if by_tier[t]:
            print(f"  {t:<11} {len(by_tier[t]):>4}")
    print(f"  {'TOTAL':<11} {len(findings):>4}  candidates (not verdicts)")
    print()
    print("A candidate is not a bomb. Confirm with:")
    print("    python3 scripts/clock_sweep.py <target>")
    print("Only a target that passes NOW and fails at a future instant is a bomb.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
