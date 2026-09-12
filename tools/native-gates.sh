#!/usr/bin/env bash
# native-gates.sh — the native lane's standing Swift gate set, in one command.
#
# ═══ WHY THIS EXISTS (#5074, native/113) ═══
#
# THE macOS APP TARGET DID NOT COMPILE FOR FIVE DAYS AND NOTHING SAID SO.
# Between 2026-09-05 and 2026-09-10 two single-line changes landed that build fine
# for iOS and cannot build for macOS at all:
#
#     OddsChartView.swift:1027      Color(.systemBackground)          UIKit-only
#     TournamentHubView.swift:47    .navigationBarTitleDisplayMode    iOS-only
#
# Neither author did anything unusual — both were single-site departures from an
# idiom the target already followed everywhere else (6 of 7, 25 of 26). The
# breakage is invisible by construction: CI compiles NO Swift, and an iOS build
# never compiles `#if os(macOS)` code, so a lane can gate green all day on work it
# has not built. native/112 could not even gate its OWN ship until it first
# repaired the target.
#
# #5074 rung 2 is a macOS CI runner (D100 — Alex's spend call). Until that exists
# this script is the whole net, and the ~90 seconds it costs is the price of not
# shipping a third one.
#
# ═══ WHAT IT RUNS ═══
#
#   1. macOS build          — the target that goes dark. THE POINT OF THE SCRIPT.
#   2. recompile proof      — that the Swift files in your diff were actually
#                             compiled by that build, not served from cache.
#   3. BainLuckTests        — on a simulator resolved at runtime, printing the
#                             `Executed N tests, with 0 failures` line that
#                             standing notice 10's iOS clause requires verbatim
#                             in the PR body of any Tier A change touching ios/**.
#
# It does NOT run the frontend gates or pytest — those are unchanged, they live in
# CLAUDE.md, and folding them in here would make a 90-second check a 6-minute one
# that lanes then skip. This is the Swift half, which is the half nothing else covers.
#
# ═══ TWO TRAPS THIS SCRIPT EXISTS TO NOT REPEAT ═══
#
# `-destination 'name=iPhone 16'` EXITS 70, NOT 1, when that simulator is not
# installed (gotcha #124: only `1` is a result; everything else is a story about
# the harness). Simulator names churn between Xcode releases and between laptops,
# so this resolves an available iPhone by UDID at runtime instead of hardcoding a
# name that will be wrong on someone else's machine.
#
# `OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'` IS NOT OPTIONAL
# (gotcha #50). Without it the build dies on `#Preview` macro expansion in
# BainLuckWidget.swift with three "external macro implementation type
# 'PreviewsMacros.Common' could not be found" errors — which looks like a widget
# bug and is not one. Do NOT respond to it by nuking the SPM cache.
#
# ═══ WHICH TREE THIS GATES (#5480, native/126) ═══
#
# IT GATES THE TREE YOU ARE STANDING IN, NOT THE TREE THE SCRIPT LIVES IN.
#
# Until 2026-09-12 `PROJECT_DIR` was derived from `${BASH_SOURCE[0]}`, so
# `bash ~/bainluck/tools/native-gates.sh` run from a lane worktree built and
# tested ~/bainluck — the shared master checkout — and printed a well-formed
# `Executed N tests, with 0 failures` line FOR MASTER. Standing notice 10's iOS
# clause makes that one line the entire iOS gate (CI compiles no Swift), so this
# is the one gate in the fleet with no independent check, and it could green a
# tree that did not contain the change. native/123 banked `Executed 2027` — the
# PREVIOUS ship's count — against a branch whose real count was 2034.
#
# So the tree is resolved from the CWD's git toplevel, and when that differs from
# the script's own toplevel the divergence is printed loudly rather than guessed
# at. `--project-root <path>` overrides both. The SUMMARY block names the gated
# tree, sha and branch, so a number pasted into a PR body is self-describing.
#
# ═══ "I COULD NOT TELL" IS NEVER SPELLED LIKE "NOTHING TO REPORT" ═══
#
# The recompile proof used `git diff --name-only "$BASE"...HEAD 2>/dev/null`.
# Three-dot needs a merge base; under a shallow clone (#5428) `git merge-base`
# exits non-zero, the redirect ate the error, the file list came back empty and
# the script printed "no changed Swift files — nothing to prove". A vacuous pass
# reported in the same words as the legitimate no-op. Both conditions now fail
# the gate by name and say which one happened.
#
# ═══ A PASS LINE COMES ONLY FROM A RUN THAT FINISHED (#5591, native/129) ═══
#
# The companion to #5480 above. That one was the right count from the WRONG TREE;
# this one was the right tree, right sha, and a count from a run that DID NOT
# HAPPEN. `xcodebuild` prints "Executed N tests, with M failures" once per test
# CLASS as well as once for the suite — 173 of them in a healthy run of this
# suite, one of which is the total. The line was picked with `tail -1`, which is
# the total only if the run reached the end. native/128, gating `124a1c82`, hit
# the #5229 silent hang; the suite was killed at 513 of ~2056 and the script
# printed `Executed 5 tests, with 0 failures` under "paste this line into the PR
# body", with "it is the count for <sha>" beneath it. Notice 10's iOS clause is
# satisfied by exactly that string, and nothing downstream can tell 5 from 2083.
#
# Now: the number is read from the "Test Suite 'All tests'" summary BY NAME, and
# it is offered as a notice-10 line only when the run exited 0 AND left
# "** TEST SUCCEEDED **" behind. A finished-but-failing run prints its real total
# labelled as a failure; a killed run prints its class count labelled PARTIAL and
# do-not-paste; `$LINE` is empty in both, so the SUMMARY cannot pair FAIL with a
# green-looking number either. `--explain` states the whole rule without building.
#
# ═══ USAGE ═══
#
#   tools/native-gates.sh              # both gates, diff measured vs origin/master
#   tools/native-gates.sh --build-only # just the macOS build + recompile proof
#   tools/native-gates.sh --base <ref> # measure the diff against another ref
#   tools/native-gates.sh --explain    # resolve tree/sha/diff and STOP. No xcodebuild.
#   tools/native-gates.sh --selftest   # prove the #5591 pass-line rule. No Xcode, no tree.
#   tools/native-gates.sh --project-root <path>   # gate a tree explicitly
#
# Exit 0 only when every gate it ran passed. Logs are left in $TMPDIR for reading;
# their paths are printed. Gotcha #54: a gate is never piped, its exit code is
# captured and reported as a VALUE.

set -u

SCHEME="Bain Luck"
SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'
LOGDIR="${TMPDIR:-/tmp}/native-gates-$$"
BASE="origin/master"
BUILD_ONLY=""
EXPLAIN=""
SELFTEST=""
PROJECT_ROOT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=1 ;;
    --explain) EXPLAIN=1 ;;
    --selftest) SELFTEST=1 ;;
    --base) BASE="${2:?--base needs a ref}"; shift ;;
    --project-root) PROJECT_ROOT="${2:?--project-root needs a path}"; shift ;;
    # Derived, not a magic number: everything above `set -u` is the header. The
    # literal 85 was already clipping the last lines of USAGE before #5591 added
    # a section above it, which would have cut the usage list off entirely.
    -h|--help) sed -n '1,/^set -u/p' "${BASH_SOURCE[0]}" | sed '$d'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

say () { printf '\n=== %s\n' "$*"; }

# ── notice-10 pass-line selection (#5591) ────────────────────────────────────
# PURE: reads a log path + an exit code, writes four globals and prints nothing,
# so `--selftest` can drive the SAME code path the real run uses. A copy of this
# logic inside a test would prove nothing about this script.
#
#   LINE           the notice-10 line, EMPTY unless it is genuinely one
#   VERDICT        PASS_LINE | SUITE_FAILED | PARTIAL | NEVER_RAN
#   ALL_TESTS_LINE the "Test Suite 'All tests'" total, if the run reached it
#   LAST_EXEC_LINE the last "Executed N tests" line of any kind (may be a class)
notice10_select () {
  _n10_log="$1"; _n10_exit="$2"
  # BY NAME, not by position: the total is the count under "Test Suite 'All
  # tests'", which only a run that reached the end ever prints.
  ALL_TESTS_LINE=$(/usr/bin/grep -A1 "Test Suite 'All tests'" "$_n10_log" 2>/dev/null \
                   | /usr/bin/grep -E "Executed [0-9]+ tests, with .* failures" \
                   | tail -1 | sed 's/^[[:space:]]*//')
  LAST_EXEC_LINE=$(/usr/bin/grep -E "^[[:space:]]+Executed [0-9]+ tests, with .* failures" "$_n10_log" 2>/dev/null \
                   | tail -1 | sed 's/^[[:space:]]*//')
  if /usr/bin/grep -q '^\*\* TEST SUCCEEDED \*\*' "$_n10_log" 2>/dev/null; then
    _n10_ok=1
  else
    _n10_ok=0
  fi

  LINE=""
  if [ "$_n10_exit" -eq 0 ] && [ "$_n10_ok" -eq 1 ] && [ -n "$ALL_TESTS_LINE" ]; then
    LINE="$ALL_TESTS_LINE"; VERDICT=PASS_LINE
  elif [ -n "$ALL_TESTS_LINE" ]; then
    VERDICT=SUITE_FAILED
  elif [ -n "$LAST_EXEC_LINE" ]; then
    VERDICT=PARTIAL
  else
    VERDICT=NEVER_RAN
  fi
}

# ── --selftest: prove the rule above, on log shapes, with no Xcode ───────────
# A gate that lied is being repaired; the repair owes proof that it no longer
# does. These fixtures go through notice10_select() itself, not a copy of it.
if [ -n "$SELFTEST" ]; then
  say "--selftest — #5591 pass-line selection (no xcodebuild, no tree needed)"
  ST_DIR="$(mktemp -d)"; ST_FAIL=0
  TAB="$(printf '\t')"

  st_check () { # name expected_verdict expect_line_substr(or -) actual_extra_note
    if [ "$VERDICT" = "$2" ] && { [ "$3" = "-" ] && [ -z "$LINE" ] || { [ "$3" != "-" ] && [ "${LINE#*$3}" != "$LINE" ]; }; }; then
      echo "  ok    $1 -> $VERDICT${LINE:+, offered \"$LINE\"}"
    else
      echo "  FAIL  $1 -> got VERDICT=$VERDICT LINE=\"$LINE\"; wanted $2 / ${3}"
      ST_FAIL=1
    fi
  }

  # A. a healthy, completed run. The one shape that may be pasted.
  { echo "Test Suite 'DiscoverViewModelLoadTests' passed at 2026-09-12 05:00:00.000."
    echo "${TAB} Executed 5 tests, with 0 failures (0 unexpected) in 1.737 (1.739) seconds"
    echo "Test Suite 'All tests' passed at 2026-09-12 05:00:30.000."
    echo "${TAB} Executed 2083 tests, with 0 failures (0 unexpected) in 27.902 (29.156) seconds"
    echo "** TEST SUCCEEDED **"; } > "$ST_DIR/pass.txt"
  notice10_select "$ST_DIR/pass.txt" 0
  st_check "completed run, exit 0" PASS_LINE "Executed 2083 tests, with 0 failures"

  # B. THE #5591 BUG, reproduced: killed mid-suite (#5229). No 'All tests'
  #    summary is ever written, so the last count is a CLASS count. The old code
  #    offered exactly this under "paste this line into the PR body".
  { echo "Test Suite 'DiscoverViewModelLoadTests' passed at 2026-09-12 03:20:00.000."
    echo "${TAB} Executed 5 tests, with 0 failures (0 unexpected) in 1.737 (1.739) seconds"; } > "$ST_DIR/killed.txt"
  notice10_select "$ST_DIR/killed.txt" 137
  st_check "killed at exit 137 (#5229)" PARTIAL -
  # ANTI-VACUITY: the fixture must actually contain the bait. If LAST_EXEC_LINE
  # were empty this case would pass for the wrong reason and prove nothing.
  if [ -n "$LAST_EXEC_LINE" ]; then
    echo "  ok    ...and the bait is present: old tail -1 would have offered \"$LAST_EXEC_LINE\""
  else
    echo "  FAIL  fixture has no 'Executed' line at all — the test is vacuous"; ST_FAIL=1
  fi

  # B2. the same kill, with the detail a synthetic fixture gets wrong: a REAL
  #     truncated log still contains the "Test Suite 'All tests' started" line,
  #     because xcodebuild prints that on the way IN. Only the SUMMARY is
  #     followed by an Executed total, so matching the name is still safe — but
  #     it must be the -A1 pairing that decides, not the bare name. Verified
  #     against a real 6,453-line log truncated at 2,417.
  { echo "Test Suite 'All tests' started at 2026-09-12 03:19:00.000."
    echo "Test Suite 'DiscoverViewModelLoadTests' passed at 2026-09-12 03:20:00.000."
    echo "${TAB} Executed 14 tests, with 0 failures (0 unexpected) in 0.011 (0.016) seconds"; } > "$ST_DIR/killed-started.txt"
  notice10_select "$ST_DIR/killed-started.txt" 137
  st_check "killed, but 'All tests' STARTED is in the log" PARTIAL -

  # C. ran to the end and failed. Real total, but not a pass line.
  { echo "Test Suite 'All tests' failed at 2026-09-12 05:00:30.000."
    echo "${TAB} Executed 2083 tests, with 3 failures (0 unexpected) in 27.902 (29.156) seconds"
    echo "** TEST FAILED **"; } > "$ST_DIR/failed.txt"
  notice10_select "$ST_DIR/failed.txt" 65
  st_check "completed run, 3 failures" SUITE_FAILED -

  # D. never started (bad simulator, build error).
  : > "$ST_DIR/empty.txt"
  notice10_select "$ST_DIR/empty.txt" 70
  st_check "suite never ran" NEVER_RAN -

  # E. defensive, not observed in the wild: a class count printed AFTER the
  #    total. `tail -1` would take it; reading 'All tests' BY NAME does not.
  { echo "Test Suite 'All tests' passed at 2026-09-12 05:00:30.000."
    echo "${TAB} Executed 2083 tests, with 0 failures (0 unexpected) in 27.902 (29.156) seconds"
    echo "Test Suite 'StragglerTests' passed at 2026-09-12 05:00:31.000."
    echo "${TAB} Executed 2 tests, with 0 failures (0 unexpected) in 0.100 (0.101) seconds"
    echo "** TEST SUCCEEDED **"; } > "$ST_DIR/trailing.txt"
  notice10_select "$ST_DIR/trailing.txt" 0
  st_check "total not last in the log" PASS_LINE "Executed 2083 tests, with 0 failures"

  # F. exit 0 but no success marker — a shape we refuse rather than guess about.
  { echo "Test Suite 'All tests' passed at 2026-09-12 05:00:30.000."
    echo "${TAB} Executed 2083 tests, with 0 failures (0 unexpected) in 27.902 (29.156) seconds"; } > "$ST_DIR/nomarker.txt"
  notice10_select "$ST_DIR/nomarker.txt" 0
  st_check "exit 0, no '** TEST SUCCEEDED **'" SUITE_FAILED -

  rm -rf "$ST_DIR"
  say "done (--selftest) — $([ $ST_FAIL -eq 0 ] && echo 'all cases passed' || echo 'FAILURES ABOVE'); nothing was built"
  exit $ST_FAIL
fi

# ── 0. RESOLVE THE TREE BEFORE ANYTHING ELSE ─────────────────────────────────
# Every git read below is `git -C "$GATE_ROOT"`. A bare git call would read the
# CWD, and the whole class of bug this section exists for is two halves of one
# gate silently describing two different trees.
toplevel_of () { ( cd "$1" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null ) || true; }

SCRIPT_ROOT="$(toplevel_of "$(dirname "${BASH_SOURCE[0]}")")"
CWD_ROOT="$(toplevel_of ".")"

if [ -n "$PROJECT_ROOT" ]; then
  GATE_ROOT="$(cd "$PROJECT_ROOT" 2>/dev/null && pwd)" || GATE_ROOT=""
  if [ -z "$GATE_ROOT" ]; then
    echo "--project-root does not exist: $PROJECT_ROOT" >&2; exit 2
  fi
  ORIGIN="--project-root"
elif [ -n "$CWD_ROOT" ]; then
  GATE_ROOT="$CWD_ROOT"; ORIGIN="the working directory"
elif [ -n "$SCRIPT_ROOT" ]; then
  GATE_ROOT="$SCRIPT_ROOT"; ORIGIN="the script's own location (CWD is not a git tree)"
else
  echo "cannot resolve a git tree to gate: neither the CWD nor $(dirname "${BASH_SOURCE[0]}") is inside one." >&2
  echo "Pass --project-root <path>." >&2
  exit 2
fi

PROJECT_DIR="$GATE_ROOT/ios/Bain Luck"
PROJECT="$PROJECT_DIR/Bain Luck.xcodeproj"
GATE_SHA="$(git -C "$GATE_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)"
GATE_BRANCH="$(git -C "$GATE_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo UNKNOWN)"

say "gating $GATE_ROOT"
echo "  resolved from : $ORIGIN"
echo "  sha           : $GATE_SHA  ($GATE_BRANCH)"
echo "  project       : $PROJECT"
if [ -n "$SCRIPT_ROOT" ] && [ "$SCRIPT_ROOT" != "$GATE_ROOT" ]; then
  echo "  ** THIS SCRIPT LIVES IN A DIFFERENT TREE: $SCRIPT_ROOT"
  echo "     Gating the one above. Before #5480 it gated the script's tree and said nothing."
fi
if [ ! -d "$PROJECT" ]; then
  echo "  NO XCODE PROJECT AT THAT PATH — nothing here can be gated." >&2
  echo "  (Looked for: $PROJECT)" >&2
  exit 2
fi

mkdir -p "$LOGDIR"
FAILED=0

# ── 0b. CHANGED SWIFT FILES — computed ONCE, and never silently empty ────────
# Returns via CHANGED / CHANGED_ERR. CHANGED_ERR non-empty means "could not
# tell", which is a gate failure and is worded differently from "nothing changed".
CHANGED=""
CHANGED_ERR=""
if [ "$(git -C "$GATE_ROOT" rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
  CHANGED_ERR="the repository is SHALLOW (#5428), so no merge base with $BASE can exist.
      Remedy: git -C $GATE_ROOT fetch --unshallow
      The build and tests below still mean what they say; the recompile proof does not."
elif ! MB="$(git -C "$GATE_ROOT" merge-base "$BASE" HEAD 2>&1)"; then
  CHANGED_ERR="no merge base between $BASE and HEAD: $MB
      Remedy: git -C $GATE_ROOT fetch origin master   (or pass --base <ref>)"
else
  # Pathspec is `ios/*.swift`, not `*.swift`: git's `*` crosses `/`, so this is
  # every Swift file under ios/ and nothing outside it. Scoped because the proof
  # asks "did THIS BUILD compile it", and only ios/ is in the project — the
  # shared checkout carries untracked scratch copies of the whole iOS tree
  # (cert-scratch-*/), 226 of which the unscoped pathspec claimed as changed.
  CHANGED=$( { git -C "$GATE_ROOT" diff --name-only "$MB" HEAD -- 'ios/*.swift';
               git -C "$GATE_ROOT" diff --name-only -- 'ios/*.swift';
               git -C "$GATE_ROOT" ls-files --others --exclude-standard -- 'ios/*.swift'; } \
             | sed '/^$/d' | sort -u )
fi

if [ -n "$EXPLAIN" ]; then
  say "changed Swift files vs $BASE"
  if [ -n "$CHANGED_ERR" ]; then
    echo "  CANNOT DETERMINE CHANGED FILES — $CHANGED_ERR"
    say "done (--explain) — resolution FAILED"
    exit 1
  fi
  if [ -z "$CHANGED" ]; then
    echo "  none (the tree above is identical to $BASE for *.swift)"
  else
    printf '%s\n' "$CHANGED" | sed 's/^/  /'
  fi
  # #5591 asked for this: the pass-line rule should be readable WITHOUT having to
  # produce a failing run to discover it.
  say "notice-10 pass line — the rule a real run would apply"
  echo "  OFFERED as a notice-10 line only when BOTH hold:"
  echo "    1. xcodebuild test exits 0, and"
  echo "    2. the log contains '** TEST SUCCEEDED **'."
  echo "  The number is then read from the \"Test Suite 'All tests'\" summary BY NAME."
  echo "  It is NOT 'the last Executed line': xcodebuild prints that shape once per"
  echo "  test class as well as once for the suite (173 lines in a healthy run of"
  echo "  this suite, 1 of them the total), so on a killed run the last one is a"
  echo "  class count wearing the suite's clothes (#5591, #5229)."
  echo "  Short of both conditions the count still prints, labelled, marked do-not-paste."
  say "done (--explain) — nothing was built"
  exit 0
fi

# ── 1. THE macOS BUILD ───────────────────────────────────────────────────────
say "macOS build (the target that went dark for five days)"
MACLOG="$LOGDIR/macos-build.txt"
xcodebuild build \
  -project "$PROJECT" -scheme "$SCHEME" \
  -destination 'platform=macOS,arch=arm64' \
  OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$MACLOG" 2>&1
MAC_EXIT=$?
echo "EXIT CODE: $MAC_EXIT   log: $MACLOG"
if [ $MAC_EXIT -eq 0 ]; then
  echo "  ** BUILD SUCCEEDED **"
else
  FAILED=1
  echo "  BUILD FAILED — the errors, in order:"
  # `error:` lines only; a macOS availability failure is usually one line and is
  # buried thousands of lines into the log.
  /usr/bin/grep -E "error:" "$MACLOG" | head -20 | sed 's/^/    /'
  # gotcha #124/#54: read the exit code's VALUE. For xcodebuild, 65 IS the normal
  # "your code does not compile" result — that is the gate doing its job. 70 means
  # it never got that far (usually an unresolvable -destination), and 127/137/143
  # mean the gate did not run at all. Those are harness stories; 65 is not.
  case $MAC_EXIT in
    65) : ;;
    70) echo "  (exit 70 — xcodebuild could not resolve the destination. The gate never" ;
        echo "   compiled anything; this is NOT a clean build and NOT a real failure.)" ;;
    127|137|143) echo "  (exit $MAC_EXIT — the gate never ran. Not a result.)" ;;
    *) echo "  (exit $MAC_EXIT is an unusual xcodebuild code — check the log before reading it as a compile failure.)" ;;
  esac
fi

# ── 2. RECOMPILE PROOF ───────────────────────────────────────────────────────
# native/111's rule: a target can simply NOT rebuild, so a green build is not by
# itself evidence that it compiled the lines you changed. Xcode 16 file-system
# synchronized groups make this sharper — filesystem presence IS target
# membership, so a new file that is silently outside the target still builds green.
if [ $MAC_EXIT -eq 0 ]; then
  say "recompile proof — were YOUR changed files compiled by that build?"
  if [ -n "$CHANGED_ERR" ]; then
    # NOT the same sentence as "nothing changed". This is the gate saying it is
    # blind, and a blind proof may never read as a pass (#5480).
    FAILED=1
    echo "  CANNOT DETERMINE CHANGED FILES — this proof did NOT run."
    echo "      $CHANGED_ERR"
  elif [ -z "$CHANGED" ]; then
    echo "  no changed Swift files vs $BASE — nothing to prove"
    echo "  (that is a real comparison against $GATE_SHA, not a failure to make one)"
  else
    while IFS= read -r f; do
      b="$(basename "$f")"
      n=$(/usr/bin/grep -c -- "$b" "$MACLOG")
      if [ "$n" -gt 0 ]; then
        echo "  compiled ($n log refs)  $b"
      else
        # Not automatically a failure: a file can be genuinely untouched by the
        # macOS target (a watch-only or widget-only source). But it is ALWAYS
        # worth a human look, because it is also exactly what a file that is
        # outside the target looks like.
        echo "  NOT SEEN IN THE BUILD LOG      $b"
        echo "      → either it is not in the macOS target, or the target did not"
        echo "        rebuild. Touch it and re-run before believing the green."
      fi
    done <<< "$CHANGED"
  fi
fi

[ -n "$BUILD_ONLY" ] && { say "done (--build-only)"; exit $FAILED; }

# ── 3. BainLuckTests ─────────────────────────────────────────────────────────
# Resolve a simulator that EXISTS on this machine. A hardcoded name that is not
# installed exits 70, which reads like a test failure and is not one.
say "BainLuckTests"
SIMLINE=$(xcrun simctl list devices available | /usr/bin/grep -E '^[[:space:]]+iPhone ' | head -1)
UDID=$(printf '%s' "$SIMLINE" | sed -E 's/.*\(([0-9A-Fa-f-]{36})\).*/\1/')
SIMNAME=$(printf '%s' "$SIMLINE" | sed -E 's/^[[:space:]]+//; s/ \(.*//')

if [ -z "$UDID" ]; then
  echo "  NO iPhone SIMULATOR AVAILABLE — cannot run BainLuckTests on this machine."
  echo "  (xcrun simctl list devices available showed no iPhone.)"
  exit 1
fi
echo "  simulator: $SIMNAME  ($UDID)"

TESTLOG="$LOGDIR/tests.txt"
xcodebuild test \
  -project "$PROJECT" -scheme "$SCHEME" \
  -destination "id=$UDID" \
  OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$TESTLOG" 2>&1
TEST_EXIT=$?
echo "EXIT CODE: $TEST_EXIT   log: $TESTLOG"

# THE LINE STANDING NOTICE 10 WANTS IN THE PR BODY, printed verbatim — but ONLY
# from a run that reached the end.
#
# #5591: xcodebuild prints "Executed N tests, with M failures" once PER CLASS as
# well as once for the whole suite — 173 such lines in a healthy run of this
# suite, exactly ONE of which is the total. `tail -1` is that total only on a run
# that finished; on a run killed partway (exit 137, the #5229 silent-hang
# signature) it is whichever class happened to finish last, and this script used
# to hand that over with "paste this line into the PR body" and an assurance that
# it was "the count for <sha>". Nothing downstream can tell `Executed 5` from
# `Executed 2083`, so a grader reading the PR body saw a green pass line for a
# suite that never ran. Same class as #5480 (right tree, wrong count) one step on.
#
# So: the line is taken from the 'All tests' summary BY NAME rather than by
# position, and it is offered as a notice-10 line only when the run both exited 0
# and left "** TEST SUCCEEDED **" in the log. Anything else is printed as labelled
# evidence that explicitly must not be pasted.
notice10_select "$TESTLOG" "$TEST_EXIT"

if [ "$VERDICT" = PASS_LINE ]; then
  echo "  $LINE"
  echo "  ^ paste this line into the PR body — notice 10's iOS clause requires it"
  echo "    it is the count for $GATE_SHA ($GATE_BRANCH) in $GATE_ROOT"
  echo "    — if that is not the sha you are shipping, do not paste it (#5480)"
elif [ "$VERDICT" = SUITE_FAILED ]; then
  # The suite ran to the end and FAILED. The total is real; it is just not a pass.
  echo "  SUITE FINISHED AND FAILED — not a notice-10 line, do not paste it (#5591)."
  echo "    suite total : $ALL_TESTS_LINE"
  echo "    exit $TEST_EXIT; '** TEST SUCCEEDED **' absent from the log."
  echo "    Fix the failures and re-run. Read $TESTLOG."
elif [ "$VERDICT" = PARTIAL ]; then
  # Killed/hung partway: there is no 'All tests' summary, so the last count is a class.
  echo "  PARTIAL RUN — the suite did NOT finish. NOT a notice-10 line, do not paste it (#5591)."
  echo "    last count in the log : $LAST_EXEC_LINE"
  echo "    ^ that is a PER-CLASS summary, not the suite total: no \"Test Suite 'All tests'\""
  echo "      summary exists in this log, which is what a completed run always leaves."
  if [ "$TEST_EXIT" -eq 137 ]; then
    echo "    exit 137 = SIGKILL — the silent-hang signature (#5229), not a test result."
  else
    echo "    exit $TEST_EXIT — a harness story, not a test result (gotcha #54)."
  fi
  echo "    Read $TESTLOG."
else
  echo "  NO 'Executed N tests' LINE IN THE LOG — the suite never ran."
  echo "  That is a harness story, not a test result. Read $TESTLOG."
fi
if [ $TEST_EXIT -ne 0 ]; then
  FAILED=1
  /usr/bin/grep -E "^.*: error:|failed \(" "$TESTLOG" | head -20 | sed 's/^/    /'
fi

say "SUMMARY"
# Self-describing on purpose: this block gets pasted, and a number with no tree
# beside it is exactly how the previous ship's count ended up in a PR body.
echo "  gated tree  : $GATE_ROOT"
echo "  gated sha   : $GATE_SHA  ($GATE_BRANCH)"
echo "  macOS build : $([ $MAC_EXIT -eq 0 ] && echo PASS || echo "FAIL (exit $MAC_EXIT)")"
echo "  recompile   : $([ -n "$CHANGED_ERR" ] && echo "COULD NOT TELL — proof did not run" || echo "checked $(printf '%s' "$CHANGED" | /usr/bin/grep -c . ) changed Swift file(s)")"
# ${LINE} is empty unless the run finished AND succeeded (#5591), so the summary
# can no longer pair the word FAIL with a green-looking count from a dead run.
echo "  BainLuckTests: $([ $TEST_EXIT -eq 0 ] && echo PASS || echo "FAIL (exit $TEST_EXIT)")   ${LINE:-no notice-10 line — see above}"
echo "  logs: $LOGDIR"
exit $FAILED
