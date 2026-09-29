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
#   3a. test-file proof     — each changed BainLuckTests file compiled in THIS
#                             log, or vouched for by an identified cached object,
#                             or recompiled + re-tested by ONE bounded fallback
#                             over just those files (#9659). Never a full rerun.
#   4. manifest.json        — tree, sha, iOS tree, verdict, per-file evidence and
#                             stage timings, beside the logs: the handoff file.
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
# ═══ AN INCREMENTAL BUILD IS NOT MISSING COVERAGE (#9659) ═══
#
# Build 32 ran its full suite green, 4356/0 in 37.3 minutes, and this gate still
# failed: 15 changed test files had no NEW SwiftCompile line, because an earlier
# run had compiled them into the same DerivedData. Absence from one log is "could
# not tell", not "not covered". So a file the log does not show is checked
# against the run's own artifacts — the output-file map its log names, the
# object, and a ledger of what earlier gate runs watched compile — and accepted
# only with an identity (exact tree path, target, configuration, content). Short
# of that, ONE bounded xcodebuild recompiles just those files and runs just their
# test classes (19 s by hand on build 32, against 37 minutes). A blind PASS is
# never an outcome. The rules are in full above `test_file_map_from_log`.
#
# ═══ USAGE ═══
#
#   tools/native-gates.sh              # both gates, diff measured vs origin/master
#   tools/native-gates.sh --build-only # just the macOS build + recompile proof
#   tools/native-gates.sh --base <ref> # measure the diff against another ref
#   tools/native-gates.sh --explain    # resolve tree/sha/diff and STOP. No xcodebuild.
#   tools/native-gates.sh --selftest   # prove the #5591 pass-line rule. No Xcode, no tree.
#   tools/native-gates.sh --project-root <path>   # gate a tree explicitly
#   tools/native-gates.sh --no-fallback           # unproven test files stay unproven (no targeted run)
#   tools/native-gates.sh --check-manifest <manifest.json>
#                                      # may an earlier run's evidence stand for THIS tree?
#                                      # Same clean iOS tree + complete green run = yes. No xcodebuild.
#   tools/native-gates.sh --selftest-provenance   # just the #9659 cases, fast. No Xcode.
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
NO_FALLBACK=""
CHECK_MANIFEST=""
SELFTEST_PROVENANCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=1 ;;
    --explain) EXPLAIN=1 ;;
    --selftest) SELFTEST=1 ;;
    --base) BASE="${2:?--base needs a ref}"; shift ;;
    --project-root) PROJECT_ROOT="${2:?--project-root needs a path}"; shift ;;
    --no-fallback) NO_FALLBACK=1 ;;
    --check-manifest) CHECK_MANIFEST="${2:?--check-manifest needs a manifest.json path}"; shift ;;
    --selftest-provenance) SELFTEST_PROVENANCE=1 ;;
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
#
# PROOF_SEEN_FILES / PROOF_UNSEEN_FILES carry the same split as paths (#9659):
# the provenance step below needs to know WHICH files are unproven, not how many.
prove_compiled () {   # <newline-separated files> <log> <clause-or-empty>
  PROOF_UNSEEN=0
  PROOF_SEEN_FILES=""
  PROOF_UNSEEN_FILES=""
  _pc_clause="${3:-}"
  while IFS= read -r _pc_f; do
    [ -n "$_pc_f" ] || continue
    _pc_b="$(basename "$_pc_f")"
    _pc_n=$(recompile_refs "$_pc_b" "$2" "$_pc_clause")
    if [ "$_pc_n" -gt 0 ]; then
      echo "  compiled ($_pc_n log refs)  $_pc_b"
      PROOF_SEEN_FILES="${PROOF_SEEN_FILES:+$PROOF_SEEN_FILES
}$_pc_f"
    else
      PROOF_UNSEEN=$((PROOF_UNSEEN + 1))
      echo "  NOT SEEN      $_pc_b"
      PROOF_UNSEEN_FILES="${PROOF_UNSEEN_FILES:+$PROOF_UNSEEN_FILES
}$_pc_f"
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

# Watch a running child and kill it if its log stops growing (#2975). Returns 1
# if it killed the child for stalling, 0 if the child finished on its own.
#
# A named function for the same reason `prove_test_sources` is one: --selftest
# drives THIS code against a child that really hangs, rather than asserting that
# a copy of the arithmetic is right. An unexercised kill path is indistinguishable
# from no kill path until the night it is needed — and the whole point of the
# watchdog is that it fires on a day nobody is watching.
watch_for_stall () {   # <pid> <logfile> <limit-seconds>
  _ws_pid=$1; _ws_log=$2; _ws_limit=$3
  _ws_last_size=-1
  _ws_last_growth=$(date +%s)
  while kill -0 "$_ws_pid" 2>/dev/null; do
    # WATCH_POLL_SECS exists for the #9659 self-test only, whose fake xcodebuild
    # exits at once; a real run always polls every 5 s.
    sleep "${WATCH_POLL_SECS:-5}"
    # `wc -c` on a file the child is still writing is a snapshot, which is all
    # this needs: it only ever asks "did it change", never "how far along is it".
    _ws_size=$(wc -c < "$_ws_log" 2>/dev/null || echo 0)
    _ws_now=$(date +%s)
    if [ "$_ws_size" != "$_ws_last_size" ]; then
      _ws_last_size=$_ws_size
      _ws_last_growth=$_ws_now
    elif [ $((_ws_now - _ws_last_growth)) -ge "$_ws_limit" ]; then
      # The GROUP, not just the leader: xcodebuild's children hold the simulator
      # and outlive a bare kill of the parent. The single-pid form is the
      # fallback for a shell that gave us no group.
      kill -TERM -"$_ws_pid" 2>/dev/null || kill -TERM "$_ws_pid" 2>/dev/null
      sleep 5
      kill -KILL -"$_ws_pid" 2>/dev/null || kill -KILL "$_ws_pid" 2>/dev/null
      return 1
    fi
  done
  return 0
}

# Which Swift files this run is being asked to prove. Writes CHANGED and
# CHANGED_ERR; CHANGED_ERR non-empty means "could not tell", which fails the gate
# and is worded differently from "nothing changed" (#5428's lesson).
#
# 🪤 SHALLOWNESS IS NOT THE TEST. THE MISSING MERGE BASE IS.
# This refused outright when `rev-parse --is-shallow-repository` said true. Every
# lane worktree on this machine IS shallow, and one rebased onto current master
# (notice 47a, the normal state of anything being offered) resolves a merge base
# perfectly well — it is `origin/master` itself. So the proof that a stale cache
# did not fake the build was switched off for every native ship, the gate exited
# 1 on runs where both real gates passed, and "COULD NOT TELL" was printed about
# a question git could answer in full. Measured on b57235c0e (#4838): refused as
# shallow, while `git merge-base origin/master HEAD` returned 9c8787a23 and the
# three-dot diff named both changed files.
#
# Now git is ASKED, and shallowness only EXPLAINS a real failure — which is what
# #5428 actually observed. A named function for the same reason the three above
# are: --selftest drives THIS code against real throwaway repositories, and a
# check that reasons about shallowness in a copy could not have caught this.
resolve_changed_swift () {   # <root> <base>
  _rc_root="$1"; _rc_base="$2"
  CHANGED=""
  CHANGED_ERR=""
  if ! _rc_mb="$(git -C "$_rc_root" merge-base "$_rc_base" HEAD 2>&1)"; then
    CHANGED_ERR="no merge base between $_rc_base and HEAD: $_rc_mb
      Remedy: git -C $_rc_root fetch origin master   (or pass --base <ref>)"
    if [ "$(git -C "$_rc_root" rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
      CHANGED_ERR="$CHANGED_ERR
      The repository is also SHALLOW (#5428), which is the likeliest cause:
      git -C $_rc_root fetch --unshallow
      The build and tests still mean what they say; the recompile proof does not."
    fi
    return 0
  fi
  # Pathspec is `ios/*.swift`, not `*.swift`: git's `*` crosses `/`, so this is
  # every Swift file under ios/ and nothing outside it. Scoped because the proof
  # asks "did THIS BUILD compile it", and only ios/ is in the project — the
  # shared checkout carries untracked scratch copies of the whole iOS tree
  # (cert-scratch-*/), 226 of which the unscoped pathspec claimed as changed.
  CHANGED=$( { git -C "$_rc_root" diff --name-only "$_rc_mb" HEAD -- 'ios/*.swift';
               git -C "$_rc_root" diff --name-only -- 'ios/*.swift';
               git -C "$_rc_root" ls-files --others --exclude-standard -- 'ios/*.swift'; } \
             | sed '/^$/d' | sort -u )
}

# ── compile provenance: cached evidence, the ledger, the fallback (#9659) ─────
#
# ═══ WHY ═══
#
# Build 32 (63455d0dfa, 2026-09-29): the full suite ran green — 4356 tests, 0
# failures, 37.3 minutes — and the gate still FAILED, because 15 changed test
# files were "NOT SEEN" in the test log. The run was incremental: an earlier run
# had compiled those files into the same DerivedData, Xcode correctly skipped
# them, and #5635's proof reads only THIS run's log, so it had nothing to point
# at. The honest reading was "could not tell", and the only remedy the gate
# offered was another 37 minutes. Native closed it by hand with a targeted
# compile of exactly those 15 files plus their 210 tests: 19 seconds.
#
# This section makes that hand fix the gate's own behaviour, and adds what the
# hand fix lacked: when an earlier gate run DID watch the file compile, the gate
# can say so with an identity instead of recompiling at all.
#
# ═══ WHAT COUNTS AS CACHED EVIDENCE — all six, or it is not evidence ═══
#
#   1. This run finished GREEN (notice10_select said PASS_LINE). A partial or
#      failed run vouches for nothing, cached or not.
#   2. This run's own log names exactly ONE `BainLuckTests-OutputFileMap.json`:
#      Xcode's map from each source path to its object, for the DerivedData this
#      run actually used. It is read from the log, never guessed, so another
#      tree's or another DerivedData's objects cannot be borrowed. Every run
#      prints it, incremental or not (the SwiftDriver step's command line).
#   3. The map sits under `Debug-iphonesimulator/BainLuckTests.build/`, the
#      configuration and target this run tests.
#   4. The map lists the file's EXACT absolute path in the gated tree, which
#      proves membership in the target AND the right tree, and the object it
#      names exists.
#   5. The object is not older than the source (Xcode's own staleness rule).
#   6. The LEDGER (below) has a row saying a gate run SAW this file compiled,
#      with this same content (the git blob of the file as it is now), into this
#      same object, with this same object mtime. Rules 4-5 only prove "Xcode
#      thinks the object is current", which is an mtime claim; a copy that
#      preserves an old mtime defeats it. Rule 6 is the identity: this content
#      was watched becoming this object.
#
# Failing rule 1 means the gate fails anyway. Failing any of 2-6 means the
# evidence is INSUFFICIENT and the file goes to the fallback — never to a blind
# pass, and never to an automatic full rerun.
#
# ═══ THE LEDGER ═══
#
# One TSV per DerivedData, beside it: `<DerivedData>/bainluck-compile-evidence.tsv`.
# Deleting DerivedData deletes the objects and the ledger together, which is the
# point. A row is written only for a file a run's log showed compiled into the
# test target, from a run that reached the end of its suite (so the build
# succeeded), and only if the object is not older than the source at that moment.
#   source path · git blob · object path · object mtime · target · config · gate sha · epoch
#
# ═══ THE FALLBACK ═══
#
# `touch` the insufficient files (mtime only: content and `git status` are
# unchanged) and run ONE bounded xcodebuild on the same simulator and packages:
# `test -only-testing:BainLuckTests/<Class>` for every XCTestCase class those
# files declare, or `build-for-testing` when they declare none (helpers). The
# files must then appear compiled in THAT log, and the run must pass on its own
# 'Selected tests' summary with at least one test executed. That summary is
# never the notice-10 line; the full suite's 'All tests' total still is.

XCODEBUILD="${NATIVE_GATES_XCODEBUILD:-xcodebuild}"
TEST_TARGET="BainLuckTests"
TEST_CONFIG_DIR="Debug-iphonesimulator"

# `date -r FILE` reads an mtime on both BSD (this Mac) and GNU (CI) date;
# `stat` spells it differently on each.
mtime_of () { date -r "$1" +%s 2>/dev/null; }

# PURE. Sets OFM_MAP (empty unless exactly ONE map is named) and OFM_COUNT.
# Log paths escape spaces (`Bain\ Luck.build`), so the pattern accepts `\ `.
test_file_map_from_log () {   # <log>
  OFM_MAP=""; OFM_COUNT=0
  [ -f "$1" ] || return 0
  _ofm=$(/usr/bin/grep -o -E 'output-file-map ([^ \\]|\\ )*/'"$TEST_TARGET"'-OutputFileMap\.json' "$1" 2>/dev/null \
         | sed -e 's/^output-file-map //' -e 's/\\ / /g' | sort -u)
  OFM_COUNT=$(printf '%s' "$_ofm" | /usr/bin/grep -c .)
  [ "$OFM_COUNT" -eq 1 ] && OFM_MAP="$_ofm"
  return 0
}

# Prints the object the map assigns to an exact source path, or nothing.
map_object_for () {   # <map> <absolute source path>
  python3 - "$1" "$2" 2>/dev/null <<'PY'
import json, sys
try:
    print((json.load(open(sys.argv[1])).get(sys.argv[2]) or {}).get("object", ""))
except Exception:
    print("")
PY
}

ledger_for_map () {   # <map>
  if [ -n "${NATIVE_GATES_EVIDENCE_LEDGER:-}" ]; then echo "$NATIVE_GATES_EVIDENCE_LEDGER"; return; fi
  case "$1" in
    */Build/Intermediates.noindex/*) echo "${1%%/Build/Intermediates.noindex/*}/bainluck-compile-evidence.tsv" ;;
    *) echo "$(dirname "$1")/bainluck-compile-evidence.tsv" ;;
  esac
}

# Appends a ledger row per file. Callers pass ONLY files a log showed compiled,
# from a run that reached the end of its suite. Sets RECORDED.
record_compile_evidence () {   # <root> <newline-separated relative files> <map> <gate sha>
  RECORDED=0
  { [ -n "$3" ] && [ -f "$3" ]; } || return 0
  _re_ledger="$(ledger_for_map "$3")"
  while IFS= read -r _re_f; do
    [ -n "$_re_f" ] || continue
    _re_src="$1/$_re_f"
    [ -f "$_re_src" ] || continue
    _re_obj="$(map_object_for "$3" "$_re_src")"
    { [ -n "$_re_obj" ] && [ -f "$_re_obj" ]; } || continue
    _re_om="$(mtime_of "$_re_obj")"; _re_sm="$(mtime_of "$_re_src")"
    { [ -n "$_re_om" ] && [ -n "$_re_sm" ] && [ "$_re_om" -ge "$_re_sm" ]; } || continue
    _re_blob="$(git -C "$1" hash-object -- "$_re_src" 2>/dev/null)" || continue
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$_re_src" "$_re_blob" "$_re_obj" "$_re_om" \
      "$TEST_TARGET" "$TEST_CONFIG_DIR" "$4" "$(date +%s)" >> "$_re_ledger" 2>/dev/null \
      && RECORDED=$((RECORDED + 1))
  done <<< "$2"
}

# PURE (reads, never writes). Applies the six rules above to one file.
# Sets CACHE_OK=1|0 and CACHE_WHY (the identity, or the first rule that failed).
cached_compile_evidence () {   # <root> <relative file> <map-or-empty> <verdict>
  CACHE_OK=0
  _ce_src="$1/$2"
  if [ "$4" != PASS_LINE ]; then
    CACHE_WHY="this run did not finish green ($4), so nothing it built vouches for anything"; return 0
  fi
  if [ -z "$3" ]; then
    CACHE_WHY="this run's log does not name exactly one $TEST_TARGET output-file map"; return 0
  fi
  if [ ! -f "$3" ]; then
    CACHE_WHY="the output-file map named in the log does not exist: $3"; return 0
  fi
  case "$3" in
    */"$TEST_CONFIG_DIR"/"$TEST_TARGET".build/*) : ;;
    *) CACHE_WHY="the map is not for $TEST_TARGET in $TEST_CONFIG_DIR: $3"; return 0 ;;
  esac
  _ce_obj="$(map_object_for "$3" "$_ce_src")"
  if [ -z "$_ce_obj" ]; then
    CACHE_WHY="this exact path is not in the run's $TEST_TARGET map (outside the target, or another tree's map)"; return 0
  fi
  if [ ! -f "$_ce_obj" ]; then
    CACHE_WHY="the map names an object that does not exist: $(basename "$_ce_obj")"; return 0
  fi
  _ce_om="$(mtime_of "$_ce_obj")"; _ce_sm="$(mtime_of "$_ce_src")"
  if [ -z "$_ce_om" ] || [ -z "$_ce_sm" ] || [ "$_ce_om" -lt "$_ce_sm" ]; then
    CACHE_WHY="stale: the object is older than the source"; return 0
  fi
  _ce_blob="$(git -C "$1" hash-object -- "$_ce_src" 2>/dev/null)"
  _ce_ledger="$(ledger_for_map "$3")"
  _ce_row=""
  if [ -n "$_ce_blob" ] && [ -f "$_ce_ledger" ]; then
    # ENVIRON, not -v: awk -v interprets backslashes in the value.
    _ce_row=$(S="$_ce_src" B="$_ce_blob" O="$_ce_obj" M="$_ce_om" T="$TEST_TARGET" C="$TEST_CONFIG_DIR" \
      awk -F'\t' '$1==ENVIRON["S"] && $2==ENVIRON["B"] && $3==ENVIRON["O"] && $4==ENVIRON["M"] \
                  && $5==ENVIRON["T"] && $6==ENVIRON["C"] { r=$7 } END { if (r != "") print r }' "$_ce_ledger")
  fi
  if [ -z "$_ce_row" ]; then
    CACHE_WHY="no recorded identity: no gate run saw this content (blob ${_ce_blob:0:10}) compiled into that object"; return 0
  fi
  CACHE_OK=1
  CACHE_WHY="blob ${_ce_blob:0:10} was seen compiled into $(basename "$_ce_obj") by the gate run at ${_ce_row:0:10}"
}

# The XCTestCase classes a Swift file declares, one per line. A class that
# inherits through an intermediate base is not listed; its file still has to
# COMPILE in the fallback, it just contributes no -only-testing selector.
xctest_classes () {   # <swift file>
  sed -n -E 's/^[[:space:]]*(@[A-Za-z]+[[:space:]]+)*((final|public|internal|open)[[:space:]]+)*class[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*:[[:space:]]*XCTestCase([^A-Za-z0-9_].*)?$/\4/p' "$1" 2>/dev/null
}

# PURE. Sets FB_MODE (test | build-for-testing), FB_ONLY (array) and FB_CLASSES.
fallback_plan () {   # <root> <newline-separated relative files>
  FB_ONLY=()
  FB_CLASSES=""
  while IFS= read -r _fp_f; do
    [ -n "$_fp_f" ] || continue
    while IFS= read -r _fp_c; do
      [ -n "$_fp_c" ] || continue
      FB_ONLY+=("-only-testing:$TEST_TARGET/$_fp_c")
      FB_CLASSES="${FB_CLASSES:+$FB_CLASSES }$_fp_c"
    done <<< "$(xctest_classes "$1/$_fp_f")"
  done <<< "$2"
  if [ ${#FB_ONLY[@]} -gt 0 ]; then FB_MODE=test; else FB_MODE=build-for-testing; fi
}

# PURE — the fallback's twin of notice10_select. An -only-testing run's total
# lives under 'Selected tests', never 'All tests' (measured on a real run,
# 2026-09-29), which is why it can never be taken for the notice-10 line.
# Sets FB_OK=1|0 and FB_TOTAL_LINE.
fallback_select () {   # <log> <exit> <mode>
  FB_OK=0
  FB_TOTAL_LINE=""
  if [ "$3" = build-for-testing ]; then
    if [ "$2" -eq 0 ] && /usr/bin/grep -q '^\*\* TEST BUILD SUCCEEDED \*\*' "$1" 2>/dev/null; then FB_OK=1; fi
    return 0
  fi
  FB_TOTAL_LINE=$(/usr/bin/grep -A1 -E "Test Suite 'Selected tests' (passed|failed)" "$1" 2>/dev/null \
                  | /usr/bin/grep -E "Executed [0-9]+ tests?, with .* failures?" | tail -1 | sed 's/^[[:space:]]*//')
  _fs_n=$(printf '%s' "$FB_TOTAL_LINE" | sed -n -E 's/^Executed ([0-9]+) tests?, .*/\1/p')
  # "Executed 0 tests" with exit 0 is what a selector naming no real class gets.
  # That is a vacuous pass, so at least one test must have run.
  if [ "$2" -eq 0 ] && /usr/bin/grep -q '^\*\* TEST SUCCEEDED \*\*' "$1" 2>/dev/null \
     && [ -n "$_fs_n" ] && [ "$_fs_n" -gt 0 ] \
     && [ "${FB_TOTAL_LINE#*with 0 failures}" != "$FB_TOTAL_LINE" ]; then
    FB_OK=1
  fi
}

# Runs the fallback. Reads the run's globals: PROJECT, SCHEME, UDID, SPM_FLAGS,
# SWIFT_FLAGS, STALL_LIMIT, XCODEBUILD. Sets FB_EXIT, FB_OK, FB_TOTAL_LINE,
# FB_STALLED, FB_SECS, FB_UNPROVEN, FB_PROVEN_FILES; the per-file proof lines
# are left in <logfile>.proof.
run_compile_fallback () {   # <root> <newline-separated relative files> <logfile>
  FB_LOG="$3"; FB_STALLED=0
  fallback_plan "$1" "$2"
  while IFS= read -r _rf_f; do
    [ -n "$_rf_f" ] && touch "$1/$_rf_f"
  done <<< "$2"
  _rf_t0=$(date +%s)
  set -m
  "$XCODEBUILD" "$FB_MODE" -project "$PROJECT" -scheme "$SCHEME" -destination "id=$UDID" \
    ${SPM_FLAGS[@]+"${SPM_FLAGS[@]}"} ${FB_ONLY[@]+"${FB_ONLY[@]}"} \
    OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$FB_LOG" 2>&1 &
  _rf_pid=$!
  set +m
  watch_for_stall "$_rf_pid" "$FB_LOG" "${STALL_LIMIT:-300}" || FB_STALLED=1
  wait "$_rf_pid" 2>/dev/null
  FB_EXIT=$?
  FB_SECS=$(( $(date +%s) - _rf_t0 ))
  fallback_select "$FB_LOG" "$FB_EXIT" "$FB_MODE"
  prove_test_sources "$2" "$FB_LOG" > "$FB_LOG.proof"
  FB_UNPROVEN=$PROOF_UNSEEN
  FB_PROVEN_FILES="$PROOF_SEEN_FILES"
}

# One evidence row per file: path · blob · kind (log|cache|fallback|none) · detail.
evidence_rows () {   # <newline-separated relative files> <kind> <detail>
  while IFS= read -r _er_f; do
    [ -n "$_er_f" ] || continue
    printf '%s\t%s\t%s\t%s\n' "$_er_f" \
      "$(git -C "$GATE_ROOT" hash-object -- "$GATE_ROOT/$_er_f" 2>/dev/null)" "$2" "$3" >> "$EVIDENCE_TSV"
  done <<< "$1"
}

# The whole provenance decision for the test files this run's log did not show
# compiled. A named function so --selftest drives the REAL sequence (cached →
# fallback → ledger) against a fake xcodebuild, not a copy of it. Prints its
# verdict lines; sets STILL_UNSEEN (the files nothing could vouch for) and FB_RAN.
provenance_for_unseen () {   # <root> <newline-separated unseen files> <map> <verdict> <fallback-log>
  STILL_UNSEEN="$2"
  FB_RAN=0
  [ -n "$2" ] || return 0
  if [ "$4" != PASS_LINE ]; then
    evidence_rows "$2" none "the run did not finish green ($4)"
    return 0
  fi
  _pu_need=""
  while IFS= read -r _pu_f; do
    [ -n "$_pu_f" ] || continue
    cached_compile_evidence "$1" "$_pu_f" "$3" "$4"
    if [ "$CACHE_OK" -eq 1 ]; then
      echo "  cached        $(basename "$_pu_f") — $CACHE_WHY"
      evidence_rows "$_pu_f" cache "$CACHE_WHY"
    else
      echo "  insufficient  $(basename "$_pu_f") — $CACHE_WHY"
      _pu_need="${_pu_need:+$_pu_need
}$_pu_f"
    fi
  done <<< "$2"
  STILL_UNSEEN="$_pu_need"
  [ -n "$_pu_need" ] || return 0
  if [ -n "${NO_FALLBACK:-}" ]; then
    echo "  --no-fallback: the files above stay unproven."
    evidence_rows "$_pu_need" none "insufficient provenance; fallback disabled"
    return 0
  fi
  FB_RAN=1
  echo "  bounded fallback: recompile ONLY these files, run ONLY their tests — not the full suite"
  run_compile_fallback "$1" "$_pu_need" "$5"
  echo "    mode : $FB_MODE${FB_CLASSES:+ -only-testing $FB_CLASSES}"
  echo "    EXIT CODE: $FB_EXIT   log: $FB_LOG   (${FB_SECS}s)"
  sed 's/^/  /' "$FB_LOG.proof"
  if [ "$FB_OK" -eq 1 ] && [ "$FB_UNPROVEN" -eq 0 ] && [ "$FB_STALLED" -eq 0 ]; then
    echo "    fallback PASSED — ${FB_TOTAL_LINE:-test build succeeded}, every file compiled by it"
    evidence_rows "$_pu_need" fallback "${FB_TOTAL_LINE:-build-for-testing succeeded} ($FB_SECS s)"
    test_file_map_from_log "$FB_LOG"
    record_compile_evidence "$1" "$FB_PROVEN_FILES" "$OFM_MAP" "${GATE_SHA:-UNKNOWN}"
    STILL_UNSEEN=""
    return 0
  fi
  if [ "$FB_STALLED" -eq 1 ]; then
    _pu_why="the fallback STALLED and was killed (#2975)"
  elif [ "$FB_UNPROVEN" -gt 0 ]; then
    _pu_why="$FB_UNPROVEN file(s) were not compiled even after touching them: outside the $TEST_TARGET target, or the build never reached them"
  elif [ "$FB_MODE" = test ] && [ -n "$FB_TOTAL_LINE" ]; then
    _pu_why="their tests FAILED on freshly compiled objects ($FB_TOTAL_LINE): a real failure the full-suite pass could not see"
  else
    _pu_why="the fallback did not finish green (exit $FB_EXIT)"
  fi
  echo "    fallback FAILED — $_pu_why"
  evidence_rows "$_pu_need" none "fallback failed: $_pu_why"
}

# The integration manifest: what was tested, on which iOS tree, with what
# evidence. Written beside the logs on every full run, so the Native→Integrator
# handoff is one file and `--check-manifest` can decide reuse without a person.
write_manifest () {   # <out>
  M_ROOT="$GATE_ROOT" M_SHA="$GATE_SHA" M_BRANCH="$GATE_BRANCH" M_BASE="$BASE" \
  M_TREE0="${IOS_TREE_START:-}" M_DIRTY0="${IOS_DIRTY_START:-}" \
  M_TREE1="$(git -C "$GATE_ROOT" rev-parse HEAD:ios 2>/dev/null)" \
  M_DIRTY1="$(git -C "$GATE_ROOT" status --porcelain --untracked-files=all -- ios 2>/dev/null | head -1)" \
  M_UDID="${UDID:-}" M_MAC="${MAC_EXIT:-}" M_TEST="${TEST_EXIT:-}" M_VERDICT="${VERDICT:-}" \
  M_LINE="${LINE:-}" M_ALL="${ALL_TESTS_LINE:-}" M_UNPROVEN="${TESTPROOF_UNSEEN:-0}" \
  M_CHANGED_ERR="${CHANGED_ERR:-}" M_FB_RAN="${FB_RAN:-0}" M_FB_MODE="${FB_MODE:-}" \
  M_FB_CLASSES="${FB_CLASSES:-}" M_FB_EXIT="${FB_EXIT:-}" M_FB_OK="${FB_OK:-}" \
  M_FB_TOTAL="${FB_TOTAL_LINE:-}" M_FB_SECS="${FB_SECS:-}" M_FB_LOG="${FB_LOG:-}" \
  M_MAC_SECS="${MAC_SECS:-}" M_TEST_SECS="${TEST_SECS:-}" M_T0="${GATE_T0:-}" \
  M_MACLOG="${MACLOG:-}" M_TESTLOG="${TESTLOG:-}" M_GATE_EXIT="$FAILED" \
  python3 - "$1" "$EVIDENCE_TSV" <<'PY'
import json, os, sys, time
e = os.environ.get
def num(k):
    v = e(k, "")
    return int(v) if v.lstrip("-").isdigit() else None
rows = []
try:
    for line in open(sys.argv[2]):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4:
            rows.append({"path": p[0], "blob": p[1], "evidence": p[2], "detail": p[3]})
except FileNotFoundError:
    pass
t0 = num("M_T0")
m = {
    "schema": "native-gates-manifest/1",
    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "gated_tree": e("M_ROOT"), "gated_sha": e("M_SHA"), "gated_branch": e("M_BRANCH"),
    "base": e("M_BASE"),
    "ios_tree_start": e("M_TREE0"), "ios_tree_end": e("M_TREE1"),
    "ios_dirty_start": bool(e("M_DIRTY0")), "ios_dirty_end": bool(e("M_DIRTY1")),
    "configuration": "Debug", "test_target": "BainLuckTests", "destination": e("M_UDID"),
    "macos_build_exit": num("M_MAC"), "test_exit": num("M_TEST"),
    "verdict": e("M_VERDICT"), "notice10_line": e("M_LINE"), "all_tests_line": e("M_ALL"),
    "changed_files_error": e("M_CHANGED_ERR") or None,
    "tests_unproven": num("M_UNPROVEN"),
    "evidence": rows,
    "fallback": {
        "ran": e("M_FB_RAN") == "1", "mode": e("M_FB_MODE") or None,
        "classes": (e("M_FB_CLASSES") or "").split(), "exit": num("M_FB_EXIT"),
        "ok": e("M_FB_OK") == "1", "total_line": e("M_FB_TOTAL") or None,
        "seconds": num("M_FB_SECS"), "log": e("M_FB_LOG") or None,
    },
    "seconds": {
        "macos_build": num("M_MAC_SECS"), "tests": num("M_TEST_SECS"),
        "fallback": num("M_FB_SECS"),
        "total": (int(time.time()) - t0) if t0 is not None else None,
    },
    "logs": {"macos": e("M_MACLOG"), "tests": e("M_TESTLOG")},
    "gate_exit": num("M_GATE_EXIT"),
}
with open(sys.argv[1], "w") as f:
    json.dump(m, f, indent=2)
    f.write("\n")
PY
}

# May an earlier run's evidence stand in for a new one on THIS tree? Yes only
# when the iOS tree is byte-identical (HEAD:ios), clean on both sides, and the
# earlier run was a complete green with every changed test file evidenced.
# Prints the verdict; returns 0 reusable, 1 not.
check_manifest () {   # <root> <manifest>
  CUR_IOS_TREE="$(git -C "$1" rev-parse HEAD:ios 2>/dev/null)" \
  CUR_IOS_DIRTY="$(git -C "$1" status --porcelain --untracked-files=all -- ios 2>/dev/null | head -1)" \
  CUR_SHA="$(git -C "$1" rev-parse HEAD 2>/dev/null)" \
  python3 - "$2" <<'PY'
import json, os, sys
try:
    m = json.load(open(sys.argv[1]))
except Exception as ex:
    print(f"  NOT REUSABLE — cannot read the manifest: {ex}")
    sys.exit(1)
cur = os.environ.get("CUR_IOS_TREE", "")
why = []
if m.get("schema") != "native-gates-manifest/1":
    why.append(f"unknown manifest schema {m.get('schema')!r}")
if not cur:
    why.append("cannot resolve HEAD:ios in this tree")
elif m.get("ios_tree_start") != cur:
    why.append(f"the iOS tree differs: the evidence is for {m.get('ios_tree_start')}, HEAD:ios here is {cur}")
if m.get("ios_tree_end") != m.get("ios_tree_start"):
    why.append("the iOS tree changed while that gate was running")
if m.get("ios_dirty_start") or m.get("ios_dirty_end"):
    why.append("that gate ran on uncommitted iOS changes, so HEAD:ios does not describe what it tested")
if os.environ.get("CUR_IOS_DIRTY"):
    why.append("this tree has uncommitted iOS changes")
if m.get("macos_build_exit") != 0:
    why.append(f"its macOS build did not pass (exit {m.get('macos_build_exit')})")
if m.get("test_exit") != 0 or m.get("verdict") != "PASS_LINE" or not m.get("notice10_line"):
    why.append(f"its test run was not a complete pass (verdict {m.get('verdict')}, exit {m.get('test_exit')})")
if m.get("changed_files_error"):
    why.append("it could not tell which files changed")
if m.get("tests_unproven") != 0:
    why.append(f"{m.get('tests_unproven')} changed test file(s) had no compile evidence")
bare = [r.get("path") for r in m.get("evidence", []) if r.get("evidence") not in ("log", "cache", "fallback")]
if bare:
    why.append("no compile evidence for: " + ", ".join(bare))
if m.get("gate_exit") != 0:
    why.append(f"the gate itself exited {m.get('gate_exit')}")
if why:
    print("  NOT REUSABLE — that evidence does not cover this tree:")
    for w in why:
        print(f"    - {w}")
    sys.exit(1)
print("  REUSABLE — same iOS tree, clean, a complete green run, every changed test file evidenced")
print(f"    {m['notice10_line']}")
print(f"    gated at {m.get('gated_sha')} ({m.get('gated_branch')}); HEAD here is {os.environ.get('CUR_SHA')}")
print(f"    iOS tree {cur}")
sys.exit(0)
PY
}

# ── --selftest: prove the rule above, on log shapes, with no Xcode ───────────
# A gate that lied is being repaired; the repair owes proof that it no longer
# does. These fixtures go through notice10_select() itself, not a copy of it.
# ── #9659 self-test: compile provenance, no Xcode ─────────────────────────────
# A named function so `--selftest` and the fast `--selftest-provenance` (which
# the CI guard drives) run the SAME cases. Real git, a real DerivedData layout
# (spaces and all, copied from a live run), and a FAKE xcodebuild only where a
# run is needed — so the fallback's plan, argv, proof and ledger write are all
# exercised through run_compile_fallback itself, not described.
selftest_provenance () {
  say "--selftest — #9659 compile provenance (no xcodebuild; a fake one where a run is needed)"
  PV="$(mktemp -d)"
  _pv_tab="$(printf '\t')"
  pv_ok () { # name actual expected
    if [ "$2" = "$3" ]; then echo "  ok    $1 -> ${2:-<empty>}"
    else echo "  FAIL  $1 -> got \"$2\", wanted \"$3\""; ST_FAIL=1; fi
  }
  pv_has () { # name haystack needle
    case "$2" in *"$3"*) echo "  ok    $1" ;;
      *) echo "  FAIL  $1 -> \"$2\" does not contain \"$3\""; ST_FAIL=1 ;; esac
  }
  pv_lacks () { # name haystack needle
    case "$2" in *"$3"*) echo "  FAIL  $1 -> \"$2\" contains \"$3\""; ST_FAIL=1 ;;
      *) echo "  ok    $1" ;; esac
  }
  pv_git () { git -C "$GATE_ROOT" -c user.email=gate@selftest -c user.name=gate "$@"; }

  # ── a tree shaped like this repo ──
  GATE_ROOT="$PV/tree"
  _pv_t="$GATE_ROOT/ios/Bain Luck/BainLuckTests"
  mkdir -p "$_pv_t"
  git init -q -b master "$GATE_ROOT"
  printf 'import XCTest\n@MainActor final class FooTests: XCTestCase {\n    func testA() {}\n}\n' > "$_pv_t/FooTests.swift"
  printf 'import XCTest\nfinal class BarTests:XCTestCase, @unchecked Sendable {\n}\n// final class GhostTests: XCTestCase {}\nfinal class NotATest: XCTestCaseLike {}\nclass Helper {}\n' > "$_pv_t/BarTests.swift"
  printf 'enum Fixtures { static let x = 1 }\n' > "$_pv_t/Fixtures.swift"
  pv_git add -A; pv_git commit -q -m base
  FOO="ios/Bain Luck/BainLuckTests/FooTests.swift"
  BAR="ios/Bain Luck/BainLuckTests/BarTests.swift"
  FIX="ios/Bain Luck/BainLuckTests/Fixtures.swift"

  # ── a DerivedData with the real layout ──
  _pv_dd="$PV/DerivedData"
  _pv_obj="$_pv_dd/Build/Intermediates.noindex/Bain Luck.build/$TEST_CONFIG_DIR/$TEST_TARGET.build/Objects-normal/arm64"
  mkdir -p "$_pv_obj"
  _pv_map="$_pv_obj/$TEST_TARGET-OutputFileMap.json"
  python3 - "$_pv_map" "$GATE_ROOT" "$_pv_obj" <<'PY'
import json, sys
out, root, obj = sys.argv[1:]
base = root + "/ios/Bain Luck/BainLuckTests/"
m = {"": {"swift-dependencies": obj + "/BainLuckTests-primary.swiftdeps"}}
for n in ("FooTests", "BarTests", "Fixtures"):
    m[base + n + ".swift"] = {"object": f"{obj}/{n}.o", "swift-dependencies": f"{obj}/{n}.swiftdeps"}
json.dump(m, open(out, "w"))
PY
  # Sources at T, objects a minute later: a clean incremental state.
  touch -t 202609290000 "$_pv_t/FooTests.swift" "$_pv_t/BarTests.swift" "$_pv_t/Fixtures.swift"
  for _pv_n in FooTests BarTests Fixtures; do : > "$_pv_obj/$_pv_n.o"; touch -t 202609290001 "$_pv_obj/$_pv_n.o"; done
  # The map as xcodebuild prints it: inside the SwiftDriver command, spaces escaped.
  printf '    builtin-Swift-Compilation -- /x/swiftc -module-name BainLuckTests -output-file-map %s -use-frontend-parseable-output\n' \
    "$(printf '%s' "$_pv_map" | sed 's/ /\\ /g')" > "$PV/incremental.log"

  # ── rule 2: the map comes from THIS run's log, and only if it is unambiguous ──
  test_file_map_from_log "$PV/incremental.log"
  pv_ok "the map is read from the log, escaped spaces undone" "$OFM_MAP" "$_pv_map"
  { cat "$PV/incremental.log"; printf '    -output-file-map /elsewhere/%s-OutputFileMap.json\n' "$TEST_TARGET"; } > "$PV/two-maps.log"
  test_file_map_from_log "$PV/two-maps.log"
  pv_ok "two different maps in one log -> neither is trusted" "${OFM_MAP:-none} ($OFM_COUNT)" "none (2)"
  test_file_map_from_log "$PV/no-such.log"
  pv_ok "no log -> no map" "${OFM_MAP:-none}" none

  # ── the ledger learns from a run that saw the file compiled ──
  record_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" selftestsha0
  pv_ok "a file seen compiled is recorded" "$RECORDED" 1
  pv_ok "the ledger lives beside the DerivedData it describes" "$(ledger_for_map "$_pv_map")" "$_pv_dd/bainluck-compile-evidence.tsv"

  # ── the six rules ──
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "recorded content, current object, green run -> CACHED" "$CACHE_OK" 1
  pv_has "...and the reason names the identity" "$CACHE_WHY" "was seen compiled into FooTests.o"

  cached_compile_evidence "$GATE_ROOT" "$BAR" "$_pv_map" PASS_LINE
  pv_ok "current object, but no gate run ever saw it compiled -> insufficient" "$CACHE_OK" 0
  pv_has "...named as missing identity" "$CACHE_WHY" "no recorded identity"
  # ANTI-VACUITY: BarTests passes rules 1-5, so the case above fails on rule 6 alone.
  pv_ok "...(its object IS newer than its source: only the ledger refused it)" \
    "$([ "$(mtime_of "$_pv_obj/BarTests.o")" -ge "$(mtime_of "$_pv_t/BarTests.swift")" ] && echo yes)" yes

  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PARTIAL
  pv_ok "rule 1: a run that did not finish green vouches for nothing" "$CACHE_OK" 0
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" SUITE_FAILED
  pv_ok "rule 1: nor does a run that finished red" "$CACHE_OK" 0
  cached_compile_evidence "$GATE_ROOT" "$FOO" "" PASS_LINE
  pv_ok "rule 2: no map in the log -> insufficient" "$CACHE_OK" 0

  _pv_rel="$_pv_dd/Build/Intermediates.noindex/Bain Luck.build/Release-iphonesimulator/$TEST_TARGET.build/Objects-normal/arm64"
  mkdir -p "$_pv_rel"; cp "$_pv_map" "$_pv_rel/"
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_rel/$TEST_TARGET-OutputFileMap.json" PASS_LINE
  pv_ok "rule 3: a Release map is not this run's configuration" "$CACHE_OK" 0
  pv_has "...said as a configuration mismatch" "$CACHE_WHY" "not for $TEST_TARGET in $TEST_CONFIG_DIR"

  mkdir -p "$PV/other"; cp -R "$GATE_ROOT/." "$PV/other/"
  cached_compile_evidence "$PV/other" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "rule 4: the same relative file in ANOTHER tree is not in this map" "$CACHE_OK" 0
  pv_has "...said as a membership/tree mismatch" "$CACHE_WHY" "not in the run's $TEST_TARGET map"

  mv "$_pv_obj/FooTests.o" "$PV/FooTests.o.aside"
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "rule 4: the map names an object that is gone -> insufficient" "$CACHE_OK" 0
  mv "$PV/FooTests.o.aside" "$_pv_obj/FooTests.o"

  touch -t 202609290002 "$_pv_t/FooTests.swift"
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "rule 5: source edited after its object -> stale" "$CACHE_OK" 0
  pv_has "...said as stale" "$CACHE_WHY" "stale"

  # THE HOLE RULE 6 EXISTS FOR: new content, old mtime (cp -p, rsync -a, tar).
  # Xcode's own rule is fooled — the object reads newer — and the identity is not.
  echo "// edited, then its mtime put back" >> "$_pv_t/FooTests.swift"
  touch -t 202609290000 "$_pv_t/FooTests.swift"
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "rule 6: changed content behind a preserved mtime -> insufficient" "$CACHE_OK" 0
  pv_ok "...(and the mtime rule alone WOULD have passed it)" \
    "$([ "$(mtime_of "$_pv_obj/FooTests.o")" -ge "$(mtime_of "$_pv_t/FooTests.swift")" ] && echo yes)" yes
  pv_git checkout -q -- "$FOO"; touch -t 202609290000 "$_pv_t/FooTests.swift"
  cached_compile_evidence "$GATE_ROOT" "$FOO" "$_pv_map" PASS_LINE
  pv_ok "...and restoring the recorded content restores the evidence" "$CACHE_OK" 1

  # ── which tests the fallback may run ──
  pv_ok "classes: attribute + final" "$(xctest_classes "$_pv_t/FooTests.swift")" FooTests
  pv_ok "classes: no space, extra conformance; comment, lookalike, helper skipped" \
    "$(xctest_classes "$_pv_t/BarTests.swift" | tr '\n' ' ')" "BarTests "
  pv_ok "classes: a helper file declares none" "$(xctest_classes "$_pv_t/Fixtures.swift")" ""
  fallback_plan "$GATE_ROOT" "$FOO
$FIX"
  pv_ok "plan: a test class present -> test mode" "$FB_MODE" test
  pv_ok "plan: selectors are that file's classes only" "${FB_ONLY[*]}" "-only-testing:$TEST_TARGET/FooTests"
  fallback_plan "$GATE_ROOT" "$FIX"
  pv_ok "plan: helpers only -> build-for-testing" "$FB_MODE" build-for-testing
  pv_ok "...with no selectors (an empty -only-testing set would run EVERYTHING)" "${#FB_ONLY[@]}" 0

  # ── reading a targeted run (shapes copied from a real -only-testing run) ──
  { echo "Test Suite 'Selected tests' started at 2026-09-29 11:51:39.510."
    echo "Test Suite 'Selected tests' passed at 2026-09-29 11:52:41.613."
    echo "${_pv_tab} Executed 11 tests, with 0 failures (0 unexpected) in 62.096 (62.102) seconds"
    echo "** TEST SUCCEEDED **"; } > "$PV/sel-pass.log"
  fallback_select "$PV/sel-pass.log" 0 test
  pv_ok "a green targeted run passes the fallback" "$FB_OK" 1
  notice10_select "$PV/sel-pass.log" 0
  pv_ok "...and is NEVER a notice-10 line (no 'All tests' summary)" "${LINE:-none}" none
  { echo "Test Suite 'Selected tests' passed at 2026-09-29 11:52:41.613."
    echo "${_pv_tab} Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds"
    echo "** TEST SUCCEEDED **"; } > "$PV/sel-zero.log"
  fallback_select "$PV/sel-zero.log" 0 test
  pv_ok "0 tests executed is a vacuous pass -> refused" "$FB_OK" 0
  { echo "Test Suite 'Selected tests' failed at 2026-09-29 11:52:41.613."
    echo "${_pv_tab} Executed 11 tests, with 2 failures (0 unexpected) in 62.096 (62.102) seconds"
    echo "** TEST FAILED **"; } > "$PV/sel-fail.log"
  fallback_select "$PV/sel-fail.log" 65 test
  pv_ok "a failing targeted run -> refused" "$FB_OK" 0
  fallback_select "$PV/sel-pass.log" 137 test
  pv_ok "a killed targeted run, whatever it printed -> refused" "$FB_OK" 0
  echo "** TEST BUILD SUCCEEDED **" > "$PV/bft.log"
  fallback_select "$PV/bft.log" 0 build-for-testing
  pv_ok "build-for-testing success -> passes" "$FB_OK" 1
  fallback_select "$PV/bft.log" 65 build-for-testing
  pv_ok "build-for-testing non-zero exit -> refused" "$FB_OK" 0

  # ── the whole sequence, through the REAL functions, against a fake xcodebuild ──
  _pv_fake="$PV/fake-xcodebuild"
  cat > "$_pv_fake" <<'FAKE'
#!/usr/bin/env bash
# Records its argv, "compiles" the basenames in FAKE_COMPILE (a line naming each
# in the test target, and a fresh object), then prints the outcome asked for.
printf '%s\n' "$@" > "$FAKE_ARGV"
mode="$1"
printf '    -output-file-map %s\n' "$(printf '%s' "$FAKE_MAP" | sed 's/ /\\ /g')"
for b in $FAKE_COMPILE; do
  echo "SwiftCompile normal arm64 Compiling\\ $b /x/BainLuckTests/$b (in target 'BainLuckTests' from project 'Bain Luck')"
  touch "$FAKE_OBJDIR/${b%.swift}.o"
done
if [ "$FAKE_OUTCOME" = fail ]; then
  echo "Test Suite 'Selected tests' failed at 2026-09-29 11:52:41.613."
  printf '\t Executed 3 tests, with 1 failure (0 unexpected) in 0.100 (0.100) seconds\n'
  echo "** TEST FAILED **"; exit 65
fi
if [ "$mode" = build-for-testing ]; then echo "** TEST BUILD SUCCEEDED **"; exit 0; fi
echo "Test Suite 'Selected tests' passed at 2026-09-29 11:52:41.613."
printf '\t Executed 3 tests, with 0 failures (0 unexpected) in 0.100 (0.100) seconds\n'
echo "** TEST SUCCEEDED **"
FAKE
  chmod +x "$_pv_fake"
  XCODEBUILD="$_pv_fake"; PROJECT="$GATE_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"; SCHEME="Bain Luck"
  UDID="SELFTEST-UDID"; SPM_FLAGS=(); STALL_LIMIT=30; WATCH_POLL_SECS=1; GATE_SHA=selftestsha1
  EVIDENCE_TSV="$PV/evidence.tsv"; : > "$EVIDENCE_TSV"; NO_FALLBACK=""
  export FAKE_ARGV="$PV/argv" FAKE_MAP="$_pv_map" FAKE_OBJDIR="$_pv_obj"

  # A. THE SHIP: one file cached, two insufficient. Only the two are rebuilt and
  #    only their tests run — the cached file's class is NOT in the argv.
  FAKE_COMPILE="BarTests.swift Fixtures.swift" FAKE_OUTCOME=pass \
    provenance_for_unseen "$GATE_ROOT" "$FOO
$BAR
$FIX" "$_pv_map" PASS_LINE "$PV/fb-a.txt" > "$PV/a.out"
  pv_ok "A: cached + fallback leave nothing unproven" "${STILL_UNSEEN:-nothing}" nothing
  pv_ok "A: the fallback ran" "$FB_RAN" 1
  _pv_argv="$(tr '\n' ' ' < "$PV/argv")"
  pv_has "A: it ran the insufficient file's tests" "$_pv_argv" "-only-testing:$TEST_TARGET/BarTests"
  pv_lacks "A: NOT the cached file's (no full rerun, no re-test of what is proven)" "$_pv_argv" "FooTests"
  pv_lacks "A: NOT a lookalike class" "$_pv_argv" "NotATest"
  pv_has "A: on the run's own simulator" "$_pv_argv" "id=SELFTEST-UDID"
  pv_ok "A: evidence rows are cache/fallback/fallback" \
    "$(cut -f3 "$EVIDENCE_TSV" | tr '\n' ' ')" "cache fallback fallback "
  cached_compile_evidence "$GATE_ROOT" "$BAR" "$_pv_map" PASS_LINE
  pv_ok "A: the ledger learned from the fallback — next run, BarTests is cached" "$CACHE_OK" 1

  # B-F start from an EMPTY ledger so nothing is cached.
  export NATIVE_GATES_EVIDENCE_LEDGER="$PV/empty-ledger.tsv"
  : > "$EVIDENCE_TSV"; rm -f "$PV/argv"
  FAKE_COMPILE="" FAKE_OUTCOME=pass \
    provenance_for_unseen "$GATE_ROOT" "$BAR" "$_pv_map" PASS_LINE "$PV/fb-b.txt" > "$PV/b.out"
  pv_ok "B: a file the fallback did not compile stays unproven" "$STILL_UNSEEN" "$BAR"
  pv_has "B: ...and says it is outside the target or unreached" "$(cat "$PV/b.out")" "not compiled even after touching"
  pv_ok "B: evidence row is none" "$(cut -f3 "$EVIDENCE_TSV")" none

  FAKE_COMPILE="BarTests.swift" FAKE_OUTCOME=fail \
    provenance_for_unseen "$GATE_ROOT" "$BAR" "$_pv_map" PASS_LINE "$PV/fb-c.txt" > "$PV/c.out"
  pv_ok "C: tests failing on fresh objects -> unproven" "$STILL_UNSEEN" "$BAR"
  pv_has "C: ...and called a REAL failure, not a proof gap" "$(cat "$PV/c.out")" "FAILED on freshly compiled objects"

  rm -f "$PV/argv"
  FAKE_COMPILE="BarTests.swift" FAKE_OUTCOME=pass \
    provenance_for_unseen "$GATE_ROOT" "$BAR" "$_pv_map" PARTIAL "$PV/fb-d.txt" > "$PV/d.out"
  pv_ok "D: a run that did not finish green gets no fallback" "$FB_RAN" 0
  pv_ok "D: ...no xcodebuild was started" "$([ -f "$PV/argv" ] && echo started || echo none)" none
  pv_ok "D: ...and the file stays unproven" "$STILL_UNSEEN" "$BAR"

  NO_FALLBACK=1
  FAKE_COMPILE="BarTests.swift" FAKE_OUTCOME=pass \
    provenance_for_unseen "$GATE_ROOT" "$BAR" "$_pv_map" PASS_LINE "$PV/fb-e.txt" > "$PV/e.out"
  pv_ok "E: --no-fallback leaves the file unproven" "$STILL_UNSEEN" "$BAR"
  pv_ok "E: ...and runs nothing" "$FB_RAN" 0
  NO_FALLBACK=""

  FAKE_COMPILE="Fixtures.swift" FAKE_OUTCOME=pass \
    provenance_for_unseen "$GATE_ROOT" "$FIX" "$_pv_map" PASS_LINE "$PV/fb-f.txt" > "$PV/f.out"
  pv_ok "F: a helper-only set is proven by build-for-testing" "${STILL_UNSEEN:-nothing}" nothing
  pv_ok "F: ...which is what was run" "$(head -1 "$PV/argv")" build-for-testing
  unset NATIVE_GATES_EVIDENCE_LEDGER

  # ── the manifest, and whether it can stand for another run ──
  BASE=master; GATE_SHA="$(git -C "$GATE_ROOT" rev-parse HEAD)"; GATE_BRANCH=master
  IOS_TREE_START="$(git -C "$GATE_ROOT" rev-parse HEAD:ios)"; IOS_DIRTY_START=""
  MAC_EXIT=0; TEST_EXIT=0; VERDICT=PASS_LINE; CHANGED_ERR=""; FAILED=0; TESTPROOF_UNSEEN=0
  LINE="Executed 2083 tests, with 0 failures (0 unexpected) in 27.902 (29.156) seconds"
  ALL_TESTS_LINE="$LINE"; GATE_T0=$(date +%s)
  printf '%s\t%s\t%s\t%s\n' "$FOO" b1 log "compiled in this run's log" "$BAR" b2 cache "identity" > "$EVIDENCE_TSV"
  write_manifest "$PV/good.json"
  pv_ok "manifest: written, and says what it tested" \
    "$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["ios_tree_start"], m["verdict"], len(m["evidence"]))' "$PV/good.json")" \
    "$IOS_TREE_START PASS_LINE 2"
  check_manifest "$GATE_ROOT" "$PV/good.json" > "$PV/cm.out"; _pv_rc=$?
  pv_ok "reuse: same clean iOS tree, green, all evidenced -> REUSABLE" "$_pv_rc" 0
  pv_has "reuse: ...and it prints the line it stands for" "$(cat "$PV/cm.out")" "Executed 2083 tests"

  echo "// later" >> "$_pv_t/Fixtures.swift"; pv_git commit -qam later
  check_manifest "$GATE_ROOT" "$PV/good.json" > "$PV/cm.out"; _pv_rc=$?
  pv_ok "reuse: a different iOS tree -> NOT reusable" "$_pv_rc" 1
  pv_has "reuse: ...said as a tree mismatch" "$(cat "$PV/cm.out")" "the iOS tree differs"
  pv_git reset -q --hard HEAD~1

  echo "// uncommitted" >> "$_pv_t/Fixtures.swift"
  check_manifest "$GATE_ROOT" "$PV/good.json" > /dev/null; _pv_rc=$?
  pv_ok "reuse: uncommitted iOS edits here -> NOT reusable" "$_pv_rc" 1
  pv_git checkout -q -- "$FIX"
  # File-system-synchronized groups compile an UNTRACKED Swift file, so it
  # changes what would be tested even though HEAD:ios does not move.
  echo "// new" > "$_pv_t/Untracked.swift"
  check_manifest "$GATE_ROOT" "$PV/good.json" > /dev/null; _pv_rc=$?
  pv_ok "reuse: an untracked Swift file here -> NOT reusable" "$_pv_rc" 1
  rm -f "$_pv_t/Untracked.swift"
  check_manifest "$GATE_ROOT" "$PV/good.json" > /dev/null; _pv_rc=$?
  pv_ok "reuse: ...(and clean again -> reusable, so the three refusals above are real)" "$_pv_rc" 0

  VERDICT=PARTIAL; LINE=""; TEST_EXIT=137; FAILED=1
  write_manifest "$PV/partial.json"
  check_manifest "$GATE_ROOT" "$PV/partial.json" > /dev/null; _pv_rc=$?
  pv_ok "reuse: evidence from a partial run -> NOT reusable" "$_pv_rc" 1
  VERDICT=PASS_LINE; LINE="$ALL_TESTS_LINE"; TEST_EXIT=0; FAILED=1; TESTPROOF_UNSEEN=1
  printf '%s\t%s\t%s\t%s\n' "$BAR" b2 none "fallback failed" > "$EVIDENCE_TSV"
  write_manifest "$PV/unproven.json"
  check_manifest "$GATE_ROOT" "$PV/unproven.json" > "$PV/cm.out"; _pv_rc=$?
  pv_ok "reuse: a changed test file with no evidence -> NOT reusable" "$_pv_rc" 1
  pv_has "reuse: ...naming the file" "$(cat "$PV/cm.out")" "BarTests.swift"
  FAILED=0; TESTPROOF_UNSEEN=0
  printf '%s\t%s\t%s\t%s\n' "$FOO" b1 log "compiled" > "$EVIDENCE_TSV"
  IOS_TREE_START="0000000000000000000000000000000000000000"
  write_manifest "$PV/moved.json"
  check_manifest "$GATE_ROOT" "$PV/moved.json" > "$PV/cm.out"; _pv_rc=$?
  pv_ok "reuse: the tree moved while that gate ran -> NOT reusable" "$_pv_rc" 1
  pv_has "reuse: ...said so" "$(cat "$PV/cm.out")" "changed while that gate was running"

  # ── section 3a itself needs a real build, so its wiring is pinned by text ──
  # Weaker than the behavioural cases above (it asserts text, not conduct); it is
  # here because the alternative for these two regressions is no guard at all:
  # the unseen files must reach provenance_for_unseen with THIS run's map and
  # verdict, and the verdict must exist before that call reads it.
  _pv_self="${BASH_SOURCE[0]}"
  _pv_call=$(/usr/bin/grep -n 'provenance_for_unseen "\$GATE_ROOT" "\$LOG_UNSEEN" "\$OFM_MAP" "\$VERDICT"' "$_pv_self" | head -1 | cut -d: -f1)
  _pv_sel=$(/usr/bin/grep -n '^notice10_select "\$TESTLOG" "\$TEST_EXIT"' "$_pv_self" | head -1 | cut -d: -f1)
  pv_ok "section 3a hands the unseen files to provenance_for_unseen with this run's map + verdict" \
    "$([ -n "$_pv_call" ] && echo yes || echo no)" yes
  pv_ok "...after notice10_select has set that verdict" \
    "$([ -n "$_pv_call" ] && [ -n "$_pv_sel" ] && [ "$_pv_sel" -lt "$_pv_call" ] && echo yes || echo no)" yes

  rm -rf "$PV"
}

if [ -n "$SELFTEST_PROVENANCE" ] && [ -z "$SELFTEST" ]; then
  ST_FAIL=0
  selftest_provenance
  say "done (--selftest-provenance) — $([ $ST_FAIL -eq 0 ] && echo 'all cases passed' || echo 'FAILURES ABOVE'); nothing was built"
  exit $ST_FAIL
fi

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

  # ── #2975: the stall watchdog, driven against children that really hang ────
  # Both arms run the REAL watch_for_stall against a REAL background process, so
  # the kill path is exercised rather than described. No Xcode: a `sleep` that
  # writes nothing is a perfect model of a deadlocked suite, and `printf` in a
  # loop is a perfect model of a slow but living one. The negative arm is the
  # load-bearing one — a watchdog that fires on a healthy run is worse than none,
  # because it would red every gate on this Mac at load 750.
  say "--selftest — #2975 stall watchdog (no xcodebuild; real children)"

  echo "  (the shell will print one 'Terminated: 15' line below — that is job"
  echo "   control reporting the child this arm is supposed to kill, not a failure)"
  : > "$ST_DIR/hang.log"
  set -m
  bash -c 'sleep 600' > "$ST_DIR/hang.log" 2>&1 &
  ST_HANG_PID=$!
  set +m
  ST_T0=$(date +%s)
  watch_for_stall "$ST_HANG_PID" "$ST_DIR/hang.log" 10
  ST_HANG_RC=$?
  ST_ELAPSED=$(( $(date +%s) - ST_T0 ))
  # 🔴 LIVENESS IS READ AND THE CHILD IS KILLED **BEFORE** `wait`, AND THE ORDER
  # IS THE WHOLE POINT. This arm first read liveness after an unconditional
  # `wait`, so a watchdog that reported the stall and failed to kill left `wait`
  # blocking for the child's full 600 s — the arm HUNG instead of failing. A guard
  # against hanging that can itself hang is not a guard. Found by this ship's own
  # battery: M2 (report, never kill) and M5 (never watch at all) both came back
  # REFUSED-HUNG rather than KILLED until this was reordered.
  if kill -0 "$ST_HANG_PID" 2>/dev/null; then
    ST_HANG_STATE=alive
    kill -KILL -"$ST_HANG_PID" 2>/dev/null || kill -KILL "$ST_HANG_PID" 2>/dev/null
  else
    ST_HANG_STATE=dead
  fi
  wait "$ST_HANG_PID" 2>/dev/null
  rc_check "a child whose log never grows is reported as STALLED" "$ST_HANG_RC" 1
  # The child must actually be GONE. A watchdog that returns 1 and leaves the
  # process running would still wedge the machine, and the return code alone
  # cannot tell the difference.
  rc_check "and the hung child is actually dead, not merely reported" "$ST_HANG_STATE" dead
  # ~10s limit + one 5s poll + the 5s TERM->KILL grace. A bound, not a target:
  # this only has to prove it does not sit there for the 600s the child asked for.
  if [ "$ST_ELAPSED" -lt 60 ]; then
    rc_check "and it gave up in seconds, not in the child's own 600" fast fast
  else
    rc_check "and it gave up in seconds, not in the child's own 600" "${ST_ELAPSED}s" fast
  fi

  : > "$ST_DIR/alive.log"
  set -m
  bash -c 'for i in $(seq 1 12); do printf "line %s\n" "$i"; sleep 1; done' > "$ST_DIR/alive.log" 2>&1 &
  ST_ALIVE_PID=$!
  set +m
  watch_for_stall "$ST_ALIVE_PID" "$ST_DIR/alive.log" 10
  ST_ALIVE_RC=$?
  wait "$ST_ALIVE_PID" 2>/dev/null
  rc_check "a child that keeps writing is left alone, even past the limit" "$ST_ALIVE_RC" 0
  rc_check "and it ran to completion (all 12 lines)" \
    "$(/usr/bin/grep -c '^line ' "$ST_DIR/alive.log")" 12

  # 🔴 THE ARM THAT SEPARATES "QUIET" FROM "STUCK", which the two above cannot.
  # The arms above only ever exercise a log that grows on EVERY poll or on NONE,
  # so a watchdog that trips on the first quiet poll — ignoring its limit
  # entirely — passes both of them. That mutant (M4: `elif true`) SURVIVED run 1
  # of this ship's battery, and it is the dangerous direction: on a Mac at load
  # 750 a healthy suite goes quiet for seconds at a time between classes, and a
  # watchdog like that would red every gate on the machine.
  #
  # So: a child that stops writing for 14 s — comfortably under its 30 s limit,
  # and long enough to be seen by two or three 5 s polls — then resumes and
  # finishes. Correct: untouched. M4: killed on the first quiet poll.
  : > "$ST_DIR/quiet.log"
  set -m
  bash -c 'printf "pre 1\n"; printf "pre 2\n"; sleep 14; for i in 1 2 3; do printf "post %s\n" "$i"; sleep 1; done' \
    > "$ST_DIR/quiet.log" 2>&1 &
  ST_QUIET_PID=$!
  set +m
  watch_for_stall "$ST_QUIET_PID" "$ST_DIR/quiet.log" 30
  ST_QUIET_RC=$?
  if kill -0 "$ST_QUIET_PID" 2>/dev/null; then
    kill -KILL -"$ST_QUIET_PID" 2>/dev/null || kill -KILL "$ST_QUIET_PID" 2>/dev/null
  fi
  wait "$ST_QUIET_PID" 2>/dev/null
  rc_check "a child quiet for 14s under a 30s limit is NOT killed" "$ST_QUIET_RC" 0
  rc_check "and it got to write again after the quiet spell" \
    "$(/usr/bin/grep -c '^post ' "$ST_DIR/quiet.log")" 3

  # ── the recompile proof's INPUT: which files changed ───────────────────────
  # Real throwaway repositories, because the bug was a claim ABOUT git that git
  # disagreed with — a fixture that mocked git would have agreed with the claim.
  say "--selftest — resolve_changed_swift: shallow is not the same as baseless"

  st_git () { _d="$1"; shift; git -C "$_d" -c user.email=gate@selftest -c user.name=gate "$@"; }
  st_commit () { st_git "$1" add -A; st_git "$1" commit -q -m "$2"; }

  ST_UP="$ST_DIR/upstream"
  mkdir -p "$ST_UP/ios"
  git init -q -b master "$ST_UP"
  echo "// one" > "$ST_UP/ios/A.swift"; st_commit "$ST_UP" one
  echo "// two" > "$ST_UP/ios/B.swift"; st_commit "$ST_UP" two

  # A. THE REGRESSION: a shallow clone whose base resolves fine. This is every
  #    lane worktree on this machine after a notice-47a rebase.
  ST_SHALLOW="$ST_DIR/shallow"
  git clone -q --depth 1 "file://$ST_UP" "$ST_SHALLOW" 2>/dev/null
  st_git "$ST_SHALLOW" checkout -q -b work
  echo "// changed" >> "$ST_SHALLOW/ios/A.swift"; st_commit "$ST_SHALLOW" work

  # ANTI-VACUITY FIRST: if the clone is not actually shallow, case A passes for
  # the wrong reason and says nothing about the defect.
  rc_check "fixture A really is a shallow clone" \
    "$(git -C "$ST_SHALLOW" rev-parse --is-shallow-repository)" true

  resolve_changed_swift "$ST_SHALLOW" origin/master
  rc_check "shallow + resolvable base -> no error (the #4838 gate run)" "${CHANGED_ERR:-none}" none
  rc_check "...and it names the changed file" "$CHANGED" "ios/A.swift"

  # B. A GENUINELY BASELESS repo, not shallow: the error must survive the fix.
  ST_NOBASE="$ST_DIR/nobase"
  mkdir -p "$ST_NOBASE/ios"
  git init -q -b master "$ST_NOBASE"
  echo "// root one" > "$ST_NOBASE/ios/A.swift"; st_commit "$ST_NOBASE" one
  st_git "$ST_NOBASE" checkout -q --orphan lonely
  echo "// root two" > "$ST_NOBASE/ios/C.swift"; st_commit "$ST_NOBASE" two

  resolve_changed_swift "$ST_NOBASE" master
  if [ -n "$CHANGED_ERR" ] && [ "${CHANGED_ERR#*no merge base}" != "$CHANGED_ERR" ]; then
    echo "  ok    unrelated histories -> still refused, by name"
  else
    echo "  FAIL  unrelated histories -> got \"${CHANGED_ERR:-<empty>}\""; ST_FAIL=1
  fi
  if [ "${CHANGED_ERR#*SHALLOW}" = "$CHANGED_ERR" ]; then
    echo "  ok    ...and it does not blame shallowness on a repo that is not shallow"
  else
    echo "  FAIL  ...but it blamed shallowness on a full clone"; ST_FAIL=1
  fi

  # C. #5428's OWN CASE: shallow AND baseless. The unshallow remedy is the whole
  #    value of that issue and must still be printed.
  st_git "$ST_SHALLOW" checkout -q --orphan stranded
  echo "// stranded" > "$ST_SHALLOW/ios/D.swift"; st_commit "$ST_SHALLOW" stranded
  resolve_changed_swift "$ST_SHALLOW" origin/master
  if [ "${CHANGED_ERR#*fetch --unshallow}" != "$CHANGED_ERR" ]; then
    echo "  ok    shallow AND baseless -> the #5428 remedy is still offered"
  else
    echo "  FAIL  shallow AND baseless -> lost the unshallow remedy: \"${CHANGED_ERR:-<empty>}\""; ST_FAIL=1
  fi

  selftest_provenance

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

# The iOS tree this run tests, read BEFORE anything builds (#9659). The manifest
# compares it with the tree at the end, so an edit made mid-run cannot hide.
GATE_T0=$(date +%s)
IOS_TREE_START="$(git -C "$GATE_ROOT" rev-parse HEAD:ios 2>/dev/null)"
IOS_DIRTY_START="$(git -C "$GATE_ROOT" status --porcelain --untracked-files=all -- ios 2>/dev/null | head -1)"
echo "  iOS tree      : ${IOS_TREE_START:-UNKNOWN}$([ -n "$IOS_DIRTY_START" ] && echo "  + UNCOMMITTED iOS changes (evidence from this run is not reusable)")"

if [ -n "$CHECK_MANIFEST" ]; then
  say "can the evidence in $CHECK_MANIFEST stand for this tree? (#9659)"
  check_manifest "$GATE_ROOT" "$CHECK_MANIFEST"
  CM_EXIT=$?
  say "done (--check-manifest) — nothing was built"
  exit $CM_EXIT
fi

mkdir -p "$LOGDIR"
FAILED=0
EVIDENCE_TSV="$LOGDIR/evidence.tsv"
: > "$EVIDENCE_TSV"
# Initialised here, not in section 3a: under `set -u` the summary reads it even
# on the paths where that section never runs (--build-only, no changed tests).
TESTPROOF_UNSEEN=0

# ── 0b. CHANGED SWIFT FILES — computed ONCE, and never silently empty ────────
resolve_changed_swift "$GATE_ROOT" "$BASE"

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
  say "a changed test file this run's log does not show compiled (#9659)"
  echo "  1. cached evidence, only with an identity: green run, this log's own"
  echo "     test-target output-file map ($TEST_CONFIG_DIR), the exact path in this tree,"
  echo "     an object not older than the source, and a ledger row for this content;"
  echo "  2. otherwise ONE bounded fallback: those files recompiled, only their"
  echo "     XCTestCase classes run ('Selected tests' — never the notice-10 line);"
  echo "  3. otherwise the file is unproven and the gate fails. Never a full rerun."
  say "done (--explain) — nothing was built"
  exit 0
fi

# ── 0. THE SPM STORE (gotcha #117) ───────────────────────────────────────────
#
# A FRESH WORKTREE HAS NO RESOLVED SPM CHECKOUT, AND THIS GATE COULD NOT BE RUN
# IN ONE (native/233c, 2026-09-18). Both invocations below re-resolved the
# package graph from scratch, and two Firebase BINARY targets are zips fetched
# from dl.google.com — which this sandbox cannot reach. Measured twice on the
# B16 snapshot worktree: `Could not resolve package dependencies … downloadError
# ("The request timed out.")`, EXIT 74 on the macOS build AND on the test run.
#
# 74 is the failure mode this whole file exists to prevent: it is not a compile
# error and not a test result, and the summary printed `macOS build: FAIL` for a
# build that never started. `scripts/ios_native_gate.sh` has borrowed master's
# store since #117 was banked; this script never did, so the gate was unusable
# in exactly the isolated worktree an archive candidate is validated in.
#
# Override with BAINLUCK_SPM_STORE, same variable the other gate reads. If the
# store is absent the flag is simply not passed — resolving normally is correct
# on a machine with egress, and a hard failure here would break the common case.
SPM_STORE="${BAINLUCK_SPM_STORE:-$HOME/Library/Developer/Xcode/DerivedData/Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages}"
SPM_FLAGS=()
if [ -d "$SPM_STORE" ]; then
  SPM_FLAGS=(-clonedSourcePackagesDirPath "$SPM_STORE")
  echo "  SPM store  : $SPM_STORE"
else
  echo "  SPM store  : none at $SPM_STORE — resolving packages normally"
fi

# ── 1. THE macOS BUILD ───────────────────────────────────────────────────────
say "macOS build (the target that went dark for five days)"
MACLOG="$LOGDIR/macos-build.txt"
MAC_T0=$(date +%s)
"$XCODEBUILD" build \
  -project "$PROJECT" -scheme "$SCHEME" \
  -destination 'platform=macOS,arch=arm64' \
  ${SPM_FLAGS[@]+"${SPM_FLAGS[@]}"} \
  OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$MACLOG" 2>&1
MAC_EXIT=$?
MAC_SECS=$(( $(date +%s) - MAC_T0 ))
echo "EXIT CODE: $MAC_EXIT   log: $MACLOG   (${MAC_SECS}s)"
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
#
# 🔴 THIS WAS THE SIXTH ENTRYPOINT (native/233c, 2026-09-18). The pick used to be
# `simctl list … | head -1` with NO reserved filter, in the one rig tool that
# INSTALLS A TEST BUNDLE — so the guard covering five shoot tools and the other
# gate did not cover the one that writes to a device. It was safe only by the
# order `simctl` happens to list in (`iPhone 17 Pro`, the disposable, is oldest);
# delete or re-create one device and the next gate run installs onto whichever
# iPhone sorts first, which can be either of Alex's signed-in phones.
#
# It was invisible for the same reason the scalar was: the self-test's own
# entrypoint list did not name this file. Both are fixed together — a guard that
# does not know about a caller is not guarding it.
say "BainLuckTests"
. "$(dirname "$0")/reserved-sim-guard.sh"
UDID=$(bl_default_shoot_sim)
SIMNAME=$(xcrun simctl list devices available 2>/dev/null \
  | /usr/bin/grep -F "$UDID" | sed -E 's/^[[:space:]]+//; s/ \(.*//')

if [ -z "$UDID" ]; then
  echo "  NO DISPOSABLE iPhone SIMULATOR AVAILABLE — cannot run BainLuckTests here."
  echo "  (Every available iPhone is reserved, or there is none at all. This gate"
  echo "   installs a test bundle, so it will not borrow a reserved device.)"
  exit 1
fi
# Belt and braces: the picker already excludes the whole reserved set, so this
# can only fire if someone reintroduces a bespoke pick above.
bl_refuse_reserved_sim "$UDID" native-gates.sh
echo "  simulator: $SIMNAME  ($UDID)"

TESTLOG="$LOGDIR/tests.txt"

# ── A HANG IS NOT A RESULT, AND UNTIL NOW NOTHING HERE HAD A BOUND (#2975) ────
#
# #5591 made a killed run unable to print a green pass line. It did not make the
# run END. `xcodebuild test` ran in the foreground with no limit, so a suite that
# deadlocked simply never returned and the lane sat on a dead process until a
# human noticed — twice now on one test (#2975: 2026-09-03, and 2026-09-16 at
# 995/2513, ten minutes of silence). Notice 10's iOS clause means no line and so
# no self-merge: the lane is blocked, silently, by a test unrelated to its ship.
#
# The bound is on PROGRESS, not on wall-clock. A healthy run of this suite takes
# 35-140 s here, but this Mac reaches load average 750 with ten lanes building,
# and a wall-clock cap generous enough to survive that is too generous to catch
# anything. The log gains a line per test start and per pass, so silence is the
# signal that separates "slow" from "stuck": a stalled run is killed and SAID,
# and #5591's machinery then reports it as the partial run it is.
STALL_LIMIT=${NATIVE_GATES_STALL_LIMIT:-300}
# `set -m` so the child becomes a PROCESS GROUP LEADER. Without it a background
# job in a non-interactive shell shares the script's group, `kill -- -$PID` finds
# no such group, and killing the leader alone orphans the xcodebuild children
# that are holding the simulator — the stall would be reported and the machine
# would keep the hung run. macOS ships no `setsid`; this is the portable form.
TEST_T0=$(date +%s)
set -m
"$XCODEBUILD" test \
  -project "$PROJECT" -scheme "$SCHEME" \
  -destination "id=$UDID" \
  ${SPM_FLAGS[@]+"${SPM_FLAGS[@]}"} \
  OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$TESTLOG" 2>&1 &
XCB_PID=$!
set +m
watch_for_stall "$XCB_PID" "$TESTLOG" "$STALL_LIMIT"
TEST_STALLED=$?
wait "$XCB_PID" 2>/dev/null
TEST_EXIT=$?
TEST_SECS=$(( $(date +%s) - TEST_T0 ))
echo "EXIT CODE: $TEST_EXIT   log: $TESTLOG   (${TEST_SECS}s)"
if [ "$TEST_STALLED" -eq 1 ]; then
  FAILED=1
  echo "  STALLED — the log did not grow for ${STALL_LIMIT}s, so this run was KILLED (#2975)."
  echo "    last test to start, which is the one that hung:"
  /usr/bin/grep "' started\.\$" "$TESTLOG" 2>/dev/null | tail -1 | sed 's/^/      /'
  echo "    This is NOT a verdict on your change — it is the suite failing to finish."
  echo "    Re-run; if the same test names itself twice, that test is the bug."
fi

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
#
# #9659: NOT SEEN in this log is not yet "not covered". An incremental run skips
# files an earlier run compiled, so the unseen ones go through
# provenance_for_unseen: cached evidence with an identity, else ONE bounded
# fallback over just those files. Only what survives both is unproven.
# The pass-line selection is read first because the provenance step needs to
# know whether this run finished green; it is pure and prints nothing.
notice10_select "$TESTLOG" "$TEST_EXIT"
if [ -n "$CHANGED_TESTS" ] && [ -z "$CHANGED_ERR" ]; then
  say "recompile proof — were your changed TEST files compiled by that run?"
  prove_test_sources "$CHANGED_TESTS" "$TESTLOG"
  LOG_SEEN="$PROOF_SEEN_FILES"
  LOG_UNSEEN="$PROOF_UNSEEN_FILES"
  evidence_rows "$LOG_SEEN" log "compiled in this run's log"
  test_file_map_from_log "$TESTLOG"
  # The ledger learns from every run that reached the end of the suite, so the
  # NEXT incremental run can vouch for these files without recompiling them.
  if [ -n "$ALL_TESTS_LINE" ] && [ -n "$LOG_SEEN" ]; then
    record_compile_evidence "$GATE_ROOT" "$LOG_SEEN" "$OFM_MAP" "$GATE_SHA"
  fi
  if [ -n "$LOG_UNSEEN" ]; then
    say "provenance — the files this log did not show compiled (#9659)"
    provenance_for_unseen "$GATE_ROOT" "$LOG_UNSEEN" "$OFM_MAP" "$VERDICT" "$LOGDIR/fallback.txt"
  else
    STILL_UNSEEN=""
  fi
  TESTPROOF_UNSEEN=$(printf '%s' "$STILL_UNSEEN" | /usr/bin/grep -c .)
  if [ "$TESTPROOF_UNSEEN" -gt 0 ]; then
    # Unlike the app-target case this has no innocent reading: a changed file
    # under BainLuckTests/ that nothing could show compiled — not this log, not
    # an identified cached object, not the fallback — is either outside the
    # target or was never reached, and either way the suite total below does
    # not cover the lines you changed.
    FAILED=1
    echo "      → under BainLuckTests/, and no compile evidence exists for it:"
    printf '%s\n' "$STILL_UNSEEN" | sed 's|.*/|          |'
    echo "        The suite count below does NOT cover your change (#5635, #9659)."
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
# evidence that explicitly must not be pasted. (notice10_select ran above,
# before section 3a, which needs its verdict.)

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
  echo "    $TESTPROOF_UNSEEN changed test file(s) have no compile evidence — not in this log, no"
  echo "    identified cached object, and no passing fallback. The reason per file is printed"
  echo "    under 'provenance' above (#9659)."
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
if [ -s "$EVIDENCE_TSV" ]; then
  _ev () { awk -F'\t' -v k="$1" '$3==k' "$EVIDENCE_TSV" | /usr/bin/grep -c .; }
  echo "  test evidence: $(_ev log) compiled in this log · $(_ev cache) cached, identified · $(_ev fallback) by the bounded fallback · $(_ev none) none"
fi
echo "  logs: $LOGDIR"
# #9659: the handoff is this one file. `--check-manifest <it>` on an identical,
# clean iOS tree says whether this evidence can stand without a rerun.
write_manifest "$LOGDIR/manifest.json" && echo "  manifest: $LOGDIR/manifest.json"
exit $FAILED
