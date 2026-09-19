#!/usr/bin/env bash
# #7163 — mutation battery for the particled-surname guard.
#
# A test file is only worth its run time if it FAILS when the thing it guards
# is broken. Each mutant below breaks one decision in the ship; the suite must
# go red for every one, and the script fails if any mutant SURVIVES.
#
# Run from the repo root:  bash tools/ux1356-mutants-7163.sh
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/frontend/lib/teamShortName.ts"
PAGE="$ROOT/frontend/app/events/[id]/page.tsx"
SUITE="particledSurname7163"

LIB_BAK="$(mktemp)"; cp "$LIB" "$LIB_BAK"
PAGE_BAK="$(mktemp)"; cp "$PAGE" "$PAGE_BAK"
restore() { cp "$LIB_BAK" "$LIB"; cp "$PAGE_BAK" "$PAGE"; }
trap restore EXIT

# mutate <file> <old> <new>
#
# THE PATTERN MUST BE UNIQUE, and this refuses rather than guessing. The first
# draft of this script replaced the FIRST occurrence of "event.sport,\n  );",
# which in `page.tsx` is the `awayIsTheComplement` call (#6238) and not the
# hero at all: the battery silently deleted a load-bearing argument from
# unrelated code, then reported the wiring mutants as SURVIVORS because the
# hero it was supposed to break was untouched. Two false survivors and one real
# regression, from one `replace(..., 1)`. `npm run typecheck` is what caught
# it. A mutation tool that can damage code outside the mutant it names is worse
# than no mutation tool.
mutate() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path).read()
hits = src.count(old)
if hits == 0:
    print("MUTANT-NOT-APPLIED: pattern absent"); sys.exit(9)
if hits > 1:
    print(f"MUTANT-NOT-APPLIED: pattern is AMBIGUOUS ({hits} occurrences)"); sys.exit(8)
open(path, "w").write(src.replace(old, new, 1))
PY
}

SURVIVORS=0
run_mutant() {
  local name="$1" file="$2" old="$3" new="$4"
  restore
  if ! mutate "$file" "$old" "$new"; then
    echo "  !! $name — PATTERN ABSENT (the battery is stale, not the code)"
    SURVIVORS=$((SURVIVORS + 1)); return
  fi
  if (cd "$ROOT/frontend" && npx jest --testPathPatterns="$SUITE" >/dev/null 2>&1); then
    echo "  SURVIVED  $name"
    SURVIVORS=$((SURVIVORS + 1))
  else
    echo "  killed    $name"
  fi
}

echo "baseline (unmutated) must be GREEN:"
restore
if (cd "$ROOT/frontend" && npx jest --testPathPatterns="$SUITE" >/dev/null 2>&1); then
  echo "  ok"
else
  echo "  BASELINE IS RED — fix that before reading anything below"; exit 2
fi

echo "mutants:"

# 1. The gate itself. Without it every club in the SCOPE table breaks.
run_mutant "gate removed (namesAPerson -> always true)" "$LIB" \
  "if (namesAPerson(sportKey)) {" "if (true) {"

# 2. The gate inverted — fires on clubs and never on people.
run_mutant "gate inverted" "$LIB" \
  "if (namesAPerson(sportKey)) {" "if (!namesAPerson(sportKey)) {"

# 3. The rule deleted outright.
run_mutant "particle rule deleted" "$LIB" \
  "    if (start < words.length - 1) return words.slice(start).join(\" \");" \
  "    if (false) return words.slice(start).join(\" \");"

# 4. The walk stops after ONE particle: "Van de Zandschulp" -> "de Zandschulp".
run_mutant "walk is a single step, not a loop" "$LIB" \
  "  while (
    start > 0 &&
    NAME_PARTICLES.has(alphanumeric(words[start - 1]).toLowerCase())
  ) {
    start -= 1;
  }" \
  "  if (
    start > 0 &&
    NAME_PARTICLES.has(alphanumeric(words[start - 1]).toLowerCase())
  ) {
    start -= 1;
  }"

# 5. Two-token names ("le Roux", "van Zijl") stop being reachable.
run_mutant "walk floor off by one (start > 0 -> start > 1)" "$LIB" \
  "    start > 0 &&" "    start > 1 &&"

# 6. Case-sensitive matching: "Van de Zandschulp", "De la Fuente" break.
run_mutant "case-sensitive particle match" "$LIB" \
  "NAME_PARTICLES.has(alphanumeric(words[start - 1]).toLowerCase())" \
  "NAME_PARTICLES.has(alphanumeric(words[start - 1]))"

# 7. The pair helper stops threading the sport.
run_mutant "teamShortNames drops the sport (home)" "$LIB" \
  "  const homeShort = teamShortName(homeFull, null, sportKey);" \
  "  const homeShort = teamShortName(homeFull, null);"

# 8. The one mutant a pure-function battery cannot see: the hero stops passing
#    its sport. This is the mistake the ship actually made once.
#
#    ANCHORED ON THE AWAY-SIDE LINE, which is what makes the pattern unique to
#    the hero — "event.sport,\n  );" on its own also matches the
#    `awayIsTheComplement` call 26 lines above. See `mutate`.
run_mutant "hero stops passing event.sport" "$PAGE" \
  "    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );" \
  "    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
  );"

# 9. The hero passes a field the payload does not carry.
run_mutant "hero passes event.sport_key (the real first draft)" "$PAGE" \
  "    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );" \
  "    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport_key,
  );"

restore

# The tree MUST be byte-identical to how this script found it. Without this the
# script can hand the next gate a tree it quietly edited — which is exactly how
# the first draft leaked a deleted argument into `page.tsx` and how its own
# backups then froze the damage in place on the following run.
echo
DIRTY=0
for pair in "$LIB:$LIB_BAK" "$PAGE:$PAGE_BAK"; do
  live="${pair%%:*}"; bak="${pair##*:}"
  if ! cmp -s "$live" "$bak"; then
    echo "NOT RESTORED: $live differs from the copy taken at startup"
    DIRTY=1
  fi
done
if [ "$DIRTY" -ne 0 ]; then
  echo "refusing to report a verdict on a tree this script left modified"
  exit 3
fi
echo "tree restored byte-for-byte (both files)"

if [ "$SURVIVORS" -eq 0 ]; then
  echo "ALL MUTANTS KILLED"
else
  echo "$SURVIVORS MUTANT(S) SURVIVED"
fi
exit "$SURVIVORS"
