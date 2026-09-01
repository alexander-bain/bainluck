#!/usr/bin/env python3
"""CAL-P200 companion — what fraction of truth-test sites could the sweep TYPE?

The P199 lesson, applied to P200 itself: a sweep that closes NEGATIVE is only
worth the fraction of the population it could actually inspect. P198's numeric
sweep closed negative and the class was recorded CLOSED; its blind spot was the
TYPE of its control. P200's blind spot, if it has one, is the fraction of truth
tests whose operand type it cannot prove at all.

This prints the honest denominator:

    total truth-test sites
      -> typed non-numeric (str/seq/map)   <- what the sweep reported
      -> typed numeric/bool                <- correctly out of scope
      -> UNTYPED                           <- the sweep is BLIND to these

An UNTYPED share near zero makes P200's negative strong. A large one makes it a
statement about a minority of the code and must be reported as such.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sweep_falsy_nonnumeric import (  # noqa: E402
    ROOT, TARGETS, build_type_map, expr_label, infer, truth_sites,
)


PREDICATES = {
    "isinstance", "issubclass", "hasattr", "callable", "any", "all", "bool",
    "startswith", "endswith", "isdigit", "isalpha", "isnumeric", "isupper",
    "islower", "isspace", "match", "search", "fullmatch", "exists", "is_file",
    "is_dir", "__contains__",
}


def is_predicate_call(node: ast.AST) -> bool:
    """A call that can only ever return True/False cannot have an EMPTY state."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    tail = fn.id if isinstance(fn, ast.Name) else (
        fn.attr if isinstance(fn, ast.Attribute) else ""
    )
    return tail in PREDICATES


def benign_self_fallback(node: ast.AST, ctx: str, parent: ast.AST) -> bool:
    """``x or 0`` / ``x or ''`` / ``x or []`` — the fallback EQUALS the falsy
    value it replaces, so nothing is conflated: the expression yields the same
    value either way. Only the *type* of the constant has to match the falsy
    value the operand could take, which for a bare 0/''/[]/{} it does."""
    if ctx != "or" or not isinstance(parent, ast.BoolOp):
        return False
    last = parent.values[-1]
    if isinstance(last, ast.Constant) and last.value in (0, 0.0, "", None) \
            and not isinstance(last.value, bool):
        return last.value is not None
    if isinstance(last, (ast.List, ast.Tuple, ast.Dict)) and not getattr(last, "elts", getattr(last, "keys", [1])):
        return True
    return False


def main() -> int:
    tally = collections.Counter()
    untyped_examples: list[tuple[str, int, str]] = []
    per_file = {}

    for path in TARGETS:
        src = path.read_text()
        lines = src.splitlines()
        tree = ast.parse(src)
        tmap = build_type_map(tree)
        seen = set()
        local = collections.Counter()
        for node, ctx, parent in truth_sites(tree):
            key = (node.lineno, node.col_offset)
            if key in seen:
                continue
            seen.add(key)
            cat = infer(node, tmap)
            # Comparisons / calls returning bool are structurally NOT falsy-prone:
            # a comparison can only ever be True/False, so "empty" is not a state
            # it has. Classify them separately or the untyped bucket is inflated
            # by expressions that could never carry the defect.
            #
            # CORRECTION (made after hand-sampling the first run's UNTYPED
            # bucket): the first cut counted ``isinstance(...)``/``any(...)``
            # and the ``X or 0`` idiom as UNTYPED, which inflated the reported
            # blind spot. Neither can carry the defect — a predicate call is
            # boolean, and a fallback EQUAL to the falsy value substitutes the
            # value for itself. Reporting the inflated number would have been
            # the same overstatement this queue exists to warn about.
            if is_predicate_call(node):
                bucket = "boolean-shaped"
            elif benign_self_fallback(node, ctx, parent):
                bucket = "benign X-or-same-falsy"
            elif isinstance(node, (ast.Compare, ast.BoolOp)) and cat is None:
                bucket = "boolean-shaped"
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                bucket = "boolean-shaped"
            elif cat in {"str", "seq", "map"}:
                bucket = f"typed non-numeric ({cat})"
            elif cat in {"num", "bool"}:
                bucket = f"typed {cat}"
            else:
                bucket = "UNTYPED"
                if len(untyped_examples) < 25:
                    untyped_examples.append(
                        (path.name, node.lineno, lines[node.lineno - 1].strip()[:96])
                    )
            tally[bucket] += 1
            local[bucket] += 1
        per_file[path.name] = local

    total = sum(tally.values())
    print("=" * 88)
    print("CAL-P200 coverage — can the non-numeric sweep TYPE what it looked at?")
    print(f"root: {ROOT}   modules: {len(TARGETS)}   truth-test sites: {total}")
    print("=" * 88)
    for bucket, n in tally.most_common():
        print(f"  {n:>5}  {100*n/total:5.1f}%   {bucket}")

    nonnum = sum(v for k, v in tally.items() if k.startswith("typed non-numeric"))
    untyped = tally["UNTYPED"]
    boolish = tally["boolean-shaped"] + tally["benign X-or-same-falsy"]
    # The population that COULD carry the defect: anything not structurally
    # boolean and not a self-substituting fallback.
    at_risk = total - boolish
    print("\n  falsy-capable population (excludes boolean-shaped):", at_risk)
    print(f"    inspected & typed non-numeric : {nonnum} ({100*nonnum/at_risk:.1f}%)")
    print(f"    typed numeric/bool (out of scope): "
          f"{sum(v for k, v in tally.items() if k.startswith('typed ') and 'non-numeric' not in k)}")
    print(f"    UNTYPED — the sweep is BLIND   : {untyped} ({100*untyped/at_risk:.1f}%)")

    print("\n### UNTYPED sites (the sweep's own blind spot), first 25\n")
    for name, ln, text in untyped_examples:
        print(f"  {name}:{ln}")
        print(f"      {text}")

    print("\n### per-module UNTYPED share\n")
    for name, local in sorted(per_file.items(),
                              key=lambda kv: -kv[1]["UNTYPED"]):
        t = sum(local.values())
        if not t or not local["UNTYPED"]:
            continue
        print(f"  {local['UNTYPED']:>4} / {t:<4} untyped   {name}")

    print("\n" + "=" * 88)
    verdict = ("STRONG" if untyped / max(at_risk, 1) < 0.25 else
               "PARTIAL — report the negative as covering a MINORITY")
    print(f"NEGATIVE-RESULT STRENGTH: {verdict}")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
