#!/usr/bin/env bash
# Ruling 086 — an exclusion is only safe where a mutation can red it.
#
# Widens every carve-out predicate in the abort-grading module to always-apply,
# one at a time, and reports how many contract tests notice. A carve-out that
# reds NOTHING is unmeasured: the suite cannot tell "this exclusion is narrow"
# from "this exclusion swallowed everything", because both are green.
#
# This is not a CI gate — mutation runs are for authoring time, when you add or
# widen an exclusion. Run it then, and put the number in the change.
#
#   cd frontend/e2e && bash mutation-census.sh
#
# Expected shape: a baseline of 471/471 green (exit 0), then EVERY predicate
# exits 1 with a non-zero failing count. Any row reading `failing=0` is the
# finding; a row reading ANCHOR-MISS means this script has drifted from the
# source and is silently testing nothing, which is the same defect one level up.
set -u

SRC=helpers/navigationAborts.js
WORK=$(mktemp -d)
trap 'cp "$WORK/orig" "$SRC" 2>/dev/null; rm -rf "$WORK"' EXIT

PREDICATES=(
  isNavigationCancellation
  isFeedRequest
  isThirdParty
  allowanceIsIntermittent
  allowanceIsInstrumentInduced
  isInstrumentInduced
  aftermathIsGraded
)

cp "$SRC" "$WORK/orig"

npm run contract > "$WORK/baseline.txt" 2>&1
base=$?
echo "baseline: exit=$base  $(grep -E '^. (pass|fail) ' "$WORK/baseline.txt" | tr '\n' ' ')"
if [ "$base" -ne 0 ]; then
  echo "REFUSING: the suite is not green before mutation; fix that first." >&2
  exit 2
fi

status=0
for fn in "${PREDICATES[@]}"; do
  cp "$WORK/orig" "$SRC"
  if ! python3 - "$fn" <<'PY'
import re, sys
from pathlib import Path
fn = sys.argv[1]
p = Path("helpers/navigationAborts.js")
t = p.read_text()
m = re.search(rf"function {fn}\((?P<args>[^)]*)\) \{{\n(?P<body>.*?)\n\}}", t, re.S)
if not m:
    sys.exit(3)
p.write_text(t[:m.start()]
             + f"function {fn}({m.group('args')}) {{\n  return true; // MUTATION\n}}"
             + t[m.end():])
PY
  then
    printf "%-32s ANCHOR-MISS (script has drifted from the source)\n" "$fn"
    status=1
    continue
  fi
  # A mutation that failed to APPLY reports green and reads as "no sensor".
  if ! grep -q "// MUTATION" "$SRC"; then
    printf "%-32s EDIT-DID-NOT-LAND\n" "$fn"
    status=1
    continue
  fi
  npm run contract > "$WORK/$fn.txt" 2>&1
  code=$?
  fails=$(grep -E '^. fail ' "$WORK/$fn.txt" | tail -1 | tr -dc '0-9')
  fails=${fails:-0}
  verdict="ok"
  if [ "$code" -eq 0 ] || [ "$fails" -eq 0 ]; then verdict="NO SENSOR"; status=1; fi
  printf "%-32s exit=%s  failing=%-4s %s\n" "$fn" "$code" "$fails" "$verdict"
done

cp "$WORK/orig" "$SRC"
exit "$status"
