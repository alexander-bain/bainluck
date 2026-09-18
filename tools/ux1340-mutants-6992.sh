#!/usr/bin/env bash
# #6992 mutation battery — does the guard bind the pool, or only restate it?
#
# The subject is one predicate in `frontend/lib/teamDivisionRace.ts`:
#
#     const peers = grid.teams.filter(
#       (t) => t.division === me.division && (!me.conference || t.conference === me.conference),
#     );
#
# This one needs a battery more than most, because NOT ONE EXISTING TEST REDDENED
# when the fix went in. That is the expected signal (the old fixtures leave
# `conference: null`, so they ride the fail-open arm) but it is also exactly what a
# no-op change looks like. The battery is how the difference is shown rather than
# asserted: each mutant is a way the pool could be wrong that reads fine in review.
#
# Run from the repo root:  bash tools/ux1340-mutants-6992.sh

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
SRC="frontend/lib/teamDivisionRace.ts"
BAK="$(mktemp)"
cp "$SRC" "$BAK"
restore() { cp "$BAK" "$SRC"; rm -f "$BAK"; }
trap restore EXIT

PATTERN="teamDivisionRace|teamPageV2"
FILTER='const peers = grid.teams.filter\(\n    \(t\) => t.division === me.division && \(!me.conference \|\| t.conference === me.conference\),\n  \);'

run_mutant() {
  local name="$1" replacement="$2"
  cp "$BAK" "$SRC"
  perl -0pi -e "s/$FILTER/$replacement/" "$SRC"
  if cmp -s "$BAK" "$SRC"; then
    echo "  !! $name — NO-OP, the mutation did not apply (battery is lying)"
    return
  fi
  # 🔴 GATE ON THE EXIT CODE. `--verbose` is here to NAME the killing clause; the
  # verdict is the exit status. rc=1 is a result; any other rc means the run never
  # happened. (ux/1339: counting the wrong mark reported 6/6 SURVIVED against a
  # green control — arithmetically impossible, and the tell that the instrument,
  # not the guard, was broken.)
  local out rc
  out=$( (cd frontend && npx jest --verbose --testPathPatterns="$PATTERN" 2>&1) )
  rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  KILLED  $name"
    # jest heads each failure with '●', not '✕'.
    printf '%s\n' "$out" | /usr/bin/grep '●' | sed 's/.*› //; s/^/            by: /' | head -4
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

# 1. THE DEFECT ITSELF, restored. If this survives, the guard never saw #6992.
run_mutant "pool-keyed-on-division-alone" \
  'const peers = grid.teams.filter((t) => t.division === me.division);'

# 2. The fail-open arm is dropped. Reads as the "obvious" strict fix, and empties
#    the section for any grid that does not carry our conference — a row that
#    vanishes leaves no trace, which is why it is fenced rather than trusted.
run_mutant "fail-open-arm-dropped" \
  'const peers = grid.teams.filter((t) => t.division === me.division \&\& t.conference === me.conference);'

# 3. The conference clause is inverted: the pool becomes the OTHER league.
run_mutant "conference-clause-inverted" \
  'const peers = grid.teams.filter((t) => t.division === me.division \&\& (!me.conference || t.conference !== me.conference));'

# 4. `&&` slips to `||`: every same-conference team joins, divisions stop mattering.
run_mutant "and-becomes-or" \
  'const peers = grid.teams.filter((t) => t.division === me.division || (!me.conference || t.conference === me.conference));'

# 5. The comparison is made against the row itself — always true, so the clause
#    looks present in review and narrows nothing. The quietest way to lose this fix.
run_mutant "conference-compared-to-itself" \
  'const peers = grid.teams.filter((t) => t.division === me.division \&\& (!me.conference || t.conference === t.conference));'

# 6. The fail-open guard is inverted: we narrow ONLY when our conference is unknown.
run_mutant "fail-open-guard-inverted" \
  'const peers = grid.teams.filter((t) => t.division === me.division \&\& (me.conference \&\& t.conference === me.conference));'

# 7. The division half is dropped: conference alone, so all 15 of a league show up.
run_mutant "division-half-dropped" \
  'const peers = grid.teams.filter((t) => !me.conference || t.conference === me.conference);'

echo
echo "=== done (source restored by trap) ==="
