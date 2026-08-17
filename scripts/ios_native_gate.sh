#!/usr/bin/env bash
#
# The canonical headless native gate. ONE implementation of the four flags and
# the three checks every iOS queue has been re-deriving by hand.
#
# Usage:
#   scripts/ios_native_gate.sh test [<device name>]     # build-for-testing + test
#   scripts/ios_native_gate.sh build [<device name>]    # build only
#   scripts/ios_native_gate.sh preflight [<device name>] # destination check alone
#
# It exists because of four banked gotchas that each cost a lane a cycle:
#
#   #116  a sandboxed `xcodebuild` dies expanding the SwiftUI `#Preview` macro
#         unless the compiler's own sandbox is disabled.
#   #117  a PROGRAM WORKTREE has no resolved SPM checkout, so the build tries to
#         re-resolve Firebase over blocked egress. It must borrow master's store.
#   #124  `$?` belongs to the LAST thing that ran. Never pipe the gate.
#   #135  a truncated run is byte-identical to a pass: no verdict line, zero
#         failures, green tail. Require the POSITIVE terminator.
#
# And one new one this script is the fix for (UX-P085, banked from the cycle-81
# directive):
#
#   A STALE DESTINATION EXITS 70 WITH NO VERDICT LINE — which is exactly what a
#   truncated run looks like. The `iPhone 16` simulator was removed from this
#   machine; every gate naming it failed in the shape of #135, so the reader's
#   correct #135 reflex ("the run was killed, re-run it") sent them to re-run a
#   command that could never work. A missing destination is a *typo class* of
#   failure wearing a *truncation class* of costume.
#
#   So the destination is RESOLVED TO A UDID BEFORE xcodebuild is invoked, and
#   the script refuses with a distinct exit code and the installed device list
#   if it cannot be. A named device is a claim about this machine; check it.

set -u

MODE="${1:-test}"
DEVICE="${2:-iPhone 17}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT="$REPO_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME="Bain Luck"

# #117: master's already-resolved package store. A worktree cannot afford its
# own resolution, so it borrows one. Overridable for a different machine.
SPM_STORE="${BAINLUCK_SPM_STORE:-$HOME/Library/Developer/Xcode/DerivedData/Bain_Luck-cwkxplfeuucvrvbplvqqlcgmpcgx/SourcePackages}"

# ---------------------------------------------------------------------------
# Preflight: resolve the destination to a UDID, or refuse.
# ---------------------------------------------------------------------------
preflight() {
    if [ ! -e "$PROJECT" ]; then
        echo "GATE PREFLIGHT FAILED: no project at $PROJECT" >&2
        return 3
    fi

    if [ ! -d "$SPM_STORE" ]; then
        echo "GATE PREFLIGHT FAILED: SPM store missing at $SPM_STORE" >&2
        echo "  gotcha #117 — a worktree borrows master's resolved packages." >&2
        echo "  Set BAINLUCK_SPM_STORE, or build once in ~/bainluck to create it." >&2
        return 4
    fi

    # Exact-name match against AVAILABLE devices only. `simctl list devices`
    # without `available` also lists unavailable runtimes, which would let an
    # unbootable device pass this check and fail identically inside xcodebuild.
    UDID="$(xcrun simctl list devices available 2>/dev/null \
        | sed -n "s/^ *${DEVICE} (\([0-9A-F-]\{36\}\)) (.*/\1/p" \
        | head -1)"

    if [ -z "$UDID" ]; then
        echo "GATE PREFLIGHT FAILED: no available simulator named '${DEVICE}'." >&2
        echo "" >&2
        echo "  This is the failure that impersonates a truncated run: xcodebuild" >&2
        echo "  exits 70 with NO '** TEST SUCCEEDED **' and NO '** TEST FAILED **'," >&2
        echo "  so gotcha #135's reflex reads it as a killed run and re-runs it." >&2
        echo "" >&2
        echo "  Installed and available:" >&2
        xcrun simctl list devices available 2>/dev/null | sed 's/^/    /' >&2
        return 5
    fi

    echo "PREFLIGHT OK: destination '${DEVICE}' -> ${UDID}"
    echo "PREFLIGHT OK: SPM store ${SPM_STORE}"
    return 0
}

preflight || exit $?
[ "$MODE" = "preflight" ] && exit 0

# ---------------------------------------------------------------------------
# The gate itself. Never piped (#124); verdict read from the log (#135).
# ---------------------------------------------------------------------------
LOG="${BAINLUCK_GATE_LOG:-/tmp/ios_gate_${MODE}.log}"

# The terminator depends on the ACTIONS, and getting this wrong is the same
# false-green class the check exists to prevent: `build-for-testing` emits
# `** TEST BUILD SUCCEEDED **` and `test-without-building` emits
# `** TEST EXECUTE SUCCEEDED **` — NEITHER of them is the `** TEST SUCCEEDED **`
# that a plain `test` action prints. Every terminator listed here must be
# present, so a run that builds but never executes cannot pass.
case "$MODE" in
    test)   ACTIONS="build-for-testing test-without-building"
            TERMINATORS='\*\* TEST BUILD SUCCEEDED \*\*|\*\* TEST EXECUTE SUCCEEDED \*\*'
            TERMINATOR_COUNT=2 ;;
    build)  ACTIONS="build"
            TERMINATORS='\*\* BUILD SUCCEEDED \*\*'
            TERMINATOR_COUNT=1 ;;
    *)      echo "unknown mode '$MODE' (want: test | build | preflight)" >&2 ; exit 2 ;;
esac

echo "GATE: xcodebuild $ACTIONS -> $LOG"

# shellcheck disable=SC2086
xcodebuild $ACTIONS \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -destination "id=${UDID}" \
    -clonedSourcePackagesDirPath "$SPM_STORE" \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    > "$LOG" 2>&1
GATE_EXIT=$?

echo "XCODEBUILD EXIT CODE: $GATE_EXIT"

# #124's third amendment: branch on the VALUE. 65/70 are xcodebuild's "I could
# not run" codes; 137/143 are a killed run. None of them is a test result.
FOUND_TERMINATORS=$(grep -cE "$TERMINATORS" "$LOG")

if [ "$GATE_EXIT" -ne 0 ] && [ "$GATE_EXIT" -ne 65 ]; then
    echo "VERDICT: NO RESULT (exit $GATE_EXIT is a story about the harness, not the code)"
elif [ "$GATE_EXIT" -eq 0 ] && [ "$FOUND_TERMINATORS" -ge "$TERMINATOR_COUNT" ]; then
    echo "VERDICT: PASS ($FOUND_TERMINATORS/$TERMINATOR_COUNT positive terminators present)"
else
    echo "VERDICT: NOT A PASS (exit $GATE_EXIT, $FOUND_TERMINATORS/$TERMINATOR_COUNT terminators in $LOG)"
fi

# Corroboration only — never the verdict (#135).
grep -E "Executed [0-9]+ tests" "$LOG" | tail -3
grep -cE "^Test Case .* failed" "$LOG" | sed 's/^/failed test cases: /'

# #135's count floor: "a truncation that happens to land after the last `failed`
# line is invisible to the terminator check alone". Set BAINLUCK_GATE_MIN_TESTS
# to the prior cycle's count plus exactly the tests you added, and say where the
# arithmetic comes from in the report.
if [ "$MODE" = "test" ] && [ -n "${BAINLUCK_GATE_MIN_TESTS:-}" ]; then
    RAN=$(grep -oE "Executed [0-9]+ tests" "$LOG" | grep -oE "[0-9]+" | sort -n | tail -1)
    RAN="${RAN:-0}"
    if [ "$RAN" -lt "$BAINLUCK_GATE_MIN_TESTS" ]; then
        echo "VERDICT OVERRIDE: COUNT FLOOR FAILED — ran $RAN, floor $BAINLUCK_GATE_MIN_TESTS"
        exit 6
    fi
    echo "COUNT FLOOR OK: ran $RAN >= $BAINLUCK_GATE_MIN_TESTS"
fi

exit "$GATE_EXIT"
