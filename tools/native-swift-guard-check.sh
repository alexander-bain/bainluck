#!/usr/bin/env bash
# native-swift-guard-check.sh — which backend tests will your iOS-only diff redden?
#
# WHY THIS EXISTS (integrator/149+150, 2026-09-04): an iOS-only diff CAN redden
# master. Several backend tests read `ios/**/*.swift` as SOURCE TEXT and assert on
# literals in it. native/006 added a `trace:` closure to a call site and two
# backend guards fired on the merged tree.
#
# The obvious check does NOT work:
#
#     grep -rln 'ios/Bain Luck' backend/tests/ backend/scripts/   # MISSES THEM
#
# It misses the two guards that actually broke master, because they build the
# path from segments — `REPO / "ios" / "Bain Luck" / ... / "FeedViewModel.swift"`
# — so the substring `ios/Bain Luck` never appears. What IS present in every
# reference form, segment-built or slash-built, is the quoted BASENAME. So we
# match on the basename of each Swift file the diff touches.
#
# Verified complete on 2026-09-04: no backend test or script globs the Swift tree
# dynamically and none composes a filename at runtime, so every coupling is
# discoverable by basename. Re-check with:
#     grep -rnE 'rglob\(|glob\(' backend/tests backend/scripts | grep -iE 'swift|ios'
#
# Usage:
#   tools/native-swift-guard-check.sh              # vs origin/master, runs the guards
#   tools/native-swift-guard-check.sh <base-ref>   # vs another base
#   tools/native-swift-guard-check.sh --list       # name the guards, don't run them
#
# Exit: 0 = no coupled guard, or coupled guards ran green. 1 = a coupled guard failed.

# No `set -u`: macOS ships bash 3.2, where an empty array expands unbound under it.
# No `mapfile`/`readarray` below for the same reason — bash 4 only.
set -o pipefail

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO" || exit 1

LIST_ONLY=0
BASE="origin/master"
for arg in "$@"; do
    case "$arg" in
        --list) LIST_ONLY=1 ;;
        *) BASE="$arg" ;;
    esac
done

# Swift files this branch touches, as basenames. A deleted file can still redden a
# guard that reads it, so --diff-filter is deliberately NOT narrowed to added/modified.
# Committed work, plus uncommitted and untracked — you want this answer BEFORE you
# commit, and `$BASE...HEAD` alone would hand you a false all-clear on a dirty tree.
SWIFT=()
while IFS= read -r line; do
    [ -n "$line" ] && SWIFT[${#SWIFT[@]}]="$line"
done < <(
    {
        git diff --name-only "$BASE...HEAD" -- '*.swift'
        git diff --name-only HEAD -- '*.swift'
        git ls-files --others --exclude-standard -- '*.swift'
    } | sed 's|.*/||' | sort -u
)

if [ ${#SWIFT[@]} -eq 0 ]; then
    echo "No Swift files changed vs $BASE — no Swift-text guard can be coupled."
    exit 0
fi

echo "Swift files changed vs $BASE (${#SWIFT[@]}):"
printf '  %s\n' "${SWIFT[@]}"
echo

# A guard is coupled if it contains the basename literally. Prose-only mentions in a
# docstring match too: that is deliberate. A false positive costs one test run; a
# false negative costs a red master.
RAW=/tmp/native-swift-guard-hits.$$.txt
: > "$RAW"
for base in "${SWIFT[@]}"; do
    grep -rl --fixed-strings "$base" backend/tests backend/scripts 2>/dev/null \
        | grep -E '\.py$' >> "$RAW"
done

GUARDS=()
while IFS= read -r line; do
    [ -n "$line" ] && GUARDS[${#GUARDS[@]}]="$line"
done < <(sort -u "$RAW")
rm -f "$RAW"

if [ ${#GUARDS[@]} -eq 0 ]; then
    echo "No backend test or script reads any of those Swift files. Nothing to run."
    exit 0
fi

echo "Backend files that read those Swift sources (${#GUARDS[@]}):"
printf '  %s\n' "${GUARDS[@]}"
echo

TESTS=()
for g in "${GUARDS[@]}"; do
    case "$g" in
        backend/tests/*) TESTS[${#TESTS[@]}]="${g#backend/}" ;;
        *) echo "NOTE: $g is not a pytest file — read it yourself, it is not run below." ;;
    esac
done

if [ ${#TESTS[@]} -eq 0 ]; then
    echo "No pytest files among them."
    exit 0
fi

if [ "$LIST_ONLY" -eq 1 ]; then
    echo "Run:  cd backend && python3 -m pytest ${TESTS[*]} -q"
    exit 0
fi

echo "Running: cd backend && python3 -m pytest ${TESTS[*]} -q"
echo
cd "$REPO/backend" || exit 1
OUT=/tmp/native-swift-guard-check.$$.txt
python3 -m pytest "${TESTS[@]}" -q > "$OUT" 2>&1
CODE=$?
echo "EXIT CODE: $CODE"
tail -15 "$OUT"
echo
echo "(full output: $OUT)"

# Gotcha #124: 1 is a result; anything else is a story about the harness.
if [ "$CODE" -eq 0 ]; then
    echo "GREEN — your iOS diff does not move a line these guards pin."
elif [ "$CODE" -eq 1 ]; then
    echo "RED — a backend guard pins a line your Swift diff moved. Fix before handover."
else
    echo "EXIT $CODE is not a test result — the gate did not run. Read $OUT."
fi
exit "$CODE"
