#!/usr/bin/env bash
# UX-P123 — the branch-surface gate: program/ux-106 and program/ux-107.
#
# ## What this check is for, and why it is not a rubber stamp
#
# UX-P122's discovery runner ended with a BRANCH COVERAGE table that named
# `program/ux-100`, `program/ux-106` and `program/ux-107` as UNCOVERED. Two of
# those three ship **no production surface at all**: measured per-increment,
# ux-106 adds 12 files and ux-107 adds 21, and every one of them is under
# `tools/`. So there is genuinely nothing for a production proof to observe.
#
# The wrong response is to leave them UNCOVERED (the table then cries wolf
# forever, and a table that always has red rows stops being read). The equally
# wrong response is to write two scripts that print PASS — a check that cannot
# fail is worse than no check, because it converts an absence of evidence into
# a green row.
#
# So this gate asserts the **antecedent** instead of the conclusion. The claim
# "ux-107 needs no production proof" is only true while "ux-107 touches no
# production code" is true. Today that second fact lives in exactly one place:
# prose, in a handoff file. This lane's own doctrine from UX-P119 is that **a
# fact recorded in prose is not a fact a check can read** — that sentence was
# written after every READY file for five cycles carried #2084's evidence as
# "blocked on the drain" when the blocking branch had already merged.
#
# This check executes that fact. The moment either branch acquires a file under
# `backend/`, `frontend/`, `ios/`, `contracts/` or `alembic/`, it goes RED and
# says the branch now owes a named production proof. That is a real failure mode
# and it is one commit away at all times: both branches are live, unmerged, and
# this lane appends to `program/ux-107` most cycles.
#
# ## The trap this check was written around
#
# `git diff origin/master...program/ux-107` reports **backend and frontend
# files** — `admin_repairs.py`, `backfill_defect_routes.py`,
# `calibration/page.tsx`, `calibrationPopulation.ts`. Every one of them belongs
# to `program/ux-105`, three branches down an unmerged stack. Diffing a stacked
# branch against master measures the whole stack, so the naive form of this
# check would have failed on ux-107 for work ux-107 never did, and the obvious
# "fix" — an allowlist of those four paths — would have permanently blinded it
# to real edits of the same files.
#
# The base is therefore the branch's **predecessor in the stack**, derived, not
# hardcoded: `program/ux-<N-1>` when it exists and is an ancestor, else the
# merge-base with origin/master. Which one was used is printed, because a base
# that silently changes changes the meaning of every verdict under it.
#
# Verdicts: PASS(0) FAIL(1) UNKNOWN(3). Per gotcha #54's amendment, 1 is a
# result and anything else is a story about the harness.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../lib.sh"

# The branches this gate speaks for. This is BOTH the coverage declaration the
# runner reads and the list this script actually iterates — deliberately one
# variable, so a check cannot claim a branch it does not examine, or examine one
# it does not claim. (The runner reads this line only; the prose above mentions
# ux-100 and ux-105 and must not be mistaken for coverage of them.)
COVERS="program/ux-106 program/ux-107"

# Any path under these roots is production surface: it can reach a user, a
# dyno, or the database. Everything else (tools/, docs/, .claude/) cannot.
PROD_ROOTS="backend frontend ios contracts alembic"

hdr "BRANCH SURFACE GATE (ux-106, ux-107)"
say "  Asserts the antecedent behind 'this branch owes no production proof':"
say "  that its own increment touches nothing that can reach production."
say ""

worst=0

for br in $COVERS; do
  say "── $br ─────────────────────────────────"

  if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "$br^{commit}" >/dev/null; then
    verdict "$br" "UNKNOWN — no such local ref"
    [ "$worst" -lt "$RC_UNKNOWN" ] && worst=$RC_UNKNOWN
    say ""
    continue
  fi

  head_sha="$(git -C "$REPO_ROOT" rev-parse --short "$br")"

  # ── base derivation, printed ────────────────────────────────────────────
  num="${br##*-}"
  pred="program/ux-$(( num - 1 ))"
  base=""
  base_kind=""
  if git -C "$REPO_ROOT" rev-parse --verify --quiet "$pred^{commit}" >/dev/null &&
     git -C "$REPO_ROOT" merge-base --is-ancestor "$pred" "$br" 2>/dev/null; then
    base="$(git -C "$REPO_ROOT" rev-parse "$pred")"
    base_kind="predecessor $pred"
  else
    base="$(git -C "$REPO_ROOT" merge-base "$br" origin/master 2>/dev/null)"
    base_kind="merge-base with origin/master (no usable predecessor $pred)"
  fi

  if [ -z "$base" ]; then
    verdict "$br" "UNKNOWN — could not derive a base"
    [ "$worst" -lt "$RC_UNKNOWN" ] && worst=$RC_UNKNOWN
    say ""
    continue
  fi

  say "   head:  $head_sha"
  say "   base:  $(git -C "$REPO_ROOT" rev-parse --short "$base")  [$base_kind]"

  if git -C "$REPO_ROOT" merge-base --is-ancestor "$br" origin/master 2>/dev/null; then
    say "   state: merged into origin/master"
  else
    say "   state: unmerged"
  fi

  # ── the increment ───────────────────────────────────────────────────────
  files="$(git -C "$REPO_ROOT" diff --name-only "$base" "$br")"
  total=0
  [ -n "$files" ] && total="$(printf '%s\n' "$files" | grep -c .)"

  if [ "$total" -eq 0 ]; then
    # An empty increment is not a pass. It means the base derivation collapsed
    # onto the head, and this check would then be green for every branch
    # forever — precisely the shape of failure it exists to prevent.
    verdict "$br" "UNKNOWN — increment is EMPTY; base derivation is degenerate, not a clean branch"
    [ "$worst" -lt "$RC_UNKNOWN" ] && worst=$RC_UNKNOWN
    say ""
    continue
  fi

  prod=""
  for root in $PROD_ROOTS; do
    hit="$(printf '%s\n' "$files" | grep "^$root/" || true)"
    [ -n "$hit" ] && prod="$prod$hit"$'\n'
  done
  prod="$(printf '%s' "$prod" | grep -c . || true)"
  [ -z "$prod" ] && prod=0

  say "   increment: $total file(s) changed vs base"
  say "   roots touched:"
  printf '%s\n' "$files" | awk -F/ 'NF>1{print "     "$1"/"} NF==1{print "     "$1}' | sort -u

  if [ "$prod" -eq 0 ]; then
    verdict "$br" "PASS — $total file(s), ZERO under {${PROD_ROOTS// /,}}; no production surface, so no production proof is owed"
  else
    say ""
    say "   production files in this branch's OWN increment:"
    for root in $PROD_ROOTS; do
      printf '%s\n' "$files" | grep "^$root/" | sed 's/^/     /' || true
    done
    say ""
    verdict "$br" "FAIL — $prod production file(s) in its own increment. This branch now ships user-reachable code and NOTHING in this harness proves it. Write a named proof check for it, or move the change to a branch that has one."
    [ "$worst" -lt "$RC_FAIL" ] && worst=$RC_FAIL
  fi
  say ""
done

hdr "VERDICT"
case "$worst" in
  0) say "  Both branches remain tools-only. The coverage table's claim that they" ;;
  *) say "  A branch's surface changed. The coverage table can no longer claim they" ;;
esac
say "  need no production proof is CHECKED, not assumed."
exit "$worst"
