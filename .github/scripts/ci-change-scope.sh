#!/usr/bin/env bash
# #5007 (THRU-H) — which CI jobs actually protect this candidate?
#
# Usage:  ci-change-scope.sh <BASE_SHA> <HEAD_SHA>
# Prints: "full", "frontend" or "native" on stdout (plus reasoning on stderr).
#
#   full      run everything (backend shards, shard-completeness, search-recall)
#   frontend  the candidate cannot reach anything those jobs test
#
# WHY: the four backend shards plus search-recall are ~11.1m and ~8.3m of a
# 12.1m run. A candidate confined to `frontend/` that no backend test can even
# read is protected by none of them, and pays for all of them.
#
# ── THIS SCRIPT FAILS TOWARD "full". ────────────────────────────────────────
# Every uncertain branch prints "full". Skipping a job that would have caught a
# defect ships the defect; running a job that proves nothing costs minutes.
# Those are not symmetric, so the tie goes to running everything.
#
# ── IT CLASSIFIES THE COMPLETE CANDIDATE, NOT THE TIP COMMIT. ───────────────
# The caller passes the full base..head range. Reading only the last commit
# would let a shared change ride in behind a frontend-only tip — the fail-open
# this issue's fixtures forbid. `release-required` (ci.yml) takes the same two
# arguments from the same event fields for the same reason.
#
# It lives in a file, not inline in ci.yml, so a guard test can execute it. An
# inline heredoc in a workflow is unreachable by every gate we own, which is how
# a decision on the test path would rot unnoticed.

set -uo pipefail

BASE="${1:-}"
HEAD_SHA="${2:-}"

# The manifest lives beside the workflow so the guard test and this script read
# ONE list. A second copy is a second thing to rot.
MANIFEST="${CI_CROSS_TIER_MANIFEST:-$(dirname "$0")/../ci-cross-tier-paths.txt}"

say () { echo "$*" >&2; }
emit () { echo "$1"; say "DECISION: $1 ($2)"; exit 0; }

# #10708 INACTIVE preparation: current ci.yml normalizes native to full.
# Native classification is not accepted reduced coverage. Transitive readers,
# database reach and residue-scanner range still require activation review.
path_bucket () {
  case "$1" in
    frontend/*) echo frontend ;;
    ios/*) echo native ;;
    *) return 1 ;;
  esac
}

case "$BASE" in
  ""|0000000000000000000000000000000000000000)
    emit full "no usable base commit — cannot prove the candidate is frontend-only" ;;
esac
[ -n "$HEAD_SHA" ] || emit full "no head commit given — cannot prove the candidate is frontend-only"

[ -r "$MANIFEST" ] || emit full "cross-tier manifest $MANIFEST unreadable — cannot prove safety"

git cat-file -e "${BASE}^{commit}" 2>/dev/null \
  || emit full "base commit ${BASE} not present — cannot prove the candidate is frontend-only"
git cat-file -e "${HEAD_SHA}^{commit}" 2>/dev/null \
  || emit full "head commit ${HEAD_SHA} not present — cannot prove the candidate is frontend-only"

# `--no-renames` is load-bearing, exactly as in heroku-release-required.sh:
# rename detection prints ONE line for a move (the destination), so moving
# `backend/app/served.py` to `frontend/app/served.py` would report a single
# frontend path and hide the vanishing backend file. `--no-renames` reports both
# halves, so the backend side is seen and forces "full".
CHANGED="$(git diff --name-only --no-renames "$BASE" "$HEAD_SHA")" \
  || emit full "git diff failed — cannot prove the candidate is frontend-only"

[ -n "$CHANGED" ] || emit full "empty diff — cannot prove the candidate is frontend-only"

# Read the manifest into a newline-delimited blob, dropping comments and blanks.
CROSS_TIER="$(sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$MANIFEST" | grep -v '^$')" \
  || emit full "manifest parsing failed or empty — cannot prove safety"
[ -n "$CROSS_TIER" ] || emit full "empty cross-tier manifest — cannot prove safety"
say "cross-tier manifest: $(printf '%s\n' "$CROSS_TIER" | wc -l | tr -d ' ') paths"

BUCKET=""
say "changed files:"
while IFS= read -r f; do
  [ -z "$f" ] && continue
  say "  $f"
  CURRENT="$(path_bucket "$f")" || emit full "$f is outside frontend/ and ios/"
  [ -z "$BUCKET" ] || [ "$CURRENT" = "$BUCKET" ] || emit full "mixed frontend/native candidate"
  BUCKET="$CURRENT"
  [ "$CURRENT" = frontend ] || continue
  # File entries match a WHOLE LINE; a substring test would let
  # `frontend/lib/marketShape.ts.bak` satisfy the entry
  # `frontend/lib/marketShape.ts` and skip the shard that reads the real file.
  # Entries ending in `/` are directory prefixes and match anything beneath.
  while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    case "$entry" in
      */) case "$f" in "$entry"*) emit full "$f is under $entry, read by a backend test" ;; esac ;;
      *)  [ "$f" = "$entry" ] && emit full "$f is read by a backend test (cross-tier manifest)" ;;
    esac
  done <<< "$CROSS_TIER"
done <<< "$CHANGED"

case "$BUCKET" in
  frontend) emit frontend "every changed path is under frontend/ and none is listed cross-tier" ;;
  native) emit native "pure ios/ candidate; INACTIVE preparation, workflow retains full selection" ;;
  *) emit full "unparseable candidate bucket" ;;
esac
