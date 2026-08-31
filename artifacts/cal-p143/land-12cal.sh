#!/usr/bin/env bash
# CAL-P143 — land the 12-CAL repair the moment D13 is answered YES.
#
# Run from the repository root, on a fresh program branch, with the freeze
# lifted or an explicit exception in hand. It applies the patch, installs the
# regression suite, and then STOPS: the gates are printed, not run, because a
# gate this script ran is a gate nobody read (gotcha #124).
#
# ORDER (RULE-DESIGN §5): D22 lands first or with this, never after. Landing
# this alone discards the staged futures bank and hands the next ~10 heavy beats
# to the class-B diagnostics timeout that D22 fixes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(git -C "$HERE" rev-parse --show-toplevel)"

echo "== pre-flight =========================================================="
git rev-parse --abbrev-ref HEAD                 # gotcha #51: know the branch
if ! git diff --quiet -- backend/app/tasks/precompute_calibration.py; then
  echo "REFUSING: the frozen file is already dirty. Resolve that first." >&2
  exit 2
fi

echo "== apply ==============================================================="
git apply --check "$HERE/12cal-lost-losses.patch"
git apply --stat  "$HERE/12cal-lost-losses.patch"
git apply         "$HERE/12cal-lost-losses.patch"
cp "$HERE/test_calibration_lost_losses_12cal.py" backend/tests/

echo "== what landed ========================================================="
git diff --stat
echo
echo "== the gates — RUN THESE, READ THE EXIT CODE (gotcha #124) ============="
cat <<'GATES'
  cd backend
  python3 -m pytest tests/test_calibration_lost_losses_12cal.py \
                    tests/test_calibration_missing_loser_census_p122.py -v \
    > /tmp/g1.txt 2>&1; echo "EXIT CODE: $?"; tail -20 /tmp/g1.txt

  python3 -m pytest tests/test_startup.py -v \
    > /tmp/g2.txt 2>&1; echo "EXIT CODE: $?"; tail -5 /tmp/g2.txt

  python3 -m pytest -k "calibration or bookmaker or ladder" \
    > /tmp/g3.txt 2>&1; echo "EXIT CODE: $?"; tail -20 /tmp/g3.txt

  # 🔴 THE ONES CAL-P143 COULD NOT RUN — no local Postgres in the sandbox, so
  # these were reasoned about and NOT executed. They seed single-outcome markets
  # with is_winner=false, which is exactly the class this patch newly admits, so
  # a row count in them may legitimately move. Read the diff before "fixing" it.
  python3 -m pytest tests/integration/test_calibration_mode_price_source_scope_pg.py \
                    tests/integration/test_calibration_mode_price_source_scope_peers_pg.py \
                    tests/integration/test_route_calibration.py \
                    tests/test_calibration_canonical_pg.py -v \
    > /tmp/g4.txt 2>&1; echo "EXIT CODE: $?"; tail -30 /tmp/g4.txt

  # and the full suite before the push — 21K tests, ~13 minutes
GATES
echo
echo "== declare the movement BEFORE the deploy (ruling 054) ================="
cat <<'DECLARE'
  published rows            : UP     (an addition of 100%-loss rows)
  restored-class win rate   : 0.0
  headline ECE              : DIRECTION UNKNOWN — measured WORSE on
                              kalshi/entertainment (5.21 -> 6.30) and BETTER on
                              polymarket/economics (3.90 -> 3.68). Measure it on
                              the first curve after the deploy; do not predict it.
  staged futures bank       : DISCARDED (input_fingerprint moves) — the next
                              census promotion is a full rebuild away, ~10 beats
DECLARE
