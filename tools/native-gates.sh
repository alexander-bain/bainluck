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
# ═══ USAGE ═══
#
#   tools/native-gates.sh              # both gates, diff measured vs origin/master
#   tools/native-gates.sh --build-only # just the macOS build + recompile proof
#   tools/native-gates.sh --base <ref> # measure the diff against another ref
#
# Exit 0 only when every gate it ran passed. Logs are left in $TMPDIR for reading;
# their paths are printed. Gotcha #54: a gate is never piped, its exit code is
# captured and reported as a VALUE.

set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../ios/Bain Luck" && pwd)"
PROJECT="$PROJECT_DIR/Bain Luck.xcodeproj"
SCHEME="Bain Luck"
SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'
LOGDIR="${TMPDIR:-/tmp}/native-gates-$$"
BASE="origin/master"
BUILD_ONLY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=1 ;;
    --base) BASE="${2:?--base needs a ref}"; shift ;;
    -h|--help) sed -n '1,60p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$LOGDIR"
FAILED=0

say () { printf '\n=== %s\n' "$*"; }

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
  CHANGED=$(git diff --name-only "$BASE"...HEAD -- '*.swift' 2>/dev/null; git diff --name-only -- '*.swift'; git ls-files --others --exclude-standard -- '*.swift')
  CHANGED=$(printf '%s\n' "$CHANGED" | sed '/^$/d' | sort -u)
  if [ -z "$CHANGED" ]; then
    echo "  no changed Swift files vs $BASE — nothing to prove"
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
else
  echo "  NO 'Executed N tests' LINE IN THE LOG — the suite never ran."
  echo "  That is a harness story, not a test result. Read $TESTLOG."
fi
if [ $TEST_EXIT -ne 0 ]; then
  FAILED=1
  /usr/bin/grep -E "^.*: error:|failed \(" "$TESTLOG" | head -20 | sed 's/^/    /'
fi

say "SUMMARY"
echo "  macOS build : $([ $MAC_EXIT -eq 0 ] && echo PASS || echo "FAIL (exit $MAC_EXIT)")"
echo "  BainLuckTests: $([ $TEST_EXIT -eq 0 ] && echo PASS || echo "FAIL (exit $TEST_EXIT)")   ${LINE:-}"
echo "  logs: $LOGDIR"
exit $FAILED
