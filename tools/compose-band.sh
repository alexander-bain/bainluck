#!/usr/bin/env bash
#
# compose-band.sh — does <sha> still pass when composed onto CURRENT master?
#
#   usage:  tools/compose-band.sh <sha> [<repo-path>]
#
#   env overrides (all optional):
#     NET=<ERE>      the semantic net (source c). Default: DERIVED from the sha's
#                    own diff. Pass one only to narrow a band you have read.
#     CI_BASE=<sha>  the master the sha's exact-sha CI ran against. Default:
#                    derived from the runs API (a LOWER BOUND — see below).
#     WT=<path>      the disposable compose worktree. Default: /tmp keyed to sha.
#
# ── THE PROBLEM IT SOLVES ────────────────────────────────────────────────────
#
# A `pull_request` workflow does NOT re-run when its base moves. So a sha with a
# green exact-sha CI row is making a claim about the master it RAN on, hours ago,
# and everything master has absorbed since is untested against it. Two shas can
# each be green and compose RED — authority/129 measured exactly that, where
# #4954's CODE broke #5139's new TEST FILE with ZERO file overlap between them.
#
# Zero file overlap is the point. A file-overlap screen cannot see this class,
# which is why the band below has a semantic source (c) as well.
#
# ── WHY THE DEFAULT NET IS DERIVED AND NOT A CONSTANT ────────────────────────
#
# This script's ancestor hardcoded source (c) to `authority|statpal|failover|
# admin_provider` — the vocabulary of the ONE ship it was first written for.
# Run unchanged on any other sha it does not fail. It silently bands the WRONG
# ship's tests, passes, and writes a marker: a false clearance, which is worse
# than no band at all. It nearly shipped that way, because the "empty net" guard
# could not fire either — the stale net still matched ~40 test files that had
# nothing to do with the sha under test.
#
# A generic tool inherits its first caller's vocabulary unless you take it away
# from it. So the net is derived from the sha's own diff on every run, and the
# derivation is PRINTED, so the operator can see what was actually banded rather
# than trusting that something sensible happened.
#
# MEASURED, so the default is not just an argument (2026-09-11, 1360 test files):
#
#   sha       derived net                          files   hand-written net  files
#   3f421a9e  admin_providers|authority_by_sport      36   authority|stat…    354
#   cb1ecd80  events|standings_shape|teams           765   standings_shape|…  200
#
# Breadth swings wildly with how generic the module names are, and the derived
# net is sometimes far NARROWER than the net a human would write. That is only
# safe if it still catches the class the tool exists for — so: the known real
# case, where #4954's code broke #5139's brand-new test file with ZERO file
# overlap, IS matched by the 36-file derived net. A test that exercises a changed
# module almost always names that module, which is why stems work at all.
#
# The remaining cost is runtime, not soundness: a 765-file band does not finish
# inside an 18-minute push window. The script warns when the band gets that big.
# Narrow it with NET= only after reading what you are dropping — a too-wide band
# costs minutes, a too-narrow one costs a false clearance.
#
# ── EXIT CODES: this script does NOT pass pytest's through unchanged ─────────
#
#   0  COMPOSES CLEAN / SCREEN CLEAN — marker written; gate 28b will pass.
#   1  RED — a real composition failure: reproduced in isolation AND absent from
#      the base. Do not push.
#   3  PROBABLE FLAKE (passes alone) or PRE-EXISTING (fails on the base too).
#      Neither is a clearance: no marker is written and gate 28b still stops.
#   2  HARNESS / INCONCLUSIVE — the run did not answer the question. Re-run.
#
# Only 0 and 1 are RESULTS (gotcha #124). pytest's own 5 (nothing collected) and
# 4 (bad invocation) both look "not failed" to a careless eye, so they are mapped
# to 2 rather than allowed to read as success.
#
# **1 requires THREE answers, not two (#5409).** Isolation separates flake from
# real; it cannot separate the sha's from master's, because an already-red-on-
# master failure is maximally deterministic and so reproduces in isolation every
# time — the re-run CONFIRMS the wrong cause. A failure is only the sha's once it
# has also been shown ABSENT from the base. A baseline that cannot be taken
# yields 2, never 1: an unattributed failure is not a verdict about a sha.
#
# ── SHELL NOTES ──────────────────────────────────────────────────────────────
#
# `#!/usr/bin/env bash` and explicit `/usr/bin/grep`: a lane's interactive `grep`
# is a function wrapping ugrep, whose `-qv` is the bit-flip of its `-q` (#5037).
# A `#!` script does not source that snapshot, but the explicit paths keep a line
# copied OUT of this file safe too.
#
# This Mac's /bin/bash is 3.2.57 — there is NO `mapfile`. Under bash 3.2 a
# `mapfile` line runs as an unknown command, leaves the array EMPTY, and the band
# silently shrinks to the two global files while still printing a count and
# exiting 0. Hence: temp file + `while read`, everywhere.
#
set -uo pipefail

G=/usr/bin/grep
REPO=alexander-bain/bainluck

SHA_IN="${1:-}"
if [ -z "$SHA_IN" ] || [ "$SHA_IN" = "-h" ] || [ "$SHA_IN" = "--help" ]; then
  # Print the header block by SENTINEL, not by line number. An earlier draft used
  # `sed -n '2,70p'`; adding a paragraph above line 70 silently truncated the help
  # mid-section, ending on a heading with no body. A slice keyed to a line number
  # is wrong the first time anyone edits the thing it slices.
  sed -n '2,${/^[^#]/q;p;}' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//'
  exit 2
fi

# `${BASH_SOURCE[0]}` is UNBOUND — and fatal under `set -u` — when this script is
# piped in rather than executed, which is how notice 18's FIRED clause invokes
# its sibling (`git show origin/master:tools/... | bash -s -- <sha>`).
REPO_PATH="${2:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

if ! git -C "$REPO_PATH" rev-parse --git-dir >/dev/null 2>&1; then
  echo "RESULT: HARNESS -- '$REPO_PATH' is not a git repository. Pass the repo path as argument 2."
  exit 2
fi


echo "### compose-band -- <sha> vs CURRENT master (self-deriving band)"
echo "### $(TZ=America/Los_Angeles date '+%a %-m/%-d %-I:%M%p PT') / $(date -u +%H:%MZ)"

# `compose_band_verdict` lives in its own file so a test can drive every branch
# of it (#5409). Sourced from the repo we were handed rather than from
# `${BASH_SOURCE[0]}`, which is UNBOUND when this script is piped in — the same
# trap `REPO_PATH` above exists for. If it is absent (an older checkout, or a
# pipe from a ref that predates it), the fallback is defined INLINE rather than
# leaving the name undefined: a missing attribution must read as INCONCLUSIVE,
# never as RED.
# shellcheck source=tools/compose_band_verdict.sh
if [ -r "$REPO_PATH/tools/compose_band_verdict.sh" ]; then
  . "$REPO_PATH/tools/compose_band_verdict.sh"
else
  echo "### NOTE: tools/compose_band_verdict.sh not found under $REPO_PATH — every exit-1"
  echo "###       band will be reported INCONCLUSIVE rather than attributed."
  compose_band_verdict() { [ "${1-}" = "0" ] && echo FLAKE || echo INCONCLUSIVE; }
fi

if ! git -C "$REPO_PATH" fetch origin master -q 2>/tmp/bl_cb_fetch_err.txt; then
  # A stale origin/master fails OPEN in the dangerous direction: the marker is
  # keyed to master, so an old master means an old marker still validates.
  echo "RESULT: HARNESS -- 'git fetch origin master' failed, so origin/master is STALE."
  echo "        Every answer below would be about a master that has since moved. Fix the fetch."
  echo "        stderr: $(tr '\n' ' ' < /tmp/bl_cb_fetch_err.txt | cut -c1-200)"
  exit 2
fi

# `rev-parse` alone is NOT an existence test. Given a full 40-character hex
# string it echoes it straight back, object or no object — so a typo'd or
# never-fetched sha reads as "resolved" and the run continues into a band about
# nothing. Only `--verify <rev>^{commit}` actually dereferences. (Same family as
# notice 28's `?head_sha=` trap, where an abbreviated sha returns a valid EMPTY
# result at exit 0.)
SHA=$(git -C "$REPO_PATH" rev-parse --verify -q "${SHA_IN}^{commit}" 2>/dev/null)
if [ -z "$SHA" ]; then
  echo "RESULT: HARNESS -- '$SHA_IN' does not resolve to a commit in $REPO_PATH."
  echo "        A full 40-char hex string rev-parses to itself even when absent, so this"
  echo "        is checked with 'rev-parse --verify <rev>^{commit}'. Fetch it, or fix the sha."
  exit 2
fi
MASTER=$(git -C "$REPO_PATH" rev-parse origin/master)

echo "### sha    $SHA"
echo "### master $MASTER"

# ---- SHALLOW CLONE (#5409). Not fatal, and deliberately not: the band's own
# question — "do these tests pass on master+sha?" — does not need history. But an
# unknown share of the tests it runs DO: any test that shells out to
# `merge-base --is-ancestor`, `rev-list`, `log` or a graft-crossing walk gets a
# wrong answer here and a right one in CI, which checks out `fetch-depth: 0`.
# `~/bainluck/.git` has been shallow since 2026-09-11 07:34 and every lane
# worktree shares it, so this is the fleet's normal state, not an oddity.
# Printed once, up front, so it is in the operator's scrollback BEFORE a verdict
# rather than being reconstructed after one.
IS_SHALLOW=$(git -C "$REPO_PATH" rev-parse --is-shallow-repository 2>/dev/null || echo unknown)
if [ "$IS_SHALLOW" = "true" ]; then
  echo "### ⚠️  SHALLOW CLONE -- '$REPO_PATH' has a graft boundary, so any test that walks history"
  echo "###     (merge-base --is-ancestor, rev-list, log) can fail here and pass in CI, which uses"
  echo "###     fetch-depth: 0. A failure of that shape is the CHECKOUT's, not the sha's. The"
  echo "###     baseline re-run below tells them apart; read its verdict, not the band's exit."
fi

# Already merged? Then there is nothing to compose, and banding it is the
# four-times-repeated waste that notice 31 exists to prevent.
if git -C "$REPO_PATH" merge-base --is-ancestor "$SHA" "$MASTER" 2>/dev/null; then
  echo "RESULT: ALREADY ON MASTER -- $SHA is an ancestor of $MASTER."
  echo "        There is nothing to compose. No band, no offer, no re-gate (notice 31)."
  exit 0
fi

# ---- CI_BASE: derived, and it is a LOWER BOUND, not "the master CI ran on".
# The runs API exposes `.pull_requests[0].base.sha`. GitHub tests
# `refs/pull/N/merge`, recomputed whenever either side moves, and the run object
# never records which master that merge actually used. The API value is the base
# recorded when the PR REF last moved, so it is <= the master CI saw. That is the
# conservative direction and the only one that keeps the cheap screen sound: if
# backend/ is unchanged from the LOWER BOUND to current master, then backend/ did
# not change anywhere in the interval. It can over-report movement; it cannot
# miss it.
CI_BASE=${CI_BASE:-$(gh api "repos/$REPO/actions/runs?head_sha=$SHA&per_page=100" \
  --jq '[.workflow_runs[]|select(.name=="CI")][0].pull_requests[0].base.sha' 2>/dev/null)}
case "${CI_BASE:-}" in
  ""|null)
    echo "RESULT: HARNESS -- could not derive the CI base from the runs API."
    echo "        Pass CI_BASE=<sha> explicitly; do NOT guess one."
    exit 2 ;;
esac
if ! git -C "$REPO_PATH" rev-parse --verify -q "$CI_BASE^{commit}" >/dev/null; then
  echo "RESULT: HARNESS -- CI base $CI_BASE is not a commit in this checkout (fetch it, or pass CI_BASE=)."
  exit 2
fi
echo "### CI base $CI_BASE  ($(git -C "$REPO_PATH" rev-list --count "$CI_BASE".."$MASTER") commits behind current master)"

# ---- the two markers. NAMES ARE A CONTRACT: offer_gates.sh gate 28b reads them.
MARK="/tmp/bl_compose_clean_${SHA:0:8}_${MASTER:0:8}"
# A SECOND marker keyed to the backend/ subtree this band actually tested, rather
# than to the master sha that happened to carry it. The sha-keyed marker
# self-expires on ANY master move — including a frontend-only merge, which cannot
# change a backend pytest outcome. Master turns over every 20-40 minutes, so the
# sha-keyed marker very probably dies INSIDE an 18-minute push window with no
# time to re-run a ~15-minute band: a false STOP.
#
# This is not a loosening. The band runs backend pytest only, and a backend/ move
# still expires it — the only move that can change the answer.
MARKT="/tmp/bl_compose_clean_${SHA:0:8}_bt_$(git -C "$REPO_PATH" rev-parse "$MASTER^{tree}:backend" | cut -c1-12)"

# ---- cheap screen: if backend/ has not moved since the CI base, CI still holds.
if [ "$(git -C "$REPO_PATH" rev-parse "$CI_BASE^{tree}:backend")" = "$(git -C "$REPO_PATH" rev-parse "$MASTER^{tree}:backend")" ]; then
  echo "RESULT: SCREEN CLEAN -- backend/ tree identical to the sha's CI base; the exact-sha CI still answers. No band needed."
  echo "screen-clean (backend/ unmoved since CI base $CI_BASE) at $(date -u +%H:%MZ)" > "$MARK"
  cp "$MARK" "$MARKT"
  echo "MARKER: $MARK"
  echo "MARKER: $MARKT"
  exit 0
fi
echo "### backend/ HAS moved since the CI base -- band required."
echo

# ---- derive the semantic net (source c) from the sha's OWN diff, unless given.
T="/tmp/bl_cb_band_${SHA:0:8}"
NET_ORIGIN=supplied
if [ -z "${NET:-}" ]; then
  NET_ORIGIN=derived
  # Module stems of the backend app files this sha touches. `routes/teams.py` ->
  # `teams`. Deliberately broad: a test that exercises the changed module usually
  # names it, and over-inclusion costs minutes while under-inclusion costs a
  # false clearance.
  git -C "$REPO_PATH" diff --name-only "$MASTER"..."$SHA" -- 'backend/app/*' \
    | $G -E '\.py$' | sed 's|.*/||; s|\.py$||' | $G -vE '^(__init__|main)$' | sort -u > "$T.stems"
  NSTEM=$(wc -l < "$T.stems" | tr -d ' ')
  if [ "$NSTEM" -eq 0 ]; then
    echo "RESULT: HARNESS -- the sha changes no backend/app/*.py file, so no semantic net can be derived."
    echo "        A backend composition band is not the right question for this sha."
    echo "        If you know the net, pass NET=<ERE> explicitly."
    exit 2
  fi
  NET=$(tr '\n' '|' < "$T.stems" | sed 's/|$//')
fi
echo "### semantic net ($NET_ORIGIN): $NET"

# ---- compose
WT=${WT:-/tmp/bl-compose-band-${SHA:0:8}}
git -C "$REPO_PATH" worktree remove --force "$WT" >/dev/null 2>&1
if ! git -C "$REPO_PATH" worktree add --detach "$WT" "$MASTER" >/dev/null 2>&1; then
  echo "RESULT: HARNESS -- could not create the compose worktree at $WT"
  exit 2
fi
if ! git -C "$WT" merge --no-edit "$SHA" > "$T.merge" 2>&1; then
  echo "RESULT: CONFLICT -- the sha no longer merges onto master. Its token is DEAD (notice 28 corollary):"
  echo "        rebase, restage, re-grade. Do NOT resolve-and-merge -- that changes the sha."
  tail -10 "$T.merge"
  exit 1
fi
echo "### composed HEAD $(git -C "$WT" rev-parse --short HEAD)  (merge clean; auto-merged files are the RISK, not the safe case)"
echo

# ---- derive the band (four sources, counted separately so a dead source shows)
git -C "$REPO_PATH" diff --name-only "$MASTER"..."$SHA"  -- 'backend/tests/*.py' > "$T.a"
git -C "$REPO_PATH" diff --name-only "$CI_BASE".."$MASTER" -- 'backend/tests/*.py' > "$T.b"
( cd "$WT" && $G -rlEi "$NET" backend/tests --include='test_*.py' ) > "$T.c" 2>/dev/null
printf '%s\n' backend/tests/test_startup.py backend/tests/test_tasks_wiring.py > "$T.d"
cat "$T.a" "$T.b" "$T.c" "$T.d" | $G -v '^$' | sort -u > "$T.all"

NA=$(wc -l < "$T.a" | tr -d ' '); NB=$(wc -l < "$T.b" | tr -d ' ')
NC=$(wc -l < "$T.c" | tr -d ' '); ND=$(wc -l < "$T.d" | tr -d ' ')
NALL=$(wc -l < "$T.all" | tr -d ' ')
echo "### band: $NA from the sha + $NB master gained + $NC semantic + $ND global  =>  $NALL unique files"

# A band that cannot finish inside the push window is a band nobody runs. ~225
# files took 16m42s on this hardware, so warn once past roughly that size rather
# than letting the operator discover it at minute eighteen.
if [ "$NALL" -gt 300 ]; then
  echo "### NOTE: $NALL files is a LARGE band (~225 files ran 16m42s here), so budget"
  echo "###       well over an 18-minute push window, or narrow the net with NET=<ERE>"
  echo "###       after reading what that drops. Do not start this at :30 and hope."
fi

# A zero on the semantic source means the derivation broke or the net is wrong —
# not that the risk vanished. (a) may legitimately be zero: a sha can change app
# code without touching a test file, and that is precisely the sha whose risk
# lives in source (c).
if [ "$NC" -eq 0 ]; then
  echo "RESULT: HARNESS -- the semantic net matched ZERO test files ($NET_ORIGIN net: $NET)."
  echo "        That is a broken derivation or a wrong net, not a clean tree."
  exit 2
fi

REL=(); MISSING=0
while IFS= read -r f; do
  [ -f "$WT/$f" ] || { echo "MISSING: $f"; MISSING=1; }
  REL+=( "${f#backend/}" )
done < "$T.all"
if [ "$MISSING" -ne 0 ]; then
  echo "RESULT: HARNESS -- a derived file is absent from the composed tree (pytest exit-4 trap); band not run."
  exit 2
fi

cd "$WT/backend" || { echo "RESULT: HARNESS -- cannot cd to composed backend"; exit 2; }
python3 -m pytest "${REL[@]}" -q --no-header > "$T.out" 2>&1
EXIT=$?
echo
echo "PYTEST EXIT CODE: $EXIT"
tail -25 "$T.out"
echo

case "$EXIT" in
  0)
    echo "RESULT: COMPOSES CLEAN -- the sha is green against master $MASTER."
    # The pass-count anchor used to be `^[0-9]* passed` — but pytest's summary is
    # `====== 5975 passed, 104 skipped ... ======`, which starts with `=`, never a
    # digit. It matched NOTHING on every run its author ever made, and the marker
    # recorded `exit 0, , at 18:53Z`: an empty field between commas that reads as a
    # formatting quirk rather than as "the evidence was never captured".
    PASSLINE=$(sed -n 's/.*[= ]\([0-9][0-9]* passed[^=]*\).*/\1/p' "$T.out" | tail -1)
    echo "$NALL-file band, exit 0, ${PASSLINE:-COUNT-NOT-CAPTURED}, at $(date -u +%H:%MZ)" > "$MARK"
    cp "$MARK" "$MARKT"
    echo "MARKER: $MARK"
    echo "MARKER: $MARKT  (survives a frontend-only master move; dies if backend/ moves)"
    ;;
  1)
    # ---- exit 1 is a RESULT, but WHICH result needs one more question ---------
    # Measured 2026-09-11: a band came back "5 failed", all in
    # tests/test_lane_launchers.py, and it did not reproduce — composed run 1 gave
    # 5 failed, plain master over the SAME file list gave 0, composed run 2 gave 0.
    # The signature was the tell: three failures asserted on output that was EMPTY
    # and one timed out waiting 45s for a subprocess line. That is starvation, not
    # a logic break, on a Mac hosting ten lane runners.
    #
    # Why automate it: the band can only be run INSIDE the push window, so a flake
    # lands exactly when there is no time to triage it, and the old text told the
    # operator "DO NOT PUSH". A false RED costs a ship a day.
    #
    # This is NOT retry-until-green. A genuine regression fails deterministically
    # and fails here too. What isolation cannot rule out is ORDER POLLUTION
    # (passes alone, fails in combination, every time) — so a cleared isolation
    # run is reported as PROBABLE FLAKE with the command that settles it, and
    # never as clean.
    $G -E '^FAILED ' "$T.out" | sed 's/^FAILED //; s/ - .*$//' > "$T.failed"
    NFAIL=$(wc -l < "$T.failed" | tr -d ' ')
    if [ "$NFAIL" -eq 0 ]; then
      # No `break` here: this is a `case`, not a loop. This branch owns its whole
      # verdict and must not fall into the isolation triage below, which would
      # print "reproduces in isolation" about a run that never happened.
      echo "RESULT: RED -- pytest exited 1 but no 'FAILED ' line was parsed."
      echo "        Read $T.out by hand; do not push."
    else
      echo "### exit 1 with $NFAIL failing node(s). Re-running them ALONE to tell a"
      echo "### regression (fails again) from a starvation flake (passes alone)."
      sed 's/^/###   /' "$T.failed"
      ISO=(); while IFS= read -r n; do ISO+=( "$n" ); done < "$T.failed"
      # Same invocation shape as the band — no extra flags. An isolation run that
      # differs in more than its FILE LIST answers a different question.
      python3 -m pytest "${ISO[@]}" -q --no-header > "$T.iso" 2>&1
      ISOEXIT=$?
      echo "### isolation re-run exit: $ISOEXIT"
      tail -6 "$T.iso"
      echo
      case "$ISOEXIT" in
        0) echo "RESULT: PROBABLE FLAKE, NOT RED -- every one of the $NFAIL failure(s) passes in isolation."
           echo "        This does NOT write a marker and does NOT clear gate 28b: a test that passes"
           echo "        alone can still fail in combination EVERY time (order pollution), and only a"
           echo "        second full band separates that from a flake. Settle it by re-running:"
           echo "            tools/compose-band.sh $SHA"
           echo "        A second clean full band => flake, and that run writes the marker itself."
           echo "        The same subset failing twice => order pollution, a REAL composition defect:"
           echo "        do not push, and report it."
           EXIT=3 ;;
        1) # ---- THE THIRD QUESTION (#5409). Isolation separates FLAKE from REAL.
           # It does NOT separate "the sha's" from "already red on master", and
           # that class is maximally deterministic — it reproduces every time, so
           # the isolation re-run actively CONFIRMS the wrong cause and the old
           # text stated that inference as fact.
           #
           # Measured by lane1/254, 2026-09-11: `65d7f749` (CERT-2653, GREEN
           # token, every merge-gate notice passed) banded 1 failed / 26,902
           # passed and got "this is the sha's ... DO NOT PUSH IT". The sha was
           # fine; the desk merged it and master CI is green. The failing node
           # shells out to `git merge-base --is-ancestor`, and `~/bainluck/.git`
           # is a SHALLOW clone, so the ancestry walk hits the graft boundary and
           # answers "not an ancestor" for commits GitHub confirms are ancestors.
           # It fails identically on master WITHOUT the sha, and CI checks out
           # `fetch-depth: 0` so it passes there. 32 minutes, and a good ship
           # nearly withheld.
           #
           # So: re-run the same nodes on the compose BASE alone. Fails there too
           # => PRE-EXISTING, never "DO NOT PUSH IT". This is general — it
           # catches every already-red-on-master case, not just the shallow one.
           BASEWT=${BASEWT:-/tmp/bl-compose-band-base-${MASTER:0:8}}
           BASE_NODES=(); BASE_SKIPPED=0
           for n in "${ISO[@]}"; do
             # A node in a file the SHA ADDS cannot exist at master, and handing
             # it to pytest there is the exit-4 trap (#124): "no tests ran"
             # arrives as a story about the harness, not as a baseline.
             case "$n" in *"::"*) f="backend/${n%%::*}" ;; *) f="backend/$n" ;; esac
             if git -C "$REPO_PATH" cat-file -e "$MASTER:$f" 2>/dev/null; then
               BASE_NODES+=( "$n" )
             else
               BASE_SKIPPED=$((BASE_SKIPPED+1))
             fi
           done
           if [ "${#BASE_NODES[@]}" -eq 0 ]; then
             case "$(compose_band_verdict 1 none 0 "$BASE_SKIPPED")" in
               RED_NO_BASELINE)
                 echo "RESULT: RED -- the failure(s) reproduce in isolation AND every failing node lives in"
                 echo "        a test file this sha ADDS ($BASE_SKIPPED of $NFAIL), so there is no baseline"
                 echo "        to compare against and the failure can only be the sha's."
                 echo "        The sha does NOT compose with current master. DO NOT PUSH IT." ;;
               *)
                 echo "RESULT: INCONCLUSIVE -- no failing node could be re-run on the base and none was"
                 echo "        skipped for being sha-only, so the node list is not what it should be."
                 echo "        The band's exit 1 stands UNATTRIBUTED. Do not push on this run."
                 EXIT=2 ;;
             esac
           else
             echo "### re-running the failing node(s) on the BASE ($MASTER) WITHOUT the sha, to tell"
             echo "### a regression this sha caused from one master is already carrying (#5409)."
             [ "$BASE_SKIPPED" -gt 0 ] && echo "###   ($BASE_SKIPPED node(s) skipped: their file does not exist at master)"
             git -C "$REPO_PATH" worktree remove --force "$BASEWT" >/dev/null 2>&1
             if ! git -C "$REPO_PATH" worktree add --detach "$BASEWT" "$MASTER" >/dev/null 2>&1; then
               echo "RESULT: INCONCLUSIVE -- could not create the baseline worktree at $BASEWT, so"
               echo "        'the sha's or master's?' was never asked. The band's exit 1 stands"
               echo "        UNATTRIBUTED. Do not push on this run; re-run or check by hand."
               EXIT=2
             else
               # Same invocation shape as the band and the isolation run. A
               # baseline that differs in more than its TREE answers a different
               # question.
               ( cd "$BASEWT/backend" && python3 -m pytest "${BASE_NODES[@]}" -q --no-header ) > "$T.base" 2>&1
               BASEEXIT=$?
               echo "### baseline re-run exit: $BASEEXIT"
               tail -6 "$T.base"
               echo
               case "$(compose_band_verdict 1 "$BASEEXIT" "${#BASE_NODES[@]}" "$BASE_SKIPPED")" in
                 PRE_EXISTING)
                    echo "RESULT: PRE-EXISTING, NOT RED -- the same failure(s) reproduce on master $MASTER"
                    echo "        WITHOUT this sha. Master is already carrying them. This band says NOTHING"
                    echo "        against the sha, and it does NOT clear it either: no marker is written,"
                    echo "        because a pre-existing failure hides whatever the sha might also have done"
                    echo "        to the same node. Narrow the band past these node(s) and re-run, or"
                    echo "        establish by hand that they are unrelated. Report the master failure."
                    if [ "$IS_SHALLOW" = "true" ]; then
                      echo "        ALSO: this checkout is a SHALLOW clone (see the warning above), which is"
                      echo "        the known cause of ancestry-dependent tests failing here and passing in CI."
                    fi
                    EXIT=3 ;;
                 RED)
                    echo "RESULT: RED -- the failure(s) reproduce in isolation AND pass on master $MASTER"
                    echo "        without this sha. It is the sha's, not the machine's and not master's."
                    echo "        The sha does NOT compose with current master. DO NOT PUSH IT." ;;
                 *) echo "RESULT: INCONCLUSIVE -- the baseline re-run exited $BASEEXIT, which is a story about"
                    echo "        the harness and not a verdict (#124), so 'the sha's or master's?' is"
                    echo "        unanswered. The band's exit 1 stands UNATTRIBUTED. Do not push on this run."
                    EXIT=2 ;;
               esac
             fi
           fi ;;
        *) echo "RESULT: HARNESS -- the isolation re-run exited $ISOEXIT, which is a story about the"
           echo "        harness and not a verdict (#124). The band's own exit 1 still stands unexplained."
           EXIT=2 ;;
      esac
    fi
    ;;
  *)
    echo "RESULT: HARNESS -- exit $EXIT is a story about the harness, not a verdict (#124). Re-run."
    EXIT=2
    ;;
esac
exit "$EXIT"
