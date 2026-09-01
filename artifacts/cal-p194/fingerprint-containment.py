"""CAL-P194-2 — the ``:4370`` comment is NOT in the input fingerprint.

Four directives carried the claim that deleting the stale comment at
``precompute_calibration:4370`` "moves the fingerprint. Not free during D-G."
It does not. ``_main_input_fingerprint`` hashes ``inspect.getsource`` of exactly
four functions; line 4370 is at MODULE LEVEL, 23 lines outside the nearest one.

Three independent checks:
  A. AST — which function encloses 4370? (none)
  B. containment — is the line's text in the hashed concatenation? (no)
  C. empirical — over P190's 42-commit sweep, did the digest ever move without
     precompute_calibration.py being touched? (never, 0/26)

Runnable from ANYWHERE (it bootstraps ``backend/`` onto sys.path itself):
    python3 artifacts/cal-p194/fingerprint-containment.py

Read-only. No source edits, no database, no network.
"""

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

SRC = REPO / "backend/app/tasks/precompute_calibration.py"
HASHED = {
    "compute_calibration_payload",
    "_calibration_population_ctes",
    "_virtual_market_ctes",
    "_main_futures_sql",
}
TARGETS = (4370, 4467)

# --- A. AST: what encloses the target lines? --------------------------------
text = SRC.read_text()
spans = [
    (n.name, n.lineno, n.end_lineno)
    for n in ast.walk(ast.parse(text))
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
]

print("=== A. enclosing scope ===")
for target in TARGETS:
    encl = sorted(
        (s for s in spans if s[1] <= target <= s[2]), key=lambda s: s[2] - s[1]
    )
    print(f"line {target}: enclosing={[e[0] for e in encl] or 'MODULE LEVEL'}")
    print(f"   -> inside a HASHED function? {any(e[0] in HASHED for e in encl)}")

print()
for name in sorted(HASHED):
    print(f"  {name}: {[s[1:] for s in spans if s[0] == name]}")

# --- B. containment: is the line in the digest's actual input? --------------
from app.tasks import precompute_calibration as pc  # noqa: E402

hashed_source = (
    inspect.getsource(pc.compute_calibration_payload)
    + inspect.getsource(pc._calibration_population_ctes)
    + inspect.getsource(pc._virtual_market_ctes)
    + inspect.getsource(pc._main_futures_sql)
)
line_4370 = text.splitlines()[4369]

print()
print("=== B. containment ===")
print("LINE 4370:", repr(line_4370))
print("hashed source chars:", len(hashed_source))
print("IS LINE 4370 IN THE HASHED SOURCE? ->", line_4370.strip() in hashed_source)

# --- C. empirical: 42 commits of P190's own sweep ---------------------------
sweep = REPO / "artifacts/cal-p190/sweep-three-digests-42-commits.jsonl"
print()
print("=== C. empirical cross-check (P190's 42-commit sweep) ===")
if not sweep.exists():
    print("sweep file not found; skipped")
else:
    rows = [json.loads(l) for l in sweep.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if not r.get("error") and r.get("wide")]
    rows.sort(key=lambda r: r["date"])
    moves = off_file = 0
    for a, b in zip(rows, rows[1:]):
        if a["wide"] == b["wide"]:
            continue
        moves += 1
        touched = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--name-only", a["sha"], b["sha"]],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.split()
        if not any("precompute_calibration.py" in f for f in touched):
            off_file += 1
            print(f"  COUNTEREXAMPLE: {a['sha'][:9]} -> {b['sha'][:9]}")
    print(f"wide-digest transitions: {moves}")
    print(f"  of which did NOT touch precompute_calibration.py: {off_file}")

print()
print("EXPECTED: MODULE LEVEL / False / False / 26 transitions / 0 counterexamples")
