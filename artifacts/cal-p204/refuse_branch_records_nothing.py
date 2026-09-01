#!/usr/bin/env python3
"""CAL-P204 — which cursor decode ACTIONS can reach the ledger?

THE POPULATION, named in the noun the marker will use: the **cursor decode
actions**. There are exactly four, and they are enumerated from source
(``app/utils/calibration_phase_ledger.py``), never hardcoded here — an
instrument that hardcodes its own population cannot report coverage honestly
(P201-1's lesson).

THE CLAIM under test: ``_run_staged_futures`` records the decode action into the
phase ledger with ``record_stage(f"staged:cursor_{action}")``. If that statement
is reachable for every action, the ledger can name any of the four. If some
action returns BEFORE it, that action is structurally unrecordable — a marker
string with zero possible occurrences, which is gotcha #53's shape.

FOUR ARMS, across two axes (reachability, and site-specificity):

  ARM A  positive control — the detector must classify at least one action
         RECORDED. A detector that says "unrecordable" for everything has not
         discriminated anything.

  ARM B  COUNTERFACTUAL — the arm that fails if the status quo would also have
         been right. The REFUSE branch's early ``return`` is deleted on the AST
         and the detector re-run. It MUST flip to 4/4 recordable. If it does
         not, the detector is keying on something other than the early return
         and the finding is a preference, not a defect.

  ARM C  SIBLING control — the OTHER ``action == REFUSE`` handler in the same
         file (the checkpoint-level one) DOES write durably. The detector must
         say so. This proves the finding is site-specific rather than a blanket
         property of how this codebase handles REFUSE.

  ARM D  EMPIRICAL — 168 consecutive production beats
         (``artifacts/cal-p118/beat-ring-full.json``): how often does each
         ``staged:cursor_*`` key actually appear?

Exit 0 on a coherent run, whatever the verdict. Runs from any cwd.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# repo bootstrap — run me from /tmp and I still work (P194+ pattern)
# --------------------------------------------------------------------------
def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "app" / "tasks" / "precompute_calibration.py").is_file():
            return parent
    raise SystemExit("could not locate repo root from %s" % here)


ROOT = repo_root()
BACKEND = ROOT / "backend"
PRECOMPUTE = BACKEND / "app" / "tasks" / "precompute_calibration.py"
LEDGER_MOD = BACKEND / "app" / "utils" / "calibration_phase_ledger.py"
RING = ROOT / "artifacts" / "cal-p118" / "beat-ring-full.json"


# --------------------------------------------------------------------------
# population: the decode actions, enumerated from source
# --------------------------------------------------------------------------
def decode_actions(src: str) -> dict[str, str]:
    """``{CONSTANT_NAME: literal}`` for the four cursor decode actions."""
    tree = ast.parse(src)
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        if tgt.id in ("FRESH", "RESUME", "INVALIDATE", "REFUSE"):
            out[tgt.id] = node.value.value
    return out


# --------------------------------------------------------------------------
# detector
# --------------------------------------------------------------------------
def _calls(node: ast.AST) -> list[str]:
    """Dotted names of every Call under ``node``."""
    names = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Attribute):
                names.append(f.attr)
            elif isinstance(f, ast.Name):
                names.append(f.id)
    return names


def find_func_with(tree: ast.AST, call_name: str, marker_call: str) -> ast.AST | None:
    """The function whose body calls both ``call_name`` and ``marker_call``."""
    best = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        c = _calls(node)
        if call_name in c and marker_call in c:
            best = node
    return best


def _is_cursor_record(stmt: ast.stmt) -> bool:
    """Is this the ``record_stage(f"staged:cursor_{action}")`` statement?"""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    call = stmt.value
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "record_stage":
        return False
    if not call.args:
        return False
    arg = call.args[0]
    if isinstance(arg, ast.JoinedStr):
        lit = "".join(
            v.value for v in arg.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
        )
        return "staged:cursor_" in lit
    return False


def _action_guard(stmt: ast.stmt) -> str | None:
    """If ``stmt`` is ``if action == <CONST>:``, return CONST's name."""
    if not isinstance(stmt, ast.If):
        return None
    test = stmt.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.Eq):
        return None
    if not isinstance(test.left, ast.Name) or test.left.id != "action":
        return None
    comp = test.comparators[0]
    return comp.id if isinstance(comp, ast.Name) else None


def _has_return(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return):
            return True
    return False


def classify(tree: ast.AST, actions: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """``({ACTION: 'recordable'|'unrecordable'}, notes)``.

    An action is UNRECORDABLE when a guard ``if action == ACTION:`` returns
    before the ``staged:cursor_{action}`` record statement is reached.
    """
    notes: list[str] = []
    fn = find_func_with(tree, "load_staged_cursor", "record_stage")
    if fn is None:
        raise SystemExit("DETECTOR BROKEN: no function calls both load_staged_cursor "
                         "and record_stage — the source shape changed")
    notes.append("host function: %s (line %d)" % (fn.name, fn.lineno))

    idx_record = None
    for i, stmt in enumerate(fn.body):
        if _is_cursor_record(stmt):
            idx_record = i
            break
    if idx_record is None:
        # No record statement at all => nothing is recordable.
        notes.append("no staged:cursor_ record statement at function-body level")
        return {a: "unrecordable" for a in actions}, notes
    notes.append("record statement at body index %d (line %d)"
                 % (idx_record, fn.body[idx_record].lineno))

    verdict = {a: "recordable" for a in actions}
    for stmt in fn.body[:idx_record]:
        guarded = _action_guard(stmt)
        if guarded and guarded in verdict and _has_return(stmt):
            verdict[guarded] = "unrecordable"
            notes.append("guard `if action == %s:` at line %d returns before the record"
                         % (guarded, stmt.lineno))
    return verdict, notes


def strip_return_from_refuse(tree: ast.AST) -> ast.AST:
    """COUNTERFACTUAL: delete the early return inside ``if action == REFUSE:``."""
    fn = find_func_with(tree, "load_staged_cursor", "record_stage")
    for stmt in fn.body:
        if _action_guard(stmt) == "REFUSE":
            stmt.body = [s for s in stmt.body if not isinstance(s, ast.Return)]
            if not stmt.body:
                stmt.body = [ast.Pass()]
    return ast.fix_missing_locations(tree)


def sibling_refuse_writes_durably(tree: ast.AST) -> tuple[bool, str]:
    """ARM C: the checkpoint-level REFUSE handler — does it write durably?"""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        c = _calls(node)
        if "build_runner" not in c:
            continue
        for stmt in node.body:
            if _action_guard(stmt) == "REFUSE":
                inner = _calls(stmt)
                if "save_phase_ledger" in inner:
                    return True, ("%s line %d: REFUSE body calls save_phase_ledger"
                                  % (node.name, stmt.lineno))
                return False, ("%s line %d: REFUSE body has no durable write"
                               % (node.name, stmt.lineno))
    return False, "no checkpoint-level REFUSE handler found"


# --------------------------------------------------------------------------
def main() -> int:
    src = PRECOMPUTE.read_text()
    actions = decode_actions(LEDGER_MOD.read_text())

    print("=" * 74)
    print("CAL-P204 — can every cursor decode ACTION reach the ledger?")
    print("=" * 74)
    print("repo root : %s" % ROOT)
    print("cwd       : %s" % Path.cwd())
    print()

    print("POPULATION (enumerated from %s):" % LEDGER_MOD.relative_to(ROOT))
    for name, lit in sorted(actions.items()):
        print("  %-11s = %r" % (name, lit))
    if len(actions) != 4:
        print("  !! expected 4 actions, found %d — detector aborting" % len(actions))
        return 1
    print()

    verdict, notes = classify(ast.parse(src), actions)
    print("DETECTOR NOTES")
    for n in notes:
        print("  - %s" % n)
    print()

    print("VERDICT — per action")
    for name in sorted(actions):
        mark = "OK " if verdict[name] == "recordable" else "!! "
        print("  %s%-11s %s   (marker string: 'staged:cursor_%s')"
              % (mark, name, verdict[name], actions[name]))
    unrec = sorted(a for a, v in verdict.items() if v == "unrecordable")
    classified = len(verdict)
    print()
    print("COVERAGE: %d/%d actions classified = %.1f%%   (denominator = the whole "
          "population, enumerated above)" % (classified, len(actions),
                                             100.0 * classified / len(actions)))
    print("UNRECORDABLE: %s" % (", ".join(unrec) if unrec else "none"))
    print()

    # ---- ARM A: positive control -----------------------------------------
    print("-" * 74)
    recordable = [a for a, v in verdict.items() if v == "recordable"]
    arm_a = len(recordable) > 0
    print("ARM A (positive control) — detector can emit RECORDABLE : %s"
          % ("PASS  [%s]" % ", ".join(sorted(recordable)) if arm_a else "FAIL"))

    # ---- ARM B: counterfactual -------------------------------------------
    patched = strip_return_from_refuse(ast.parse(src))
    v2, _ = classify(patched, actions)
    flipped = [a for a in actions if verdict[a] == "unrecordable" and v2[a] == "recordable"]
    arm_b = all(v == "recordable" for v in v2.values()) and bool(flipped)
    print("ARM B (COUNTERFACTUAL: delete the early return) -> %d/%d recordable : %s"
          % (sum(1 for v in v2.values() if v == "recordable"), len(actions),
             "PASS  [flipped: %s]" % ", ".join(flipped) if arm_b else "FAIL"))
    print("        ^ this arm FAILS if the status quo would also have been right.")

    # ---- ARM C: sibling control ------------------------------------------
    ok_sib, why = sibling_refuse_writes_durably(ast.parse(src))
    print("ARM C (sibling: checkpoint-level REFUSE writes durably) : %s"
          % ("PASS" if ok_sib else "FAIL"))
    print("        %s" % why)

    # ---- ARM D: empirical ------------------------------------------------
    if RING.is_file():
        beats = json.load(RING.open())
        counts: dict[str, int] = {}
        for b in beats:
            for k in b.get("gauges", {}):
                if k.startswith("staged:cursor_"):
                    counts[k] = counts.get(k, 0) + 1
        print("ARM D (empirical, %d consecutive production beats):" % len(beats))
        for name in sorted(actions):
            key = "staged:cursor_%s" % actions[name]
            print("        %-28s seen in %3d/%d beats" % (key, counts.get(key, 0), len(beats)))
        for k in sorted(counts):
            if not any(k == "staged:cursor_%s" % v for v in actions.values()):
                print("        %-28s seen in %3d/%d beats  (reason token)"
                      % (k, counts[k], len(beats)))
        print("        NOTE: fresh/invalidate are absent too, so absence alone is NOT")
        print("              evidence. ARM B is what makes REFUSE's absence structural.")
    else:
        print("ARM D: ring artifact absent at %s — skipped" % RING)

    print("-" * 74)
    all_pass = arm_a and arm_b and ok_sib
    print("ARMS: A=%s B=%s C=%s  => detector %s"
          % (arm_a, arm_b, ok_sib, "TRUSTWORTHY" if all_pass else "NOT TRUSTWORTHY"))
    print()
    if unrec and all_pass:
        print("FINDING: %s is structurally unrecordable in the phase ledger."
              % ", ".join("staged:cursor_%s" % actions[a] for a in unrec))
    elif not unrec:
        print("FINDING: none — every action can reach the ledger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
