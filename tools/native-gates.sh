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

# ── recompile evidence, per log (#5635) ──────────────────────────────────────
# PURE: prints the number of lines in LOG that are evidence FILE was compiled.
# Same reason notice10_select is pure — `--selftest` drives THIS function, not a
# copy of it.
#
# Why a caller ever passes a clause: a `BainLuckTests` source cannot appear in
# the macOS app build at all (that scheme has no test target), so the only log
# that can prove it is the TEST log — and there the honest evidence is the
# basename on a line that also names the target it was compiled into:
#
#   SwiftCompile normal arm64 Compiling\ Foo.swift /…/BainLuckTests/Foo.swift \
#     (in target 'BainLuckTests' from project 'Bain Luck')
#
# Requiring the clause stops a bare mention — a path quoted in a diagnostic, a
# linker map, the xcodebuild command line itself — from reading as a compile.
#
# -F, not a bare pattern: a basename is full of dots, and `Foo.swift` as a
# regex also matches `FooXswift`. The old proof used the unanchored form.
recompile_refs () {   # <basename> <log> [<must-also-be-on-the-same-line>]
  [ -f "$2" ] || { echo 0; return; }
  if [ -n "${3:-}" ]; then
    /usr/bin/grep -F -- "$1" "$2" 2>/dev/null | /usr/bin/grep -c -F -- "$3"
  else
    /usr/bin/grep -c -F -- "$1" "$2" 2>/dev/null
  fi
}

# Is this changed path a test source? Decided on the PATH, not the filename: a
# file called FooTests.swift can live in the app target, and a helper with no
# "Tests" in its name can live in BainLuckTests/.
is_test_source () { case "$1" in */BainLuckTests/*) return 0 ;; *) return 1 ;; esac; }

# Prints one verdict line per file and sets PROOF_UNSEEN to how many were not
# evidenced. Callers print their own follow-up, because "not in the macOS
# target" is a shrug and "not compiled by the test target" is a gate failure.
prove_compiled () {   # <newline-separated files> <log> <clause-or-empty>
  PROOF_UNSEEN=0
  _pc_clause="${3:-}"
  while IFS= read -r _pc_f; do
    [ -n "$_pc_f" ] || continue
    _pc_b="$(basename "$_pc_f")"
    _pc_n=$(recompile_refs "$_pc_b" "$2" "$_pc_clause")
    if [ "$_pc_n" -gt 0 ]; then
      echo "  compiled ($_pc_n log refs)  $_pc_b"
    else
      PROOF_UNSEEN=$((PROOF_UNSEEN + 1))
      echo "  NOT SEEN      $_pc_b"
    fi
  done <<< "$1"
}

# The whole of #5635 in one function: test sources are proved against the TEST
# log, requiring the target clause. It exists as a named function so --selftest
# can drive the REAL call, not a copy of its arguments — the bug being fixed was
# a call site reading the wrong log, and a proof that only exercises the helper
# cannot see that class of mistake at all.
prove_test_sources () {   # <newline-separated files> <testlog>
  prove_compiled "$1" "$2" "in target 'BainLuckTests'"
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

  # ── #5635: the recompile proof reads the log that COULD hold the file ──────
  # Fixture lines are copied from a real run ($TMPDIR/native-gates-76649), not
  # imagined — #5591's lesson was that a synthetic log gets the detail wrong.
  say "--selftest — #5635 recompile evidence"

  rc_check () { # name actual expected
    if [ "$2" = "$3" ]; then echo "  ok    $1 -> $2"
    else echo "  FAIL  $1 -> got $2, wanted $3"; ST_FAIL=1; fi
  }

  { echo "SwiftCompile normal arm64 Compiling\\ AppView.swift /x/ios/Bain\\ Luck/Views/AppView.swift (in target 'Bain Luck' from project 'Bain Luck')"
    echo "SwiftDriver \"Bain Luck\" normal arm64 com.apple.xcode.tools.swift.compiler (in target 'Bain Luck' from project 'Bain Luck')"
  } > "$ST_DIR/mac.txt"

  { echo "SwiftCompile normal arm64 Compiling\\ DiscoverViewModelLoadTests.swift /x/BainLuckTests/DiscoverViewModelLoadTests.swift (in target 'BainLuckTests' from project 'Bain Luck')"
    echo "SwiftCompile normal arm64 /x/BainLuckTests/DiscoverViewModelLoadTests.swift (in target 'BainLuckTests' from project 'Bain Luck')"
  } > "$ST_DIR/test.txt"

  # THE BUG: a test file proved against the macOS log reads 0 — that is the
  # false alarm #5635 fixes, and it must stay 0 so the split is load-bearing.
  rc_check "test file vs the macOS log (the old, wrong log)" \
    "$(recompile_refs DiscoverViewModelLoadTests.swift "$ST_DIR/mac.txt")" 0
  rc_check "test file vs the TEST log, with the target clause" \
    "$(recompile_refs DiscoverViewModelLoadTests.swift "$ST_DIR/test.txt" "in target 'BainLuckTests'")" 2
  rc_check "app file vs the macOS log" \
    "$(recompile_refs AppView.swift "$ST_DIR/mac.txt")" 1

  # The clause is not decoration: a file merely NAMED in the log (a diagnostic,
  # the invocation) must not read as compiled.
  { echo "note: /x/BainLuckTests/GhostTests.swift is newer than its output"
    echo "error: /x/BainLuckTests/GhostTests.swift:12:5: cannot find 'foo' in scope"
  } > "$ST_DIR/mentioned.txt"
  rc_check "mentioned-but-not-compiled, clause required" \
    "$(recompile_refs GhostTests.swift "$ST_DIR/mentioned.txt" "in target 'BainLuckTests'")" 0
  rc_check "...and WITHOUT the clause it would have read as compiled" \
    "$(recompile_refs GhostTests.swift "$ST_DIR/mentioned.txt")" 2

  # -F, not a regex: the dot in a basename must not act as a wildcard. Asserted
  # on BOTH branches — the clause branch and the bare branch each carry their
  # own -F, and a case that exercises only one leaves the other free to regress.
  echo "SwiftCompile normal arm64 /x/BainLuckTests/FooXswift.swift (in target 'BainLuckTests' from project 'Bain Luck')" > "$ST_DIR/dot.txt"
  rc_check "basename is literal, not a regex (clause branch)" \
    "$(recompile_refs Foo.swift "$ST_DIR/dot.txt" "in target 'BainLuckTests'")" 0
  rc_check "basename is literal, not a regex (bare branch)" \
    "$(recompile_refs Foo.swift "$ST_DIR/dot.txt")" 0

  # A missing log is 0, never a crash — section 3a can be reached with no log
  # if the test build died before writing one.
  rc_check "absent log" "$(recompile_refs Any.swift "$ST_DIR/nope.txt")" 0

  # Routing: decided on the PATH, so a test-named file in the app target still
  # gets proved against the macOS log.
  is_test_source "ios/Bain Luck/BainLuckTests/DiscoverViewModelLoadTests.swift" \
    && rc_check "routing: BainLuckTests/ path -> test log" yes yes \
    || rc_check "routing: BainLuckTests/ path -> test log" no yes
  is_test_source "ios/Bain Luck/Bain Luck/Views/FooTests.swift" \
    && rc_check "routing: app file merely NAMED *Tests -> macOS log" no yes \
    || rc_check "routing: app file merely NAMED *Tests -> macOS log" yes yes

  # ── the bug itself, at the CALL SITE ────────────────────────────────────────
  # #5635 was not a bad helper, it was a caller reading a log that could not
  # hold the answer. So drive prove_test_sources() — the real call — and pin
  # BOTH directions: the macOS log can never satisfy it, the test log does.
  # Without the second case the first passes for a function that never matches
  # anything; without the first, the original bug reads green.
  ST_FILES="ios/Bain Luck/BainLuckTests/DiscoverViewModelLoadTests.swift"

  prove_test_sources "$ST_FILES" "$ST_DIR/mac.txt" > /dev/null
  rc_check "call site: test sources vs the macOS log are UNSEEN (the #5635 bug)" \
    "$PROOF_UNSEEN" 1

  prove_test_sources "$ST_FILES" "$ST_DIR/test.txt" > /dev/null
  rc_check "call site: test sources vs the TEST log are proved" \
    "$PROOF_UNSEEN" 0

  # A test file the run only MENTIONED must still count as unseen through the
  # real call, not just through the helper — this is what makes dropping the
  # clause at the call site a failing case rather than a silent widening.
  prove_test_sources "ios/Bain Luck/BainLuckTests/GhostTests.swift" "$ST_DIR/mentioned.txt" > /dev/null
  rc_check "call site: mentioned-but-not-compiled stays unseen" \
    "$PROOF_UNSEEN" 1

  # Empty input is 0 unseen, not one phantom for the empty line. The COUNT alone
  # cannot see this: `grep -F ""` matches every line, so a phantom empty
  # filename reads as "compiled" and keeps PROOF_UNSEEN at 0 while printing a
  # junk verdict line. So assert the OUTPUT too.
  # Redirected to a FILE, not captured with $( ): command substitution runs in a
  # subshell, so PROOF_UNSEEN set inside it never reaches here and the check
  # silently reads the PREVIOUS case's value. That is how this very case first
  # read 1 — a green-looking assertion about a call that had not happened.
  prove_test_sources "" "$ST_DIR/test.txt" > "$ST_DIR/empty-proof.out"
  rc_check "call site: no changed test files -> nothing unproved" "$PROOF_UNSEEN" 0
  rc_check "call site: no changed test files -> and no verdict lines printed" \
    "$(/usr/bin/grep -c . "$ST_DIR/empty-proof.out")" 0

  # #5635 WAS a call site reading a log that could not hold the answer, and
  # --selftest cannot execute section 3a — that needs a real build. So this one
  # line is pinned by reading this script's own source. It is a weaker guard
  # than the behavioural cases above (it asserts text, not conduct); it is here
  # because the alternative for this specific regression is no guard at all.
  if /usr/bin/grep -q 'prove_test_sources "\$CHANGED_TESTS" "\$TESTLOG"' "${BASH_SOURCE[0]}"; then
    rc_check "section 3a hands prove_test_sources the TEST log" yes yes
  else
    rc_check "section 3a hands prove_test_sources the TEST log" no yes
  fi

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
# Initialised here, not in section 3a: under `set -u` the summary reads it even
# on the paths where that section never runs (--build-only, no changed tests).
TESTPROOF_UNSEEN=0

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

# #5635: the proof is split by which log COULD contain the file. Before this,
# every changed file was grepped for in the macOS build log, so every
# BainLuckTests source read "NOT SEEN IN THE BUILD LOG" — a permanent false
# alarm on every test-only iOS ship, on the one signal notice 10's iOS clause
# leans on (CI compiles no Swift, #4302). A warning that always fires is a
# warning that gets skimmed, which is how #5591's fabricated pass line survived.
CHANGED_APP=""
CHANGED_TESTS=""
if [ -n "$CHANGED" ]; then
  while IFS= read -r _cf; do
    [ -n "$_cf" ] || continue
    if is_test_source "$_cf"; then
      CHANGED_TESTS="${CHANGED_TESTS}${_cf}
"
    else
      CHANGED_APP="${CHANGED_APP}${_cf}
"
    fi
  done <<< "$CHANGED"
  CHANGED_APP="${CHANGED_APP%$'\n'}"
  CHANGED_TESTS="${CHANGED_TESTS%$'\n'}"
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
    if [ -z "$CHANGED_APP" ]; then
      echo "  no changed APP sources vs $BASE — this build had nothing of yours to compile"
    fi
    prove_compiled "$CHANGED_APP" "$MACLOG" ""
    if [ "$PROOF_UNSEEN" -gt 0 ]; then
      # Not automatically a failure: a file can be genuinely untouched by the
      # macOS target (a watch-only or widget-only source). But it is ALWAYS
      # worth a human look, because it is also exactly what a file that is
      # outside the target looks like.
      echo "      → either it is not in the macOS target, or the target did not"
      echo "        rebuild. Touch it and re-run before believing the green."
    fi
    # #5635: NOT grepped for here. The macOS scheme has no test target, so this
    # log is the one place they provably cannot be. Proved in section 3 instead,
    # against the log that can actually contain them.
    if [ -n "$CHANGED_TESTS" ]; then
      echo "  deferred to the TEST build (this log cannot contain them):"
      printf '%s\n' "$CHANGED_TESTS" | sed 's|.*/|      |'
    fi
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

# ── 3a. RECOMPILE PROOF, TEST SOURCES (#5635) ────────────────────────────────
# The other half of section 2. These files could never appear in the macOS log,
# so until now the gate called every one of them "NOT SEEN IN THE BUILD LOG"
# even as this build compiled them — measured on #5229's own gate run:
# DiscoverViewModelLoadTests.swift had 0 refs in macos-build.txt and 5 here.
#
# The clause matters as much as the log. A changed test file's path appears in
# the xcodebuild invocation and in any diagnostic that cites it, so a bare
# basename match would pass for a file that failed to compile. Requiring
# "in target 'BainLuckTests'" on the same line means the build system said it
# built it.
if [ -n "$CHANGED_TESTS" ] && [ -z "$CHANGED_ERR" ]; then
  say "recompile proof — were your changed TEST files compiled by that run?"
  prove_test_sources "$CHANGED_TESTS" "$TESTLOG"
  TESTPROOF_UNSEEN=$PROOF_UNSEEN
  if [ "$PROOF_UNSEEN" -gt 0 ]; then
    # Unlike the app-target case this has no innocent reading: a changed file
    # under BainLuckTests/ that the test target did not compile is either
    # outside the target or was never reached, and either way the suite total
    # below does not cover the lines you changed.
    FAILED=1
    echo "      → under BainLuckTests/, but this run did not build it."
    echo "        The suite count below does NOT cover your change (#5635)."
  fi
fi

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

# #5635, same principle as #5591: a suite total only vouches for the lines the
# run actually compiled. If a changed test file was NOT built, the count is
# real but it does not cover the change, so it must not be offered as the
# notice-10 line — otherwise this fix would reintroduce exactly the pairing
# #5591 removed, a green number printed beside a red proof.
if [ "$TESTPROOF_UNSEEN" -gt 0 ] && [ "$VERDICT" = PASS_LINE ]; then
  VERDICT=UNCOVERED
  LINE=""
fi

if [ "$VERDICT" = UNCOVERED ]; then
  echo "  SUITE PASSED BUT DOES NOT COVER YOUR CHANGE — not a notice-10 line, do not paste it (#5635)."
  echo "    suite total : $ALL_TESTS_LINE"
  echo "    $TESTPROOF_UNSEEN changed test file(s) were not compiled by this run (above)."
  echo "    Touch them and re-run, or check they are inside the BainLuckTests target."
elif [ "$VERDICT" = PASS_LINE ]; then
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
echo "  recompile   : $([ -n "$CHANGED_ERR" ] && echo "COULD NOT TELL — proof did not run" || echo "checked $(printf '%s' "$CHANGED" | /usr/bin/grep -c . ) changed Swift file(s)$([ "$TESTPROOF_UNSEEN" -gt 0 ] && echo ", $TESTPROOF_UNSEEN test file(s) NOT COMPILED")")"
# ${LINE} is empty unless the run finished AND succeeded (#5591) AND every
# changed test file was compiled (#5635), so the summary can no longer pair a
# green-looking count with a dead run or with a run that skipped your change.
echo "  BainLuckTests: $([ $TEST_EXIT -eq 0 ] && [ "$TESTPROOF_UNSEEN" -eq 0 ] && echo PASS || echo "FAIL$([ $TEST_EXIT -ne 0 ] && echo " (exit $TEST_EXIT)" || echo " (change not covered)")")   ${LINE:-no notice-10 line — see above}"
echo "  logs: $LOGDIR"
exit $FAILED
