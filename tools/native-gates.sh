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
# ═══ USAGE ═══
#
#   tools/native-gates.sh              # both gates, diff measured vs origin/master
#   tools/native-gates.sh --build-only # just the macOS build + recompile proof
#   tools/native-gates.sh --base <ref> # measure the diff against another ref
#   tools/native-gates.sh --explain    # resolve tree/sha/diff and STOP. No xcodebuild.
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
PROJECT_ROOT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=1 ;;
    --explain) EXPLAIN=1 ;;
    --base) BASE="${2:?--base needs a ref}"; shift ;;
    --project-root) PROJECT_ROOT="${2:?--project-root needs a path}"; shift ;;
    -h|--help) sed -n '1,85p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

say () { printf '\n=== %s\n' "$*"; }

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

# THE LINE STANDING NOTICE 10 WANTS IN THE PR BODY, printed verbatim.
LINE=$(/usr/bin/grep -E "^[[:space:]]+Executed [0-9]+ tests, with .* failures" "$TESTLOG" | tail -1 | sed 's/^[[:space:]]*//')
if [ -n "$LINE" ]; then
  echo "  $LINE"
  echo "  ^ paste this line into the PR body — notice 10's iOS clause requires it"
  echo "    it is the count for $GATE_SHA ($GATE_BRANCH) in $GATE_ROOT"
  echo "    — if that is not the sha you are shipping, do not paste it (#5480)"
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
echo "  BainLuckTests: $([ $TEST_EXIT -eq 0 ] && echo PASS || echo "FAIL (exit $TEST_EXIT)")   ${LINE:-}"
echo "  logs: $LOGDIR"
exit $FAILED
