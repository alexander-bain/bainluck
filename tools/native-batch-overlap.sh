#!/usr/bin/env bash
# native-batch-overlap.sh — which files do the branches in a handover batch share?
#
# WHY THIS EXISTS (integrator/149+150, 2026-09-04): native/126 handed over five
# branches described as touching disjoint files. Five files were touched by two or
# three branches each; `EventDetailView.swift` took three separate diffs. Git
# automerged all five without a conflict, so nothing complained — but no one had
# ever COMPILED the combination. Each branch's green test run was against master,
# not against its siblings. `merge-tree` clean is not "the batch builds".
#
# A batch with overlap is not wrong, it just has to be built as a combination
# before it is trusted. This names the overlap so the handover note can say so.
#
# Usage:
#   tools/native-batch-overlap.sh <branch-or-sha> <branch-or-sha> [...]
#   tools/native-batch-overlap.sh --base <ref> <branch> <branch> [...]
#
# Exit: 0 = no overlap (independent green runs are meaningful).
#       1 = overlap found (the integrator must build the combination).

set -o pipefail

REPO="$(git rev-parse --show-toplevel)"
cd "$REPO" || exit 1

BASE="origin/master"
BRANCHES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --base) BASE="$2"; shift 2 ;;
        *) BRANCHES[${#BRANCHES[@]}]="$1"; shift ;;
    esac
done

if [ ${#BRANCHES[@]} -lt 2 ]; then
    echo "usage: tools/native-batch-overlap.sh [--base <ref>] <branch> <branch> [...]" >&2
    exit 2
fi

TALLY=/tmp/native-batch-overlap.$$.txt
: > "$TALLY"

for b in "${BRANCHES[@]}"; do
    if ! git rev-parse --verify --quiet "$b" >/dev/null; then
        echo "unknown ref: $b" >&2
        rm -f "$TALLY"
        exit 2
    fi
    n=$(git diff --name-only "$BASE...$b" | wc -l | tr -d ' ')
    echo "$b: $n file(s) vs $BASE"
    # Tag every changed path with the branch that changed it.
    git diff --name-only "$BASE...$b" | while IFS= read -r f; do
        printf '%s\t%s\n' "$f" "$b"
    done >> "$TALLY"
done
echo

# A path claimed by more than one branch is an overlap.
SHARED=$(cut -f1 "$TALLY" | sort | uniq -d)

if [ -z "$SHARED" ]; then
    echo "NO OVERLAP — no file is touched by two branches."
    echo "Independent per-branch test runs cover this batch."
    rm -f "$TALLY"
    exit 0
fi

echo "OVERLAP — these files are touched by more than one branch:"
echo
echo "$SHARED" | while IFS= read -r f; do
    owners=$(grep -F "$(printf '%s\t' "$f")" "$TALLY" | cut -f2 | sort -u | tr '\n' ' ')
    count=$(echo "$owners" | wc -w | tr -d ' ')
    echo "  $f"
    echo "      $count branches: $owners"
done
echo
echo "Say this in the handover note. A clean \`git merge-tree\` does NOT mean the"
echo "batch builds — no branch was ever tested against its siblings. The integrator"
echo "must build and test the MERGED tree, not trust the per-branch green runs."
rm -f "$TALLY"
exit 1
