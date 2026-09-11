#!/usr/bin/env bash
# The attribution decision of `compose-band.sh`, lifted out so it can be TESTED.
#
# #5409. The band's exit 1 needs THREE answers, not two:
#
#   1. did it fail?                  — pytest's exit
#   2. does it fail ALONE?           — the isolation re-run (flake vs real)
#   3. does it fail WITHOUT the sha? — the baseline re-run (the sha's vs master's)
#
# Question 3 is the one that was missing, and its absence is not a rare corner:
# an already-red-on-master failure is maximally DETERMINISTIC, so it reproduces
# in isolation every time and question 2 actively confirms the wrong cause. On
# 2026-09-11 that told lane1/254 "this is the sha's ... DO NOT PUSH IT" about
# `65d7f749`, a sha with a GREEN token that the desk merged minutes later.
#
# Lifted into its own file rather than left as a `case` inside a 350-line script
# that needs a repo, a PR and the GitHub API before it reaches the decision:
# a verdict nobody can drive from a test is a verdict nobody can check.
#
# Pure: reads its arguments, echoes one token, sets no state, touches no repo.

# compose_band_verdict <iso_exit> <base_exit> <n_base_nodes> <n_skipped>
#
#   iso_exit      exit of the isolation re-run (the failing nodes, alone)
#   base_exit     exit of the baseline re-run (same nodes, on the base, no sha).
#                 Pass `none` when no baseline was taken.
#   n_base_nodes  how many failing nodes existed on the base to re-run
#   n_skipped     how many were skipped because their file is only in the sha
#
# Echoes exactly one of:
#
#   FLAKE               every failure passes alone. Not a clearance.
#   RED_NO_BASELINE     reproduces alone, and EVERY failing node is in a file the
#                       sha adds — so no baseline exists and the failure can only
#                       be the sha's.
#   PRE_EXISTING        reproduces alone AND on the base. Master is already
#                       carrying it. Says nothing against the sha; clears nothing.
#   RED                 reproduces alone and is ABSENT from the base. The sha's.
#   INCONCLUSIVE        a run exited something that is a story about the harness
#                       (gotcha #124), so the question was never answered.
#
# The default is INCONCLUSIVE, never RED. An unattributed failure is not a
# verdict about a sha, and the expensive direction of this tool's error is
# withholding a good ship, not delaying a bad one by one re-run.
compose_band_verdict() {
  local iso_exit="${1-}" base_exit="${2-}" n_base_nodes="${3-0}" n_skipped="${4-0}"

  case "$iso_exit" in
    0) echo FLAKE; return 0 ;;
    1) : ;;
    *) echo INCONCLUSIVE; return 0 ;;
  esac

  # No node survived the "does this file exist on the base?" filter. Handing a
  # sha-added path to pytest at master is the exit-4 trap (#124) — "no tests ran"
  # would arrive looking like a clean baseline, which would print RED for the
  # right answer by the wrong route. Only reachable when nothing was skippable
  # for another reason, so `n_skipped` is required to be the whole set.
  if [ "${n_base_nodes:-0}" -eq 0 ]; then
    if [ "${n_skipped:-0}" -gt 0 ]; then echo RED_NO_BASELINE; else echo INCONCLUSIVE; fi
    return 0
  fi

  case "$base_exit" in
    1) echo PRE_EXISTING ;;
    0) echo RED ;;
    *) echo INCONCLUSIVE ;;
  esac
}
