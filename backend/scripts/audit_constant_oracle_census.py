#!/usr/bin/env python3
"""Census of constant-oracle (tautological) assertions in the backend test suite.

THE DEFECT
----------
A test that asserts a production value against **the same imported constant the
production code reads** cannot detect a change to that value. Mutating the
constant moves the implementation and the oracle together, so the test stays
green while a threshold, TTL, wire token, state name or sample-size gate changes
underneath it.

    # production
    HUB_PRIMARY_TTL = 180
    def write(...): ... primary_ttl=HUB_PRIMARY_TTL ...

    # test -- passes for ANY value of HUB_PRIMARY_TTL, pins nothing
    assert ttl_written == hub_route.HUB_PRIMARY_TTL

LAT-P026 is the recorded escape: that exact shape let the mutation 180 -> 60
survive the suite until the expectation became a literal. See
``tests/test_hub_cache_swr.py:236-240`` for the landed correction.

NOT EVERY HIT IS A DEFECT
-------------------------
An assertion that tests **branch selection** -- "the fallback path returns the
default", "this row classifies as foreign" -- is legitimately written against
the constant, and is not claiming to pin a value. It is a defect only when the
numeric/token value is *itself the contract* and nothing else pins it.

The discriminator is not readable from the assertion. It is:

    Does ANY test go red when the production constant is mutated?

which is why this scan is a **triage input, not a verdict**. Grade a candidate
by mutation before changing it.

WHAT THIS SCANNER COUNTS
------------------------
Conservative, reproducing C272/B3's method: an ``assert`` where a name imported
from a production module is used as the expected value, AND a callable
referenced in the same assertion resolves to that same production module, AND
that callable's own source references the same constant.

Its number is a FLOOR, not a total. Deliberately excluded:
  * helper-mediated assertions (the production call happens inside a test
    helper, so the assert statement itself has no resolvable production call)
  * frontend/TypeScript constant oracles
  * anything reached only through a method on an object returned by a helper

Usage:
    python3 scripts/audit_constant_oracle_census.py            # summary
    python3 scripts/audit_constant_oracle_census.py --markdown # artifact table
    python3 scripts/audit_constant_oracle_census.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS = BACKEND / "tests"
APP = BACKEND / "app"

# Alex's tranche-1 scope (queue 331): calibration / settlement / admin / 300B.
TRUTH_PATH_TOKENS = ("calibration", "settlement", "admin", "300b")
# Explicitly ruled OUT of tranche 1 even though the name may brush the scope.
TRUTH_PATH_EXCLUDED = {
    "tests/test_market_shape.py",          # ambiguous -- fix-on-touch
    "tests/test_sentinel_filing.py",       # ambiguous -- fix-on-touch
}


def _is_const_name(name: str) -> bool:
    """Module-level CONSTANT_CASE, with or without a leading underscore."""
    core = name.lstrip("_")
    return bool(core) and core.upper() == core and any(c.isalpha() for c in core)


def _module_path(dotted: str) -> Path | None:
    if not dotted.startswith("app"):
        return None
    p = BACKEND / (dotted.replace(".", "/") + ".py")
    return p if p.exists() else None


class _ProdModule:
    """Constants and callable sources for one production module."""

    _cache: dict[str, "_ProdModule | None"] = {}

    def __init__(self, dotted: str, path: Path):
        self.dotted = dotted
        self.path = path
        self.constants: dict[str, str] = {}
        self.callable_src: dict[str, str] = {}
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and _is_const_name(t.id):
                        self.constants[t.id] = ast.unparse(node.value)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and _is_const_name(node.target.id) and node.value:
                    self.constants[node.target.id] = ast.unparse(node.value)
        # every function/method anywhere in the module, by bare name
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.callable_src.setdefault(node.name, ast.get_source_segment(source, node) or "")

    @classmethod
    def get(cls, dotted: str) -> "_ProdModule | None":
        if dotted not in cls._cache:
            path = _module_path(dotted)
            cls._cache[dotted] = cls(dotted, path) if path else None
        return cls._cache[dotted]


def _imports(tree: ast.AST) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """local name -> (module, original name); plus modules imported wholesale."""
    named: dict[str, tuple[str, str]] = {}
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            for a in node.names:
                named[a.asname or a.name] = (node.module, a.name)
                sub = f"{node.module}.{a.name}"
                if _module_path(sub):
                    modules.append(sub)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("app"):
                    named[a.asname or a.name.split(".")[0]] = (a.name, "")
                    modules.append(a.name)
    return named, modules


def _callable_names(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def scan_file(path: Path) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    named, wholesale = _imports(tree)
    # candidate production modules this test file can reach
    reachable: list[str] = list(dict.fromkeys(
        [m for m, _ in named.values() if _module_path(m)] + wholesale
    ))
    if not reachable:
        return []

    # local constant name -> (module, prod name)
    const_locals: dict[str, tuple[str, str]] = {
        local: (mod, orig)
        for local, (mod, orig) in named.items()
        if orig and _is_const_name(orig)
    }

    # Local variables assigned from a production call, per enclosing function.
    # This catches the extremely common two-step shape that a pure
    # assert-statement scan misses entirely:
    #     sql = kalshi_prop_threshold_exclude_sql(...)   # production call
    #     assert f">= {KALSHI_HOCKEY_HONEST_BAND_MAX}" in sql
    # The oracle is just as circular as the one-liner; only the plumbing differs.
    var_origin: dict[int, dict[str, set[str]]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        local: dict[str, set[str]] = defaultdict(set)
        for stmt in ast.walk(fn):
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                value = stmt.value
                if value is None:
                    continue
                calls = _callable_names(value)
                if not calls:
                    continue
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for t in targets:
                    names = [t.id] if isinstance(t, ast.Name) else [
                        e.id for e in getattr(t, "elts", []) if isinstance(e, ast.Name)
                    ]
                    for nm in names:
                        local[nm] |= calls
        var_origin[id(fn)] = local

    def _calls_in_scope(assert_node: ast.Assert) -> set[str]:
        """Callables reachable from this assert: called inline, or via a local
        variable that was assigned from a call in the same function."""
        calls = _callable_names(assert_node)
        used_vars = {n.id for n in ast.walk(assert_node) if isinstance(n, ast.Name)}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                continue
            if assert_node not in set(ast.walk(fn)):
                continue
            for var, origin in var_origin.get(id(fn), {}).items():
                if var in used_vars:
                    calls |= origin
        return calls

    rows: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        used_calls = _calls_in_scope(node)
        if not used_calls:
            continue

        # constants referenced in this assert, both bare and module-qualified
        found: set[tuple[str, str]] = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in const_locals:
                found.add(const_locals[n.id])
            elif isinstance(n, ast.Attribute) and _is_const_name(n.attr):
                base = n.value
                if isinstance(base, ast.Name) and base.id in named:
                    mod = named[base.id][0]
                    if _ProdModule.get(mod) and n.attr in _ProdModule.get(mod).constants:
                        found.add((mod, n.attr))
        if not found:
            continue

        for mod, const in sorted(found):
            pm = _ProdModule.get(mod)
            if not pm or const not in pm.constants:
                continue
            # a callable in this assert, from this module, that reads the constant
            for cname in sorted(used_calls):
                src = pm.callable_src.get(cname)
                if src and const in src:
                    rows.append({
                        "file": str(path.relative_to(BACKEND)),
                        "line": node.lineno,
                        "constant": const,
                        "origin": f"{mod}:{const}",
                        "value": pm.constants[const],
                        "via": cname,
                    })
                    break
    # de-dupe (file, line, constant)
    seen, uniq = set(), []
    for r in rows:
        key = (r["file"], r["line"], r["constant"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def in_tranche1(relpath: str) -> bool:
    if relpath in TRUTH_PATH_EXCLUDED:
        return False
    name = Path(relpath).name.lower()
    return any(tok in name for tok in TRUTH_PATH_TOKENS)


def collect() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        rows.extend(scan_file(path))
    for r in rows:
        r["tranche1"] = in_tranche1(r["file"])
    return rows


ARTIFACT_HEADER = '''# Constant-oracle (tautological) assertion census

> **Generated. Do not hand-edit.**
> `cd backend && python3 scripts/audit_constant_oracle_census.py --artifact > docs/constant-oracle-census.md`
>
> Tracking issue: **#1766**. Authorizing queue for tranche 1: **331**.

## THE RULE — fix-on-touch

**If you touch a line listed in this census, fix it in the same change.**

That is Alex's standing disposition for every row outside tranche 1. There is no
scheduled sweep coming for them; a rule recorded only in a queue report expires with
the session, so it is recorded here, where the person editing the line will find it.
`docs/gotchas-reference.md` carries the one-line pointer.

"Fix it" means: **make the assertion fail when the production constant changes.**
Either assert an independent literal in place, or pin the constant's value in a
companion assertion. Then prove it by mutating the constant and watching the test go red.

**Do NOT delete or weaken an assertion to make it non-tautological.** A branch-selection
assertion that happens to reference a constant is fine and stays — see "Not every hit is
a defect" below.

## The defect

A test that asserts a production value against **the same imported constant the
production code reads** cannot detect a change to that value. Mutating the constant moves
the implementation and the oracle together, so the test stays green while a threshold,
TTL, wire token, state name or sample-size gate changes underneath it.

```python
# production
HUB_PRIMARY_TTL = 180

# test — passes for ANY value of HUB_PRIMARY_TTL, pins nothing
assert ttl_written == hub_route.HUB_PRIMARY_TTL
```

**LAT-P026 is the recorded escape.** That exact shape let the mutation `180 → 60` survive
the suite until the expectation became a literal. The landed correction, with its
rationale, is at `backend/tests/test_hub_cache_swr.py:236-240`.

## Not every hit is a defect

An assertion that tests **branch selection** — "the fallback path returns the default",
"this row classifies as foreign" — is legitimately written against the constant and is
not claiming to pin a value. It is a defect only when the value is *itself the contract*
**and nothing else pins it**.

The discriminator is not readable from the assertion. It is:

> Does **any** test go red when the production constant is mutated?

So this census is a **triage input, not a verdict**. Two constants here already had
companion literal pins before tranche 1 began, and their rows are not defects:
`_DEFAULT_MIN_CATEGORY_OUTCOMES` (pinned at `test_calibration_min_sample_gate.py:69`) and
`MEX_NORMALIZE_THRESHOLD` (pinned at `test_calibration_mex_normalization.py:61`).

## This count is a FLOOR, not a total

Any completeness claim against it is false by construction. Deliberately not counted:

* **helper-mediated assertions** where the production call happens inside a test helper —
  including `test_hub_cache_swr.py:163,198,216,232,253,287`
* **frontend / TypeScript** constant oracles — never scanned
* method calls on objects returned by a helper, where the callable cannot be resolved
  back to a production module

## Provenance

Reproduces C272/B3 (CODEX run 2026-08-11, `.claude/handoff/CODEX-REPORT.md:15516-15522`),
which reported **200 assertions across 42 files** but published *concentrations* — only
~133 rows across 12 of the 42 files were ever enumerated with line numbers. That prose is
not a work list, so this scanner re-derives the census from the tree instead of
transcribing it.

Agreement with B3 on the files B3 did enumerate is exact for
`test_db_session_identity_300b.py` (15), `test_highlights.py` (13),
`test_personalization.py` (45), `test_market_shape.py` (9),
`test_line_movement.py` (4) and `test_calibration_min_sample_gate.py` (5).
This scan also reaches the two-step `x = prod_call(...)` / `assert CONST in x` shape that
B3's direct-call requirement excluded, which is why its total is higher.

'''


TRANCHE1_DISPOSITION = '''
## Tranche 1 disposition (queue 331, 2026-08-11)

Every constant reachable from the tranche-1 files was graded **by mutation**: change the
production constant, run every test that could plausibly detect it, record red or green.
36 distinct constants were graded.

### Mutation-blind → fixed (20)

Each was changed with the **entire** relevant suite staying green. Each now has an
independent literal pin, and each was re-mutated afterwards to confirm it goes red.

| module | constants | pin |
|---|---|---|
| `app/utils/db_session_identity.py` | `APPLICATION_NAME_MAX`, `TAG_SCHEMA`, `UNKNOWN_BUILD`, `CURRENT`, `SUPERSEDED`, `KIND_CURRENT_BEAT`, `KIND_SUPERSEDED_RUN`, `KIND_PREDEPLOY_RUN`, `KIND_UNCLASSIFIED`, `KIND_FOREIGN` | `tests/test_db_session_identity_300b.py::TestWireValuesArePinnedIndependently` |
| `app/utils/calibration_phase_ledger.py` | `BUDGET_SAFETY`, `TERMINAL_FAILED`, `TERMINAL_HARD_LOSS`, `TERMINAL_OVERLAP_REFUSED`, `GREEN`, `UNKNOWN`, `RED`, `FRESH`, `REFUSE`, `RESUME` | `tests/test_calibration_phase_ledger.py::TestLedgerVocabularyIsPinnedIndependently` |

The worst single case was `APPLICATION_NAME_MAX = 63`. It is not a value the project
chooses — Postgres truncates `application_name` at `NAMEDATALEN-1` = 63 bytes, silently,
and the tail it drops is the owner handle. Three assertions bounded the tag against the
constant (`len(tag) <= APPLICATION_NAME_MAX`), so widening the constant to 200 kept all
three green while every emitted tag would have been truncated on the way into
`pg_stat_activity` — defeating the identity contract the 300B work exists to provide.

### Already protected → left alone (16)

Graded, found detectable, **not touched**. Their census rows are branch-selection
assertions, which is what those assertions are for.

`PREDEPLOY` (pinned as a literal in `calibration_orphan_containment_contract.json`),
`PHASE_FUTURES`, `TERMINAL_COMPLETE`, `TERMINAL_PARTIAL`, `TERMINAL_CANCELLED`,
`STATUS_COMPLETE`, `STATUS_INCOMPLETE`, `STATUS_UNAVAILABLE`, `SENTINEL_COVERAGE_THRESHOLD`,
`KALSHI_HOCKEY_HONEST_BAND_MAX`, `KALSHI_PROP_THRESHOLD_DEGENERATE_BAND` (both caught
behaviourally by `test_hockey_goal_family_honest_band_recovered`), `MEX_NORMALIZE_THRESHOLD`,
`_DEFAULT_MIN_CATEGORY_OUTCOMES`, and the composite/structural constants
`REQUIRED_PHASES`, `REACHABILITY_TIER_KEYS`, `DRAW_CAPABLE_CATEGORIES`.

**This split is the argument for grading by mutation instead of by reading.** In one module,
`TERMINAL_COMPLETE`, `TERMINAL_PARTIAL` and `TERMINAL_CANCELLED` were protected while
`TERMINAL_FAILED`, `TERMINAL_HARD_LOSS` and `TERMINAL_OVERLAP_REFUSED` were not — six
constants declared on consecutive lines, used the same way, split three-three. Nothing in
the source distinguishes them; only the mutation does.

### Deferred (1)

`tests/test_calibration_staged_futures.py` (2 lines) is in tranche 1 by scope but was
**excluded**: it is in flight on `program/calibration-34/35/36/37`. Fix-on-touch applies —
the calibration lane owns it. Note that `tests/test_calibration_staged_futures_sql_300d.py`
is a *different* file and was cleared and included; match on path, never on a name that
looks like it belongs to your set.

'''


def _artifact(rows, by_file, nlines, total_lines) -> None:
    t1_files = sorted(f for f in by_file if by_file[f][0]["tranche1"])
    t1_lines = sum(nlines(by_file[f]) for f in t1_files)
    print(ARTIFACT_HEADER)
    print(f"## Totals\n")
    print(f"- **{total_lines} assertion lines** ({len(rows)} file/line/constant rows) "
          f"across **{len(by_file)} files**")
    print(f"- **{t1_lines} lines in tranche 1** (calibration / settlement / admin / 300B) "
          f"across {len(t1_files)} files")
    print(f"- {total_lines - t1_lines} lines outside tranche 1 → **fix-on-touch**")
    print(TRANCHE1_DISPOSITION)
    print("## Rows\n")
    print("`tranche 1` marks Alex's authorized scope for queue 331. Everything else is "
          "fix-on-touch.\n")
    print("| file | lines | assertion lines | constants | tranche 1 |")
    print("|---|---|---|---|---|")
    for f in sorted(by_file, key=lambda k: (-nlines(by_file[k]), k)):
        rs = by_file[f]
        lines = ",".join(str(n) for n in sorted({r["line"] for r in rs}))
        consts = ", ".join(f"`{c}`" for c in sorted({r["constant"] for r in rs}))
        mark = "**yes**" if rs[0]["tranche1"] else "no"
        print(f"| `{f}` | {nlines(rs)} | {lines} | {consts} | {mark} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--artifact", action="store_true",
                    help="write the full tracked census document to stdout")
    args = ap.parse_args()

    rows = collect()
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_file[r["file"]].append(r)

    # B3 counts unique ASSERTION LINES; a single line can carry two constants,
    # which this scan reports as two rows. Report both so the numbers are
    # comparable to the census they reproduce.
    def nlines(rs: list[dict]) -> int:
        return len({r["line"] for r in rs})

    total_lines = sum(nlines(rs) for rs in by_file.values())

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return

    if args.artifact:
        _artifact(rows, by_file, nlines, total_lines)
        return

    if args.markdown:
        t1_files = [f for f in by_file if by_file[f][0]["tranche1"]]
        t1_lines = sum(nlines(by_file[f]) for f in t1_files)
        print("| file | lines | assertion lines | constants | tranche 1 |")
        print("|---|---|---|---|---|")
        for f in sorted(by_file, key=lambda k: (-nlines(by_file[k]), k)):
            rs = by_file[f]
            lines = ",".join(str(n) for n in sorted({r["line"] for r in rs}))
            consts = ", ".join(sorted({r["constant"] for r in rs}))
            mark = "**yes**" if rs[0]["tranche1"] else "no"
            print(f"| `{f}` | {nlines(rs)} | {lines} | {consts} | {mark} |")
        print(f"\nTotal: {total_lines} assertion lines ({len(rows)} file/line/constant rows) "
              f"across {len(by_file)} files; {t1_lines} lines in tranche 1 "
              f"({len(t1_files)} files).")
        return

    print(f"{total_lines} constant-oracle assertion lines "
          f"({len(rows)} file/line/constant rows) across {len(by_file)} files")
    print(f"  tranche 1 (calibration/settlement/admin/300B): "
          f"{sum(nlines(by_file[f]) for f in by_file if by_file[f][0]['tranche1'])}")
    print()
    for f in sorted(by_file, key=lambda k: (-nlines(by_file[k]), k)):
        rs = by_file[f]
        flag = "T1" if rs[0]["tranche1"] else "  "
        lines = ",".join(str(n) for n in sorted({r["line"] for r in rs}))
        print(f"  {flag} {nlines(rs):3}  {f}  ({lines})")


if __name__ == "__main__":
    sys.exit(main())
