#!/bin/bash
# offer-file-set.sh [sha] [--repo-dir DIR] — derive a merge offer's FILE LIST, tier call and
# overlap check from ONE source, so the list and the check can never disagree.
#
# WHY THIS EXISTS (integrator/296, Thu 2026-09-10, on lane1/234's #4809 offer):
# the offer listed THREE files; PR #4848 changed FOUR. The missing one was
# `backend/app/routes/events.py` — 92 insertions, the largest hunk set in the branch and the
# file the ship actually lands in. Cause: the list was read off the TIP COMMIT's own diff
# (`git diff <sha>^ <sha>`), which on a two-commit branch is not the branch. `routes/events.py`
# was modified in the FIRST commit, so the tip diff could not see it.
#
# The offer's no-overlap CONCLUSION was still correct — master had not touched that file — but
# it was correct by luck of the population, not by coverage: the check ran over a list that was
# missing the one file most likely to collide, on the busiest shared route file in the backend.
# In the same batch, live/136's 5d6c5911 (#4844) modified `routes/events.py` too. They were
# ~7,000 lines apart and merged clean. Nothing about that was visible to the offer.
#
# THE SHARPER HAZARD, measured on lane1/237 the same afternoon: that branch's tip commit is a
# single test file, while the branch is 167 insertions in `routes/events.py` plus a contracts
# JSON. Sized off the tip commit it reads as TESTS-ONLY — which standing notice 10's tests-only
# clause would have self-certified as Tier A, routing a route-file change AROUND the cert bus.
# A wrong file list is not just a mis-sized review; it can be a mis-TIER.
#
# RULE: `<merge-base>..<sha>`, never `<sha>^..<sha>`. This script only knows that one rule.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
SHA_IN="HEAD"
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    *) SHA_IN="$1"; shift ;;
  esac
done

G() { git -C "$REPO_DIR" "$@"; }

SHA="$(G rev-parse "$SHA_IN")"
G fetch origin master -q
BASE="$(G merge-base "$SHA" origin/master)"

echo "sha:        $SHA"
echo "merge-base: $BASE"

# --- Notice 31: ancestry before offer. Already merged ⇒ there is no offer to make. ---
if G merge-base --is-ancestor "$SHA" origin/master; then
  echo
  echo "STOP (standing notice 31): this sha is ALREADY AN ANCESTOR of origin/master."
  echo "Do not offer it and do not re-run a gate table. Record 'already on master' and move on."
  exit 3
fi

NCOMMITS="$(G rev-list --count "$BASE".."$SHA")"
echo "commits:    $NCOMMITS"
if [ "$NCOMMITS" -gt 1 ]; then
  echo "            ^ MULTI-COMMIT BRANCH: the tip commit's own diff is NOT this branch."
fi
echo

echo "=== FILE SET (merge-base..sha — the set that LANDS) ==="
G diff --numstat "$BASE" "$SHA" | while read -r add del path; do
  st="modified"
  G cat-file -e "origin/master:$path" 2>/dev/null || st="added"
  printf '  %-8s +%-5s -%-5s %s\n' "$st" "$add" "$del" "$path"
done
echo

# --- Tier call (standing notice 10), derived from the SAME list. ---
FILES="$(G diff --name-only "$BASE" "$SHA")"
APPCODE="$(printf '%s\n' "$FILES" | grep -vE '^(backend/tests/|frontend/e2e/|tools/)' || true)"
echo "=== TIER (standing notice 10), from the same list ==="
if [ -z "$APPCODE" ]; then
  echo "  tests-only (backend/tests|frontend/e2e|tools) ⇒ Tier A for GRADING."
  if printf '%s\n' "$FILES" | grep -q '^backend/tests/'; then
    echo "  NOTE: backend/tests/** forces a Heroku release — never releases ALONE;"
    echo "        it rides the next server-side batch or waits in the tray."
  fi
else
  echo "  NOT tests-only. App code present ⇒ bus-graded, not self-certifying:"
  printf '    %s\n' $APPCODE
fi
echo

echo "=== OVERLAP: has master touched these files since the merge-base? ==="
OVL=0
for f in $FILES; do
  C="$(G log --oneline "$BASE"..origin/master -- "$f")"
  if [ -n "$C" ]; then
    OVL=1
    echo "  OVERLAP  $f"
    printf '%s\n' "$C" | sed 's/^/             /'
  else
    echo "  clean    $f"
  fi
done
[ "$OVL" -eq 0 ] && echo "  => no path overlap with master."
echo

# --- The hazard the offer above could not see: a SIBLING still in flight in the same file. ---
echo "=== SIBLINGS: other OPEN PRs touching any of these files ==="
SELF="$(G rev-parse --abbrev-ref HEAD)"
FOUND=0
for pr in $(gh pr list --repo alexander-bain/bainluck --state open --limit 60 --json number --jq '.[].number'); do
  HEADREF="$(gh api "repos/alexander-bain/bainluck/pulls/$pr" --jq '.head.ref' 2>/dev/null || echo '')"
  [ "$HEADREF" = "$SELF" ] && continue
  PRF="$(gh api "repos/alexander-bain/bainluck/pulls/$pr/files" --jq '.[].filename' 2>/dev/null || echo '')"
  for f in $FILES; do
    if printf '%s\n' "$PRF" | grep -qx "$f"; then
      echo "  PR #$pr ($HEADREF) also touches $f"
      FOUND=1
    fi
  done
done
[ "$FOUND" -eq 0 ] && echo "  => no open PR shares a file with this branch."
echo
echo "Paste the FILE SET block into the offer verbatim. Do not restate it by hand."
