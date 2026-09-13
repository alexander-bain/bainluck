#!/bin/bash
# #6007 — mutation check for the Kalshi date-only placeholder fold.
#
# A guard file that passes is worth nothing until each thing it claims to defend
# is broken in turn and the file is seen to die. Every mutant below is a
# plausible edit a later change could make. Mutant 2 is the one this rig exists
# for: it is the version of #6007 that ships INERT — predicate relaxed, sliding
# window left alone — which folds nothing in production while every two-row test
# in the suite still passes.
#
# Usage: bash tools/n299-6007-mutants.sh
set -u

SRC="backend/app/utils/event_twin_fold.py"
TESTS="tests/test_kalshi_date_only_fold_6007.py tests/test_soccer_kickoff_drift_fold_5964.py tests/test_soccer_name_pair_fold_5918.py tests/test_kalshi_occurrence_start_5905.py tests/test_event_twin_fold.py"
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

# CERT-2814's FOLLOW-UP `5964-MUTANT-BASELINE-EXIT-CODE`, paid here: the sibling
# rig printed its baseline through a pipe, so a RED baseline would have read as
# a page of dead mutants. This one reads the exit code and refuses to continue.
echo "BASELINE"
baseline=$(cd backend && python3 -m pytest $TESTS -q 2>&1)
baseline_rc=$?
printf '%s\n' "$baseline" | tail -1
if [ "$baseline_rc" -ne 0 ]; then
  echo "*** BASELINE IS NOT GREEN (exit $baseline_rc) — every mutant below would"
  echo "*** read as killed for the wrong reason. Fix the baseline first."
  exit 1
fi

echo
echo "MUTANTS"

# 1. The exception is reverted: every pair is held to the drift bound again.
#    This is master, and the phantom EPL cards come back.
perl -0pi -e 's/        if not \(dateless\[left\] or dateless\[right\]\):\n            if abs\(left\[3\] - right\[3\]\) > SOCCER_KICKOFF_DRIFT:\n                return False/        if abs(left[3] - right[3]) > SOCCER_KICKOFF_DRIFT:\n            return False/' "$SRC"
run "the date-only exception reverted (master)" kill

# 2. THE INERT SHIP. The predicate is relaxed but the sliding window is not, so
#    the loop breaks hours before it reaches the real kick-off and the question
#    is never asked. Every two-row test still passes; production folds nothing.
perl -0pi -e 's/            if not dateless\[left\] and right\[3\] - left\[3\] > SOCCER_KICKOFF_DRIFT:/            if right[3] - left[3] > SOCCER_KICKOFF_DRIFT:/' "$SRC"
run "window not exempted — the INERT version of this ship" kill

# 3. Everything is treated as dateless: the clock half is gone for all soccer.
perl -0pi -e 's/        dateless\[key\] = all\(is_kalshi_date_only\(member\) for member in groups\[key\]\)/        dateless[key] = True/' "$SRC"
run "every group dateless (clock half deleted for soccer)" kill

# 4. Nothing is dateless: the helper is wired up but never answers True.
perl -0pi -e 's/        dateless\[key\] = all\(is_kalshi_date_only\(member\) for member in groups\[key\]\)/        dateless[key] = False/' "$SRC"
run "no group dateless (helper wired but inert)" kill

# 5. The source gate is widened to Kalshi's own close time, which is a real
#    instant — the midnight `soccer_other` rows this deliberately excludes.
perl -0pi -e 's/KALSHI_DATE_ONLY_SOURCE = "kalshi_ticker"/KALSHI_DATE_ONLY_SOURCE = "kalshi"/' "$SRC"
run "source gate widened to plain kalshi" kill

# 6. The source gate is dropped entirely: any midnight row is a placeholder.
perl -0pi -e 's/    if getattr\(event, "commence_time_source", None\) != KALSHI_DATE_ONLY_SOURCE:\n        return False\n//' "$SRC"
run "source gate deleted (any midnight row)" kill

# 7-10. The midnight fingerprint loses one component at a time. Each one is the
#    invariant `_name_clusters` leans on when it exempts a group from the break.
perl -0pi -e 's/            commence\.hour == 0\n            and commence\.minute == 0/            commence.minute == 0/' "$SRC"
run "midnight test drops the hour" kill

perl -0pi -e 's/            and commence\.minute == 0\n//' "$SRC"
run "midnight test drops the minute" kill

perl -0pi -e 's/            and commence\.second == 0\n//' "$SRC"
run "midnight test drops the second" kill

perl -0pi -e 's/            and commence\.microsecond == 0\n//' "$SRC"
run "midnight test drops the microsecond" kill

# 11. Only the earlier row in a pair may be dateless. A placeholder sorts first
#     in its day so the union-find never notices, but the clique re-check asks
#     in arrival order and refuses the cluster whole.
perl -0pi -e 's/        if not \(dateless\[left\] or dateless\[right\]\):/        if not dateless[left]:/' "$SRC"
run "exception only honours the left-hand row" kill

# 12. The exception stops being an exception and becomes the rule for the pair:
#     a dateless row folds on names alone with no bucket left to bound it.
#     (The bucket is still `(sport_id, date)`, so this tests the day boundary.)
perl -0pi -e 's/    sport_id, _away, _home, minute = key\n    return \(sport_id, minute\.date\(\)\)/    sport_id, _away, _home, minute = key\n    return (sport_id,)/' "$SRC"
run "day boundary removed from the bucket" kill

echo
echo "done"
