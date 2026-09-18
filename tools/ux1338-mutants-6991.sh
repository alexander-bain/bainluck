#!/usr/bin/env bash
# #6991 mutation battery — does the guard actually bind the fence, or does it
# only restate it?
#
# The subject is one predicate in `TwoSidedTimeline.tsx`:
#
#     const fieldIsThePair = (competitors || []).length === 2;
#
# A fence is worth exactly what its guard kills. Each mutant below is a way the
# fence could be wrong that a reader would not see in review; the battery reports
# WHICH test clause kills each one, not just a pass count, because a count alone
# calls six different signatures one signature.
#
# Run from the repo root:  bash tools/ux1338-mutants-6991.sh

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
SRC="frontend/components/event/TwoSidedTimeline.tsx"
BAK="$(mktemp)"
cp "$SRC" "$BAK"
restore() { cp "$BAK" "$SRC"; rm -f "$BAK"; }
trap restore EXIT

PATTERN="aFightsTwoPercentsAgree6816|aLongerFieldIsNotADuel6991"

# name | perl expression applied to the source
run_mutant() {
  local name="$1" expr="$2"
  cp "$BAK" "$SRC"
  perl -0pi -e "$expr" "$SRC"
  if cmp -s "$BAK" "$SRC"; then
    echo "  !! $name — NO-OP, the mutation did not apply (battery is lying)"
    return
  fi
  # 🔴 GATE ON THE EXIT CODE, NOT ON MATCHED OUTPUT. The first version of this
  # battery counted '✕' marks, which jest only prints under --verbose — so every
  # mutant "survived" against a green control, which is the battery lying rather
  # than six holes. `--verbose` is here to NAME the killing clause; the verdict
  # is the exit status.
  local out rc
  out=$( (cd frontend && npx jest --verbose --testPathPatterns="$PATTERN" 2>&1) )
  rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  KILLED  $name"
    # jest heads each failure with '●', not the '✕' of the suite list (which is
    # not emitted here) — keying on the wrong mark is how the clause report came
    # back empty while the counts were right.
    printf '%s\n' "$out" | grep '●' | sed 's/.*› //; s/^/            by: /' | head -6
  elif [ "$rc" -eq 0 ]; then
    echo "  SURVIVED  $name   <-- a hole in the guard"
  else
    echo "  !! $name — jest exited $rc: the run never happened, not a verdict"
  fi
}

echo "=== control: unmutated tree ==="
cp "$BAK" "$SRC"
if (cd frontend && npx jest --testPathPatterns="$PATTERN" >/dev/null 2>&1); then
  echo "  green (a battery whose control is red proves nothing)"
else
  echo "  !! CONTROL IS RED — stop, the battery cannot be read"; exit 1
fi

echo
echo "=== mutants ==="

# 1. The fence is removed outright: every field pairs, which is the defect.
run_mutant "fence-always-true" \
  's/const fieldIsThePair = \(competitors \|\| \[\]\)\.length === 2;/const fieldIsThePair = true;/'

# 2. The fence never opens: a genuine bout stops pairing, which is #6844 undone.
run_mutant "fence-always-false" \
  's/const fieldIsThePair = \(competitors \|\| \[\]\)\.length === 2;/const fieldIsThePair = false;/'

# 3. THE NATURAL MISTAKE. `pair` is `.slice(0, 2)`, so its length is 2 for every
#    field of two or more — keying the fence on it reads as correct and fences
#    nothing. This is the mutant the whole battery exists for.
run_mutant "keyed-on-pair-not-field" \
  's/const fieldIsThePair = \(competitors \|\| \[\]\)\.length === 2;/const fieldIsThePair = pair.length === 2;/'

# 4. Off-by-one in the comparison: a longer field passes the fence again.
run_mutant "length-gte-2" \
  's/const fieldIsThePair = \(competitors \|\| \[\]\)\.length === 2;/const fieldIsThePair = (competitors || []).length >= 2;/'

# 5. The "no claim" sentinel becomes a real value — 0 is falsy and a plausible
#    slip, and it would print 0% over every unpaired row.
run_mutant "no-claim-becomes-zero" \
  's/\? renderedDuelPercents\(a\.probability, b\.probability\)\n    : \[null, null\];/? renderedDuelPercents(a.probability, b.probability)\n    : [0, 0];/'

# 6. The fence is applied to the LOCAL arm only and the served arm is freed —
#    proves the shared predicate is load-bearing on both, not just on one.
run_mutant "served-arm-unfenced" \
  's/const \[aServed, bServed\] = fieldIsThePair \? servedBoutPercents\(pair\) : \[null, null\];/const [aServed, bServed] = servedBoutPercents(pair);/'

echo
echo "=== done (source restored by trap) ==="
