#!/usr/bin/env python3
"""CAL-P201 — Q10 turned on the ORPHAN census (P197 proof_1 §E + P198 census).

The question bank's highest-value open item: *"this sweep closed NEGATIVE. What
FRACTION of its population did it CLASSIFY?"* P200 answered it for the falsy
sweeps. This answers it for the other instrument that set a standing marker --
the no-production-consumer census, which produced two verdicts the conveyor now
repeats as law:

    "PhaseLedger.failed_phase has no production consumer"
    "five others ... are consumed in-module: internal machinery, not dead.
     Do not re-report those five."

and which the question bank records as::

    "which ledger KEY has NO reader?" SPENT on the ledger module (P197) and on
    calibration_staged_futures / calibration_main_build /
    calibration_staged_disclosure (P198).

Two independent axes are measured, because they fail differently:

  AXIS 1 — POPULATION.  What did the census put in scope at all?
      ``public_members()`` walks ``tree.body`` and keeps only ``FunctionDef`` /
      ``AsyncFunctionDef`` -- module-level functions and the methods of
      top-level classes.  Module-level CONSTANTS, class/dataclass FIELDS, class
      NAMES, and anything defined under ``if``/``try`` are never enumerated.
      That matters specifically because a ledger *key* is a constant --
      ``GAUGE_UNITS_BANKED = "staged:units_banked"`` -- so the population that
      answered the "which ledger key has no reader" question contained no keys.

  AXIS 2 — DETECTOR PRECISION.  ``refs()`` is ``\\bname\\b`` over the raw line,
      so a mention inside a COMMENT or DOCSTRING counts as a consumer.  A member
      whose only evidence is prose is recorded as consumed.  This re-runs the
      same detection with comments and string literals blanked out and reports
      any verdict that flips.

CONTROL ARMS -- two-sided on each axis, per the P200 pattern.  A sweep that
returns zero is worthless unless a known hit surfaces AND a known non-hit stays
down.

  A1-positive  PHASE_DEADLINE_MS is in the full surface but NOT in the census
               population.  If it is absent from the surface, the coverage
               figure is a bookkeeping artifact.
  A1-negative  record_gauge is in BOTH.  If the census population is somehow
               empty, coverage would read 0% for the wrong reason.
  A2-positive  failed_phase must surface as having no production-CODE consumer
               (P197's known finding must reproduce).
  A2-negative  record_gauge must NOT surface -- it is consumed everywhere.

HONEST DENOMINATOR.  Locals bound inside function bodies are excluded: they
cannot have an external consumer, and counting them would inflate the blind
spot exactly the way P200's first cut did (77.4% -> corrected 66.0%).  This
script never descends into a function body.

Runs from any cwd; bootstraps the repo root itself.  Exit 0 = all four controls
held.  Exit 1 = a control failed and every number below is void.
"""

from __future__ import annotations

import ast
import collections
import io
import pathlib
import re
import sys
import tokenize


def repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
            return p
    cand = pathlib.Path("/Users/bain/bainluck-dev/calibration")
    if (cand / "backend" / "app" / "utils" / "calibration_phase_ledger.py").exists():
        return cand
    raise SystemExit("FATAL: could not locate repo root")


ROOT = repo_root()
APP = ROOT / "backend" / "app"
TESTS = ROOT / "backend" / "tests"

LEDGER = APP / "utils" / "calibration_phase_ledger.py"
MODULES = [
    LEDGER,
    APP / "utils" / "calibration_staged_futures.py",
    APP / "tasks" / "calibration_main_build.py",
    APP / "utils" / "calibration_staged_disclosure.py",
]

APP_FILES = sorted(APP.rglob("*.py"))
TEST_FILES = sorted(TESTS.rglob("*.py")) if TESTS.exists() else []

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------------------------------------------------------------- populations

def census_population(tree: ast.AST) -> set[str]:
    """EXACTLY what P197 proof_1 §E / P198 census enumerated."""
    out: set[str] = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            out.add(n.name)
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_"):
                    out.add(m.name)
    return out


def public_surface(tree: ast.AST) -> dict[str, tuple[str, int, int]]:
    """name -> (kind, start_line, end_line), scope-aware.

    Never descends into a function body: a local cannot have a consumer, and
    including locals is the denominator inflation P200 had to retract.
    """
    found: dict[str, tuple[str, int, int]] = {}

    def emit(name: str, kind: str, s: int, e: int) -> None:
        if not name.startswith("_"):
            found.setdefault(name, (kind, s, e))

    def walk(body, inclass: bool) -> None:
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                emit(n.name, "method" if inclass else "function", n.lineno, n.end_lineno)
            elif isinstance(n, ast.ClassDef):
                emit(n.name, "class", n.lineno, n.end_lineno)
                walk(n.body, True)
            elif isinstance(n, ast.AnnAssign):
                if isinstance(n.target, ast.Name):
                    emit(n.target.id, "field" if inclass else "constant", n.lineno, n.end_lineno or n.lineno)
            elif isinstance(n, ast.Assign):
                for tg in n.targets:
                    if isinstance(tg, ast.Name):
                        emit(tg.id, "field" if inclass else "constant", n.lineno, n.end_lineno or n.lineno)
            elif isinstance(n, (ast.If, ast.Try)):
                for sub in ("body", "orelse", "finalbody"):
                    walk(getattr(n, sub, []) or [], inclass)
                for h in getattr(n, "handlers", []) or []:
                    walk(h.body, inclass)

    walk(tree.body, False)
    return found


# ------------------------------------------------------------------- indexing

def code_words(path: pathlib.Path) -> tuple[set[str], dict[str, int]]:
    """Identifiers appearing in real CODE (comments + string literals blanked)."""
    words: set[str] = set()
    first: dict[str, int] = {}
    try:
        src = path.read_text(errors="ignore")
    except OSError:
        return words, first
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.NAME:
                words.add(tok.string)
                first.setdefault(tok.string, tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        for i, line in enumerate(src.splitlines(), 1):
            for w in WORD.findall(line):
                words.add(w)
                first.setdefault(w, i)
    return words, first


def raw_words(path: pathlib.Path) -> tuple[set[str], dict[str, int]]:
    """Identifiers appearing ANYWHERE, prose included -- the census's own view."""
    words: set[str] = set()
    first: dict[str, int] = {}
    try:
        src = path.read_text(errors="ignore")
    except OSError:
        return words, first
    for i, line in enumerate(src.splitlines(), 1):
        for w in WORD.findall(line):
            words.add(w)
            first.setdefault(w, i)
    return words, first


def own_module_words(path: pathlib.Path, span: tuple[int, int]) -> tuple[set[str], set[str]]:
    """In-module identifiers OUTSIDE the member's own definition span."""
    src = path.read_text(errors="ignore")
    lines = src.splitlines()
    keep = [l for i, l in enumerate(lines, 1) if not (span[0] <= i <= span[1])]
    text = "\n".join(keep)
    raw = set(WORD.findall(text))
    code: set[str] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.NAME:
                code.add(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        code = raw
    return raw, code


# ---------------------------------------------------------------------- main

def main() -> int:
    print("=" * 84)
    print("CAL-P201 — Q10 on the no-production-consumer census (P197 §E / P198)")
    print("root:", ROOT)
    print("app files: %d   test files: %d" % (len(APP_FILES), len(TEST_FILES)))
    print("=" * 84)

    # ---- index every app/test file ONCE -------------------------------------
    app_code: dict[pathlib.Path, set[str]] = {}
    app_raw: dict[pathlib.Path, set[str]] = {}
    app_raw_ln: dict[pathlib.Path, dict[str, int]] = {}
    for f in APP_FILES:
        app_code[f], _ = code_words(f)
        app_raw[f], app_raw_ln[f] = raw_words(f)
    test_raw: dict[pathlib.Path, set[str]] = {}
    for f in TEST_FILES:
        test_raw[f], _ = raw_words(f)

    # ---- AXIS 1: population coverage ---------------------------------------
    print("\n" + "-" * 84)
    print("AXIS 1 — POPULATION: what fraction of the public surface was ENUMERATED?")
    print("-" * 84)
    tot_cen = tot_sur = 0
    missed_kinds: collections.Counter = collections.Counter()
    surfaces: dict[pathlib.Path, dict] = {}
    censuses: dict[pathlib.Path, set[str]] = {}
    for m in MODULES:
        tree = ast.parse(m.read_text())
        sur = public_surface(tree)
        cen = census_population(tree)
        surfaces[m], censuses[m] = sur, cen
        miss = collections.Counter(k for n, (k, _, _) in sur.items() if n not in cen)
        missed_kinds += miss
        tot_cen += len(cen)
        tot_sur += len(sur)
        print("\n  %s" % m.relative_to(ROOT))
        print("     enumerated by the census : %3d" % len(cen))
        print("     public surface           : %3d      COVERAGE %5.1f%%"
              % (len(sur), 100 * len(cen) / max(len(sur), 1)))
        print("     never in scope           : %s" % (dict(miss) or "{}"))
    print("\n  TOTAL  %d enumerated / %d public names  =  %.1f%% COVERAGE"
          % (tot_cen, tot_sur, 100 * tot_cen / max(tot_sur, 1)))
    print("  the %d names never in scope, by kind: %s"
          % (tot_sur - tot_cen, dict(missed_kinds)))

    # ---- AXIS 1 orphan run over the MISSED bucket ---------------------------
    print("\n" + "-" * 84)
    print("AXIS 1b — the census's OWN detector, run over the bucket it never saw")
    print("-" * 84)
    axis1_hits: list[tuple[str, str, int]] = []
    for m in MODULES:
        sur, cen = surfaces[m], censuses[m]
        for name, (kind, s, e) in sorted(sur.items(), key=lambda kv: kv[1][1]):
            if name in cen or kind in ("function", "method"):
                continue
            in_raw, _ = own_module_words(m, (s, e))
            if name in in_raw:
                continue
            if any(name in app_raw[f] for f in APP_FILES if f != m):
                continue
            if any(name in test_raw[f] for f in TEST_FILES):
                continue
            axis1_hits.append((str(m.relative_to(ROOT)), name, s))
    print("  ORPHANS found in the never-enumerated bucket: %d" % len(axis1_hits))
    for rel, name, ln in axis1_hits:
        print("      %s:%d   %s" % (rel, ln, name))

    # ---- AXIS 2: detector precision ----------------------------------------
    print("\n" + "-" * 84)
    print("AXIS 2 — DETECTOR: consumed verdicts resting on PROSE ONLY")
    print("-" * 84)
    scanned = consumed = prose_only = 0
    prose_hits: list[tuple[str, str, int]] = []
    for m in MODULES:
        tree = ast.parse(m.read_text())
        sur = surfaces[m]
        for name in sorted(censuses[m]):
            kind, s, e = sur.get(name, ("method", 1, 1))
            scanned += 1
            in_raw, in_code = own_module_words(m, (s, e))
            raw_hit = name in in_raw or any(name in app_raw[f] for f in APP_FILES if f != m)
            code_hit = name in in_code or any(name in app_code[f] for f in APP_FILES if f != m)
            if not raw_hit:
                continue
            consumed += 1
            if not code_hit:
                prose_only += 1
                where = next((("%s:%d" % (f.relative_to(ROOT), app_raw_ln[f].get(name, 0)))
                              for f in APP_FILES if f != m and name in app_raw[f]), "in-module prose")
                prose_hits.append((str(m.relative_to(ROOT)), name, s))
                print("      %s.%s (line %d) — evidence is prose only, e.g. %s"
                      % (m.name, name, s, where))
    print("  members the census called CONSUMED : %d of %d scanned" % (consumed, scanned))
    print("  ...of which the evidence is PROSE ONLY: %d" % prose_only)

    # ---- CONTROLS -----------------------------------------------------------
    print("\n" + "-" * 84)
    print("CONTROL ARMS (two-sided, both axes)")
    print("-" * 84)
    led_sur, led_cen = surfaces[LEDGER], censuses[LEDGER]

    a1p = "PHASE_DEADLINE_MS" in led_sur and "PHASE_DEADLINE_MS" not in led_cen
    a1n = "record_gauge" in led_sur and "record_gauge" in led_cen

    # A2: failed_phase must have no production-CODE consumer.
    fp_kind, fp_s, fp_e = led_sur.get("failed_phase", ("method", 1, 1))
    _, fp_incode = own_module_words(LEDGER, (fp_s, fp_e))
    fp_code = "failed_phase" in fp_incode or any(
        "failed_phase" in app_code[f] for f in APP_FILES if f != LEDGER)
    a2p = not fp_code
    rg_kind, rg_s, rg_e = led_sur.get("record_gauge", ("method", 1, 1))
    _, rg_incode = own_module_words(LEDGER, (rg_s, rg_e))
    rg_code = "record_gauge" in rg_incode or any(
        "record_gauge" in app_code[f] for f in APP_FILES if f != LEDGER)
    a2n = rg_code

    for tag, ok, desc in [
        ("A1-positive", a1p, "PHASE_DEADLINE_MS is in the surface and NOT in the census population"),
        ("A1-negative", a1n, "record_gauge is in BOTH (population is not vacuously empty)"),
        ("A2-positive", a2p, "failed_phase has no production-CODE consumer (P197 reproduces)"),
        ("A2-negative", a2n, "record_gauge DOES have a production-CODE consumer (no false alarm)"),
    ]:
        print("  %-12s %s   %s" % (tag, "PASS" if ok else "FAIL", desc))

    all_ok = a1p and a1n and a2p and a2n
    print("\n" + "=" * 84)
    print("CONTROLS: %s" % ("ALL PASS" if all_ok else "FAILED — every number above is VOID"))
    if all_ok:
        print("COVERAGE VERDICT: the census classified %.1f%% of the public surface."
              % (100 * tot_cen / max(tot_sur, 1)))
        print("  It enumerated 100%% of callables and 0%% of constants/fields/classes.")
        print("  Running its own detector over the unseen bucket yields %d orphan(s)."
              % len(axis1_hits))
    print("=" * 84)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
