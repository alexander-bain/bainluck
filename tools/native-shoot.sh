#!/bin/bash
# native/020 (#3157) — photograph ANY screen in the iPhone app, unattended.
#
# Replaces the patch-build-shoot-revert cycle that
# tools/native-look-scaffold-TempScreenshot.swift.txt required. The app reads
# `-launch_route` on master (Utilities/LaunchRig.swift, pinned by
# LaunchRigContractTests), hands it to the one router, and lands on the screen.
#
# Usage:
#   tools/native-shoot.sh <label> [route] [--counts] [--cooled] [--scroll N]
#
#   tools/native-shoot.sh discover
#   tools/native-shoot.sh g1 '' --counts --cooled
#   tools/native-shoot.sh search 'bainluck://search?q=US%20Open'
#   tools/native-shoot.sh browse bainluck://playoffs
#   tools/native-shoot.sh event bainluck://events/9001
#   tools/native-shoot.sh maps bainluck://events/9001 --scroll 1600
#
#   --counts   draw Discover's SERVED/DRAWN card counter (SHOWABLE-1 G1's number)
#   --cooled   seed the 11-category cooled interaction profile #1221 needs to be
#              visible at all — on a clean install the defect does not appear
#   --scroll N photograph N POINTS down the page instead of the top viewport
#
# ONE SHOT IS ONE VIEWPORT. iPhone 17 is 402×874 points, and an event page runs
# past 3,000 — so until `--scroll` existed, the margin maps, the half maps and
# every probability ladder had never been photographed by this rig at all, and
# #3533 had to be filed with "its rendering is unverified" in the issue body.
# When you shoot a card that lives below the hero, shoot it with --scroll or say
# in your write-up that you did not see it. Over-asking is safe: the app clamps
# to the bottom of the page rather than photographing past the end of it (which
# would be a blank shot, and a blank shot reads as a missing card).
#
# Build first, and NEVER with -derivedDataPath: a fresh path forces SPM
# resolution and the sandbox cannot reach dl.google.com. The OTHER_SWIFT_FLAGS
# are NOT optional (gotcha #50): without them the build dies with three
# "external macro implementation type 'PreviewsMacros.Common' could not be
# found" errors in BainLuckWidget.swift — a #Preview macro the compiler sandbox
# refuses to expand. It looks like a widget bug and is not one; native/021 lost
# a build cycle to it because this header omitted the flag.
#   xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
#     -destination 'platform=iOS Simulator,name=iPhone 17' \
#     -disableAutomaticPackageResolution \
#     OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' build
#
# IF A SHOT COMES BACK WITH THE NOTIFICATION ALERT, ERASE AND RE-SHOOT — do not
# conclude the suppression failed. `-suppress_notification_prompt` is checked at
# the single call site (`Bain_LuckApp` → `requestPermissionAfterDelay`) and there
# is no other authorization request in the tree, but MEASURED over 8 shoots on
# 2026-09-05 the alert still surfaced twice, and once it is up it belongs to
# SpringBoard: `install` does not clear it, `terminate` does not clear it, and
# every subsequent shot photographs it. `simctl openurl`'s "Open in 'Bain Luck'?"
# confirm behaves the same way. The erase always clears it:
#   xcrun simctl shutdown $SIM; xcrun simctl erase $SIM; xcrun simctl boot $SIM
# Budget one erase per shoot session and read every PNG before believing it.
set -u
SIM=76D961F0-8575-479F-ABCE-652D8A79DBF9    # iPhone 17 — PIN IT, `booted` picks the iPad
BUNDLE=com.bainluck.Bain-Luck
APP="/Users/bain/Library/Developer/Xcode/DerivedData/Bain_Luck-bkmrwhmxuqqsseeuqlyqvcavesmz/Build/Products/Debug-iphonesimulator/Bain Luck.app"
OUT="${NATIVE_SHOOT_OUT:-/Users/bain/bainluck-dev/native/artifacts-native-020}"

LABEL="${1:?label required, e.g. discover / search-usopen}"
ROUTE="${2:-}"
shift $(( $# > 2 ? 2 : $# ))
COUNTS=""
COOLED=""
SCROLL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --counts) COUNTS=1 ;;
    --cooled) COOLED=1 ;;
    --scroll)
      SCROLL="${2:?--scroll needs a point count, e.g. --scroll 1600}"
      shift
      ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

mkdir -p "$OUT"
xcrun simctl bootstatus "$SIM" -b >/dev/null 2>&1
xcrun simctl install "$SIM" "$APP" || { echo "install failed — build first" >&2; exit 1; }
xcrun simctl terminate "$SIM" "$BUNDLE" >/dev/null 2>&1
sleep 1

if [ -n "$COOLED" ]; then
  # The 11 largest categories on the live page, each cooled past the -3
  # suppression threshold and stamped now so nothing has decayed. Exactly the
  # profile DiscoverClientFilterFloorTests pins in Swift. Without it a clean
  # install shows no G1 defect at all (server 50, phone 50).
  CONT=$(xcrun simctl get_app_container "$SIM" "$BUNDLE" data)
  PLIST="$CONT/Library/Preferences/$BUNDLE.plist"
  NOW=$(date +%s)
  mkdir -p "$(dirname "$PLIST")"
  python3 - "$PLIST" "$NOW" <<'PY'
import plistlib, sys, os
path, now = sys.argv[1], float(sys.argv[2])
cooled = ["politics","entertainment","soccer","hockey","tech","baseball",
          "weather","motorsports","geopolitics","cycling","football"]
d = {}
if os.path.exists(path):
    with open(path,"rb") as f: d = plistlib.load(f)
d["discover_interaction_profile_native_v2"] = {c: {"score": -4.0, "at": now} for c in cooled}
d["discover_onboarded"] = True
with open(path,"wb") as f: plistlib.dump(d, f)
print("  seeded %d cooled categories" % len(cooled))
PY
fi

ARGS=(-suppress_notification_prompt YES -bainluck_telemetry_consent none -discover_onboarded YES)
[ -n "$ROUTE" ]  && ARGS+=(-launch_route "$ROUTE")
[ -n "$COUNTS" ] && ARGS+=(-launch_debug_counts YES)
[ -n "$SCROLL" ] && ARGS+=(-launch_scroll "$SCROLL")

xcrun simctl launch "$SIM" "$BUNDLE" "${ARGS[@]}" >/dev/null 2>&1

# The app hands the route to the router after LaunchRig.routeDelay (2.5s), and
# the destination screen then loads. 18s covers a cold feed on a cold sim.
#
# A scroll waits LaunchRig.scrollDelay (8s) AFTER the route before it moves, so
# the camera has to wait that out too or it photographs the page pre-scroll —
# which is a shot of the top with a scrolled label on it, the worst kind of
# wrong evidence. +4s of slack for the scrolled content's own lazy loads.
sleep 18
[ -n "$SCROLL" ] && sleep 12
SHOT="$OUT/$LABEL.png"
xcrun simctl io "$SIM" screenshot "$SHOT" >/dev/null 2>&1 \
  && echo "  shot $SHOT" \
  || { echo "  screenshot FAILED" >&2; exit 1; }
