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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT="$REPO_ROOT/ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME="Bain Luck"

# native/233 — the reserved set, from the one file that owns it. This preflight
# used to keep its own copy of the constant, which is how it went on protecting
# one device after Alex signed in on a second: a second copy is a second thing
# to remember. The refusal below stays local because the gate RETURNS its codes
# rather than exiting; only the membership question is shared.
. "$REPO_ROOT/tools/reserved-sim-guard.sh"

# THE DEFAULT DEVICE IS RESOLVED, NOT NAMED. It was the literal string
# `iPhone 17`, and on 2026-09-18 that stopped naming a device at all: Alex's two
# signed-in simulators are BOTH called exactly `iPhone 17`, so the ambiguity
# refusal above fired on every bare invocation (exit 6) and the only two devices
# it offered as disambiguations were the two nobody may touch. The gate was
# unrunnable by default and its own advice pointed at the reserved pair.
#
# `bl_default_shoot_sim` returns a UDID, which is unambiguous by construction and
# already excludes the whole reserved set. The old name stays as the fallback for
# a machine with no iPhone at all, so the "no such device" message (exit 5) still
# reads the way it always did rather than as an empty destination.
DEVICE="${2:-$(bl_default_shoot_sim)}"
DEVICE="${DEVICE:-iPhone 17}"

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

    # A UDID IS ACCEPTED AS WELL AS A NAME, and is what the default now is.
    #
    # native/233: the destination was resolved by NAME only, which is the one
    # form that can be ambiguous — and on 2026-09-18 the default name `iPhone 17`
    # matched both of Alex's signed-in devices and nothing else, so the gate
    # refused every bare invocation. A UDID cannot be ambiguous, so the picker
    # hands one over and this branch takes it. Still checked against AVAILABLE,
    # so a UDID that is real but unbootable is refused here rather than inside
    # xcodebuild.
    case "$DEVICE" in
        [0-9A-Fa-f]*-*-*-*-*)
            ALL_UDIDS="$(xcrun simctl list devices available 2>/dev/null \
                | sed -n "s/^ *.* (\(${DEVICE}\)) (.*/\1/p")"
            ;;
        *)
            # Exact-name match against AVAILABLE devices only. `simctl list devices`
            # without `available` also lists unavailable runtimes, which would let an
            # unbootable device pass this check and fail identically inside xcodebuild.
            ALL_UDIDS="$(xcrun simctl list devices available 2>/dev/null \
                | sed -n "s/^ *${DEVICE} (\([0-9A-F-]\{36\}\)) (.*/\1/p")"
            ;;
    esac
    UDID="$(printf '%s\n' "$ALL_UDIDS" | head -1)"

    # A NAME THAT MATCHES TWO DEVICES IS A TYPO, NOT A CHOICE.
    #
    # There are two simulators called exactly "iPhone 17" on this machine, and
    # one of them is Alex's reserved launch candidate. The old `head -1` picked
    # whichever simctl listed first and said nothing — so `iPhone 17` was a coin
    # flip on erasing the device the sign-in evidence lives on. int426 hit the
    # ambiguity on 2026-09-18 and dodged it by convention ("always say iPhone 17
    # Pro"); a convention is not a guard.
    MATCH_COUNT="$(printf '%s\n' "$ALL_UDIDS" | /usr/bin/grep -c .)"
    if [ "$MATCH_COUNT" -gt 1 ]; then
        echo "GATE PREFLIGHT FAILED: '${DEVICE}' names ${MATCH_COUNT} available simulators." >&2
        echo "" >&2
        echo "  Refusing rather than picking one. Name a unique device:" >&2
        printf '%s\n' "$ALL_UDIDS" | sed 's/^/    /' >&2
        return 6
    fi

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

    # A RESERVED DEVICE IS REFUSED BY UDID, NOT BY NAME.
    #
    # Two `iPhone 17`s hold Alex's signed-in account — 76D961F0 (iOS 26.5) and
    # DD0DC456 (iOS 27.0), the one he signed in on after the first was
    # reinstalled by some gate on 2026-09-17. Only he can re-create that state,
    # because no lane may sign in. Codex reserved the first by directive; a
    # directive protects the lanes that read it, and this protects the ones that
    # do not.
    #
    # The set lives in `tools/reserved-sim-guard.sh` and is a LIST. It was a
    # scalar here and there, which could express one protected device on a
    # machine that had two — and the name is no help either, since both are
    # named exactly `iPhone 17`.
    if bl_is_reserved_sim "$UDID"; then
        echo "GATE PREFLIGHT FAILED: '${DEVICE}' resolves to a RESERVED simulator ${UDID}." >&2
        echo "" >&2
        echo "  That device holds Alex's signed-in account for the launch check." >&2
        echo "  Installing, erasing or running a gate on it destroys evidence" >&2
        echo "  nobody here can re-create. Use the disposable 'iPhone 17 Pro'." >&2
        return 7
    fi

    echo "PREFLIGHT OK: destination '${DEVICE}' -> ${UDID}"
    echo "PREFLIGHT OK: not a reserved device ($(printf '%s' "$BL_RESERVED_SIMS" | /usr/bin/grep -c . ) protected)"
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
