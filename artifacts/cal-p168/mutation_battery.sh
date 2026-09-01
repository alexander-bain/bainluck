#!/bin/bash
# CAL-P168 mutation battery for K' (rank 1, polymarket/baseball).
#
# Runs in an rsync COPY of the repo, never the live worktree: editing sources
# while pytest is collecting in the same tree produces phantom failures, and a
# battery that edits the tree it is measuring cannot be trusted either way.
#
# Each mutation disables ONE thing the design says is load-bearing. A mutation
# that leaves the suite GREEN is a guard that does not guard.
set -u
SRC=/Users/bain/bainluck-dev/calibration
WORK=/tmp/cal-p168-mut
TESTS="tests/test_player_props_placeholder_kprime.py tests/test_calibration_rule_e_structural_bundle_p162.py tests/test_calibration_staged_fold_p034.py tests/test_calibration_staged_census_contract_p164.py tests/evals/test_calibration_fingerprint_derived_map.py"

rm -rf "$WORK"; mkdir -p "$WORK"
rsync -a --exclude '.git' --exclude 'node_modules' --exclude '__pycache__' \
      --exclude '.next' "$SRC/backend/" "$WORK/backend/" >/dev/null 2>&1
rsync -a "$SRC/scripts/" "$WORK/scripts/" >/dev/null 2>&1 || true
cd "$WORK/backend" || exit 1

BUILD=app/tasks/precompute_calibration.py
MIRROR=app/utils/calibration_staged_futures.py
cp "$BUILD" /tmp/p168_build.orig
cp "$MIRROR" /tmp/p168_mirror.orig

run_case () {
  local name="$1"
  find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null
  out=$(python3 -m pytest $TESTS -q 2>&1)
  code=$?
  nfail=$(printf '%s' "$out" | grep -oE '[0-9]+ failed' | head -1)
  if [ "$code" -eq 0 ]; then
    echo "SURVIVED  ($name) -- NO GUARD CAUGHT THIS"
  elif [ "$code" -eq 1 ]; then
    echo "KILLED    ($name) -- ${nfail:-failures}"
  else
    echo "HARNESS   ($name) -- exit $code, the battery did not run"
    printf '%s\n' "$out" | tail -5
  fi
  cp /tmp/p168_build.orig "$BUILD"; cp /tmp/p168_mirror.orig "$MIRROR"
}

echo "=== CONTROL (unmutated) ==="
run_case "control: expect no failures at all" | sed 's/^KILLED/UNEXPECTED-RED/'

echo
echo "=== MUTATIONS ==="

# 1. R1 removed from the CTE's disjunction.
python3 - <<'PY'
import re,pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("                        {half_spike_pair_predicate('mrs')}\n                        OR ","                        ",1)
p.write_text(s)
PY
run_case "R1 (half-spike pair) dropped from the rule"

# 2. R2 removed -- the arm whose solo delta is -0.11pp and which decides the pass.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("                        OR {published_pair_coherence_predicate('mrs')}\n","",1)
p.write_text(s)
PY
run_case "R2 (published pair incoherence) dropped -- cell returns to 3.10"

# 3. R3 loses its sum conjunct (name-only: refused, NEW half 3.10).
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("""    return f"({name_expr} ILIKE '{PLAYER_PROPS_NAME_PATTERN}' AND {sum_expr} > {MEX_NORMALIZE_THRESHOLD})\"""",
            """    return f"({name_expr} ILIKE '{PLAYER_PROPS_NAME_PATTERN}')\"""",1)
p.write_text(s)
PY
run_case "R3 sum arm dropped (name-only)"

# 4. R3's threshold re-tuned to the value the holdout REFUSED.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("{sum_expr} > {MEX_NORMALIZE_THRESHOLD}","{sum_expr} > 15",1)
p.write_text(s)
PY
run_case "R3 threshold re-tuned to >15 (passes pooled, fails BOTH halves)"

# 5. M1's band widened past the control class.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("PLAYER_PROPS_MIDPOINT_BAND_LO = 0.45","PLAYER_PROPS_MIDPOINT_BAND_LO = 0.40",1)
s=s.replace("PLAYER_PROPS_MIDPOINT_BAND_HI = 0.55","PLAYER_PROPS_MIDPOINT_BAND_HI = 0.60",1)
p.write_text(s)
PY
run_case "M1 band widened to [0.40,0.60]"

# 6. M1's drift floor removed -- this is the one that deletes ordinary line movement.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("PLAYER_PROPS_FORCED_DRIFT_MIN = 0.25","PLAYER_PROPS_FORCED_DRIFT_MIN = 0.0",1)
p.write_text(s)
PY
run_case "M1 drift floor removed -- the control class dies with it"

# 7. M1 reads the curve price instead of calibration_probability.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("f\"({o}.calibration_probability BETWEEN {PLAYER_PROPS_MIDPOINT_BAND_LO} \"",
            "f\"(COALESCE({o}.calibration_probability, {o}.opening_probability) BETWEEN {PLAYER_PROPS_MIDPOINT_BAND_LO} \"",1)
p.write_text(s)
PY
run_case "M1 reads COALESCE(cp, opening) -- horizon-variant membership"

# 8. The curve gate removed: the rule computes and excludes nothing.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("                    AND NOT ro.is_player_props_placeholder\n","",1)
p.write_text(s)
PY
run_case "deduped gate removed -- flag computed, curve unchanged"

# 9. The cell added to RULE E's allowlist (measured 8.35 vs a 4.71 control).
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace('    ("kalshi", "economics"),\n)','    ("kalshi", "economics"),\n    ("polymarket", "baseball"),\n)',1)
p.write_text(s)
PY
run_case "cell ALSO added to RULE E's allowlist -- double count + 8.35"

# 10. The temporary map emptied: the page silently stops promising the return.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
i=s.index("PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL: dict[str, str] = {")
j=s.index("}\n",s.index('"polymarket/baseball": ('  ,i))
s=s[:i]+"PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL: dict[str, str] = {}\n"+s[j+2:]
p.write_text(s)
PY
run_case "temporary_by_cell emptied -- the disclosure promise disappears"

# 11. The census column undeclared to the fail-closed merger (the CAL-P162 bug).
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/utils/calibration_staged_futures.py'); s=p.read_text()
s=s.replace('    "nxb_cell_1",\n    "pp_cell_0",\n','    "nxb_cell_1",\n',1)
p.write_text(s)
PY
run_case "pp_cell_0 undeclared to the merger -- CAL-P162's exact failure"

# 12. The per-cell column counts the WRONG flag.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace('"COUNT(*) FILTER (WHERE is_player_props_placeholder "\n            f"AND source','"COUNT(*) FILTER (WHERE is_esports_bundle "\n            f"AND source',1)
p.write_text(s)
PY
run_case "pp_cell_0 counts is_esports_bundle -- a number from a rule never applied"

# 13. The allowlist widened to a whole category (CAL-P114: 3.91 -> 17.75).
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace('PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS = (("polymarket", "baseball"),)',
            'PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS = (("polymarket", "baseball"), ("polymarket", "basketball"))',1)
p.write_text(s)
PY
run_case "allowlist widened to an unmeasured second cell"

# 14. The population-shaping constants dropped from the fingerprint.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
for line in ('        f"player_props_cells={sorted(PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)}",\n',
             '        f"player_props_half_spike={PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE}",\n',
             '        f"player_props_band={PLAYER_PROPS_MIDPOINT_BAND_LO},{PLAYER_PROPS_MIDPOINT_BAND_HI}",\n'):
    s=s.replace(line,'',1)
p.write_text(s)
PY
run_case "K' constants dropped from the input fingerprint"

# 15. The totals dropped from the outer aggregate's pass-through.
#     🔴 THIS ONE HAPPENED FOR REAL DURING THE BUILD. The inner scan emitted the
#     columns and the outer aggregate dropped them; the existing p164 contract
#     test caught it before any of my own guards ran.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/tasks/precompute_calibration.py'); s=p.read_text()
s=s.replace("""                MAX(ls.player_props_placeholder_excluded)
                    AS player_props_placeholder_excluded,
                MAX(ls.player_props_placeholder_markets)
                    AS player_props_placeholder_markets,
""","",1)
p.write_text(s)
PY
run_case "totals dropped from the OUTER aggregate -- disclosure fails open"

# 16. The totals undeclared in DEFAULT_CENSUS_COLUMNS.
#     🔴 ALSO HAPPENED FOR REAL: the fail-closed merge raised
#     UndeclaredColumnError and no generation could bank -- CAL-P162 exactly.
python3 - <<'PY'
import pathlib
p=pathlib.Path('app/utils/calibration_staged_futures.py'); s=p.read_text()
s=s.replace('    "player_props_placeholder_excluded",\n    "player_props_placeholder_markets",\n','',1)
p.write_text(s)
PY
run_case "totals undeclared to the merger -- no generation can bank"

echo
echo "battery complete"
