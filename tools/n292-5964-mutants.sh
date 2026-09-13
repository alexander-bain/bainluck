#!/bin/bash
# #5964 — mutation check for the soccer kick-off drift fold.
#
# A guard file that passes is worth nothing until each thing it claims to defend
# is broken in turn and the file is seen to die. Every mutant below is a plausible
# edit a later change could make; the one marked EQUIVALENT is expected to survive
# and is listed so that its survival is a recorded decision rather than a gap.
#
# Usage: bash tools/n292-5964-mutants.sh
set -u

SRC="backend/app/utils/event_twin_fold.py"
TESTS="tests/test_soccer_kickoff_drift_fold_5964.py tests/test_soccer_name_pair_fold_5918.py tests/test_kalshi_occurrence_start_5905.py tests/test_event_twin_fold.py"
BACKUP=$(mktemp)
cp "$SRC" "$BACKUP"
restore() { cp "$BACKUP" "$SRC"; }
trap restore EXIT

run() {  # run <label> <expectation>
  local label="$1" expect="$2" out rc summary

  # The mutation must actually have applied. A perl pattern that silently fails
  # to match produces a clean pass that reads exactly like a surviving mutant,
  # which would turn this whole rig into a rubber stamp.
  if cmp -s "$SRC" "$BACKUP"; then
    echo "  *** MUTATION DID NOT APPLY *** — $label"
    restore; return
  fi

  # Never pipe a gate (gotcha #54): the exit code of a pipeline is the last
  # command's, so piping pytest into `tail` reports tail's success every time.
  out=$(cd backend && python3 -m pytest $TESTS -q 2>&1)
  rc=$?
  summary=$(printf '%s\n' "$out" | tail -1)

  if [ "$rc" -eq 0 ]; then
    if [ "$expect" = "survive" ]; then
      echo "  SURVIVED (expected) — $label :: $summary"
    else
      echo "  *** SURVIVED (NOT EXPECTED) *** — $label :: $summary"
    fi
  elif [ "$rc" -eq 1 ]; then
    echo "  killed — $label :: $summary"
  else
    echo "  *** HARNESS STORY, exit $rc *** — $label :: $summary"
  fi
  restore
}

echo "BASELINE"
(cd backend && python3 -m pytest $TESTS -q 2>&1 | tail -1)

echo
echo "MUTANTS"

# 1. The bound goes to zero — i.e. master's exact-minute rule. The ship must die.
perl -0pi -e 's/SOCCER_KICKOFF_DRIFT = timedelta\(minutes=5\)/SOCCER_KICKOFF_DRIFT = timedelta(minutes=0)/' "$SRC"
run "drift=0 (master's exact-minute rule)" kill

# 2. The bound is widened past the populations other ships own.
perl -0pi -e 's/SOCCER_KICKOFF_DRIFT = timedelta\(minutes=5\)/SOCCER_KICKOFF_DRIFT = timedelta(minutes=60)/' "$SRC"
run "drift=60 (swallows #5918's re-mints)" kill

# 3. The bound is widened by one minute — the smallest real widening.
perl -0pi -e 's/SOCCER_KICKOFF_DRIFT = timedelta\(minutes=5\)/SOCCER_KICKOFF_DRIFT = timedelta(minutes=6)/' "$SRC"
run "drift=6 (off-by-one widening)" kill

# 4. The bound is narrowed by one minute — the smallest real narrowing.
perl -0pi -e 's/SOCCER_KICKOFF_DRIFT = timedelta\(minutes=5\)/SOCCER_KICKOFF_DRIFT = timedelta(minutes=4)/' "$SRC"
run "drift=4 (off-by-one narrowing)" kill

# 5. The clock test is dropped from the pair predicate entirely.
perl -0pi -e 's/        if abs\(left\[3\] - right\[3\]\) > SOCCER_KICKOFF_DRIFT:\n            return False\n//' "$SRC"
run "the drift test deleted from same_fixture" kill

# 6. The comparison loses its strictness, so the bound is inclusive+1.
perl -0pi -e 's/if abs\(left\[3\] - right\[3\]\) > SOCCER_KICKOFF_DRIFT:/if abs(left[3] - right[3]) > SOCCER_KICKOFF_DRIFT + timedelta(minutes=1):/' "$SRC"
run "bound off by one at the comparison" kill

# 7. The candidate bucket goes back to the minute — the change undone.
perl -0pi -e 's/    return \(sport_id, minute\.date\(\)\)/    return (sport_id, minute)/' "$SRC"
run "bucket reverted to the minute" kill

# 8. The clique refusal is dropped, so drift can be chained.
perl -0pi -e 's/        if all\(\n            same_fixture\(left, right\)\n            for i, left in enumerate\(members\)\n            for right in members\[i \+ 1 :\]\n        \):/        if True:/' "$SRC"
run "clique refusal dropped (drift chains)" kill

# 9. EQUIVALENT BY CONSTRUCTION: the sliding window is a speedup over a predicate
#    that already refuses everything it skips. Removing it must change nothing,
#    and its survival is the evidence that the window is not load-bearing logic.
perl -0pi -e 's/            if right\[3\] - left\[3\] > SOCCER_KICKOFF_DRIFT:\n                break\n//' "$SRC"
run "sliding-window break removed (EQUIVALENT)" survive

echo
echo "done"
