#!/bin/bash
# native/089 — prove the iPhone app can actually be ARCHIVED, not just built.
#
# WHY THIS EXISTS
# ---------------
# CI compiles no Swift at all (standing notice 10), and every Swift gate we do
# run — `xcodebuild build` for the simulator, `xcodebuild test` — is a **Debug**
# build. Debug runs no optimizer. Swift 6.3.3's `EarlyPerfInliner` crashes while
# inlining into the synthesized deallocating destructor of a generic class, which
# only happens at `-O`, so on 2026-09-09 master `421bdc36` was in a state where:
#
#   * every simulator build passed,
#   * `BainLuckTests` passed 1700+,
#   * CI was green,
#   * and `xcodebuild archive` could not produce a binary at all.
#
# The app had not been archivable for however long those classes had existed and
# nothing in the repo could tell. TestFlight is the D106 ship; this is its gate.
#
# THE TRAP THIS SCRIPT IS BUILT AROUND (gotcha #124)
# --------------------------------------------------
# `xcodebuild archive` exited **0** on the crashing build and printed
# "Archiving project" and "(2 failures)" in the same log. There was no
# `.xcarchive` on disk. So the exit code is NOT the pass condition and never was:
# this script grades the ARTIFACT — the archive directory, the .app inside it,
# and its Info.plist — and greps the log for compiler crashes independently.
# A check that read `$?` would have called the broken tree green.
#
# USAGE
#   tools/native-release-check.sh            # archive + grade, log to /tmp
#   NATIVE_RELEASE_LOG=/path/x.txt tools/...  # choose the log path
#
# Exit 0 only when a real archive containing a real signed .app exists.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$REPO_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
LOG="${NATIVE_RELEASE_LOG:-/tmp/native-release-check.txt}"
ARCHIVE="${NATIVE_RELEASE_ARCHIVE:-/tmp/BainLuck-release-check.xcarchive}"

if [ ! -d "$PROJECT" ]; then
  echo "FAIL: no project at $PROJECT" >&2
  exit 2
fi

echo "==> archiving (Release, generic/platform=iOS); log: $LOG"
rm -rf "$ARCHIVE"

# OTHER_SWIFT_FLAGS is NOT optional (gotcha #50): without it the build dies on a
# #Preview macro the compiler sandbox refuses to expand, in the widget target.
xcodebuild \
  -project "$PROJECT" \
  -scheme "Bain Luck" \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE" \
  -disableAutomaticPackageResolution \
  OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
  archive > "$LOG" 2>&1
RAW_EXIT=$?

fail=0
note() { echo "  $1"; }

# 1. Compiler crashes. Reported independently of the exit code, because the
#    crashing build exits 0.
# `grep -c` prints the count AND exits 1 when that count is zero, so the obvious
# `$(grep -c ... || echo 0)` yields the two-line string "0\n0", `[ -gt ]` then
# errors with "integer expression expected", and — because that error is not a
# non-zero test result — the crash check is silently SKIPPED. Caught on this
# script's own first run. Take grep's stdout as-is and default only when the file
# is missing entirely.
DUMPS=$(grep -c "Stack dump" "$LOG" 2>/dev/null)
DUMPS=${DUMPS:-0}
if [ "$DUMPS" -gt 0 ] 2>/dev/null; then
  fail=1
  echo "FAIL: $DUMPS swift-frontend crash(es) — the optimizer died."
  grep -n "While running pass\| for 'deinit'" "$LOG" | head -6 | sed 's/^/    /'
  note "If it names a deinit, a generic class lost its explicit destructor."
  note "See ReleaseBuildArchivabilityTests and MemoizedPresentation.deinit."
fi

# 2. The artifact. This is the real pass condition.
APP=""
if [ ! -d "$ARCHIVE" ]; then
  fail=1
  echo "FAIL: no archive at $ARCHIVE (xcodebuild exit was $RAW_EXIT — do not trust it)"
else
  APP=$(find "$ARCHIVE/Products/Applications" -maxdepth 1 -name '*.app' 2>/dev/null | head -1)
  if [ -z "$APP" ]; then
    fail=1
    echo "FAIL: archive exists but contains no .app"
  elif [ ! -f "$APP/Info.plist" ]; then
    fail=1
    echo "FAIL: $APP has no Info.plist"
  fi
fi

# 3. Ordinary build errors, reported after the two above so the headline is the
#    interesting failure rather than its fallout.
if grep -q "^.*error: " "$LOG" 2>/dev/null; then
  echo "note: build errors present:"
  grep "error: " "$LOG" | sort -u | head -8 | sed 's/^/    /'
fi

if [ "$fail" -ne 0 ]; then
  echo
  echo "RELEASE CHECK: FAIL  (log: $LOG)"
  exit 1
fi

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Info.plist" 2>/dev/null || echo "?")
BUILD=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$APP/Info.plist" 2>/dev/null || echo "?")
echo
echo "RELEASE CHECK: PASS"
echo "  archive : $ARCHIVE"
echo "  app     : $(basename "$APP")  version $VERSION ($BUILD)"
echo "  crashes : 0"
echo "  sha     : $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
exit 0
