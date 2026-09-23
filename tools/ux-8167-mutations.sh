#!/usr/bin/env bash
# #8167 mutation run.
#
# Guards against the two lies of ux/1455's run, both of which print as a clean
# number: a mutant that never landed (scores a false KILL when the revert wipes
# the feature, or a false SURVIVOR when `s///` hits a duplicate line), and a
# module that stopped loading (whole-suite failure reads as a well-guarded
# change). So each mutant must (a) show up in `git diff` and (b) leave the suite
# importable — and the FAILURE SHAPE is printed, not just its presence.
#
# Run from the worktree root on a COMMITTED tree.
set -u
cd "$(dirname "$0")/.."

LIB=frontend/lib/futuresLadder.ts
QG=frontend/components/QuantityGroup.tsx
PAGE='frontend/app/futures/[id]/page.tsx'
PATTERN='8167|thresholdLadderTitle7398'

if [ -n "$(git status --porcelain -- $LIB $QG "$PAGE")" ]; then
  echo "REFUSING: tree is dirty. Commit first — an uncommitted implementation is"
  echo "what made ux/1455's revert delete the feature and score four false kills."
  exit 2
fi

# name | file | perl expression
MUTANTS=(
"single-group gate|$LIB|s/groups\.length < 2/groups.length < 1/"
"distinctness gate|$LIB|s/!== subjects\.length/< 2/"
"strip stops one word short|$LIB|s/p\.length\)\);/p.length - 1));/"
"char cap|$LIB|s/MAX_SUBJECT_CHARS = 24/MAX_SUBJECT_CHARS = 240/"
"word cap|$LIB|s/MAX_SUBJECT_WORDS = 4/MAX_SUBJECT_WORDS = 40/"
"case-insensitive word compare|$LIB|s/a\.toLowerCase\(\) === b\.toLowerCase\(\)/a === b/"
"echo refusal on the subject|$LIB|s/printableHeading\(subjects\[i\] \?\? \"\", pageTitle\)/subjects[i]/"
"per-card rule runs FIRST|$LIB|s/thresholdLadderTitle\(g\.stem, groupTitle, pageTitle, g\.outcomeNames\) \?\?\n?\s*printableHeading\(subjects\[i\] \?\? \"\", pageTitle\)/printableHeading(subjects[i] ?? \"\", pageTitle) ?? thresholdLadderTitle(g.stem, groupTitle, pageTitle, g.outcomeNames)/"
"zero draws no pill|$QG|s/heat\.known && rung\.probability! > 0/heat.known/"
"floor value|$QG|s/Math\.max\(2, Math\.round/Math.max(0, Math.round/"
)

killed=0; survived=0; invalid=0
for entry in "${MUTANTS[@]}"; do
  IFS='|' read -r name file expr <<< "$entry"
  perl -0pi -e "$expr" "$file"

  # (a) DID IT LAND? A pattern that matched nothing is not a survivor.
  if git diff --quiet -- "$file"; then
    echo "INVALID  $name — pattern matched nothing, mutant never applied"
    invalid=$((invalid+1))
    git checkout -- "$file"
    continue
  fi

  out=$(cd frontend && npx jest --testPathPatterns="$PATTERN" 2>&1)
  line=$(echo "$out" | /usr/bin/grep -E "^Tests:" | tail -1)
  suites=$(echo "$out" | /usr/bin/grep -E "^Test Suites:" | tail -1)

  # (b) DID THE MODULE STILL LOAD? Whole-suite death is a broken instrument.
  if echo "$out" | /usr/bin/grep -q "Cannot find module\|SyntaxError\|Your test suite must contain"; then
    echo "INVALID  $name — module stopped loading: $suites"
    invalid=$((invalid+1))
  elif echo "$line" | /usr/bin/grep -q "failed"; then
    echo "KILLED   $name — $line"
    killed=$((killed+1))
  else
    echo "SURVIVED $name — $line"
    survived=$((survived+1))
  fi
  git checkout -- "$file"
done

echo
echo "killed=$killed survived=$survived invalid=$invalid"
git status --porcelain -- $LIB $QG "$PAGE" | /usr/bin/grep . && echo "WARNING: tree left dirty" || echo "tree restored clean"
