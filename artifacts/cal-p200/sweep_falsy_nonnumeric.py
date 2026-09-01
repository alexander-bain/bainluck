#!/usr/bin/env python3
"""CAL-P200 sweep — NON-NUMERIC falsy conflation across every calibration module.

WHAT SHAPE THIS DETECTOR ENCODES (state it, per the P199 control-arm lesson):
    A value whose type is ``str`` / list-like / dict-like, whose EMPTY value is a
    meaningful state, is subjected to a TRUTH test (``if x:`` / ``not x`` /
    ``x or default``).  Python's ``''``, ``[]``, ``{}`` are falsy, so "empty" is
    silently conflated with "absent"/the default.

    This is deliberately NOT the numeric shape.  CAL-P198 swept for falsy ZERO,
    closed NEGATIVE, and the conveyor recorded the class CLOSED — but its control
    arm was a numeric ``.get(k, 0) or None`` (phase_ledger:1299), so nothing in
    its detector could ever have surfaced a string.  CAL-P199 then found exactly
    such a string (``record.detail = detail or None``).  A passing control is not
    a complete control; it is only as broad as the TYPE its hit encodes.

TYPE ORACLE
    Annotations, not name heuristics.  Dataclass fields (``detail: Optional[str]``),
    annotated assignments, annotated function parameters and return types build a
    per-module map from bare name -> type category.  A name annotated with two
    DIFFERENT categories anywhere in the module is marked ``conflict`` and
    EXCLUDED — the sweep would rather under-report than assert a type it cannot
    prove.  Expression-level inference (``str(...)``, f-strings, ``.get(k, "")``,
    literals, comprehensions) supplements it.

CONTROL ARMS (two-sided; the sweep exits 1 if either fails)
    POSITIVE — must surface, and they are STRINGS:
        calibration_phase_ledger.py:1360  record.detail = detail or None
        calibration_phase_ledger.py:1128  if self.detail:
    NEGATIVE — must NOT surface, and they are NUMBERS:
        calibration_phase_ledger.py:1299  self.stage_ok_maxima.get(name, 0) or None
        calibration_main_build.py:1613    completed_mean if completed_mean else mean_ms
    The positive arm proves the sweep can see the class at all.  The negative arm
    proves it is genuinely TYPED and has not degenerated into "flag every truth
    test", which would make a long hit list meaningless.

Runs from any cwd; bootstraps the repo root itself.
"""

from __future__ import annotations

import ast
import pathlib
import sys


# --------------------------------------------------------------------------- #
# repo bootstrap
# --------------------------------------------------------------------------- #
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

TARGETS = sorted(
    [p for p in (APP / "tasks").glob("*calibration*.py")]
    + [p for p in (APP / "utils").glob("*calibration*.py")]
    + [APP / "routes" / "calibration.py"]
)

POSITIVE_CONTROLS = [
    (APP / "utils" / "calibration_phase_ledger.py", 1360, "record.detail = detail or None"),
    (APP / "utils" / "calibration_phase_ledger.py", 1128, "if self.detail:"),
]
NEGATIVE_CONTROLS = [
    (APP / "utils" / "calibration_phase_ledger.py", 1299, "numeric .get(name, 0) or None"),
    (APP / "tasks" / "calibration_main_build.py", 1613, "numeric completed_mean if/else"),
]

# --------------------------------------------------------------------------- #
# type categories
# --------------------------------------------------------------------------- #
STR_T = {"str", "AnyStr", "LiteralString"}
SEQ_T = {"list", "List", "Sequence", "Iterable", "Collection", "tuple", "Tuple",
         "set", "Set", "FrozenSet", "frozenset", "MutableSequence"}
MAP_T = {"dict", "Dict", "Mapping", "MutableMapping", "OrderedDict", "defaultdict",
         "Counter"}
NUM_T = {"int", "float", "complex", "Decimal"}
BOOL_T = {"bool"}

NONNUMERIC = {"str", "seq", "map"}

STR_METHODS = {"strip", "lstrip", "rstrip", "lower", "upper", "join", "format",
               "replace", "title", "casefold", "removeprefix", "removesuffix",
               "capitalize", "expandtabs", "zfill"}
SEQ_CALLS = {"list", "sorted", "split", "rsplit", "splitlines", "values", "keys",
             "items", "findall", "readlines"}
MAP_CALLS = {"dict"}


def _ann_names(node: ast.AST) -> list[str]:
    """Every bare identifier appearing in an annotation expression."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)  # string forward refs
    return out


def ann_category(node: ast.AST | None) -> str | None:
    """Map an annotation expression to one of str/seq/map/num/bool, else None.

    ``Optional[str]`` / ``str | None`` collapse to 'str': None is already an
    explicit absent, which is precisely what makes conflating '' with it a bug.
    """
    if node is None:
        return None
    names = set(_ann_names(node))
    names.discard("Optional")
    names.discard("Union")
    names.discard("None")
    names.discard("NoneType")
    # Container payloads must not vote: Dict[str, int] is a map, not a str/num.
    root = node
    while isinstance(root, ast.Subscript):
        root = root.value
    root_names = set(_ann_names(root)) if not isinstance(root, ast.Constant) else set()
    if isinstance(node, ast.BinOp):  # X | None
        cats = {c for v in (node.left, node.right) if (c := ann_category(v))}
        return next(iter(cats)) if len(cats) == 1 else None
    if isinstance(node, ast.Subscript) and root_names:
        head = root_names
    else:
        head = names or root_names
    if head & MAP_T:
        return "map"
    if head & SEQ_T:
        return "seq"
    if head & STR_T:
        return "str"
    if head & NUM_T:
        return "num"
    if head & BOOL_T:
        return "bool"
    return None


def build_type_map(tree: ast.AST) -> dict[str, str]:
    """name -> category, from annotations only. Conflicting names are dropped."""
    seen: dict[str, set[str]] = {}

    def note(name: str | None, cat: str | None) -> None:
        if not name or not cat:
            return
        seen.setdefault(name, set()).add(cat)

    for n in ast.walk(tree):
        if isinstance(n, ast.AnnAssign):
            tgt = n.target
            nm = tgt.id if isinstance(tgt, ast.Name) else (
                tgt.attr if isinstance(tgt, ast.Attribute) else None
            )
            note(nm, ann_category(n.annotation))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
                note(arg.arg, ann_category(arg.annotation))
            rc = ann_category(n.returns)
            if rc:
                note(n.name + "()", rc)

    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def expr_label(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = expr_label(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        base = expr_label(node.value)
        key = repr(node.slice.value) if isinstance(node.slice, ast.Constant) else "..."
        return f"{base}[{key}]" if base else None
    if isinstance(node, ast.Call):
        fn = expr_label(node.func)
        return f"{fn}()" if fn else None
    return None


def infer(node: ast.AST, tmap: dict[str, str]) -> str | None:
    """Category of the VALUE this expression produces, or None if unproven."""
    # literals
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return "str"
        return None
    if isinstance(node, ast.JoinedStr):
        return "str"
    if isinstance(node, (ast.List, ast.ListComp, ast.Tuple, ast.Set, ast.SetComp,
                         ast.GeneratorExp)):
        return "seq"
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return "map"

    # calls
    if isinstance(node, ast.Call):
        fn = expr_label(node.func) or ""
        tail = fn.split(".")[-1].rstrip("()")
        if tail == "str":
            return "str"
        if tail in STR_METHODS:
            return "str"
        if tail in SEQ_CALLS:
            return "seq"
        if tail in MAP_CALLS:
            return "map"
        if tail in NUM_T | {"len", "sum", "abs", "round"}:
            return "num"
        # x.get(k, DEFAULT) — the default proves the caller's expected type,
        # the exact structural analogue of P198's numeric_default_get.
        if tail == "get" and len(node.args) >= 2:
            return infer(node.args[1], tmap)
        # annotated local function return
        if (fn + "()") in tmap:
            return tmap[fn + "()"]
        if (tail + "()") in tmap:
            return tmap[tail + "()"]
        return None

    # slices of a typed base:  self.detail[:200]
    if isinstance(node, ast.Subscript):
        if isinstance(node.slice, ast.Slice):
            return infer(node.value, tmap)
        base = infer(node.value, tmap)
        return "str" if base == "str" else None

    # names / attributes, via the annotation map
    if isinstance(node, (ast.Name, ast.Attribute)):
        tail = node.id if isinstance(node, ast.Name) else node.attr
        return tmap.get(tail)

    if isinstance(node, ast.BoolOp):
        cats = {c for v in node.values if (c := infer(v, tmap))}
        return next(iter(cats)) if len(cats) == 1 else None

    return None


def truth_sites(tree: ast.AST):
    """(node, context, parent) for every expression whose TRUTH value is taken."""
    for n in ast.walk(tree):
        if isinstance(n, ast.BoolOp):
            for v in n.values[:-1]:
                yield v, ("or" if isinstance(n.op, ast.Or) else "and"), n
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            yield n.operand, "not", n
        elif isinstance(n, (ast.If, ast.While)):
            yield n.test, "if", n
        elif isinstance(n, ast.IfExp):
            yield n.test, "ifexp", n
        elif isinstance(n, ast.comprehension):
            for c in n.ifs:
                yield c, "comp-if", n
        elif isinstance(n, ast.Assert):
            yield n.test, "assert", n


def fallback_of(ctx: str, parent: ast.AST, node: ast.AST) -> str:
    """What the EMPTY value silently becomes."""
    try:
        if ctx == "or" and isinstance(parent, ast.BoolOp):
            return ast.unparse(parent.values[-1])
        if ctx == "ifexp" and isinstance(parent, ast.IfExp):
            return ast.unparse(parent.orelse)
    except Exception:
        pass
    return "-"


def scan(path: pathlib.Path):
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    tmap = build_type_map(tree)
    hits, seen = [], set()
    for node, ctx, parent in truth_sites(tree):
        cat = infer(node, tmap)
        if cat not in NONNUMERIC:
            continue
        lbl = expr_label(node) or ast.unparse(node)
        key = (node.lineno, node.col_offset, lbl)
        if key in seen:
            continue
        seen.add(key)
        hits.append((node.lineno, ctx, cat, lbl,
                     fallback_of(ctx, parent, node),
                     lines[node.lineno - 1].strip()))
    return sorted(hits), tmap


def main() -> int:
    print("=" * 90)
    print("CAL-P200 — NON-NUMERIC falsy sweep ('' / [] / {}) across every calibration module")
    print("root:", ROOT)
    print("shape encoded: a str/list/dict-typed value whose EMPTY is meaningful, truth-tested")
    print("=" * 90)

    cache: dict[pathlib.Path, list] = {}

    def hits_for(p: pathlib.Path):
        if p not in cache:
            cache[p] = scan(p)[0]
        return cache[p]

    print("\n### CONTROL ARM A (POSITIVE) — known STRING hits must re-surface\n")
    pos_ok = True
    for path, line, what in POSITIVE_CONTROLS:
        got = [h for h in hits_for(path) if abs(h[0] - line) <= 3]
        mark = "PASS" if got else "FAIL"
        pos_ok &= bool(got)
        print(f"  {mark}  {path.name}:{line}  {what}")
        for ln, ctx, cat, lbl, fb, text in got:
            print(f"         -> L{ln} [{ctx}/{cat}] {lbl}   {text}")

    print("\n### CONTROL ARM B (NEGATIVE) — known NUMERIC hits must NOT surface\n")
    neg_ok = True
    for path, line, what in NEGATIVE_CONTROLS:
        got = [h for h in hits_for(path) if abs(h[0] - line) <= 1]
        mark = "PASS" if not got else "FAIL"
        neg_ok &= not got
        print(f"  {mark}  {path.name}:{line}  {what}"
              + ("" if not got else f"   <-- LEAKED: {got}"))

    total = 0
    per_file = []
    for path in TARGETS:
        hits = hits_for(path)
        total += len(hits)
        per_file.append((len(hits), path))
        if not hits:
            continue
        print(f"\n### {path.relative_to(ROOT)}  —  {len(hits)} site(s)\n")
        for ln, ctx, cat, lbl, fb, text in hits:
            print(f"  L{ln:<5} [{ctx:<7}/{cat:<4}] {lbl}"
                  + (f"    empty -> {fb}" if fb != "-" else ""))
            print(f"           {text}")

    print("\n" + "=" * 90)
    print(f"modules scanned: {len(TARGETS)}   total non-numeric truth-tested sites: {total}")
    for n, p in sorted(per_file, reverse=True)[:6]:
        print(f"    {n:>3}  {p.name}")
    ok = pos_ok and neg_ok
    print("CONTROL A (positive, string):", "PASS" if pos_ok else "FAIL")
    print("CONTROL B (negative, numeric):", "PASS" if neg_ok else "FAIL")
    if not ok:
        print("VERDICT: detector is NOT trustworthy — a zero or a long list is equally vacuous")
    print("=" * 90)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
