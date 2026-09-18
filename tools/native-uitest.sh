#!/usr/bin/env bash
# native-uitest.sh — run the tap-driven journey (BainLuckUITests) in a simulator.
#
# ═══ WHY THIS EXISTS ═══
#
# EVERY NATIVE WALKTHROUGH SINCE #3157 HAS WRITTEN THE SAME SENTENCE: swipe,
# pull-to-refresh, back and card→detail are UNKNOWN, not PASS. The reason given
# was always "this sandbox cannot tap" — no macOS Accessibility permission, so
# `osascript`/System Events fails with error -54, no `cliclick`, no `idb`.
#
# THAT REASON IS TRUE AND IT IS ABOUT THE WRONG CHANNEL. All three of those
# drive the simulator from OUTSIDE, as if it were a Mac window, which is exactly
# what needs the TCC grant. XCUITest drives it from INSIDE: the runner is itself
# an app on the simulator, talking to the simulator's own accessibility server.
# Measured 2026-09-14: a tap on the Search tab selects it, first try, no grant
# asked for and none bypassed. `BainLuckUITests/CanThisRigTapAtAllTests` is that
# premise written down as a test, so the day it stops being true one line says so
# instead of four journey tests failing like product defects.
#
# ═══ WHAT IT RUNS ═══
#
#   check 5  Discover opens on real cards · a vertical swipe moves the feed ·
#            a horizontal swipe dismisses one card · a pull arms the refresh
#   check 6  a card opens its event and BACK returns · tab away and back
#   check 7  a typed query produces results, one opens, and back keeps the query
#
# It does NOT replace `tools/native-gates.sh`. That is the standing Swift gate
# (macOS build + BainLuckTests) and it runs the `Bain Luck` scheme; this is the
# `BainLuckUITests` scheme and nothing else. Keeping them apart is deliberate:
# these tests talk to the network, so folding them into the gate every lane runs
# before every push would make a 90-second check a flaky five-minute one.
#
# ═══ DISPOSABLE LOCAL STATE, AND WHY IT IS THE DEFAULT ═══
#
# The app's container survives between runs, and it holds things these journeys
# read: recent searches, the swipe-dismiss store, the Discover interaction
# profile, the swipe hint's "already seen" flag. A run inheriting the last run's
# state is a run whose starting screen nobody chose — native/169's simulator
# still had `yank` / `Red Sox` / `sox` in Recent from the walkthrough before it.
# So this uninstalls the app first, every time, and `xcodebuild` reinstalls it.
# `--keep-state` opts out when you are debugging one test and the reinstall is
# the slow part.
#
# ═══ iPHONE ONLY, AND SAID OUT LOUD ═══
#
# `MainTabView` draws a TabView on iPhone and a NavigationSplitView on iPad, so
# every journey here that starts "find the tab bar" is iPhone-shaped. Pointed at
# an iPad this produced eight identical failures reading "the app never reached
# MainTabView", which is false — measured on iPad Air 13-inch: `tabBars=0`,
# `navigationBars=["Discover"]`, four event cards drawn, and a 'Show Sidebar'
# button where the tabs would be, plus a first-run Continue/Skip sheet on top.
# The app was fine; the rig was looking for furniture that platform does not
# have. Eight red tests that all mean "wrong device" is worse than one refusal,
# so this refuses. `--allow-non-iphone` runs anyway.
#
# iPad is the next rung and it needs two things this target does not have: a
# chrome helper that taps 'Show Sidebar' and then the sidebar row, and an
# onboarding-sheet dismissal. Neither is written; do not read a green iPhone run
# as covering iPad.
#
# ═══ NO PRODUCTION WRITE ═══
#
# The journeys tap cards and swipe them, and in a reader's hands both POST a row
# to `/api/feed/interactions`. The target launches with the app's own
# `-launch_no_interaction_upload` (LaunchRig.suppressesInteractionUpload), so the
# POST is not made — standing notice 39: our own robots are TAGGED, never minted.
# Everything else these journeys touch is a GET the app would make anyway. No
# sign-in, no account, no `simctl privacy`, no TCC.
#
# ═══ WHAT A GREEN RUN DOES NOT SAY ═══
#
# It does not say the app is FAST. Nothing here times a launch: the waits are
# generous ceilings, and a ceiling a launch passes says only that it finished
# inside it. Launch latency stays UNKNOWN until it is measured by an instrument
# built to measure it.
#
# It does not say a SKIPPED journey passed. A journey whose precondition was
# missing (an empty feed, a query with no rows) skips with a reason instead of
# failing, because failing would blame navigation for a data outage — so the
# SUMMARY below prints the skip count beside the pass count, and a run with
# skips is not a clean run.
#
# ═══ USAGE ═══
#
#   tools/native-uitest.sh                     # whole journey, iPhone resolved at runtime
#   tools/native-uitest.sh --device <udid>     # a specific simulator (e.g. the iPad)
#   tools/native-uitest.sh --only <TestClass>  # one class
#   tools/native-uitest.sh --keep-state        # do not uninstall first
#   tools/native-uitest.sh --allow-non-iphone  # run on an iPad anyway (see above)
#   tools/native-uitest.sh --explain           # resolve everything and STOP. No xcodebuild.
#   tools/native-uitest.sh --rearm-first-run-gates   # THE NEGATIVE CONTROL — see below
#
# ═══ THE NEGATIVE CONTROL, AND WHY THIS SUITE NEEDS ONE ═══
#
# A journey test whose every assertion is satisfied by "nothing happened" passes
# forever and is indistinguishable, from the outside, from one that walked. This
# suite cannot detect that about itself: a green run is exactly what both look
# like.
#
# So `--rearm-first-run-gates` puts Discover's first-run sheet back in front of
# the app, which makes the whole app untouchable, and then EVERY test must go
# RED. A test that stays green in that state is asserting nothing, and the
# verdict below is inverted to say so by name.
#
# Measured 2026-09-15 on 29d42093: 2 of 10 stayed green — check 5 itself (which
# asserted cards EXIST, and they do underneath a modal) and check 6's tab
# round-trip (which never asserted it LEFT Discover). Both were given the
# assertion they were missing; the control now reads 9 red + 1 named exemption,
# documented at the verdict below. Run this whenever a test is added to the
# target; it is not part of a normal run.
#
# Exit 0 only when the run finished AND nothing failed. Gotcha #54: the gate is
# never piped, its exit code is captured and reported as a VALUE — and for
# xcodebuild, 65 is a normal failure while 70 means the destination could not be
# resolved and the run never happened.

set -u
. "$(dirname "$0")/reserved-sim-guard.sh"

BUNDLE="com.bainluck.Bain-Luck"
SCHEME="BainLuckUITests"
SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox'
DEVICE=""
ONLY=""
KEEP_STATE=""
ALLOW_NON_IPHONE=""
EXPLAIN=""
REARM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --device) DEVICE="${2:?--device needs a udid}"; shift ;;
    --only) ONLY="${2:?--only needs a test class}"; shift ;;
    --keep-state) KEEP_STATE=1 ;;
    --allow-non-iphone) ALLOW_NON_IPHONE=1 ;;
    --explain) EXPLAIN=1 ;;
    --rearm-first-run-gates) REARM=1 ;;
    -h|--help) sed -n '1,/^set -u/p' "${BASH_SOURCE[0]}" | sed '$d'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

say () { printf '\n=== %s\n' "$*"; }

# ── The tree to test ─────────────────────────────────────────────────────────
# Resolved from the CWD, not from this script's own path. #5480: deriving it
# from ${BASH_SOURCE[0]} meant a lane running the shared copy tested the shared
# checkout and printed a well-formed pass line FOR MASTER.
REPO="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO" ]; then
  echo "not inside a git worktree — cd to the tree you mean to test" >&2
  exit 2
fi
PROJECT="$REPO/ios/Bain Luck/Bain Luck.xcodeproj"
if [ ! -d "$PROJECT" ]; then
  echo "no Xcode project at $PROJECT" >&2
  exit 2
fi

# ── The simulator ────────────────────────────────────────────────────────────
# Resolved at runtime. A hardcoded `name=iPhone 16` exits 70 when that device is
# not installed, and 70 reads like a test failure while meaning the run never
# started (gotcha #124). Names churn between Xcode releases and between laptops.
if [ -z "$DEVICE" ]; then
  # `head -1` over every available iPhone MEASURED to 76D961F0 — the RESERVED
  # device — so this runner installed and ran UITests on Alex's signed-in
  # launch candidate by DEFAULT. Same `head -1` hazard the gate's preflight was
  # built for (#6910); the reserved UDID is excluded before the pick.
  SIMLINE=$(xcrun simctl list devices available \
    | /usr/bin/grep -E '^[[:space:]]+iPhone ' \
    | /usr/bin/grep -v "$BL_RESERVED_SIM" | head -1)
  DEVICE=$(printf '%s' "$SIMLINE" | sed -E 's/.*\(([0-9A-Fa-f-]{36})\).*/\1/')
  SIMNAME=$(printf '%s' "$SIMLINE" | sed -E 's/^[[:space:]]+//; s/ \(.*//')
else
  SIMNAME=$(xcrun simctl list devices available | /usr/bin/grep "$DEVICE" | sed -E 's/^[[:space:]]+//; s/ \(.*//')
fi
if [ -z "$DEVICE" ]; then
  echo "NO iPhone SIMULATOR AVAILABLE — cannot run $SCHEME on this machine." >&2
  echo "(xcrun simctl list devices available showed no iPhone.)" >&2
  exit 1
fi

# Also covers an explicit `--device <reserved udid>`: this runner installs and
# can reset state, so the refusal is on the RESOLVED device, not just the pick.
bl_refuse_reserved_sim "$DEVICE" native-uitest.sh

# iPhone only — see the header. Refuse early and by NAME, so the operator reads
# one sentence about the device instead of eight assertion failures about the app.
case "$SIMNAME" in
  iPhone*|"") ;;
  *)
    if [ -z "$ALLOW_NON_IPHONE" ]; then
      echo "REFUSING: '$SIMNAME' is not an iPhone." >&2
      echo "  These journeys start by finding the tab bar, and MainTabView draws a" >&2
      echo "  NavigationSplitView (a sidebar) on iPad — so every test would fail with" >&2
      echo "  'the app never reached MainTabView', which is not what happened." >&2
      echo "  iPad needs its own chrome helper and is not written yet." >&2
      echo "  Pass --allow-non-iphone to run anyway and read the failures as device mismatch." >&2
      exit 2
    fi
    echo "WARNING: '$SIMNAME' is not an iPhone and --allow-non-iphone was passed."
    echo "  Failures below are most likely device mismatch, not app defects."
    ;;
esac

LOGDIR="${TMPDIR:-/tmp}/native-uitest-$$"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/uitest.txt"

say "plan"
echo "  tree      : $REPO"
echo "  sha       : $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null) ($(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null))"
echo "  scheme    : $SCHEME"
echo "  simulator : ${SIMNAME:-<named by udid>}  ($DEVICE)"
echo "  state     : $([ -n "$KEEP_STATE" ] && echo 'KEPT (--keep-state)' || echo 'uninstalled first, so the run starts on a clean container')"
echo "  scope     : ${ONLY:-all classes}"
[ -n "$REARM" ] && echo "  mode      : NEGATIVE CONTROL — first-run gates re-armed, EVERY test must go RED"
echo "  log       : $LOG"

[ -n "$EXPLAIN" ] && { say "done (--explain) — nothing was built and nothing was run"; exit 0; }

# ── Disposable local state ───────────────────────────────────────────────────
if [ -z "$KEEP_STATE" ]; then
  say "uninstall (disposable local state)"
  # Boot first: `simctl uninstall` on a shut-down device exits non-zero and the
  # message reads like a missing app rather than a sleeping simulator.
  xcrun simctl bootstatus "$DEVICE" -b > /dev/null 2>&1
  xcrun simctl uninstall "$DEVICE" "$BUNDLE" > /dev/null 2>&1
  # Not gated on the exit code ON PURPOSE: "the app was not installed" and "the
  # app was removed" are both the state this wants, and they are indistinguishable
  # here. What matters is what is true afterwards.
  if xcrun simctl get_app_container "$DEVICE" "$BUNDLE" > /dev/null 2>&1; then
    echo "  STILL INSTALLED after uninstall — the run would inherit the previous container."
    echo "  Re-run with --keep-state if that is what you want, but do not read the result as a clean-state run."
    exit 1
  fi
  echo "  clean: $BUNDLE is not installed on $DEVICE"
fi

# ── The run ──────────────────────────────────────────────────────────────────
say "$SCHEME"
ONLY_ARG=()
[ -n "$ONLY" ] && ONLY_ARG=(-only-testing:"BainLuckUITests/$ONLY")

# `"${ONLY_ARG[@]}"` alone is an UNBOUND VARIABLE under `set -u` in bash 3.2,
# which is what /bin/bash on macOS is — so the whole-suite path (the default,
# and the one every lane runs) died before xcodebuild started while `--only`
# worked fine. The `+` form expands to nothing when the array is empty.
# `TEST_RUNNER_<VAR>` is xcodebuild's channel into the test RUNNER's environment
# (the prefix is stripped before the runner sees it). It must be exported into
# xcodebuild's own environment: passed as a trailing `VAR=value` argument it is
# read as a BUILD SETTING, lands in the build environment, and never reaches the
# runner — measured 2026-09-15, and the run came back looking perfectly normal,
# which is why the verdict below refuses to trust a control it cannot see.
if [ -n "$REARM" ]; then
  export TEST_RUNNER_BL_UITEST_REARM_FIRST_RUN_GATES=1
fi

xcodebuild test \
  -project "$PROJECT" -scheme "$SCHEME" \
  -destination "id=$DEVICE" \
  ${ONLY_ARG[@]+"${ONLY_ARG[@]}"} \
  OTHER_SWIFT_FLAGS="$SWIFT_FLAGS" > "$LOG" 2>&1
EXIT=$?
echo "EXIT CODE: $EXIT   log: $LOG"
case "$EXIT" in
  0) ;;
  65) echo "  (65 is xcodebuild's normal 'something failed' — a result, read the failures below.)" ;;
  70) echo "  (70 — the destination could not be resolved. THE RUN NEVER HAPPENED; this is not a failing journey.)" ;;
  *) echo "  ($EXIT is an unusual xcodebuild code — check the log before reading it as a test result.)" ;;
esac

# ── The verdict, when this is the negative control ───────────────────────────
# Inverted ON PURPOSE: with the app behind its first-run sheet nothing is
# reachable, so a green test is a test that is not looking at the app.
if [ -n "$REARM" ]; then
  say "negative control (first-run gates RE-ARMED)"
  PASSED=$(/usr/bin/grep -cE "^Test Case .* passed" "$LOG" 2>/dev/null)
  RAN=$(/usr/bin/grep -cE "^Test Case .* (passed|failed)" "$LOG" 2>/dev/null)

  # A control that passes because nothing ran is the exact failure it exists to
  # catch, one level up. Zero executed tests is never a pass here.
  if [ "${RAN:-0}" -eq 0 ]; then
    echo "  THE CONTROL DID NOT RUN: 0 test cases executed (xcodebuild exit $EXIT)."
    echo "  This is NOT a clean control — read the log, do not record a result."
    echo "  log: $LOG"
    exit 1
  fi

  # THE CONTROL MUST PROVE IT CONTROLLED. `UITestLaunch.launchApp` logs which
  # mode it is in on every launch; if the switch did not reach the runner the
  # app was never blocked, every test is green for the ordinary reason, and
  # reporting that as "your tests assert nothing" is a false accusation.
  if ! /usr/bin/grep -q "first-run gates: RE-ARMED" "$LOG" 2>/dev/null; then
    echo "  THE SWITCH DID NOT REACH THE RUNNER — no launch logged 'first-run gates:"
    echo "  RE-ARMED', so the app was NOT blocked and this run is not a control."
    echo "  Nothing about the suite can be concluded from it. log: $LOG"
    exit 1
  fi

  echo "  $RAN test cases ran, $PASSED of them PASSED."

  # THE ONE TEST THIS CONTROL CANNOT BLOCK, named with its measured reason.
  #
  # The default is FAIL — a green test not named here is a test whose assertions
  # are satisfied by "nothing happened". This list is the exception and it is
  # short on purpose; adding a name to it is a claim you have to have measured.
  #
  # testLeavingDiscover…: measured 2026-09-15. Its first tab tap lands nowhere
  # (`Computed hit point {-1, -1}`), but XCUITest's own interrupting-element
  # handling clears the sheet before `openTab`'s single retry, so by the retry
  # the app is genuinely unblocked and the test really does walk the round trip.
  # The control cannot hold a modal open across a helper that retries. Its new
  # "the Discover nav bar must GO AWAY" assertion is proved load-bearing by
  # mutation instead (point `openTab` at the already-selected Discover tab and
  # it goes red), not by this control.
  CONTROL_CANNOT_BLOCK="testLeavingDiscoverForAnotherTabAndComingBackLandsOnDiscover"

  UNEXPLAINED=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    NAME=$(printf '%s' "$line" | sed -E 's/.* (test[A-Za-z0-9_]+)\].*/\1/')
    if printf '%s\n' "$CONTROL_CANNOT_BLOCK" | /usr/bin/grep -qx "$NAME"; then
      echo "      EXEMPT  $NAME (control cannot hold the modal across its retry — see the note in this script)"
    else
      echo "      GREEN   $NAME"
      UNEXPLAINED=$((UNEXPLAINED + 1))
    fi
  done <<< "$(/usr/bin/grep -E "^Test Case .* passed" "$LOG")"

  if [ "$UNEXPLAINED" -eq 0 ]; then
    echo "  CONTROL HELD: every test the control can block went red, so each has at"
    echo "  least one assertion that can see a blocked screen."
    exit 0
  fi
  echo "  CONTROL FAILED — $UNEXPLAINED test(s) above are green on an app nobody can"
  echo "  touch, so their assertions are satisfied by 'nothing happened'."
  echo "  Give each one an assertion that a stuck app fails. See #6318 / #6268."
  exit 1
fi

# ── The verdict ──────────────────────────────────────────────────────────────
# Read BY NAME from the "All tests" summary, never by position. #5591: xcodebuild
# prints "Executed N tests" once per CLASS as well as once for the suite, so a
# `tail -1` reports a killed run's last class count as if it were the total.
say "verdict"
ALL=$(/usr/bin/grep -A1 "Test Suite 'All tests'" "$LOG" 2>/dev/null \
      | /usr/bin/grep -E "Executed [0-9]+ tests?, with .* failures" \
      | tail -1 | sed 's/^[[:space:]]*//')
SKIPPED=$(/usr/bin/grep -cE "^Test Case .* skipped" "$LOG" 2>/dev/null)

if /usr/bin/grep -q '^\*\* TEST SUCCEEDED \*\*' "$LOG" 2>/dev/null && [ "$EXIT" -eq 0 ]; then
  echo "  ${ALL:-<no All tests summary — read the log>}"
  if [ "${SKIPPED:-0}" -gt 0 ]; then
    echo "  ⚠️  $SKIPPED SKIPPED — a skipped journey was NOT WALKED. This run is not clean:"
    /usr/bin/grep -E "^Test Case .* skipped|NOT WALKED" "$LOG" | sed 's/^/      /'
  else
    echo "  0 skipped — every journey in scope was actually walked."
  fi
  echo
  echo "  Remember what this does NOT say: nothing here timed a launch, so cold-open"
  echo "  latency is UNKNOWN, not fast."
  exit 0
fi

echo "  RUN DID NOT PASS."
[ -n "$ALL" ] && echo "  $ALL" || echo "  no 'All tests' summary in the log — the run did not reach the end (killed, or it never started)."
/usr/bin/grep -E "^Test Case .* (failed|skipped)|error:|XCTAssert" "$LOG" | head -40 | sed 's/^/      /'
exit 1
